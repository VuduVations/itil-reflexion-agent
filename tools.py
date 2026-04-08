"""ITIL MCP tools — expose ITIL capabilities and optionally consume ServiceNow MCP servers.

Dual role:
1. EXPOSE: FastMCP server exposing search_incidents, get_cmdb_info, calculate_risk_score
2. CONSUME: Optional MultiServerMCPClient for ServiceNow MCP servers (snow-mcp, servicenow-mcp)
"""

import json
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import config


# =============================================================================
# Pydantic schemas for MCP tool interface
# =============================================================================

class ToolInput(BaseModel):
    """Generic tool input."""
    query: str = ""
    scenario_id: str = "db-migration"
    ci_id: Optional[str] = None
    n_results: int = 5


class ToolDefinition(BaseModel):
    """MCP tool definition."""
    name: str
    description: str
    input_schema: dict


# =============================================================================
# Data loaders (fixtures)
# =============================================================================

def _load_json(filename: str) -> dict:
    filepath = os.path.join(config.data_dir, filename)
    with open(filepath) as f:
        return json.load(f)


# =============================================================================
# ITIL Tool Functions
# =============================================================================

def search_incidents(query: str, scenario_id: str = "db-migration", n_results: int = 5) -> list:
    """Search incident records. Priority: direct REST > MCP > fixtures."""
    if config.use_servicenow_direct:
        return _servicenow_rest_search_incidents(query, scenario_id, n_results)
    if config.use_servicenow:
        return _servicenow_mcp_search_incidents(query, n_results)

    incidents = _load_json("incidents.json")
    scenario_incidents = incidents.get(scenario_id, [])

    # Simple keyword matching for fixture data
    if query:
        query_lower = query.lower()
        scored = []
        for inc in scenario_incidents:
            text = json.dumps(inc).lower()
            score = sum(1 for word in query_lower.split() if word in text)
            scored.append((score, inc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [inc for _, inc in scored[:n_results]]

    return scenario_incidents[:n_results]


def get_cmdb_info(scenario_id: str = "db-migration", ci_id: Optional[str] = None) -> dict:
    """Get CMDB configuration item information. Priority: direct REST > MCP > fixtures."""
    if config.use_servicenow_direct:
        return _servicenow_rest_get_cmdb(ci_id, scenario_id)
    if config.use_servicenow:
        return _servicenow_mcp_get_cmdb(ci_id or scenario_id)

    cmdb = _load_json("cmdb.json")
    scenario_cmdb = cmdb.get(scenario_id, {})

    if ci_id:
        for item in scenario_cmdb.get("items", []):
            if item["ci_id"] == ci_id:
                return item
        return {"error": f"CI {ci_id} not found"}

    return scenario_cmdb


def calculate_risk_score(scenario_id: str = "db-migration") -> dict:
    """Calculate risk score based on incidents and CMDB data."""
    incidents = _load_json("incidents.json").get(scenario_id, [])
    scenarios = _load_json("scenarios.json").get(scenario_id, {})

    # Severity weights
    severity_scores = {"P1": 10, "P2": 7, "P3": 4, "P4": 1}

    total_risk = 0
    for inc in incidents:
        sev = inc.get("severity", "P3")
        total_risk += severity_scores.get(sev, 4)

    risk_factors = scenarios.get("risk_factors", [])
    factor_risk = len(risk_factors) * 3

    combined = min((total_risk + factor_risk) / 10, 10)

    # Determine trend
    mttr_values = [inc.get("mttr_hours", 0) for inc in incidents if inc.get("mttr_hours")]
    trend = "stable"
    if len(mttr_values) >= 2:
        if mttr_values[-1] > mttr_values[0]:
            trend = "worsening"
        elif mttr_values[-1] < mttr_values[0]:
            trend = "improving"

    return {
        "total_risk": round(combined, 1),
        "incident_risk": total_risk,
        "factor_risk": factor_risk,
        "incident_count": len(incidents),
        "risk_factor_count": len(risk_factors),
        "trend": trend,
        "severity_breakdown": {sev: sum(1 for i in incidents if i.get("severity") == sev) for sev in ["P1", "P2", "P3", "P4"]},
    }


# =============================================================================
# ServiceNow Direct REST Client
# =============================================================================

def _snow_rest_request(table: str, params: dict = None) -> list:
    """Make an authenticated GET request to ServiceNow Table API."""
    import httpx
    url = f"{config.servicenow_instance}/api/now/table/{table}"
    default_params = {
        "sysparm_display_value": "true",
        "sysparm_exclude_reference_link": "true",
    }
    if params:
        default_params.update(params)
    response = httpx.get(
        url,
        params=default_params,
        auth=(config.servicenow_username, config.servicenow_password),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("result", [])


# Scenario-specific filters for VUDU-tagged records in the PDI
_SCENARIO_INCIDENT_KEYWORDS = {
    "db-migration": "postgresql,database,connection pool,replication,stored procedure,cve",
    "security-patch": "log4j,log4shell,cve-2021-44228,kafka,vulnerability",
    "cost-optimization": "aws bill,nat gateway,auto-scaling,cost,traffic spike",
}

_SCENARIO_CMDB_PREFIXES = {
    "db-migration": ["VUDU-DB", "VUDU-LB-DB", "VUDU-APP-PAYMENT", "VUDU-APP-AUTH"],
    "security-patch": ["VUDU-APP-JAVA", "VUDU-WAF"],
    "cost-optimization": ["VUDU-ASG", "VUDU-NAT"],
}


def _servicenow_rest_search_incidents(query: str, scenario_id: str = "", n_results: int = 10) -> list:
    """Search incidents via ServiceNow REST API. Filters for VUDU-tagged scenario records."""
    try:
        params = {
            "sysparm_limit": n_results,
            "sysparm_fields": "number,short_description,priority,category,description,cmdb_ci,close_notes,sys_created_on,business_duration",
        }

        # Always filter to VUDU-tagged incidents first
        query_parts = ["short_descriptionLIKE[VUDU]"]

        # Add scenario-specific keyword filter if scenario provided
        if scenario_id and scenario_id in _SCENARIO_INCIDENT_KEYWORDS:
            keywords = _SCENARIO_INCIDENT_KEYWORDS[scenario_id].split(",")
            keyword_clauses = [f"short_descriptionLIKE{k}^ORdescriptionLIKE{k}" for k in keywords]
            query_parts.append(f"^({'^OR'.join(keyword_clauses)})")
        elif query:
            query_parts.append(f"^short_descriptionLIKE{query}^ORdescriptionLIKE{query}")

        params["sysparm_query"] = "".join(query_parts) + "^ORDERBYDESCsys_created_on"

        records = _snow_rest_request("incident", params)
        return [_map_snow_incident(r) for r in records]
    except Exception as e:
        print(f"ServiceNow REST error: {e}. Falling back to fixtures.")
        incidents = _load_json("incidents.json")
        return incidents.get(scenario_id, [])[:n_results] if scenario_id else []


def _servicenow_rest_get_cmdb(ci_id: Optional[str] = None, scenario_id: str = "") -> dict:
    """Get CMDB items via ServiceNow REST API. Filters for VUDU-tagged scenario CIs."""
    try:
        params = {
            "sysparm_fields": "name,sys_class_name,short_description,busines_criticality,operational_status",
            "sysparm_limit": 50,
        }

        if ci_id:
            params["sysparm_query"] = f"name={ci_id}"
            params["sysparm_limit"] = 1
        elif scenario_id and scenario_id in _SCENARIO_CMDB_PREFIXES:
            prefixes = _SCENARIO_CMDB_PREFIXES[scenario_id]
            clauses = [f"nameSTARTSWITH{p}" for p in prefixes]
            params["sysparm_query"] = "^OR".join(clauses)
        else:
            # Default: pull any VUDU-tagged CI
            params["sysparm_query"] = "nameSTARTSWITHVUDU-"

        records = _snow_rest_request("cmdb_ci", params)
        items = [_map_snow_cmdb(r) for r in records]

        if ci_id and items:
            return items[0]

        return {
            "items": items,
            "total_ci_count": len(items),
            "primary_ci": items[0]["ci_id"] if items else "",
            "environment": "Production",
        }
    except Exception as e:
        print(f"ServiceNow REST error: {e}. Falling back to fixtures.")
        cmdb = _load_json("cmdb.json")
        return list(cmdb.values())[0] if cmdb else {}


def _map_snow_incident(record: dict) -> dict:
    """Map a ServiceNow incident record to our schema."""
    # Parse business_duration (ServiceNow format: "1970-01-01 04:30:00" meaning 4.5 hours)
    mttr = None
    bd = record.get("business_duration", "")
    if bd:
        try:
            parts = bd.split(" ")[-1].split(":")
            mttr = int(parts[0]) + int(parts[1]) / 60
        except (ValueError, IndexError):
            pass

    return {
        "id": record.get("number", ""),
        "title": record.get("short_description", ""),
        "severity": _map_snow_priority(record.get("priority", "3")),
        "category": record.get("category", ""),
        "description": record.get("description", ""),
        "affected_ci": record.get("cmdb_ci", ""),
        "resolution": record.get("close_notes", ""),
        "created": record.get("sys_created_on", ""),
        "mttr_hours": mttr,
    }


def _map_snow_cmdb(record: dict) -> dict:
    """Map a ServiceNow CMDB CI record to our schema."""
    criticality_map = {"1 - most critical": "Critical", "2 - somewhat critical": "High", "3 - less critical": "Medium", "4 - not critical": "Low"}
    return {
        "ci_id": record.get("name", ""),
        "type": record.get("sys_class_name", ""),
        "description": record.get("short_description", ""),
        "criticality": criticality_map.get(record.get("busines_criticality", "").lower(), "Medium"),
    }


def _map_snow_priority(priority: str) -> str:
    """Map ServiceNow priority (1-5) to our severity format (P1-P4)."""
    mapping = {"1": "P1", "2": "P1", "3": "P2", "4": "P3", "5": "P4"}
    # Handle both "1" and "1 - Critical" formats
    key = priority.split(" ")[0] if " " in priority else priority
    return mapping.get(key, "P3")


# =============================================================================
# ServiceNow MCP Client (alternative to direct REST)
# =============================================================================

def _servicenow_mcp_search_incidents(query: str, n_results: int) -> list:
    """Query ServiceNow MCP server for incidents. Requires SERVICENOW_MCP_URL."""
    try:
        import httpx
        response = httpx.post(
            f"{config.servicenow_mcp_url}/tools/search_incidents",
            json={"query": query, "limit": n_results},
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        print(f"ServiceNow MCP error: {e}. Falling back to fixtures.")
        incidents = _load_json("incidents.json")
        return list(incidents.values())[0][:n_results] if incidents else []


def _servicenow_mcp_get_cmdb(ci_id: str) -> dict:
    """Query ServiceNow MCP server for CMDB data."""
    try:
        import httpx
        response = httpx.post(
            f"{config.servicenow_mcp_url}/tools/get_cmdb_info",
            json={"ci_id": ci_id},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"ServiceNow MCP error: {e}. Falling back to fixtures.")
        cmdb = _load_json("cmdb.json")
        return list(cmdb.values())[0] if cmdb else {}


# =============================================================================
# MCP Server (FastAPI router)
# =============================================================================

def create_mcp_router():
    """Create a FastAPI router exposing ITIL tools as MCP endpoints."""
    from fastapi import APIRouter
    router = APIRouter(prefix="/mcp", tags=["MCP Tools"])

    @router.get("/tools")
    async def list_tools():
        return [
            {
                "name": "search_incidents",
                "description": "Search ITIL incident records by keyword. Returns matching incidents with severity, category, and resolution details.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "scenario_id": {"type": "string", "enum": ["db-migration", "security-patch", "cost-optimization"]},
                        "n_results": {"type": "integer", "default": 5},
                    },
                },
            },
            {
                "name": "get_cmdb_info",
                "description": "Get CMDB configuration item details including dependencies, criticality, and environment.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "ci_id": {"type": "string", "description": "Specific CI ID, or omit for all"},
                    },
                },
            },
            {
                "name": "calculate_risk_score",
                "description": "Calculate risk score based on incident history and risk factors.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                    },
                },
            },
        ]

    @router.post("/tools/{tool_name}")
    async def call_tool(tool_name: str, input_data: ToolInput):
        if tool_name == "search_incidents":
            return search_incidents(input_data.query, input_data.scenario_id, input_data.n_results)
        elif tool_name == "get_cmdb_info":
            return get_cmdb_info(input_data.scenario_id, input_data.ci_id)
        elif tool_name == "calculate_risk_score":
            return calculate_risk_score(input_data.scenario_id)
        else:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    return router
