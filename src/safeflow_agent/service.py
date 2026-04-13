from __future__ import annotations

from .config import Settings, settings
from .multimodal import MultimodalAnalyzer
from .models import CaseEvaluationResponse, CaseInput, ClarificationRequest, ExecuteRequest, WorkflowState
from .reasoning import SafetyReasoner
from .retrieval import KnowledgeBase
from .seeds import sample_cases_for_demo
from .store import RunStore
from .tools import ToolRegistry
from .workflow import SafeFlowWorkflow


class SafeFlowService:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or settings
        self.settings.ensure_runtime_dirs()
        self.knowledge_base = KnowledgeBase(self.settings.chroma_dir)
        self.tools = ToolRegistry(self.knowledge_base, top_k_retrieval=self.settings.top_k_retrieval)
        self.reasoner = SafetyReasoner(
            model=self.settings.llm_model,
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
        )
        self.multimodal = MultimodalAnalyzer(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            vision_model=self.settings.vision_model,
            audio_model=self.settings.audio_model,
            fallback_model=self.settings.llm_model,
        )
        self.store = RunStore(self.settings.db_path)
        self.workflow = SafeFlowWorkflow(
            reasoner=self.reasoner,
            tools=self.tools,
            multimodal=self.multimodal,
            max_clarification_rounds=self.settings.max_clarification_rounds,
        )

    def evaluate_case(self, case_input: CaseInput) -> CaseEvaluationResponse:
        state = self.workflow.run(WorkflowState(case_input=case_input))
        self.store.save(state)
        return self._to_response(state)

    def clarify_case(self, request: ClarificationRequest) -> CaseEvaluationResponse:
        state = self.store.load(request.run_id)
        state.clarification_round += 1
        state.clarification_answers.extend(request.answers)
        state = self.workflow.run(state)
        self.store.save(state)
        return self._to_response(state)

    def execute_case(self, request: ExecuteRequest) -> CaseEvaluationResponse:
        state = self.store.load(request.run_id)
        state = self.workflow.execute(state, dry_run=request.dry_run)
        self.store.save(state)
        return self._to_response(state)

    def get_run(self, run_id: str) -> CaseEvaluationResponse:
        return self._to_response(self.store.load(run_id))

    def demo_cases(self) -> list[CaseInput]:
        return sample_cases_for_demo()

    @staticmethod
    def _to_response(state: WorkflowState) -> CaseEvaluationResponse:
        return CaseEvaluationResponse(
            run_id=state.run_id,
            status=state.status,
            clarification_questions=state.clarification_questions,
            report=state.report,
            trace=state.trace,
            tool_executions=state.tool_executions,
        )
