"""LangGraph StateGraph definition for the ITIL Reflexion Agent."""

from langgraph.graph import StateGraph, END

from schemas import RFCState
from agents import (
    retrieve_data,
    meta_learning,
    generate_rfc,
    evaluate_rfc,
    reflect,
    should_continue,
    increment_iteration,
    finalize_results,
    cab_summary,
)


def build_reflexion_graph() -> StateGraph:
    """Construct and compile the LangGraph StateGraph for Reflexion RFC generation.

    Flow:
        START -> retrieve_data -> meta_learning -> generate_rfc -> evaluate_rfc
                                    ^                                  |
                                    |                           [should_continue?]
                                    |                            /           \\
                                increment <- reflect        finalize -> cab_summary -> END
    """
    workflow = StateGraph(RFCState)

    # Add nodes
    workflow.add_node("retrieve_data", retrieve_data)
    workflow.add_node("meta_learning", meta_learning)
    workflow.add_node("generate_rfc", generate_rfc)
    workflow.add_node("evaluate_rfc", evaluate_rfc)
    workflow.add_node("reflect", reflect)
    workflow.add_node("increment", increment_iteration)
    workflow.add_node("finalize", finalize_results)
    workflow.add_node("generate_cab_summary", cab_summary)

    # Define edges
    workflow.set_entry_point("retrieve_data")
    workflow.add_edge("retrieve_data", "meta_learning")
    workflow.add_edge("meta_learning", "generate_rfc")
    workflow.add_edge("generate_rfc", "evaluate_rfc")

    # Conditional edge: continue iterating or finalize
    workflow.add_conditional_edges(
        "evaluate_rfc",
        should_continue,
        {
            "continue": "reflect",
            "finalize": "finalize",
        },
    )

    # Reflection loop
    workflow.add_edge("reflect", "increment")
    workflow.add_edge("increment", "meta_learning")

    # Finalization
    workflow.add_edge("finalize", "generate_cab_summary")
    workflow.add_edge("generate_cab_summary", END)

    return workflow.compile()


# Compiled graph singleton
reflexion_graph = build_reflexion_graph()
