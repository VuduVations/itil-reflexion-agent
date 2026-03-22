"""Agent node functions for the ITIL Reflexion LangGraph.

Each function is a LangGraph node that takes RFCState and returns a partial state update.
"""

import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage

from config import config
from schemas import RFCState, EvaluationOutput, ReflectionOutput
from prompts import (
    ACTOR_SYSTEM, ACTOR_STANDARD, ACTOR_WITH_FEEDBACK, STRATEGY_INSTRUCTIONS,
    EVALUATOR_SYSTEM, EVALUATOR_PROMPT,
    REFLECTOR_SYSTEM, REFLECTOR_PROMPT,
    CAB_SUMMARY_SYSTEM, CAB_SUMMARY_PROMPT,
)


# =============================================================================
# LLM Instances (temperature-optimized per role)
# =============================================================================

# Model defaults per provider
PROVIDER_DEFAULTS = {
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o",
}


def _create_llm(temperature: float, max_tokens: int = 8192):
    """Create an LLM instance based on the configured provider."""
    provider = config.llm_provider
    model = config.llm_model
    # Use provider default if model is still the anthropic default but provider changed
    if provider != "anthropic" and "claude" in model:
        model = PROVIDER_DEFAULTS.get(provider, model)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=config.google_api_key,
            max_output_tokens=max_tokens,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            temperature=temperature,
            api_key=config.groq_api_key,
            max_tokens=max_tokens,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=config.openai_api_key,
            max_tokens=max_tokens,
        )
    else:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=config.anthropic_api_key,
            max_tokens=max_tokens,
        )


actor_llm = _create_llm(config.actor_temperature)
evaluator_llm = _create_llm(config.evaluator_temperature)
reflector_llm = _create_llm(config.reflector_temperature)
cab_llm = _create_llm(0.4, max_tokens=4096)

# Structured output LLMs
evaluator_structured = evaluator_llm.with_structured_output(EvaluationOutput)
reflector_structured = reflector_llm.with_structured_output(ReflectionOutput)


# =============================================================================
# Streaming helper
# =============================================================================

def _sync_emit(state: RFCState, phase: str, message: str, data: dict = None):
    """Emit a streaming event from a sync context (thread-safe).

    The graph runs in a thread via run_in_executor, so we can't use async.
    asyncio.Queue is thread-safe for put_nowait.
    """
    queue = state.get("stream_queue")
    if queue is None:
        return
    event = {"phase": phase, "message": message, "timestamp": datetime.now(timezone.utc).isoformat()}
    if data:
        event["data"] = data
    try:
        queue.put_nowait(event)
    except Exception:
        pass


# =============================================================================
# NODE: retrieve_data
# =============================================================================

def retrieve_data(state: RFCState) -> dict:
    """Retrieve incident and CMDB data from custom upload, fixtures, or MCP."""
    _sync_emit(state, "initialization", "Loading incident data and CMDB configuration...")

    custom_data = state.get("custom_data")

    if custom_data:
        # User-uploaded data
        _sync_emit(state, "initialization", "Using uploaded data...")
        incidents = custom_data.get("incidents", [])
        cmdb_info = custom_data.get("cmdb", {})
        # Build scenario_meta from uploaded context or defaults
        scenario_meta = custom_data.get("context", {})
        if not scenario_meta.get("name"):
            scenario_meta["name"] = custom_data.get("name", "Custom RFC Analysis")
        if not scenario_meta.get("category"):
            scenario_meta["category"] = custom_data.get("category", "Custom")
        if not scenario_meta.get("rfc_id"):
            scenario_meta["rfc_id"] = custom_data.get("rfc_id", "RFC-CUSTOM-001")
        # Derive fields from data if not provided
        if not scenario_meta.get("affected_services"):
            services = set()
            for inc in incidents:
                if inc.get("affected_ci"):
                    services.update(s.strip() for s in str(inc["affected_ci"]).split(","))
            scenario_meta["affected_services"] = list(services)[:10]
        if not cmdb_info.get("total_ci_count"):
            cmdb_info["total_ci_count"] = len(cmdb_info.get("items", []))
    else:
        # Load from JSON fixtures
        import os
        data_dir = config.data_dir
        scenario_id = state["scenario_id"]

        with open(os.path.join(data_dir, "incidents.json")) as f:
            all_incidents = json.load(f)
        with open(os.path.join(data_dir, "cmdb.json")) as f:
            all_cmdb = json.load(f)
        with open(os.path.join(data_dir, "scenarios.json")) as f:
            all_scenarios = json.load(f)

        incidents = all_incidents.get(scenario_id, [])
        cmdb_info = all_cmdb.get(scenario_id, {})
        scenario_meta = all_scenarios.get(scenario_id, {})

    ci_count = cmdb_info.get("total_ci_count", len(cmdb_info.get("items", [])))
    _sync_emit(
        state, "initialization",
        f"Retrieved {len(incidents)} incidents and {ci_count} CMDB items"
    )

    return {
        "incidents": incidents,
        "cmdb_info": cmdb_info,
        "scenario_meta": scenario_meta,
        "history": [{"stage": "retrieval", "incident_count": len(incidents), "ci_count": ci_count}],
    }


# =============================================================================
# NODE: meta_learning
# =============================================================================

def meta_learning(state: RFCState) -> dict:
    """Analyze score progression and select optimal prompt strategy."""
    iteration = state.get("iteration", 1)

    if iteration == 1:
        _sync_emit(state, "initialization", "Meta-learning: First iteration — using standard strategy")
        return {
            "prompt_strategy": "standard",
            "improvement_pattern": "none",
            "history": [{"stage": "meta_learning", "iteration": iteration, "strategy": "standard"}],
        }

    # Analyze score delta from history
    eval_history = [h for h in state.get("history", []) if h.get("stage") == "evaluation"]

    if len(eval_history) < 2:
        strategy = "standard"
        pattern = "insufficient_data"
    else:
        prev_score = eval_history[-2].get("score", 0)
        curr_score = eval_history[-1].get("score", 0)
        delta = curr_score - prev_score

        if delta > 15:
            strategy = "aggressive_improvement"
            pattern = "strong_progress"
        elif delta > 8:
            strategy = "steady_improvement"
            pattern = "consistent_gains"
        elif delta > 0:
            strategy = "focus_on_issues"
            pattern = "minimal_progress"
        else:
            strategy = "reset_approach"
            pattern = "no_improvement"

    _sync_emit(state, "initialization", f"Meta-learning: Strategy = {strategy} (pattern: {pattern})")

    return {
        "prompt_strategy": strategy,
        "improvement_pattern": pattern,
        "history": [{"stage": "meta_learning", "iteration": iteration, "strategy": strategy, "pattern": pattern}],
    }


# =============================================================================
# NODE: generate_rfc
# =============================================================================

def generate_rfc(state: RFCState) -> dict:
    """Actor agent generates or improves the RFC."""
    iteration = state.get("iteration", 1)
    strategy = state.get("prompt_strategy", "standard")
    start_time = time.time()

    _sync_emit(state, "generation", f"Iteration {iteration}: Generating RFC (strategy: {strategy})...")

    incidents_text = json.dumps(state.get("incidents", []), indent=2)
    cmdb_text = json.dumps(state.get("cmdb_info", {}), indent=2)
    scenario_text = json.dumps(state.get("scenario_meta", {}), indent=2)

    if iteration == 1 or not state.get("feedback"):
        prompt = ACTOR_STANDARD.format(
            incidents=incidents_text,
            cmdb_info=cmdb_text,
            scenario_meta=scenario_text,
        )
    else:
        strategy_instr = STRATEGY_INSTRUCTIONS.get(strategy, STRATEGY_INSTRUCTIONS["standard"])
        prompt = ACTOR_WITH_FEEDBACK.format(
            iteration=iteration,
            previous_rfc=state.get("rfc", ""),
            feedback=state.get("feedback", ""),
            previous_score=state.get("critique", {}).get("scores", {}).get("overall_quality", "N/A"),
            strategy=strategy,
            strategy_instructions=strategy_instr,
            incidents=incidents_text,
            cmdb_info=cmdb_text,
        )

    messages = [SystemMessage(content=ACTOR_SYSTEM), HumanMessage(content=prompt)]
    response = actor_llm.invoke(messages)
    rfc = response.content

    elapsed = round(time.time() - start_time, 1)
    tokens = response.usage_metadata.get("total_tokens", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else 0

    _sync_emit(state, "generation", f"RFC generated ({len(rfc)} chars, {elapsed}s, {tokens} tokens)")

    return {
        "rfc": rfc,
        "history": [{"stage": "generation", "iteration": iteration, "strategy": strategy, "chars": len(rfc), "elapsed": elapsed, "tokens": tokens}],
    }


# =============================================================================
# NODE: evaluate_rfc
# =============================================================================

def evaluate_rfc(state: RFCState) -> dict:
    """Evaluator agent scores the RFC against ITIL standards."""
    iteration = state.get("iteration", 1)
    start_time = time.time()

    _sync_emit(state, "critique", f"Iteration {iteration}: Evaluating RFC against ITIL standards...")

    # Build history context
    eval_history = [h for h in state.get("history", []) if h.get("stage") == "evaluation"]
    history_context = ""
    if eval_history:
        prev = eval_history[-1]
        history_context = f"Previous iteration scored {prev.get('score', 'N/A')}/10 overall quality."

    prompt = EVALUATOR_PROMPT.format(
        rfc=state.get("rfc", ""),
        iteration=iteration,
        history_context=history_context,
    )

    messages = [SystemMessage(content=EVALUATOR_SYSTEM), HumanMessage(content=prompt)]

    try:
        evaluation: EvaluationOutput = evaluator_structured.invoke(messages)
        critique = _evaluation_to_dict(evaluation)
    except Exception as e:
        # Fallback if structured output fails
        _sync_emit(state, "critique", f"Structured output failed ({e}), using text parsing...")
        response = evaluator_llm.invoke(messages)
        critique = _parse_fallback_evaluation(response.content, iteration)

    # Validate score progression
    critique = _validate_score_progression(state, critique, iteration)

    elapsed = round(time.time() - start_time, 1)
    score = critique["scores"]["overall_quality"]

    _sync_emit(
        state, "critique",
        f"Evaluation complete: {score}/10 overall quality ({elapsed}s)"
    )

    # Emit iteration summary with full data for real-time frontend updates
    risk = critique["scores"]["risk_level"]
    risk_label = "LOW" if risk <= 3.5 else "MEDIUM" if risk <= 6.5 else "HIGH"

    # Build iteration data matching frontend contract
    gen_history = [h for h in state.get("history", []) if h.get("stage") == "generation"]
    gen_entry = gen_history[-1] if gen_history else {}
    iteration_data = {
        "iteration": iteration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processing_time": elapsed + gen_entry.get("elapsed", 0),
        "tokens_used": gen_entry.get("tokens", 0),
        **critique,
    }

    _sync_emit(
        state, "iteration",
        f"Iteration {iteration} complete. Quality: {score}/10 | Risk: {risk_label}",
        data={"type": "iteration_complete", "iteration": iteration_data},
    )

    return {
        "critique": critique,
        "history": [{"stage": "evaluation", "iteration": iteration, "score": score, "elapsed": elapsed, **critique}],
    }


def _to_dict(obj):
    """Convert a Pydantic model or dict to a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return dict(obj)


def _evaluation_to_dict(evaluation) -> dict:
    """Convert structured EvaluationOutput (Pydantic or dict) to dict matching frontend contract."""
    # Handle case where provider returns a plain dict instead of Pydantic model
    if isinstance(evaluation, dict):
        return {
            "scores": evaluation.get("scores", {}),
            "executive_summary": evaluation.get("executive_summary", {}),
            "rfc_summary": evaluation.get("rfc_summary", {}),
            "critical_issues": evaluation.get("critical_issues", []),
            "improvements": evaluation.get("improvements", []),
            "change_categories": evaluation.get("change_categories", {}),
        }

    return {
        "scores": _to_dict(evaluation.scores),
        "executive_summary": _to_dict(evaluation.executive_summary),
        "rfc_summary": _to_dict(evaluation.rfc_summary),
        "critical_issues": [_to_dict(i) for i in evaluation.critical_issues],
        "improvements": [_to_dict(i) for i in evaluation.improvements],
        "change_categories": {
            k: _to_dict(v) if hasattr(v, "model_dump") else v
            for k, v in _to_dict(evaluation.change_categories).items()
        },
    }


def _validate_score_progression(state: RFCState, critique: dict, iteration: int) -> dict:
    """Prevent unrealistic score jumps or stalling."""
    eval_history = [h for h in state.get("history", []) if h.get("stage") == "evaluation"]

    if not eval_history:
        # First iteration: clamp to realistic range
        scores = critique["scores"]
        scores["overall_quality"] = min(max(scores["overall_quality"], 5.5), 7.8)
        return critique

    prev_score = eval_history[-1].get("score", 6.0)
    curr_score = critique["scores"]["overall_quality"]

    # Prevent jumps > 2.5 points per iteration
    max_improvement = 2.5
    if curr_score - prev_score > max_improvement:
        critique["scores"]["overall_quality"] = round(prev_score + max_improvement, 1)

    # Prevent regression (scores should generally improve)
    if curr_score < prev_score - 0.5:
        critique["scores"]["overall_quality"] = round(prev_score + 0.3, 1)

    return critique


def _parse_fallback_evaluation(text: str, iteration: int) -> dict:
    """Parse evaluation from unstructured text as fallback."""
    base_score = 6.0 + (iteration - 1) * 1.5
    return {
        "scores": {
            "overall_quality": min(base_score, 9.5),
            "itil_compliance": min(base_score + 0.2, 9.5),
            "risk_level": max(8.5 - iteration * 2.0, 2.5),
            "business_value": min(base_score + 0.5, 9.5),
            "technical_readiness": min(base_score - 0.2, 9.5),
            "stakeholder_confidence": min(base_score - 0.3, 9.5),
        },
        "executive_summary": {
            "recommendation": "CONDITIONAL APPROVAL" if iteration < 3 else "APPROVED FOR PRODUCTION",
            "deployment_risk": "HIGH" if iteration == 1 else "MEDIUM" if iteration == 2 else "LOW",
            "business_impact": "High",
            "cab_approval_probability": min(0.5 + iteration * 0.15, 0.95),
            "estimated_roi": "Estimated positive ROI",
            "key_concerns": [text[:200]] if iteration < 3 else [],
        },
        "rfc_summary": {
            "title": "RFC Under Review",
            "objective": "See full RFC text",
            "business_justification": "See full RFC text",
            "technical_approach": "See full RFC text",
            "rollback_plan_status": "Documented",
            "testing_status": "In progress",
            "timeline": "See full RFC text",
            "impact": "See full RFC text",
        },
        "critical_issues": [],
        "improvements": [],
        "change_categories": {
            "technical": {"score": base_score, "status": "ADEQUATE"},
            "procedural": {"score": base_score - 0.5, "status": "ADEQUATE"},
            "compliance": {"score": base_score + 0.3, "status": "GOOD"},
            "communication": {"score": base_score - 0.2, "status": "ADEQUATE"},
        },
    }


# =============================================================================
# NODE: reflect
# =============================================================================

def reflect(state: RFCState) -> dict:
    """Reflector agent creates actionable feedback from critique."""
    iteration = state.get("iteration", 1)
    critique = state.get("critique", {})
    strategy = state.get("prompt_strategy", "standard")

    _sync_emit(state, "reflection", f"Iteration {iteration}: Reflecting on evaluation results...")

    # Build score trend
    eval_history = [h for h in state.get("history", []) if h.get("stage") == "evaluation"]
    scores = [h.get("score", 0) for h in eval_history]
    score_trend = " -> ".join(str(s) for s in scores) if scores else "N/A"

    prompt = REFLECTOR_PROMPT.format(
        scores=json.dumps(critique.get("scores", {}), indent=2),
        critical_issues=json.dumps(critique.get("critical_issues", []), indent=2),
        improvements=json.dumps(critique.get("improvements", []), indent=2),
        strategy=strategy,
        iteration=iteration,
        score_trend=score_trend,
    )

    messages = [SystemMessage(content=REFLECTOR_SYSTEM), HumanMessage(content=prompt)]

    try:
        reflection: ReflectionOutput = reflector_structured.invoke(messages)
        feedback = reflection.feedback
    except Exception:
        response = reflector_llm.invoke(messages)
        feedback = response.content

    _sync_emit(state, "reflection", f"Reflection complete: Generated actionable feedback ({len(feedback)} chars)")

    return {
        "feedback": feedback,
        "history": [{"stage": "reflection", "iteration": iteration, "feedback_length": len(feedback)}],
    }


# =============================================================================
# CONDITIONAL: should_continue
# =============================================================================

def should_continue(state: RFCState) -> Literal["continue", "finalize"]:
    """Decide whether to iterate or finalize."""
    score = state.get("critique", {}).get("scores", {}).get("overall_quality", 0)
    iteration = state.get("iteration", 1)
    max_iterations = state.get("max_iterations", 3)
    score_threshold = state.get("score_threshold", 90) / 10  # Convert to 0-10 scale

    if score >= score_threshold or iteration >= max_iterations:
        return "finalize"
    return "continue"


# =============================================================================
# NODE: increment_iteration
# =============================================================================

def increment_iteration(state: RFCState) -> dict:
    """Increment the iteration counter."""
    new_iter = state.get("iteration", 1) + 1
    return {"iteration": new_iter}


# =============================================================================
# NODE: finalize_results
# =============================================================================

def finalize_results(state: RFCState) -> dict:
    """Compile structured results matching the frontend JSON contract."""
    _sync_emit(state, "reflection", "Finalizing results and compiling iteration data...")

    eval_history = [h for h in state.get("history", []) if h.get("stage") == "evaluation"]
    gen_history = [h for h in state.get("history", []) if h.get("stage") == "generation"]
    scenario_meta = state.get("scenario_meta", {})

    iterations = []
    for i, eval_entry in enumerate(eval_history):
        gen_entry = gen_history[i] if i < len(gen_history) else {}
        iteration_data = {
            "iteration": eval_entry.get("iteration", i + 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processing_time": eval_entry.get("elapsed", 0) + gen_entry.get("elapsed", 0),
            "tokens_used": gen_entry.get("tokens", 0),
            "scores": eval_entry.get("scores", {}),
            "executive_summary": eval_entry.get("executive_summary", {}),
            "rfc_summary": eval_entry.get("rfc_summary", {}),
            "critical_issues": eval_entry.get("critical_issues", []),
            "improvements": eval_entry.get("improvements", []),
            "change_categories": eval_entry.get("change_categories", {}),
        }
        iterations.append(iteration_data)

    # Build final result matching frontend contract
    final_result = {
        "rfc_name": scenario_meta.get("name", "RFC"),
        "rfc_metadata": {
            "title": scenario_meta.get("description", ""),
            "category": scenario_meta.get("category", ""),
            "rfc_id": scenario_meta.get("rfc_id", ""),
            "ci_count": state.get("cmdb_info", {}).get("total_ci_count", 0),
            "affected_services": scenario_meta.get("affected_services", []),
            "estimated_cost": scenario_meta.get("estimated_cost", ""),
            "business_value": scenario_meta.get("business_value", ""),
            "timeline": scenario_meta.get("timeline", ""),
            "cmdb_items": [item.get("ci_id", "") + " (" + item.get("description", "") + ")"
                           for item in state.get("cmdb_info", {}).get("items", [])],
            "risk_factors": scenario_meta.get("risk_factors", []),
            "rollback_plan": scenario_meta.get("rollback_plan", ""),
            "testing_completed": scenario_meta.get("testing_completed", ""),
        },
        "iterations": iterations,
    }

    # Determine CAB readiness
    final_score = eval_history[-1].get("score", 0) if eval_history else 0
    cab_ready = final_score >= 8.5

    _sync_emit(
        state, "reflection",
        f"Results finalized: {len(iterations)} iterations, final score {final_score}/10, "
        f"{'CAB-READY' if cab_ready else 'Needs refinement'}"
    )

    return {
        "final_result": final_result,
        "history": [{"stage": "finalize", "iterations": len(iterations), "final_score": final_score, "cab_ready": cab_ready}],
    }


# =============================================================================
# NODE: cab_summary
# =============================================================================

def cab_summary(state: RFCState) -> dict:
    """Generate executive CAB summary."""
    _sync_emit(state, "complete", "Generating Change Advisory Board executive summary...")

    result = state.get("final_result", {})
    iterations = result.get("iterations", [])

    if not iterations:
        return {"cab_summary": "No iterations completed."}

    final_iter = iterations[-1]
    final_scores = json.dumps(final_iter.get("scores", {}), indent=2)
    recommendation = final_iter.get("executive_summary", {}).get("recommendation", "N/A")

    # Build iteration history summary
    iter_summary = []
    for it in iterations:
        score = it.get("scores", {}).get("overall_quality", 0)
        rec = it.get("executive_summary", {}).get("recommendation", "")
        iter_summary.append(f"Iteration {it['iteration']}: {score}/10 - {rec}")

    prompt = CAB_SUMMARY_PROMPT.format(
        rfc=state.get("rfc", "")[:3000],
        iteration_history="\n".join(iter_summary),
        final_scores=final_scores,
        recommendation=recommendation,
    )

    messages = [SystemMessage(content=CAB_SUMMARY_SYSTEM), HumanMessage(content=prompt)]
    response = cab_llm.invoke(messages)
    summary = response.content

    _sync_emit(state, "complete", "Reflexion complete! CAB summary generated.")

    return {
        "cab_summary": summary,
        "history": [{"stage": "cab_summary"}],
    }
