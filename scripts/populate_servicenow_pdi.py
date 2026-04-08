"""Populate ServiceNow PDI with scenario-specific CMDB items and incidents.

Creates realistic demo data for the ITIL Reflexion Agent scenarios so the
end-to-end integration shows meaningful, scenario-relevant records instead
of ServiceNow's bundled sample data.

Usage:
    SERVICENOW_INSTANCE=https://devXXXXX.service-now.com \
    SERVICENOW_USERNAME=admin \
    SERVICENOW_PASSWORD=your-password \
    python scripts/populate_servicenow_pdi.py
"""

import os
import sys
import httpx
import json

INSTANCE = os.environ.get("SERVICENOW_INSTANCE", "")
USERNAME = os.environ.get("SERVICENOW_USERNAME", "")
PASSWORD = os.environ.get("SERVICENOW_PASSWORD", "")

if not (INSTANCE and USERNAME and PASSWORD):
    print("ERROR: Set SERVICENOW_INSTANCE, SERVICENOW_USERNAME, SERVICENOW_PASSWORD")
    sys.exit(1)

auth = (USERNAME, PASSWORD)
headers = {"Content-Type": "application/json", "Accept": "application/json"}


def create_record(table, data):
    """Create a record in a ServiceNow table."""
    url = f"{INSTANCE}/api/now/table/{table}"
    r = httpx.post(url, auth=auth, headers=headers, json=data, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  FAIL {table}: {r.status_code} {r.text[:200]}")
        return None
    return r.json().get("result")


# =============================================================================
# CMDB ITEMS — all tagged with "VUDU-" prefix for easy filtering
# =============================================================================

CMDB_ITEMS = [
    # Database Migration scenario
    {"name": "VUDU-DB-PROD-PG-01", "sys_class_name": "cmdb_ci_db_postgresql", "short_description": "Primary PostgreSQL 14.8 - us-east-1a, 32 vCPU, 256GB RAM, 30TB data", "operational_status": "1"},
    {"name": "VUDU-DB-PROD-PG-02", "sys_class_name": "cmdb_ci_db_postgresql", "short_description": "PostgreSQL 14.8 Replica - us-east-1b, 32 vCPU, 256GB RAM", "operational_status": "1"},
    {"name": "VUDU-DB-PROD-PG-03", "sys_class_name": "cmdb_ci_db_postgresql", "short_description": "PostgreSQL 14.8 Replica - us-east-1c, 32 vCPU, 256GB RAM", "operational_status": "1"},
    {"name": "VUDU-DB-PROD-PG-04", "sys_class_name": "cmdb_ci_db_postgresql", "short_description": "PostgreSQL 14.8 Analytics Replica - us-east-1d, 64 vCPU, 512GB RAM", "operational_status": "1"},
    {"name": "VUDU-LB-DB-PROD-01", "sys_class_name": "cmdb_ci_lb_service", "short_description": "HAProxy Primary - Database load balancer", "operational_status": "1"},
    {"name": "VUDU-APP-PAYMENT-API", "sys_class_name": "cmdb_ci_appl", "short_description": "Payment API - 20 instances ECS, critical service", "operational_status": "1"},
    {"name": "VUDU-APP-AUTH-SERVICE", "sys_class_name": "cmdb_ci_appl", "short_description": "Auth Service - 15 instances ECS, critical service", "operational_status": "1"},

    # Security Patch scenario
    {"name": "VUDU-APP-JAVA-KAFKA", "sys_class_name": "cmdb_ci_app_server_java", "short_description": "Kafka Broker - 12 brokers, Log4j 2.14 vulnerable", "operational_status": "1"},
    {"name": "VUDU-APP-JAVA-ELASTIC", "sys_class_name": "cmdb_ci_app_server_java", "short_description": "Elasticsearch Node - 9-node cluster, Log4j 2.14 vulnerable", "operational_status": "1"},
    {"name": "VUDU-APP-JAVA-ADMIN", "sys_class_name": "cmdb_ci_app_server_java", "short_description": "Admin Portal - Java, 8 instances, Log4j 2.14 vulnerable", "operational_status": "1"},
    {"name": "VUDU-WAF-CLOUDFLARE", "sys_class_name": "cmdb_ci", "short_description": "CloudFlare WAF with Log4j mitigation rules", "operational_status": "1"},

    # Cost Optimization scenario
    {"name": "VUDU-ASG-WEB-PROD-US", "sys_class_name": "cmdb_ci", "short_description": "Auto-scaling group - 50-500 t3.large instances, us-east-1", "operational_status": "1"},
    {"name": "VUDU-ASG-API-PROD-US", "sys_class_name": "cmdb_ci", "short_description": "Auto-scaling group - 40-400 c5.xlarge instances, us-east-1", "operational_status": "1"},
    {"name": "VUDU-NAT-GATEWAY-US", "sys_class_name": "cmdb_ci", "short_description": "NAT Gateway us-east-1 - $60K/month data transfer costs", "operational_status": "1"},
]

# =============================================================================
# INCIDENTS — tagged with "VUDU" in short_description for easy filtering
# =============================================================================

INCIDENTS = [
    # Database Migration scenario
    {
        "short_description": "[VUDU] Slow query performance on payment processing tables",
        "description": "Payment API response times increased from 45ms to 380ms during peak hours. Query execution plans show sequential scans on transaction_history table (2.1B rows). PostgreSQL 14 lacks advanced partitioning features needed for optimal performance.",
        "category": "database",
        "priority": "2",
        "impact": "2",
        "urgency": "2",
    },
    {
        "short_description": "[VUDU] Connection pool exhaustion during Black Friday load",
        "description": "PgBouncer connection pool saturated at 1000 connections causing 502 errors for 12 minutes. PostgreSQL 14 connection handling lacks improvements available in 16.",
        "category": "database",
        "priority": "1",
        "impact": "1",
        "urgency": "1",
    },
    {
        "short_description": "[VUDU] PostgreSQL 14 replication lag spike in analytics",
        "description": "Analytics replica showed 850ms replication lag during batch processing window. PostgreSQL 16 logical replication improvements would reduce this to under 100ms.",
        "category": "database",
        "priority": "3",
        "impact": "3",
        "urgency": "3",
    },
    {
        "short_description": "[VUDU] Legacy stored procedure failure after minor patch",
        "description": "3 of 12 legacy stored procedures failed after PostgreSQL 14.8.1 minor patch. Procedures use deprecated syntax that must be rewritten for any future version.",
        "category": "database",
        "priority": "2",
        "impact": "2",
        "urgency": "2",
    },
    {
        "short_description": "[VUDU] Security scan flagged PostgreSQL 14 CVEs",
        "description": "Quarterly security scan identified 3 CVEs in PostgreSQL 14.8. PostgreSQL 16 addresses all known CVEs and provides extended support until 2028.",
        "category": "security",
        "priority": "2",
        "impact": "2",
        "urgency": "2",
    },

    # Security Patch scenario
    {
        "short_description": "[VUDU] Log4Shell CVE-2021-44228 detected on 340 Java services",
        "description": "Vulnerability scan confirmed CVE-2021-44228 (CVSS 10.0) present in 340 Java microservices including payment processing, authentication, Kafka, and Elasticsearch. RCE possible on all affected services.",
        "category": "security",
        "priority": "1",
        "impact": "1",
        "urgency": "1",
    },
    {
        "short_description": "[VUDU] WAF blocking Log4j exploit attempts on API gateway",
        "description": "CloudFlare WAF blocked 127 exploit attempts in 24 hours targeting Log4Shell CVE-2021-44228. Attack patterns match known financial services targeting campaigns.",
        "category": "security",
        "priority": "1",
        "impact": "1",
        "urgency": "1",
    },
    {
        "short_description": "[VUDU] Kafka cluster running vulnerable Log4j version",
        "description": "Production Kafka cluster (12 brokers, 450 topics, 2.1M msg/sec) running vulnerable Log4j. Exploitation could compromise message integrity across all dependent services.",
        "category": "security",
        "priority": "1",
        "impact": "1",
        "urgency": "1",
    },

    # Cost Optimization scenario
    {
        "short_description": "[VUDU] AWS bill exceeded budget by 40% in November",
        "description": "November AWS spend hit 4.5M against 3.2M budget. Root cause: auto-scaling groups running at maximum capacity 24/7 despite 10x traffic variability. Off-peak utilization averaging 12 percent.",
        "category": "inquiry",
        "priority": "2",
        "impact": "2",
        "urgency": "3",
    },
    {
        "short_description": "[VUDU] NAT Gateway data transfer costs spiking unexpectedly",
        "description": "NAT Gateway costs reached 180K per month across 3 regions. Analysis shows 60 percent of traffic is to S3 and DynamoDB which could use VPC endpoints at zero cost.",
        "category": "inquiry",
        "priority": "3",
        "impact": "3",
        "urgency": "3",
    },
    {
        "short_description": "[VUDU] Performance degradation during traffic spike - scaling too slow",
        "description": "Flash sale caused 8x traffic increase. Manual scaling took 15 minutes to respond, causing 3 minutes of degraded service (P99 latency 2.8s vs 200ms target).",
        "category": "software",
        "priority": "2",
        "impact": "2",
        "urgency": "2",
    },
]


def main():
    print(f"Populating ServiceNow PDI: {INSTANCE}")
    print("=" * 60)

    print(f"\nCreating {len(CMDB_ITEMS)} CMDB items...")
    cmdb_success = 0
    for ci in CMDB_ITEMS:
        result = create_record("cmdb_ci", ci)
        if result:
            cmdb_success += 1
            print(f"  OK  {ci['name']}")
    print(f"Created {cmdb_success}/{len(CMDB_ITEMS)} CMDB items")

    print(f"\nCreating {len(INCIDENTS)} incidents...")
    inc_success = 0
    for inc in INCIDENTS:
        result = create_record("incident", inc)
        if result:
            inc_success += 1
            print(f"  OK  {result.get('number', '?')} - {inc['short_description'][:60]}")
    print(f"Created {inc_success}/{len(INCIDENTS)} incidents")

    print("\n" + "=" * 60)
    print("Done. Filter by 'VUDU' in name or short_description to find these records.")


if __name__ == "__main__":
    main()
