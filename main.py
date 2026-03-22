"""FastAPI application for the ITIL Reflexion Agent.

Endpoints:
- POST /api/run-reflexion          — Run reflexion loop, return JSON result
- POST /api/run-reflexion-stream   — Run reflexion loop with SSE streaming
- GET  /api/scenarios              — List available scenarios
- GET  /api/health                 — Health check
- GET  /api/status                 — Service status
- GET  /mcp/tools                  — List MCP tools
- POST /mcp/tools/{name}           — Call MCP tool
"""

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import config
from graph import reflexion_graph
from tools import create_mcp_router, search_incidents, get_cmdb_info, calculate_risk_score


# =============================================================================
# App Setup
# =============================================================================

app = FastAPI(
    title="ITIL Reflexion Agent",
    description="LangGraph-based ITIL Change Management Reflexion agent with MCP integration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP router
mcp_router = create_mcp_router()
app.include_router(mcp_router)


# =============================================================================
# Request/Response Models
# =============================================================================

class ReflexionRequest(BaseModel):
    scenario_id: str = Field(default="db-migration", description="Scenario: db-migration, security-patch, cost-optimization")
    max_iterations: int = Field(default=3, ge=1, le=5)
    score_threshold: int = Field(default=90, ge=50, le=100)
    custom_data: dict = Field(default=None, description="Optional user-uploaded data: {incidents: [...], cmdb: {...}, context: {...}}")


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ITIL Reflexion Agent",
        "version": "1.0.0",
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "servicenow_connected": config.use_servicenow,
    }


@app.get("/api/status")
async def status():
    return {"status": "ready", "version": "1.0.0"}


@app.get("/api/scenarios")
async def list_scenarios():
    """List available demo scenarios."""
    import os
    scenarios_path = os.path.join(config.data_dir, "scenarios.json")
    with open(scenarios_path) as f:
        scenarios = json.load(f)
    return {
        "scenarios": [
            {"id": k, "name": v["name"], "category": v["category"]}
            for k, v in scenarios.items()
        ]
    }


@app.get("/api/test-servicenow")
async def test_servicenow():
    """Test ServiceNow connection — returns sample incidents and CMDB items."""
    if not config.use_servicenow:
        return {
            "connected": False,
            "method": None,
            "message": "No ServiceNow connection configured. Set SERVICENOW_INSTANCE + credentials or SERVICENOW_MCP_URL.",
        }

    method = "direct_rest" if config.use_servicenow_direct else "mcp"
    try:
        incidents = search_incidents("", n_results=3)
        cmdb = get_cmdb_info()
        return {
            "connected": True,
            "method": method,
            "instance": config.servicenow_instance or config.servicenow_mcp_url,
            "incidents_sample": incidents[:3],
            "incidents_count": len(incidents),
            "cmdb_items_count": cmdb.get("total_ci_count", len(cmdb.get("items", []))),
            "cmdb_sample": cmdb.get("items", [])[:3],
        }
    except Exception as e:
        return {
            "connected": False,
            "method": method,
            "error": str(e),
        }


@app.post("/api/run-reflexion")
async def run_reflexion(request: ReflexionRequest):
    """Run the full Reflexion loop and return JSON result."""
    initial_state = _build_initial_state(request)

    try:
        final_state = await asyncio.to_thread(reflexion_graph.invoke, initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reflexion loop failed: {str(e)}")

    result = final_state.get("final_result", {})
    result["cab_summary"] = final_state.get("cab_summary", "")
    return result


@app.post("/api/run-reflexion-stream")
async def run_reflexion_stream(request: ReflexionRequest):
    """Run the Reflexion loop with Server-Sent Events streaming."""
    queue = asyncio.Queue()
    initial_state = _build_initial_state(request, stream_queue=queue)

    async def event_generator():
        # Start the graph in a background thread
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, reflexion_graph.invoke, initial_state)

        # Stream events from queue while graph runs
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                # Check if graph is done
                if task.done():
                    # Drain remaining events
                    while not queue.empty():
                        event = queue.get_nowait()
                        yield f"data: {json.dumps(event)}\n\n"
                    break

        # Get final result
        try:
            final_state = task.result()
            result = final_state.get("final_result", {})
            result["cab_summary"] = final_state.get("cab_summary", "")
            yield f"data: {json.dumps({'type': 'complete', 'iterations': result.get('iterations', []), 'rfc_name': result.get('rfc_name', ''), 'rfc_metadata': result.get('rfc_metadata', {}), 'cab_summary': result.get('cab_summary', '')})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# =============================================================================
# Helpers
# =============================================================================

def _build_initial_state(request: ReflexionRequest, stream_queue=None) -> dict:
    """Build the initial RFCState for the graph."""
    return {
        "scenario_id": request.scenario_id,
        "incidents": [],
        "cmdb_info": {},
        "scenario_meta": {},
        "custom_data": request.custom_data,
        "iteration": 1,
        "max_iterations": request.max_iterations,
        "score_threshold": request.score_threshold,
        "rfc": "",
        "critique": {},
        "feedback": "",
        "prompt_strategy": "standard",
        "improvement_pattern": "none",
        "history": [],
        "should_continue": True,
        "final_result": None,
        "cab_summary": "",
        "stream_queue": stream_queue,
    }


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.port)
