from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RunStatus(str, Enum):
    awaiting_clarification = "awaiting_clarification"
    evaluated = "evaluated"
    ready_for_execution = "ready_for_execution"
    executed = "executed"
    downgraded = "downgraded"


class CaseType(str, Enum):
    harassment = "harassment"
    threat = "threat"
    route_deviation = "route_deviation"
    late_night_contact = "late_night_contact"
    fare_dispute = "fare_dispute"
    fraud = "fraud"
    property_loss = "property_loss"
    suspicious_behavior = "suspicious_behavior"
    uncertain = "uncertain"


class AttachmentModality(str, Enum):
    text = "text"
    image = "image"
    audio = "audio"


class ConversationTurn(BaseModel):
    speaker: str
    text: str
    timestamp: str | None = None


class Attachment(BaseModel):
    modality: AttachmentModality
    content: str | None = None
    ocr_text: str | None = None
    transcript: str | None = None
    mime_type: str | None = None
    file_name: str | None = None
    media_base64: str | None = None
    media_url: str | None = None


class CaseInput(BaseModel):
    order_id: str
    complaint_text: str
    chat_messages: list[ConversationTurn] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    passenger_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ClarificationRequest(BaseModel):
    run_id: str
    answers: list[str]


class ExecuteRequest(BaseModel):
    run_id: str
    dry_run: bool = True


class EvidenceSpan(BaseModel):
    source: str
    text: str


class RetrievedDoc(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    score: float
    snippet: str
    retrieval_query: str | None = None
    match_reason: str | None = None


class RetrievalPlan(BaseModel):
    query: str
    rationale: str
    target_doc_types: list[str] = Field(default_factory=list)


class ToolPlanItem(BaseModel):
    tool_name: str
    reason: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolPlan(BaseModel):
    items: list[ToolPlanItem] = Field(default_factory=list)
    rationale: str
    auto_executable: bool = True


class MultimodalFinding(BaseModel):
    modality: AttachmentModality
    source: str
    text: str
    summary: str | None = None
    extracted_text: str | None = None
    signals: list[str] = Field(default_factory=list)
    model_used: str | None = None
    file_name: str | None = None
    error: str | None = None


class FactBundle(BaseModel):
    case_type: CaseType = CaseType.uncertain
    parties: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    severity: Severity
    risk_score: float
    ranking_reasons: list[str] = Field(default_factory=list)
    needs_human: bool


class ActionPlan(BaseModel):
    recommended_action: str
    candidate_actions: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    rationale: str


class VerificationResult(BaseModel):
    approved: bool
    notes: list[str] = Field(default_factory=list)
    final_action: str
    final_needs_human: bool
    downgraded: bool = False


class ToolExecution(BaseModel):
    tool_name: str
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)


class StageRecord(BaseModel):
    stage: str
    role: str | None = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CaseReport(BaseModel):
    case_type: CaseType
    severity: Severity
    risk_score: float
    evidence_spans: list[EvidenceSpan]
    policy_refs: list[str]
    recommended_action: str
    needs_human: bool
    decision_rationale: str


class WorkflowState(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    case_input: CaseInput
    clarification_round: int = 0
    clarification_answers: list[str] = Field(default_factory=list)
    normalized_text: str = ""
    multimodal_findings: list[MultimodalFinding] = Field(default_factory=list)
    facts: FactBundle | None = None
    retrieval_plan: RetrievalPlan | None = None
    retrieved_docs: list[RetrievedDoc] = Field(default_factory=list)
    risk: RiskAssessment | None = None
    action_plan: ActionPlan | None = None
    tool_plan: ToolPlan | None = None
    verification: VerificationResult | None = None
    tool_executions: list[ToolExecution] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    status: RunStatus = RunStatus.evaluated
    report: CaseReport | None = None
    trace: list[StageRecord] = Field(default_factory=list)


class CaseEvaluationResponse(BaseModel):
    run_id: str
    status: RunStatus
    clarification_questions: list[str] = Field(default_factory=list)
    report: CaseReport | None = None
    trace: list[StageRecord] = Field(default_factory=list)
    tool_executions: list[ToolExecution] = Field(default_factory=list)


class StoredRun(BaseModel):
    run_id: str
    status: RunStatus
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime
