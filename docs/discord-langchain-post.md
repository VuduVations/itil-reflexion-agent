# LangChain Discord — #showcase Post

## Guidelines
- Keep it concise — Discord isn't LinkedIn
- Lead with what you built, not the problem
- Include a screenshot or the flow diagram
- Links at the bottom
- No hashtags, no marketing language
- Talk like a developer sharing a project

---

## Post (copy below the line)

---

**ITIL Reflexion Agent — LangGraph StateGraph with meta-learning**

Built an open-source Reflexion agent for ITIL Change Management using LangGraph. It iteratively generates and improves RFC (Request for Change) documents until they're CAB-ready.

**Architecture:**
`retrieve_data → meta_learning → generate_rfc → evaluate_rfc → [reflect → increment → loop back] or [finalize → cab_summary]`

8 nodes, 1 conditional edge, bounded loop (max 3 iterations or score >= 90).

**What makes it interesting:**
- Meta-learning node observes score delta between iterations and switches prompt strategy (5 strategies: standard, aggressive, steady, focus, reset)
- Evaluator uses `with_structured_output()` to produce typed Pydantic scores across 6 dimensions
- State uses `Annotated[List[Dict], operator.add]` accumulator pattern for history
- Score validation prevents unrealistic LLM-generated jumps
- SSE streaming via `asyncio.Queue` from sync graph nodes to async FastAPI endpoint

**Multi-provider LLM:**
Swappable via env var — Claude, Gemini, Groq/Llama, GPT-4o. Same `BaseChatModel` interface, different temperatures per role (0.7 actor, 0.3 evaluator, 0.5 reflector).

**MCP dual-role:**
Exposes ITIL tools (search_incidents, get_cmdb_info, calculate_risk_score) AND consumes ServiceNow MCP servers for real ITSM data. Falls back to JSON fixtures.

**Try it:** https://huggingface.co/spaces/VuduVations/itil-reflexion-agent
**Repo:** https://github.com/VuduVations/itil-reflexion-agent (MIT)
**Dataset:** https://huggingface.co/datasets/VuduVations/itsm-change-management-benchmark

Would love feedback on the meta-learning strategy selection — currently using hardcoded score delta thresholds. Considering cross-run learning but keeping it stateless for now.

---

## Attach
- The flow diagram image (docs/reflexion-flow.png)

## Notes
- Post in #showcase channel
- This is developer-to-developer — technical language is expected
- The ask at the end ("would love feedback on...") invites engagement
- Don't post in #general — that's for questions, not projects
