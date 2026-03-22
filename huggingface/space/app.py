"""ITIL Reflexion Agent — Hugging Face Space (Gradio Interface)

Interactive demo that runs the Reflexion loop and displays results.
Uses Groq Llama 3.3 70B (free tier) for zero-cost inference.
"""

import os
import json
import time
import gradio as gr
from datetime import datetime, timezone

# Ensure we use Groq for the free HF Space
os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("LLM_MODEL", "llama-3.3-70b-versatile")

from config import config
from graph import reflexion_graph


# =============================================================================
# SCENARIOS
# =============================================================================

SCENARIOS = {
    "Database Migration — PostgreSQL 16 Upgrade": "db-migration",
    "Security Patch — Log4Shell Emergency": "security-patch",
    "Cost Optimization — Multi-Region Auto-Scaling": "cost-optimization",
}

SCENARIO_DESCRIPTIONS = {
    "db-migration": "23 CMDB items, 30TB data, 10 critical services, zero-downtime requirement",
    "security-patch": "340 Java services, CVSS 10.0, 20 CMDB items, 72-hour emergency window",
    "cost-optimization": "$2.1M annual savings target, 3 AWS regions, 25 CMDB items, 8-week rollout",
}


# =============================================================================
# RUN REFLEXION
# =============================================================================

def run_reflexion(scenario_name, max_iterations, progress=gr.Progress()):
    """Run the Reflexion loop and yield progressive updates."""
    scenario_id = SCENARIOS.get(scenario_name, "db-migration")

    progress(0, desc="Initializing...")

    initial_state = {
        "scenario_id": scenario_id,
        "incidents": [],
        "cmdb_info": {},
        "scenario_meta": {},
        "custom_data": None,
        "iteration": 1,
        "max_iterations": max_iterations,
        "score_threshold": 90,
        "rfc": "",
        "critique": {},
        "feedback": "",
        "prompt_strategy": "standard",
        "improvement_pattern": "none",
        "history": [],
        "should_continue": True,
        "final_result": None,
        "cab_summary": "",
        "stream_queue": None,
    }

    start_time = time.time()
    progress(0.1, desc="Loading incident data and CMDB...")

    try:
        final_state = reflexion_graph.invoke(initial_state)
    except Exception as e:
        return (
            f"**Error:** {str(e)}",
            "Error",
            "Error",
            "Error",
            "Error",
        )

    elapsed = round(time.time() - start_time, 1)
    result = final_state.get("final_result", {})
    iterations = result.get("iterations", [])
    cab = final_state.get("cab_summary", "")

    progress(1.0, desc="Complete!")

    # Format iteration results
    iter_output = _format_iterations(iterations)
    scores_output = _format_scores(iterations)
    metadata_output = _format_metadata(result, elapsed)
    cab_output = cab if cab else "No CAB summary generated."

    return iter_output, scores_output, metadata_output, cab_output, _format_log(iterations, elapsed)


def _format_iterations(iterations):
    """Format iteration details as markdown."""
    if not iterations:
        return "No iterations completed."

    lines = []
    for it in iterations:
        scores = it.get("scores", {})
        exec_sum = it.get("executive_summary", {})
        rfc_sum = it.get("rfc_summary", {})
        issues = it.get("critical_issues", [])
        improvements = it.get("improvements", [])

        lines.append(f"## Iteration {it.get('iteration', '?')}")
        lines.append("")
        lines.append(f"**Recommendation:** {exec_sum.get('recommendation', 'N/A')}")
        lines.append(f"**CAB Approval Probability:** {exec_sum.get('cab_approval_probability', 0) * 100:.0f}%")
        lines.append(f"**Deployment Risk:** {exec_sum.get('deployment_risk', 'N/A')}")
        lines.append("")

        # RFC Summary
        lines.append(f"### RFC Summary")
        lines.append(f"**{rfc_sum.get('title', 'N/A')}**")
        lines.append(f"- **Objective:** {rfc_sum.get('objective', 'N/A')}")
        lines.append(f"- **Rollback:** {rfc_sum.get('rollback_plan_status', 'N/A')}")
        lines.append(f"- **Testing:** {rfc_sum.get('testing_status', 'N/A')}")
        lines.append(f"- **Timeline:** {rfc_sum.get('timeline', 'N/A')}")
        lines.append("")

        # Issues
        if issues:
            lines.append("### Critical Issues")
            for iss in issues:
                lines.append(f"- **[{iss.get('severity', 'N/A')}]** {iss.get('category', '')}: {iss.get('issue', '')}")
            lines.append("")

        # Improvements
        if improvements:
            lines.append("### Improvements")
            for imp in improvements:
                lines.append(f"- **[{imp.get('priority', 'N/A')}]** {imp.get('action', '')} *(~{imp.get('effort_hours', '?')}h)*")
            lines.append("")

        # Key concerns
        concerns = exec_sum.get("key_concerns", [])
        if concerns:
            lines.append("### Key Concerns")
            for c in concerns:
                lines.append(f"- {c}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _format_scores(iterations):
    """Format scores as a comparison table."""
    if not iterations:
        return "No scores available."

    lines = ["| Dimension | " + " | ".join(f"Iter {it['iteration']}" for it in iterations) + " |"]
    lines.append("|---|" + "|".join("---" for _ in iterations) + "|")

    dimensions = [
        ("Overall Quality", "overall_quality"),
        ("ITIL Compliance", "itil_compliance"),
        ("Risk Level", "risk_level"),
        ("Business Value", "business_value"),
        ("Technical Readiness", "technical_readiness"),
        ("Stakeholder Confidence", "stakeholder_confidence"),
    ]

    for label, key in dimensions:
        vals = []
        for it in iterations:
            v = it.get("scores", {}).get(key, 0)
            vals.append(f"**{v:.1f}**" if it == iterations[-1] else f"{v:.1f}")
        lines.append(f"| {label} | " + " | ".join(vals) + " |")

    # Add CAB probability row
    vals = []
    for it in iterations:
        p = it.get("executive_summary", {}).get("cab_approval_probability", 0)
        vals.append(f"**{p * 100:.0f}%**" if it == iterations[-1] else f"{p * 100:.0f}%")
    lines.append(f"| CAB Approval Prob. | " + " | ".join(vals) + " |")

    return "\n".join(lines)


def _format_metadata(result, elapsed):
    """Format RFC metadata."""
    meta = result.get("rfc_metadata", {})
    if not meta:
        return "No metadata available."

    lines = [
        f"**RFC:** {result.get('rfc_name', 'N/A')}",
        f"**ID:** {meta.get('rfc_id', 'N/A')}",
        f"**Category:** {meta.get('category', 'N/A')}",
        f"**CI Count:** {meta.get('ci_count', 'N/A')}",
        f"**Estimated Cost:** {meta.get('estimated_cost', 'N/A')}",
        f"**Timeline:** {meta.get('timeline', 'N/A')}",
        f"**Processing Time:** {elapsed}s",
        "",
        "**Affected Services:**",
    ]
    for svc in meta.get("affected_services", []):
        lines.append(f"- {svc}")

    if meta.get("risk_factors"):
        lines.append("")
        lines.append("**Risk Factors:**")
        for rf in meta["risk_factors"]:
            lines.append(f"- {rf}")

    return "\n".join(lines)


def _format_log(iterations, elapsed):
    """Format a simple execution log."""
    lines = [f"Reflexion completed in {elapsed}s with {len(iterations)} iterations.", ""]
    for it in iterations:
        score = it.get("scores", {}).get("overall_quality", 0)
        rec = it.get("executive_summary", {}).get("recommendation", "")
        lines.append(f"Iteration {it['iteration']}: {score:.1f}/10 — {rec}")
    return "\n".join(lines)


# =============================================================================
# GRADIO UI
# =============================================================================

DESCRIPTION = """
# ITIL Reflexion Agent

An AI agent that **iteratively improves** Request for Change (RFC) documents through a structured
**Actor → Evaluator → Reflector** loop with adaptive meta-learning.

Built on [LangGraph](https://github.com/langchain-ai/langgraph) |
[GitHub](https://github.com/vuduvations/itil-reflexion-agent) |
[Whitepaper](https://github.com/vuduvations/itil-reflexion-agent/blob/main/docs/whitepaper.pdf)

**How it works:** Select a scenario → the agent generates an RFC, evaluates it against ITIL v4 standards,
reflects on weaknesses, and improves it. Each iteration gets better. Typically reaches CAB-ready quality (9+/10) in 3 iterations.
"""

with gr.Blocks(
    title="ITIL Reflexion Agent",
    theme=gr.themes.Base(
        primary_hue="purple",
        secondary_hue="emerald",
        neutral_hue="slate",
    ),
) as demo:
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        with gr.Column(scale=2):
            scenario = gr.Dropdown(
                choices=list(SCENARIOS.keys()),
                value="Database Migration — PostgreSQL 16 Upgrade",
                label="Scenario",
            )
            scenario_desc = gr.Markdown(
                value=f"*{SCENARIO_DESCRIPTIONS['db-migration']}*"
            )
        with gr.Column(scale=1):
            max_iter = gr.Slider(
                minimum=1, maximum=3, value=3, step=1,
                label="Max Iterations",
            )
            run_btn = gr.Button("Run Reflexion", variant="primary", size="lg")

    # Update description when scenario changes
    def update_desc(name):
        sid = SCENARIOS.get(name, "db-migration")
        return f"*{SCENARIO_DESCRIPTIONS.get(sid, '')}*"
    scenario.change(update_desc, scenario, scenario_desc)

    with gr.Row():
        log_output = gr.Textbox(label="Execution Log", lines=5, interactive=False)

    with gr.Tabs():
        with gr.TabItem("Score Progression"):
            scores_output = gr.Markdown(label="Scores")
        with gr.TabItem("Iteration Details"):
            iter_output = gr.Markdown(label="Details")
        with gr.TabItem("RFC Metadata"):
            meta_output = gr.Markdown(label="Metadata")
        with gr.TabItem("CAB Summary"):
            cab_output = gr.Markdown(label="CAB Summary")

    run_btn.click(
        fn=run_reflexion,
        inputs=[scenario, max_iter],
        outputs=[iter_output, scores_output, meta_output, cab_output, log_output],
    )

    gr.Markdown("""
---
*Built by [Vuduvations](https://vuduvations.io) | Powered by LangGraph + Groq Llama 3.3 |
[GitHub](https://github.com/vuduvations/itil-reflexion-agent) |
[Technical Paper](https://github.com/vuduvations/itil-reflexion-agent/blob/main/docs/technical-paper.pdf)*
    """)

if __name__ == "__main__":
    demo.launch()
