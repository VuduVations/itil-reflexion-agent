# ITIL Reflexion Agent

A LangGraph-based ITIL Change Management agent that uses the **Reflexion** pattern to iteratively improve Request for Change (RFC) documents until they meet CAB (Change Advisory Board) approval standards.

## What It Does

The agent runs a multi-agent loop:

1. **Retrieve** — Loads incident data and CMDB configuration (from fixtures or ServiceNow via MCP)
2. **Meta-Learn** — Analyzes score progression and selects optimal prompt strategy
3. **Generate** — Actor agent creates/improves the RFC using the selected strategy
4. **Evaluate** — Critic agent scores the RFC on 6 dimensions against ITIL v4 standards
5. **Reflect** — Creates actionable feedback if the score doesn't meet threshold
6. **Repeat** — Loop continues until score >= 90/100 or max iterations reached
7. **Finalize** — Compiles results and generates a CAB executive summary

```
START → retrieve_data → meta_learning → generate_rfc → evaluate_rfc
                              ^                              |
                              |                       [should_continue?]
                              |                        /           \
                          increment ← reflect    finalize → cab_summary → END
```

## Quick Start

```bash
# Clone
git clone https://github.com/vuduvations/itil-reflexion-agent.git
cd itil-reflexion-agent

# Install
pip install -r requirements.txt

# Configure
export ANTHROPIC_API_KEY=sk-ant-...

# Run
python main.py
```

The server starts on `http://localhost:8080`. Try it:

```bash
# Health check
curl http://localhost:8080/api/health

# Run reflexion (returns JSON)
curl -X POST http://localhost:8080/api/run-reflexion \
  -H "Content-Type: application/json" \
  -d '{"scenario_id": "db-migration"}'

# Run with SSE streaming
curl -N -X POST http://localhost:8080/api/run-reflexion-stream \
  -H "Content-Type: application/json" \
  -d '{"scenario_id": "security-patch"}'

# List scenarios
curl http://localhost:8080/api/scenarios
```

## Live Demo & Traces

- **Try it now** (no setup): [Hugging Face Space](https://huggingface.co/spaces/VuduVations/itil-reflexion-agent)
- **See the full execution trace** (every prompt, score, token): [LangSmith Trace](https://smith.langchain.com/public/c1a48f49-01c3-4a77-ab46-e3b3d69069b8/r)
- **ITSM benchmark dataset**: [Hugging Face Dataset](https://huggingface.co/datasets/VuduVations/itsm-change-management-benchmark)

## Demo Scenarios

Three built-in scenarios work out of the box (no ServiceNow required):

| Scenario | Category | Description |
|----------|----------|-------------|
| `db-migration` | Infrastructure | PostgreSQL 16 upgrade across 23 CMDB items |
| `security-patch` | Security | Emergency Log4Shell remediation for 340 services |
| `cost-optimization` | Infrastructure | Multi-region auto-scaling saving $2.1M/year |

## MCP Integration

### Exposing ITIL Tools

The agent exposes MCP-compatible tools at `/mcp/tools`:

- `search_incidents` — Search incident records
- `get_cmdb_info` — Get CMDB configuration items
- `calculate_risk_score` — Calculate risk scores

These can be consumed by Claude Desktop, other LangGraph agents, or any MCP client.

### Consuming ServiceNow Data

Set `SERVICENOW_MCP_URL` to connect to a ServiceNow MCP server:

```bash
export SERVICENOW_MCP_URL=http://localhost:8200
```

Compatible with:
- [snow-mcp](https://github.com/ShunyaAI/snow-mcp) (60+ ServiceNow tools)
- [servicenow-mcp](https://github.com/michaelbuckner/servicenow-mcp) (incidents, CMDB, knowledge)
- ServiceNow native MCP (Zurich release)

See [examples/connect_servicenow.md](examples/connect_servicenow.md) for setup instructions.

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required. Anthropic API key |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | LLM model ID |
| `MAX_ITERATIONS` | `3` | Maximum reflexion iterations |
| `SCORE_THRESHOLD` | `90` | Score threshold to stop iterating |
| `SERVICENOW_MCP_URL` | — | Optional. ServiceNow MCP server URL |

## Architecture

- **LangGraph StateGraph** — Declarative agent orchestration with conditional edges
- **Reflexion Pattern** — Actor-Critic-Reflector loop with meta-learning
- **Meta-Learning** — Dynamically adjusts prompt strategy based on score progression
- **Score Validation** — Prevents unrealistic jumps, ensures monotonic improvement
- **SSE Streaming** — Real-time progress events via asyncio.Queue
- **MCP Dual Role** — Exposes tools AND consumes ServiceNow

## Deploy

```bash
# Docker
docker build -t itil-reflexion-agent .
docker run -p 8080:8080 -e ANTHROPIC_API_KEY=sk-ant-... itil-reflexion-agent

# Cloud Run
chmod +x deploy.sh
./deploy.sh
```

## License

MIT
