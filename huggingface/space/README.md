---
title: ITIL Reflexion Agent
emoji: 🔄
colorFrom: purple
colorTo: green
sdk: gradio
sdk_version: 5.23.0
app_file: app.py
pinned: true
license: mit
tags:
  - langgraph
  - reflexion
  - itil
  - change-management
  - servicenow
  - ai-agent
  - itsm
short_description: AI agent that improves ITIL Change Management RFCs
---

# ITIL Reflexion Agent

An AI agent that **iteratively improves** Request for Change (RFC) documents through a structured Actor-Evaluator-Reflector loop with adaptive meta-learning.

## How It Works

1. **Select a scenario** — database migration, security patch, or cost optimization
2. **Click Run** — the agent generates an RFC, evaluates it against ITIL v4 standards, reflects on weaknesses, and improves
3. **Watch the scores improve** — typically from 6/10 to 9+/10 in 3 iterations

## Architecture

Built on LangGraph with a Reflexion pattern:

```
Generate RFC → Evaluate (6 dimensions) → Reflect → Improve → Repeat
```

The meta-learning layer observes score progression and adapts the improvement strategy each iteration.

## ServiceNow Integration

This Space runs on demo fixtures, but the full agent supports three data modes:

- **Demo fixtures** (what you see here) — 3 built-in scenarios with bundled data
- **CSV/JSON upload** — bring your own incident export from any ITSM platform
- **Live ServiceNow** — direct REST API or MCP, validated end-to-end against a ServiceNow Personal Developer Instance

The repo includes a script that populates any ServiceNow PDI with scenario-specific data so you can reproduce the validation in under 10 minutes.

## Links

- [GitHub Repository](https://github.com/VuduVations/itil-reflexion-agent)
- [ServiceNow Setup Script](https://github.com/VuduVations/itil-reflexion-agent/blob/main/scripts/populate_servicenow_pdi.py)
- [ServiceNow Integration Guide](https://github.com/VuduVations/itil-reflexion-agent/blob/main/examples/connect_servicenow.md)
- [Technical Paper](https://github.com/VuduVations/itil-reflexion-agent/blob/main/docs/technical-paper.pdf)
- [Whitepaper](https://github.com/VuduVations/itil-reflexion-agent/blob/main/docs/whitepaper.pdf)
- [Vuduvations](https://vuduvations.io)

## License

MIT
