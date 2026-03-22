"""State schema and Pydantic output models for the ITIL Reflexion Agent."""

from typing import TypedDict, List, Dict, Annotated, Optional
from pydantic import BaseModel, Field
import operator


# =============================================================================
# LangGraph State
# =============================================================================

class RFCState(TypedDict):
    """State object passed between LangGraph nodes."""
    # Input data
    scenario_id: str
    incidents: List[Dict]
    cmdb_info: Dict
    scenario_meta: Dict
    custom_data: Optional[Dict]  # User-uploaded incidents/CMDB data

    # Iteration control
    iteration: int
    max_iterations: int
    score_threshold: int

    # Agent outputs
    rfc: str
    critique: Dict
    feedback: str
    prompt_strategy: str
    improvement_pattern: str

    # Accumulated history (append-only via operator.add)
    history: Annotated[List[Dict], operator.add]

    # Control flow
    should_continue: bool
    final_result: Optional[Dict]
    cab_summary: str

    # Streaming
    stream_queue: Optional[object]


# =============================================================================
# Pydantic Output Models (for structured LLM output)
# =============================================================================

class RFCScores(BaseModel):
    """Six-dimension scoring for an RFC iteration."""
    overall_quality: float = Field(ge=0, le=10, description="Overall RFC quality 0-10")
    itil_compliance: float = Field(ge=0, le=10, description="ITIL framework compliance 0-10")
    risk_level: float = Field(ge=0, le=10, description="Risk level 0-10 (lower is better)")
    business_value: float = Field(ge=0, le=10, description="Business value articulation 0-10")
    technical_readiness: float = Field(ge=0, le=10, description="Technical readiness 0-10")
    stakeholder_confidence: float = Field(ge=0, le=10, description="Stakeholder confidence 0-10")


class ExecutiveSummary(BaseModel):
    """Executive summary for CAB review."""
    recommendation: str = Field(description="e.g. CONDITIONAL APPROVAL, APPROVED FOR PRODUCTION")
    deployment_risk: str = Field(description="e.g. HIGH, MEDIUM, LOW")
    business_impact: str = Field(description="Business impact level")
    cab_approval_probability: float = Field(ge=0, le=1, description="Probability 0-1")
    estimated_roi: str = Field(description="ROI estimate")
    key_concerns: List[str] = Field(default_factory=list, description="Remaining concerns")


class RFCSummary(BaseModel):
    """Structured RFC summary."""
    title: str
    objective: str
    business_justification: str
    technical_approach: str
    rollback_plan_status: str
    testing_status: str
    timeline: str
    impact: str


class CriticalIssue(BaseModel):
    """A critical issue identified in the RFC."""
    issue: str
    category: str
    severity: str = Field(description="HIGH, MEDIUM, or LOW")
    priority: str
    impact: str


class Improvement(BaseModel):
    """A recommended improvement."""
    action: str
    priority: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    estimated_impact: str
    effort_hours: float


class ChangeCategoryScore(BaseModel):
    """Score for a change category."""
    score: float = Field(ge=0, le=10)
    status: str = Field(description="EXCELLENT, GOOD, ADEQUATE, or NEEDS IMPROVEMENT")


class ChangeCategories(BaseModel):
    """Four change management categories."""
    technical: ChangeCategoryScore
    procedural: ChangeCategoryScore
    compliance: ChangeCategoryScore
    communication: ChangeCategoryScore


class EvaluationOutput(BaseModel):
    """Structured output from the evaluator agent."""
    scores: RFCScores
    executive_summary: ExecutiveSummary
    rfc_summary: RFCSummary
    critical_issues: List[CriticalIssue] = Field(default_factory=list)
    improvements: List[Improvement] = Field(default_factory=list)
    change_categories: ChangeCategories


class ReflectionOutput(BaseModel):
    """Structured output from the reflector agent."""
    feedback: str = Field(description="Actionable feedback for the actor")
    focus_areas: List[str] = Field(description="Key areas to improve")
    strategy_recommendation: str = Field(description="Suggested prompt strategy for next iteration")
