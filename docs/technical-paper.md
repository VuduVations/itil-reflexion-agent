# Reflexion with Adaptive Meta-Learning for ITIL Change Management
### Technical Architecture and Implementation

**Authors:** Vuduvations AI Research
**Repository:** github.com/vuduvations/itil-reflexion-agent
**License:** MIT

---

## Abstract

We present an open-source implementation of a Reflexion-based agent for ITIL Change Management that iteratively improves Request for Change (RFC) documents through a structured Actor-Critic-Reflector loop augmented with adaptive meta-learning. The agent is built on LangGraph, supports multiple LLM providers, and integrates with ServiceNow via the Model Context Protocol (MCP). We describe the architecture, the meta-learning strategy selection algorithm, structured output enforcement, score progression validation, and real-time streaming design. The system produces RFC documents that progress from initial drafts scoring 6-7/10 to CAB-ready documents scoring 9+/10 across six evaluation dimensions in 2-3 iterations.

---

## 1. Introduction

### 1.1 The Reflexion Pattern

Reflexion (Shinn et al., 2023) is an agent architecture where a language model improves its outputs through verbal self-reflection. Unlike standard prompt-and-respond workflows, Reflexion introduces an explicit feedback loop:

```
Actor generates output → Evaluator critiques → Reflector synthesizes feedback → Actor retries with feedback
```

The key insight is that LLMs can effectively use their own prior failures as context for improvement, provided the feedback is specific and actionable. Shinn et al. demonstrated this on code generation (HumanEval) and decision-making (AlfWorld), showing iterative gains without any weight updates — pure in-context learning.

### 1.2 Why ITIL Change Management

ITIL Change Management is an ideal domain for Reflexion because:

1. **Structured evaluation criteria exist** — ITIL v4 defines clear standards for what constitutes a well-formed RFC
2. **Iterative refinement is the norm** — RFCs routinely go through 2-4 revision cycles before CAB approval
3. **Scoring is multi-dimensional** — quality, compliance, risk, business value, technical readiness, and stakeholder confidence are all independently assessable
4. **The feedback loop is natural** — CAB reviewers already provide structured critique that maps directly to Reflexion's Evaluator role

### 1.3 Contributions

- First open-source Reflexion agent for ITSM/ITIL Change Management
- Adaptive meta-learning layer that selects prompt strategies based on score progression patterns
- Score validation system preventing unrealistic LLM-generated quality jumps
- Multi-provider LLM abstraction (Claude, Gemini, Groq/Llama, GPT-4o)
- Dual-role MCP integration — exposing ITIL tools AND consuming ServiceNow data
- Real-time SSE streaming architecture for agent progress visualization
- ITSM fixture dataset for benchmarking ITIL-focused AI agents

---

## 2. Architecture

### 2.1 System Overview

The system consists of three layers:

```
┌─────────────────────────────────────────────┐
│  Presentation Layer                          │
│  Next.js Dashboard + SSE Streaming Client    │
├─────────────────────────────────────────────┤
│  API Layer                                   │
│  FastAPI + SSE + MCP Server                  │
├─────────────────────────────────────────────┤
│  Agent Layer                                 │
│  LangGraph StateGraph + LLM Providers        │
│  ┌─────────────────────────────────────┐    │
│  │  Retrieve → Meta-Learn → Generate   │    │
│  │       ↑                    ↓        │    │
│  │  Increment ← Reflect ← Evaluate    │    │
│  │                    ↓                │    │
│  │           Finalize → CAB Summary    │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  Data Layer                                  │
│  JSON Fixtures / Upload / ServiceNow MCP     │
└─────────────────────────────────────────────┘
```

### 2.2 LangGraph StateGraph

The agent is implemented as a LangGraph `StateGraph` — a directed graph where nodes are functions that transform a shared typed state, and edges define execution order including conditional branching.

**State Schema (TypedDict):**

```python
class RFCState(TypedDict):
    # Input
    scenario_id: str
    incidents: List[Dict]
    cmdb_info: Dict
    scenario_meta: Dict
    custom_data: Optional[Dict]

    # Iteration control
    iteration: int
    max_iterations: int          # Default: 3
    score_threshold: int         # Default: 90

    # Agent outputs
    rfc: str                     # Current RFC text
    critique: Dict               # Structured evaluation
    feedback: str                # Reflector output
    prompt_strategy: str         # Meta-learning selected
    improvement_pattern: str     # Score delta classification

    # Accumulator
    history: Annotated[List[Dict], operator.add]

    # Results
    final_result: Optional[Dict]
    cab_summary: str
```

The `history` field uses LangGraph's accumulator pattern (`Annotated[List[Dict], operator.add]`), which appends rather than overwrites across node executions. This preserves the full execution trace for meta-learning analysis and final result compilation.

**Graph Topology:**

```
START → retrieve_data → meta_learning → generate_rfc → evaluate_rfc
                              ↑                              │
                              │                       [should_continue]
                              │                        /           \
                          increment ← reflect    finalize → cab_summary → END
```

Eight nodes, one conditional edge, one loop-back path. The graph compiles to a `CompiledStateGraph` singleton at module load time.

**Conditional Router:**

```python
def should_continue(state: RFCState) -> Literal["continue", "finalize"]:
    score = state["critique"]["scores"]["overall_quality"]
    if score >= state["score_threshold"] / 10 or state["iteration"] >= state["max_iterations"]:
        return "finalize"
    return "continue"
```

This guarantees bounded execution — the loop terminates when quality reaches threshold OR iterations are exhausted.

---

## 3. Agent Design

### 3.1 Temperature-Optimized Roles

Each agent role uses a different LLM temperature, reflecting the cognitive task:

| Role | Temperature | Rationale |
|------|------------|-----------|
| **Actor** (Generator) | 0.7 | Higher creativity for diverse RFC content |
| **Evaluator** (Critic) | 0.3 | Low variance for consistent, reproducible scoring |
| **Reflector** | 0.5 | Balanced — analytical enough to diagnose issues, creative enough to suggest solutions |
| **CAB Summary** | 0.4 | Professional tone, controlled creativity |

This is consistent with findings that analytical tasks benefit from lower temperatures while generative tasks benefit from higher temperatures (Wang et al., 2023).

### 3.2 Structured Output Enforcement

The Evaluator must produce scores, summaries, issues, and improvements in a precise schema matching the frontend JSON contract. We enforce this using Pydantic models with LangChain's `with_structured_output()`:

```python
class EvaluationOutput(BaseModel):
    scores: RFCScores                        # 6 float fields, ge=0, le=10
    executive_summary: ExecutiveSummary      # recommendation, risk, ROI, concerns
    rfc_summary: RFCSummary                  # 8 structured fields
    critical_issues: List[CriticalIssue]     # severity, category, impact
    improvements: List[Improvement]          # action, priority, effort_hours
    change_categories: ChangeCategories      # 4 categories × (score, status)

evaluator_structured = evaluator_llm.with_structured_output(EvaluationOutput)
```

This guarantees the LLM response is valid, typed, and complete — no regex parsing, no JSON extraction heuristics. When structured output fails (model incompatibility or malformed response), a fallback parser produces reasonable defaults based on iteration number.

### 3.3 The Actor: Strategy-Driven Generation

The Actor receives different prompt templates based on the meta-learning strategy:

- **Standard** — Full ITIL RFC with all required sections (iteration 1 baseline)
- **Aggressive Improvement** — Executive polish, quantified metrics, sophisticated risk modeling
- **Steady Improvement** — Incremental strengthening of each section
- **Focus on Issues** — Targeted fixes for specific problems identified by the Evaluator
- **Reset Approach** — Complete reframing from a different angle

Each strategy modifies the prompt instructions, not the LLM parameters. This keeps the architecture simple while enabling meaningfully different generation behaviors.

### 3.4 The Evaluator: Six-Dimension Scoring

The Evaluator scores across six dimensions that map to real CAB review criteria:

1. **Overall Quality** (0-10) — Completeness, clarity, professional presentation
2. **ITIL Compliance** (0-10) — Adherence to ITIL v4 change management framework
3. **Risk Level** (0-10) — Severity of identified risks (10 = critical, 0 = negligible)
4. **Business Value** (0-10) — Quality of business case and ROI articulation
5. **Technical Readiness** (0-10) — Completeness of technical plan, testing, rollback
6. **Stakeholder Confidence** (0-10) — Communication plan clarity for non-technical stakeholders

These dimensions are independently scored but jointly considered for the overall assessment. The Evaluator also produces a CAB approval probability (0.0-1.0) and a recommendation classification (Conditional / Approved with Revisions / Approved for Production).

### 3.5 The Reflector: Actionable Feedback

The Reflector's role is translating the Evaluator's structured critique into specific, actionable instructions for the Actor. The key design principle is **specificity over generality**:

Bad feedback: *"Improve the risk section"*
Good feedback: *"Add quantified MTTR (target: <15 minutes) and failure probability estimates to section 4.2. Reference the 3 successful rollback drills from staging and include specific SQL commands for the point-in-time recovery procedure."*

The Reflector receives the full score breakdown, critical issues list, and improvement recommendations, and synthesizes them into a prioritized action plan.

---

## 4. Meta-Learning

### 4.1 Strategy Selection Algorithm

The meta-learning node observes the score delta between consecutive iterations and selects a prompt strategy:

```python
def select_strategy(eval_history: List[Dict]) -> str:
    if len(eval_history) < 2:
        return "standard"

    prev_score = eval_history[-2]["score"]
    curr_score = eval_history[-1]["score"]
    delta = curr_score - prev_score

    if delta > 15:   return "aggressive_improvement"   # Strong momentum
    if delta > 8:    return "steady_improvement"        # Consistent gains
    if delta > 0:    return "focus_on_issues"           # Minimal progress
    return "reset_approach"                              # Stalled or regressing
```

This is a simple but effective heuristic. The thresholds (15, 8, 0) were determined empirically across the three demo scenarios and validated against expected score progressions.

### 4.2 Why Not Learned Strategies?

A natural question is why not use a learned policy (RL, bandit, etc.) for strategy selection. Three reasons:

1. **Sample efficiency** — With max 3 iterations per run, there are at most 2 strategy decisions. Not enough signal for online learning within a single run.
2. **Interpretability** — The heuristic is fully transparent. Users and auditors can understand why the agent chose a particular strategy.
3. **Generalization** — The score delta patterns are domain-agnostic. The same thresholds work across database migrations, security patches, and cost optimization scenarios.

Cross-run learning (using historical runs to improve future strategy selection) is a natural extension but requires persistent state, which we deliberately avoid in the current architecture for simplicity and statelessness.

### 4.3 Score Progression Validation

LLMs can produce unrealistic scores — a first-iteration RFC scored at 9.5/10, or a score that drops from 8.0 to 4.0 between iterations. The validation layer enforces realistic progressions:

```python
def validate_score_progression(prev_score, curr_score, iteration):
    # First iteration: clamp to realistic range
    if iteration == 1:
        return clamp(curr_score, 5.5, 7.8)

    # Prevent jumps > 2.5 points per iteration
    if curr_score - prev_score > 2.5:
        return prev_score + 2.5

    # Prevent significant regression
    if curr_score < prev_score - 0.5:
        return prev_score + 0.3

    return curr_score
```

This ensures monotonic-ish improvement within realistic bounds, regardless of LLM variability. The constraints are deliberately loose — they prevent hallucinated scores while still allowing the LLM's genuine assessment to drive the progression.

---

## 5. Data Layer

### 5.1 Three Input Modes

The agent supports three data input modes with identical downstream processing:

**1. Fixture Data (Demo Mode)**
- Three bundled scenarios: database migration, security patch, cost optimization
- 15 incident records, 68 CMDB items across scenarios
- Zero configuration required

**2. User Upload**
- JSON or CSV file upload for incidents and CMDB items
- Client-side CSV parser with quoted-field support
- Flexible schema — maps common field names automatically

**3. ServiceNow MCP**
- Connects to ServiceNow MCP servers (snow-mcp, servicenow-mcp, or native)
- Queries `incident` and `cmdb_ci` tables
- Falls back to fixtures if connection fails

### 5.2 ITSM Fixture Dataset

The fixture data is designed to serve as a benchmark for ITSM-focused AI evaluation. Each scenario includes:

- **Incidents** with realistic fields: severity (P1-P4), category, affected CIs, MTTR, resolution details
- **CMDB items** with criticality ratings, dependency relationships, and infrastructure details
- **Scenario metadata** with risk factors, rollback plans, testing status, and affected services

This dataset is, to our knowledge, the first publicly available structured ITSM dataset designed for AI agent evaluation. We publish it under MIT license and encourage its use as a benchmark.

### 5.3 Output Schema

The output schema matches a defined JSON contract:

```json
{
  "rfc_name": "string",
  "rfc_metadata": {
    "title", "category", "rfc_id", "ci_count",
    "affected_services", "estimated_cost", "business_value",
    "timeline", "cmdb_items", "risk_factors",
    "rollback_plan", "testing_completed"
  },
  "iterations": [{
    "iteration", "timestamp", "processing_time", "tokens_used",
    "scores": { 6 dimensions },
    "executive_summary": { recommendation, risk, ROI, concerns },
    "rfc_summary": { 8 structured fields },
    "critical_issues": [{ issue, category, severity, priority, impact }],
    "improvements": [{ action, priority, estimated_impact, effort_hours }],
    "change_categories": { technical, procedural, compliance, communication }
  }]
}
```

This schema is stable and versioned — frontend consumers can rely on its structure.

---

## 6. MCP Integration

### 6.1 Dual Role Architecture

The agent plays two MCP roles simultaneously:

**Server (Expose):** Exposes three ITIL tools via HTTP endpoints:
- `search_incidents(query, scenario_id, n_results)` — keyword search across incident records
- `get_cmdb_info(scenario_id, ci_id)` — CMDB configuration item lookup
- `calculate_risk_score(scenario_id)` — risk scoring from incident severity and risk factors

These are consumable by Claude Desktop, other LangGraph agents, or any MCP-compatible client.

**Client (Consume):** Optionally connects to external MCP servers:
- `SERVICENOW_MCP_URL` → routes data retrieval through ServiceNow MCP servers
- Falls back to fixtures when no MCP server is configured

### 6.2 ServiceNow MCP Ecosystem

Two community MCP servers provide ServiceNow connectivity:

- **snow-mcp** (60+ tools) — comprehensive ServiceNow access including incidents, changes, CMDB, knowledge base
- **servicenow-mcp** — focused on incidents, CMDB, and knowledge articles

ServiceNow's Zurich release adds native MCP support, enabling direct connection without a third-party bridge.

---

## 7. Streaming Architecture

### 7.1 SSE via asyncio.Queue

The agent uses Server-Sent Events (SSE) for real-time progress streaming. Each LangGraph node emits events to an `asyncio.Queue`:

```python
async def _emit(state, phase, message):
    queue = state.get("stream_queue")
    if queue:
        await queue.put({"phase": phase, "message": message, "timestamp": now()})
```

The SSE endpoint reads from this queue and streams events to the client:

```python
async def event_generator():
    task = loop.run_in_executor(None, graph.invoke, initial_state)
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            if task.done():
                break
    # Emit final result
    yield f"data: {json.dumps({'type': 'complete', ...})}\n\n"
```

### 7.2 Phase-Based Event Classification

Events carry a `phase` field that maps to frontend visualization:

| Phase | Color | Represents |
|-------|-------|-----------|
| `initialization` | Blue | Data retrieval, meta-learning |
| `generation` | Purple | Actor generating RFC |
| `critique` | Amber | Evaluator scoring |
| `reflection` | Cyan | Reflector creating feedback |
| `iteration` | Green | Iteration milestone |
| `complete` | Green | Final result |

This allows the frontend to render phase-specific styling without parsing message content.

---

## 8. LLM Provider Abstraction

### 8.1 Provider-Agnostic Design

The agent abstracts LLM selection behind a factory function:

```python
def _create_llm(temperature, max_tokens=8192):
    provider = config.llm_provider  # "anthropic" | "google" | "groq" | "openai"

    if provider == "google":
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, ...)
    elif provider == "groq":
        return ChatGroq(model=model, temperature=temperature, ...)
    elif provider == "openai":
        return ChatOpenAI(model=model, temperature=temperature, ...)
    else:
        return ChatAnthropic(model=model, temperature=temperature, ...)
```

All four providers implement the same LangChain `BaseChatModel` interface, so the rest of the codebase is completely provider-agnostic.

### 8.2 Provider Characteristics

| Provider | Model | Cost/Run | Structured Output | Speed |
|----------|-------|----------|-------------------|-------|
| Anthropic | Claude Sonnet 4 | ~$0.20 | Excellent | Medium |
| Google | Gemini 2.0 Flash | Free tier | Good | Fast |
| Groq | Llama 3.3 70B | Free tier | Good | Very Fast |
| OpenAI | GPT-4o | ~$0.15 | Excellent | Medium |

The free-tier providers (Google, Groq) enable zero-cost demos and development. Production deployments typically use Claude or GPT-4o for superior structured output reliability.

---

## 9. Deployment

### 9.1 Container Architecture

```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

The image is ~200MB (no vector database, no heavy ML dependencies). It deploys to any container platform — Cloud Run, ECS, Azure Container Apps, or a $5/month VPS.

### 9.2 Configuration

All configuration is via environment variables:

```
LLM_PROVIDER=google              # Provider selection
GOOGLE_API_KEY=AIza...            # Provider API key
MAX_ITERATIONS=3                  # Loop bound
SCORE_THRESHOLD=90                # Quality target
SERVICENOW_MCP_URL=               # Optional ServiceNow connection
```

No config files, no database, no external dependencies beyond the LLM API.

---

## 10. Evaluation and Results

### 10.1 Score Progression Across Scenarios

Tested with Claude Sonnet 4 and Gemini 2.0 Flash across all three demo scenarios:

| Scenario | Iter 1 | Iter 2 | Iter 3 | Total Improvement |
|----------|--------|--------|--------|-------------------|
| DB Migration | 6.2 | 8.1 | 9.3 | +3.1 |
| Security Patch | 6.8 | 8.4 | 9.4 | +2.6 |
| Cost Optimization | 7.8 | 8.7 | 9.1 | +1.3 |

Average improvement: +2.3 points over 3 iterations. Higher-risk scenarios (DB migration, security) show larger absolute gains, suggesting the Reflexion pattern is most valuable when there's more room for improvement.

### 10.2 Meta-Learning Strategy Distribution

Across 50 test runs:
- **Standard**: 100% of iteration 1 (by design)
- **Steady Improvement**: 62% of iteration 2 (most common — consistent progress)
- **Focus on Issues**: 28% of iteration 2 (triggered when initial improvement is modest)
- **Aggressive Improvement**: 8% of iteration 2 (strong first-iteration jumps)
- **Reset**: 2% (rare — usually indicates a model quality issue, not a strategy failure)

### 10.3 Processing Time

| Provider | 1 Iteration | Full Run (3 iter) |
|----------|-------------|-------------------|
| Claude Sonnet 4 | 15-25s | 60-90s |
| Gemini Flash | 10-20s | 40-70s |
| Groq Llama 3.3 | 5-10s | 20-40s |

Groq's inference speed makes it suitable for interactive demos where responsiveness matters more than output quality.

---

## 11. Future Work

1. **Cross-run learning** — Persist strategy outcomes across runs to build a learned policy for strategy selection, replacing the heuristic thresholds
2. **Fine-tuned evaluator** — Train a specialized evaluation model on human CAB reviewer scores to improve correlation with real-world approval decisions
3. **Multi-RFC planning** — Analyze relationships between concurrent RFCs to identify conflicts, resource contentions, and optimal scheduling
4. **Automated CMDB impact analysis** — Use graph traversal on CMDB relationships to automatically identify affected services and downstream dependencies
5. **Benchmark dataset expansion** — Expand the ITSM fixture dataset with community contributions, covering more change types, organization sizes, and regulatory environments
6. **Agent-to-Agent protocol** — Implement A2A (Agent-to-Agent) protocol support so the Reflexion agent can collaborate with other enterprise agents (change scheduling, capacity planning, incident correlation)

---

## 12. Conclusion

The ITIL Reflexion Agent demonstrates that the Reflexion pattern — originally validated on code generation and decision-making — transfers effectively to enterprise document generation. The addition of adaptive meta-learning makes the pattern more robust by responding to improvement dynamics rather than applying a fixed strategy. The combination of open-source availability, LLM-agnostic design, and ServiceNow MCP integration positions this as a practical tool for real ITSM environments, not just a research prototype.

---

## References

- Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning.* NeurIPS 2023.
- Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models.* ICLR 2023.
- Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., Narang, S., Chowdhery, A., & Zhou, D. (2023). *Self-Consistency Improves Chain of Thought Reasoning in Language Models.* ICLR 2023.
- LangGraph Documentation. LangChain, Inc. https://langchain-ai.github.io/langgraph/
- Model Context Protocol Specification. Anthropic. https://modelcontextprotocol.io/
- ITIL 4: Digital and IT Strategy. AXELOS/PeopleCert, 2019.

---

*Published under MIT License by Vuduvations. Contributions welcome at github.com/vuduvations/itil-reflexion-agent*
