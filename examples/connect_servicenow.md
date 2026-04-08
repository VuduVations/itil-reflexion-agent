# ServiceNow Integration Guide

This guide covers four ways to connect the ITIL Reflexion Agent to your ServiceNow instance, from simplest to most advanced. The direct REST API path (Option 2) has been validated end-to-end against a live ServiceNow Personal Developer Instance.

**Quick validation path** (10 minutes, free):

```bash
# 1. Get a free ServiceNow PDI at developer.servicenow.com
# 2. Populate it with scenario-specific test data
SERVICENOW_INSTANCE=https://devXXXXX.service-now.com \
SERVICENOW_USERNAME=admin \
SERVICENOW_PASSWORD='your-password' \
python scripts/populate_servicenow_pdi.py

# 3. Run the agent against your PDI
export SERVICENOW_INSTANCE=https://devXXXXX.service-now.com
export SERVICENOW_USERNAME=admin
export SERVICENOW_PASSWORD='your-password'
export GOOGLE_API_KEY=your-gemini-key
export LLM_PROVIDER=google
python main.py

# 4. Verify the connection
curl http://localhost:8080/api/test-servicenow
```

You should see real incidents (INC0010001-INC0010011) and VUDU-tagged CMDB items returned from your live PDI.

---

## Option 1: Export & Upload (No Integration Required)

The fastest path — export data from ServiceNow, upload it through the dashboard.

### Exporting Incidents

1. In ServiceNow, navigate to **Incident > All**
2. Apply filters for the change you're documenting (e.g., category, CI, date range)
3. Click the **hamburger menu** (top-left of list) → **Export** → **JSON** or **CSV**
4. In the Reflexion dashboard, toggle to **Upload Your Data** and upload the file

**Minimum fields needed:** `number` (or `id`), `short_description` (or `title`), `priority` (or `severity`), `category`, `description`

The agent maps common ServiceNow field names automatically:
| ServiceNow Field | Maps To |
|---|---|
| `number` | `id` |
| `short_description` | `title` |
| `priority` | `severity` |
| `cmdb_ci` | `affected_ci` |
| `close_notes` | `resolution` |
| `sys_created_on` | `created` |

### Exporting CMDB Items

1. Navigate to **Configuration > All CIs** (or a specific CI class)
2. Filter to the CIs relevant to your change
3. Export as JSON or CSV

**Minimum fields:** `name` (or `ci_id`), `sys_class_name` (or `type`), `short_description` (or `description`)

### When to Use This

- Evaluating the agent for the first time
- One-off RFC generation
- No ServiceNow admin access available
- Security team hasn't approved API access yet

---

## Option 2: ServiceNow REST API Token (Recommended for Production)

Direct API connection using a scoped service account. This is how most SaaS tools integrate with ServiceNow.

### Step 1: Create a Service Account

In ServiceNow:

1. Navigate to **User Administration > Users**
2. Create a new user (e.g., `svc_reflexion_agent`)
3. Assign the role: `itil` (read access to incident, change, CMDB tables)
4. **Do NOT assign** `admin` — principle of least privilege

### Step 2: Generate API Credentials

**Option A: Basic Auth (simplest)**
- Use the service account username and password
- Set in environment:
  ```
  SERVICENOW_INSTANCE=https://your-instance.service-now.com
  SERVICENOW_USERNAME=svc_reflexion_agent
  SERVICENOW_PASSWORD=your-secure-password
  ```

**Option B: OAuth 2.0 (recommended for production)**
1. In ServiceNow, navigate to **System OAuth > Application Registry**
2. Create a new OAuth application
3. Note the Client ID and Client Secret
4. The agent will use client credentials grant to obtain tokens

### Step 3: Test the Connection

```bash
# Test that your credentials can read incidents
curl -u "svc_reflexion_agent:password" \
  "https://your-instance.service-now.com/api/now/table/incident?sysparm_limit=1"

# Test CMDB access
curl -u "svc_reflexion_agent:password" \
  "https://your-instance.service-now.com/api/now/table/cmdb_ci?sysparm_limit=1"
```

A `200` response with JSON data confirms your credentials and permissions are correct.

### Step 4: Configure the Agent

Set the environment variable and restart:

```bash
export SERVICENOW_INSTANCE=https://your-instance.service-now.com
export SERVICENOW_USERNAME=svc_reflexion_agent
export SERVICENOW_PASSWORD=your-secure-password
python main.py
```

### ServiceNow Tables Used

The agent queries these tables (read-only):

| Table | API Endpoint | Purpose |
|-------|-------------|---------|
| `incident` | `/api/now/table/incident` | Incident history for risk analysis |
| `cmdb_ci` | `/api/now/table/cmdb_ci` | Configuration items and dependencies |

The agent **never writes** to ServiceNow. All access is read-only.

### When to Use This

- Ongoing RFC generation against live data
- Production deployment
- When you want the agent to always have current incident/CMDB data

---

## Option 3: MCP Server Bridge (Advanced)

Connect via Model Context Protocol using a community MCP server running in your network.

### Architecture

```
Your Network                          Cloud / Local
┌──────────────────────┐              ┌──────────────────┐
│  ServiceNow Instance │              │  Reflexion Agent  │
│         ↓            │              │       ↓           │
│  MCP Server          │◄── HTTPS ──► │  MCP Client       │
│  (snow-mcp or        │              │  (tools.py)       │
│   servicenow-mcp)    │              │                   │
└──────────────────────┘              └──────────────────┘
```

The MCP server runs inside your network with access to ServiceNow. The Reflexion Agent connects to it over HTTPS.

### Setup with snow-mcp (60+ tools)

```bash
# On a server with ServiceNow network access
git clone https://github.com/ShunyaAI/snow-mcp.git
cd snow-mcp
npm install

export SERVICENOW_INSTANCE=https://your-instance.service-now.com
export SERVICENOW_USERNAME=svc_reflexion_agent
export SERVICENOW_PASSWORD=your-secure-password

npm start  # Default port 8200
```

### Setup with servicenow-mcp

```bash
git clone https://github.com/michaelbuckner/servicenow-mcp.git
cd servicenow-mcp
pip install -r requirements.txt

export SERVICENOW_INSTANCE=https://your-instance.service-now.com
export SERVICENOW_USERNAME=svc_reflexion_agent
export SERVICENOW_PASSWORD=your-secure-password

python server.py  # Default port 8200
```

### Configure the Reflexion Agent

```bash
export SERVICENOW_MCP_URL=http://your-mcp-server:8200
python main.py
```

### Exposing the MCP Server Securely

If the Reflexion Agent runs outside your network (e.g., Cloud Run), you need a secure tunnel:

**Cloudflare Tunnel (recommended):**
```bash
cloudflared tunnel --url http://localhost:8200
```

**ngrok (for testing):**
```bash
ngrok http 8200
```

Then set `SERVICENOW_MCP_URL` to the tunnel URL.

### How Data Flows

When `SERVICENOW_MCP_URL` is configured:

1. The `retrieve_data` node calls `search_incidents` via the MCP server
2. The MCP server queries ServiceNow's REST API
3. Results are returned as JSON to the agent
4. The agent processes real incident/CMDB data through the Reflexion loop

When NOT configured:
- All data comes from bundled JSON fixtures in `data/`
- Three demo scenarios work out of the box

### Testing the MCP Connection

```bash
# Verify the MCP server is running
curl http://localhost:8200/tools

# Test incident search
curl -X POST http://localhost:8200/tools/search_incidents \
  -H "Content-Type: application/json" \
  -d '{"query": "database performance", "limit": 5}'

# Test CMDB lookup
curl -X POST http://localhost:8200/tools/get_cmdb_info \
  -H "Content-Type: application/json" \
  -d '{"ci_id": "DB-PROD-SQL01"}'
```

### When to Use This

- You want real-time ServiceNow data but can't expose ServiceNow directly
- You need the full MCP tool catalog (60+ tools with snow-mcp)
- You're running the Reflexion Agent as part of a larger MCP ecosystem
- You want to connect Claude Desktop or other MCP clients to the same tools

---

## Option 4: Native ServiceNow MCP (Zurich Release+)

ServiceNow's Zurich release includes native MCP support built into the platform.

If your instance is on Zurich or later:

1. Enable MCP in your ServiceNow instance (System Properties)
2. Configure which tables/operations to expose
3. Set the MCP endpoint URL as `SERVICENOW_MCP_URL`

No third-party MCP server needed. Consult ServiceNow's documentation for your specific version.

---

## Security Considerations

### Principle of Least Privilege
- Create a dedicated service account — never use `admin`
- Grant only `itil` role (read access to incident, change, CMDB)
- Review and audit API access periodically

### Network Security
- Use HTTPS for all connections
- If using MCP bridge, restrict access by IP or use authenticated tunnels
- ServiceNow supports IP access control lists (ACLs) for API access

### Data Handling
- The agent processes data in memory only — nothing is persisted to disk
- No incident or CMDB data is sent to third parties (only to the configured LLM provider)
- When using cloud-hosted LLMs, be aware that incident descriptions are sent as prompt context

### Compliance
- The agent is read-only — it never modifies ServiceNow data
- All generated RFCs are returned to the user, not written back to ServiceNow
- Audit trail: the streaming log shows exactly what data was retrieved and how it was used

---

## Troubleshooting

### "Backend not available" in the dashboard
- Verify the Reflexion Agent backend is running: `curl http://localhost:8080/api/health`
- Check that `SERVICENOW_MCP_URL` is set correctly

### MCP server returns empty results
- Verify ServiceNow credentials: test with a direct REST API call (see Step 3 in Option 2)
- Check that the service account has `itil` role
- Verify the MCP server logs for authentication errors

### "Falling back to fixtures" message
- The agent couldn't reach the MCP server — check the URL and network connectivity
- This is a graceful fallback, not an error — the agent still runs using demo data

### Slow queries
- ServiceNow REST API can be slow on large tables — add filters (date range, category) to narrow results
- The MCP server may need pagination configuration for large result sets

### SSL/TLS errors
- Ensure your ServiceNow instance certificate is valid
- If using a corporate CA, the MCP server may need the CA bundle configured

---

## Data Field Mapping Reference

### Incident Fields

| ServiceNow Field | Agent Field | Required |
|---|---|---|
| `number` | `id` | Yes |
| `short_description` | `title` | Yes |
| `priority` | `severity` | Yes |
| `category` | `category` | Recommended |
| `description` | `description` | Recommended |
| `cmdb_ci.name` | `affected_ci` | Recommended |
| `close_notes` | `resolution` | Optional |
| `sys_created_on` | `created` | Optional |
| `business_duration` | `mttr_hours` | Optional |

### CMDB Fields

| ServiceNow Field | Agent Field | Required |
|---|---|---|
| `name` | `ci_id` | Yes |
| `sys_class_name` | `type` | Recommended |
| `short_description` | `description` | Recommended |
| `business_criticality` | `criticality` | Optional |

Fields not present in the upload are handled gracefully — the agent works with whatever data is available.
