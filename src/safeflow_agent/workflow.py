from __future__ import annotations

from typing import Any

from .models import CaseReport, RunStatus, StageRecord, ToolExecution, WorkflowState
from .multimodal import MultimodalAnalyzer
from .reasoning import SafetyReasoner
from .tools import ToolRegistry

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover
    END = "__end__"
    StateGraph = None


class SafeFlowWorkflow:
    def __init__(
        self,
        reasoner: SafetyReasoner,
        tools: ToolRegistry,
        multimodal: MultimodalAnalyzer,
        max_clarification_rounds: int = 2,
    ) -> None:
        self.reasoner = reasoner
        self.tools = tools
        self.multimodal = multimodal
        self.max_clarification_rounds = max_clarification_rounds
        self._graph = self._build_graph()

    def run(self, state: WorkflowState) -> WorkflowState:
        if self._graph is not None:
            result = self._graph.invoke(state.model_dump(mode="json"))
            return WorkflowState.model_validate(result)
        return self._run_sequential(state)

    def execute(self, state: WorkflowState, dry_run: bool = True) -> WorkflowState:
        if state.report is None or state.verification is None:
            raise ValueError("必须先完成案件评估，才能执行动作")

        executions: list[ToolExecution] = []
        if state.tool_plan is not None and state.tool_plan.items:
            for item in state.tool_plan.items:
                execution = self._execute_planned_tool(
                    tool_name=item.tool_name,
                    case_id=state.run_id,
                    severity=state.report.severity,
                    summary=state.report.decision_rationale,
                    reason=item.reason,
                    args=item.args,
                    dry_run=dry_run,
                )
                if execution is not None:
                    executions.append(execution)
        else:
            summary = state.report.decision_rationale
            action = state.verification.final_action
            if action in {"notify_human_reviewer", "create_safety_ticket"} or state.report.needs_human:
                executions.append(
                    self.tools.create_safety_ticket(
                        case_id=state.run_id,
                        severity=state.report.severity,
                        summary=summary,
                        dry_run=dry_run,
                    )
                )
            if action == "notify_human_reviewer" or state.report.needs_human:
                executions.append(
                    self.tools.notify_human_reviewer(
                        case_id=state.run_id,
                        reason=summary,
                        dry_run=dry_run,
                    )
                )

        if not executions:
            executions.append(
                ToolExecution(
                    tool_name="no_op",
                    success=True,
                    details={"说明": "当前案件无需执行沙箱动作。", "是否沙箱": dry_run},
                )
            )

        state.tool_executions = executions
        state.status = RunStatus.executed if all(item.success for item in executions) else RunStatus.downgraded
        self._record(
            state,
            "execute_actions",
            "已完成沙箱安全动作执行。",
            {"dry_run": dry_run, "tools": [item.model_dump(mode="json") for item in executions]},
            role="executor",
        )
        return state

    def _run_sequential(self, state: WorkflowState) -> WorkflowState:
        state = self._normalize_input(state)
        state = self._parse_multimodal(state)
        state = self._extract_facts(state)
        state = self._clarify_gate(state)
        if state.status == RunStatus.awaiting_clarification:
            return state
        state = self._retrieve_knowledge(state)
        state = self._assess_risk(state)
        state = self._plan_actions(state)
        state = self._verify_plan(state)
        state = self._finalize_report(state)
        return state

    def _build_graph(self):  # type: ignore[no-untyped-def]
        if StateGraph is None:
            return None
        try:
            graph = StateGraph(dict)
            graph.add_node("intake_agent", self._normalize_node)
            graph.add_node("multimodal_agent", self._multimodal_node)
            graph.add_node("evidence_agent", self._extract_node)
            graph.add_node("clarification_agent", self._clarify_node)
            graph.add_node("retrieval_agent", self._retrieve_node)
            graph.add_node("planner_risk_agent", self._assess_node)
            graph.add_node("planner_action_agent", self._plan_node)
            graph.add_node("verifier_agent", self._verify_node)
            graph.add_node("report_agent", self._finalize_node)
            graph.set_entry_point("intake_agent")
            graph.add_edge("intake_agent", "multimodal_agent")
            graph.add_edge("multimodal_agent", "evidence_agent")
            graph.add_edge("evidence_agent", "clarification_agent")
            graph.add_conditional_edges(
                "clarification_agent",
                self._route_after_clarify,
                {"awaiting_clarification": END, "continue": "retrieval_agent"},
            )
            graph.add_edge("retrieval_agent", "planner_risk_agent")
            graph.add_edge("planner_risk_agent", "planner_action_agent")
            graph.add_edge("planner_action_agent", "verifier_agent")
            graph.add_edge("verifier_agent", "report_agent")
            graph.add_edge("report_agent", END)
            return graph.compile()
        except Exception:
            return None

    def _normalize_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._normalize_input(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _multimodal_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._parse_multimodal(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _extract_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._extract_facts(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _clarify_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._clarify_gate(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _retrieve_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._retrieve_knowledge(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _assess_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._assess_risk(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _plan_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._plan_actions(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _verify_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._verify_plan(WorkflowState.model_validate(payload)).model_dump(mode="json")

    def _finalize_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._finalize_report(WorkflowState.model_validate(payload)).model_dump(mode="json")

    @staticmethod
    def _route_after_clarify(payload: dict[str, Any]) -> str:
        status = payload.get("status")
        return "awaiting_clarification" if status == RunStatus.awaiting_clarification.value else "continue"

    def _normalize_input(self, state: WorkflowState) -> WorkflowState:
        order_context = self.tools.get_order_context(state.case_input.order_id)
        sections = [
            f"投诉内容：{state.case_input.complaint_text}",
            f"订单上下文：{self._format_order_context(order_context)}",
        ]
        if state.case_input.chat_messages:
            chat = " | ".join(f"{msg.speaker}: {msg.text}" for msg in state.case_input.chat_messages)
            sections.append(f"聊天记录：{chat}")
        if state.case_input.attachments:
            attachment_texts = []
            for attachment in state.case_input.attachments:
                if attachment.modality.value == "image" and attachment.ocr_text:
                    attachment_texts.append(f"OCR 文本：{attachment.ocr_text}")
                elif attachment.modality.value == "audio" and attachment.transcript:
                    attachment_texts.append(f"ASR 文本：{attachment.transcript}")
                elif attachment.content:
                    attachment_texts.append(attachment.content)
            if attachment_texts:
                sections.append("附件内容：" + " | ".join(attachment_texts))
        if state.clarification_answers:
            sections.append("补充说明：" + " | ".join(state.clarification_answers))
        state.normalized_text = "\n".join(sections)
        self._record(
            state,
            "normalize_input",
            "已合并投诉文本、订单上下文、聊天记录和 OCR/ASR 附件文本。",
            {"标准化文本预览": state.normalized_text[:240]},
            role="intake_agent",
        )
        return state

    def _parse_multimodal(self, state: WorkflowState) -> WorkflowState:
        if not state.case_input.attachments:
            return state
        if state.multimodal_findings:
            findings = state.multimodal_findings
            usable_findings = [item for item in findings if item.text]
            if usable_findings:
                state.normalized_text = "\n".join(
                    [
                        state.normalized_text,
                        "多模态解析结果：" + " | ".join(item.text for item in usable_findings),
                    ]
                )
            self._record(
                state,
                "parse_multimodal",
                "已复用已有附件解析结果，并继续后续研判。",
                {
                    "findings": [item.model_dump(mode="json") for item in findings],
                    "使用多模态增强": bool(usable_findings),
                },
                role="evidence_agent",
            )
            return state

        findings = self.multimodal.analyze_attachments(state.case_input.attachments)
        usable_findings = [item for item in findings if item.text]
        state.multimodal_findings = findings
        if usable_findings:
            state.normalized_text = "\n".join(
                [
                    state.normalized_text,
                    "多模态解析结果：" + " | ".join(item.text for item in usable_findings),
                ]
            )
        debug_items = self.multimodal.get_last_debug()
        payload: dict[str, Any] = {
            "findings": [item.model_dump(mode="json") for item in findings],
            "使用多模态增强": bool(usable_findings),
        }
        if debug_items:
            payload["llm_debug"] = debug_items[0]
            payload["llm_debug_items"] = debug_items
        self._record(
            state,
            "parse_multimodal",
            "已完成附件多模态解析，并将可用结果并入案件上下文。",
            payload,
            role="evidence_agent",
        )
        return state

    def _extract_facts(self, state: WorkflowState) -> WorkflowState:
        order_context = self.tools.get_order_context(state.case_input.order_id)
        state.facts = self.reasoner.extract_facts(state.normalized_text, order_context)
        self._record(
            state,
            "extract_facts",
            "已抽取证据片段、案件类型和待补充信息。",
            self._with_llm_debug(state.facts.model_dump(mode="json"), "extract_facts"),
            role="evidence_agent",
        )
        return state

    def _clarify_gate(self, state: WorkflowState) -> WorkflowState:
        assert state.facts is not None
        if state.facts.missing_information and state.clarification_round < self.max_clarification_rounds:
            state.clarification_questions = state.facts.clarification_questions
            state.status = RunStatus.awaiting_clarification
            self._record(
                state,
                "clarify_gate",
                "当前证据不足，进入补充说明环节。",
                {"questions": state.clarification_questions, "round": state.clarification_round},
                role="evidence_agent",
            )
            return state
        state.clarification_questions = []
        state.status = RunStatus.evaluated
        self._record(
            state,
            "clarify_gate",
            "补充说明门控已通过，或已达到追问轮次上限。",
            {"round": state.clarification_round, "missing_information": state.facts.missing_information},
            role="evidence_agent",
        )
        return state

    def _retrieve_knowledge(self, state: WorkflowState) -> WorkflowState:
        assert state.facts is not None
        order_context = self.tools.get_order_context(state.case_input.order_id)
        state.retrieval_plan = self.reasoner.build_retrieval_query(state.facts, order_context)
        state.retrieved_docs = self.tools.retrieve_policy(
            state.retrieval_plan.query,
            case_type=state.facts.case_type.value,
            top_k=self.tools.top_k_retrieval,
        )
        self._record(
            state,
            "retrieve_knowledge",
            "已检索相关 SOP 和合成历史案例，用于 grounding。",
            self._with_llm_debug(
                {
                    "retrieval_plan": state.retrieval_plan.model_dump(mode="json"),
                    "docs": [doc.model_dump(mode="json") for doc in state.retrieved_docs],
                },
                "build_retrieval_query",
            ),
            role="retrieval_agent",
        )
        return state

    def _assess_risk(self, state: WorkflowState) -> WorkflowState:
        assert state.facts is not None
        order_context = self.tools.get_order_context(state.case_input.order_id)
        state.risk = self.reasoner.assess_risk(state.facts, order_context)
        self._record(
            state,
            "assess_risk",
            "已完成风险等级、风险分数和人工介入需求评估。",
            self._with_llm_debug(state.risk.model_dump(mode="json"), "assess_risk"),
            role="planner_agent",
        )
        return state

    def _plan_actions(self, state: WorkflowState) -> WorkflowState:
        assert state.facts is not None
        assert state.risk is not None
        state.action_plan = self.reasoner.plan_actions(state.facts, state.risk, state.retrieved_docs)
        state.tool_plan = self.reasoner.build_tool_plan(state.facts, state.risk, state.action_plan)
        self._record(
            state,
            "plan_actions",
            "已完成候选动作排序，并给出推荐动作。",
            self._with_llm_debug(
                {
                    **state.action_plan.model_dump(mode="json"),
                    "tool_plan": state.tool_plan.model_dump(mode="json") if state.tool_plan else None,
                },
                "plan_actions",
            ),
            role="planner_agent",
        )
        return state

    def _verify_plan(self, state: WorkflowState) -> WorkflowState:
        assert state.facts is not None
        assert state.risk is not None
        assert state.action_plan is not None
        state.verification = self.reasoner.verify_decision(
            state.facts,
            state.risk,
            state.action_plan,
            state.retrieved_docs,
            state.clarification_round,
            self.max_clarification_rounds,
        )
        self._record(
            state,
            "verify_plan",
            "已完成 verifier 复核，检查策略支撑和降级条件。",
            self._with_llm_debug(state.verification.model_dump(mode="json"), "verify_decision"),
            role="verifier_agent",
        )
        return state

    def _finalize_report(self, state: WorkflowState) -> WorkflowState:
        assert state.facts is not None
        assert state.risk is not None
        assert state.action_plan is not None
        assert state.verification is not None
        status = RunStatus.downgraded if state.verification.downgraded else RunStatus.ready_for_execution
        rationale = " ".join(
            [
                f"案件类型判定为{self._case_type_label(state.facts.case_type.value)}。",
                f"风险分数为 {state.risk.risk_score}，风险等级为{self._severity_label(state.risk.severity.value)}。",
                f"推荐动作为{self._action_label(state.verification.final_action)}。",
                f"复核说明：{'；'.join(state.verification.notes)}",
            ]
        )
        state.report = CaseReport(
            case_type=state.facts.case_type,
            severity=state.risk.severity,
            risk_score=state.risk.risk_score,
            evidence_spans=state.facts.evidence_spans,
            policy_refs=state.action_plan.policy_refs,
            recommended_action=state.verification.final_action,
            needs_human=state.verification.final_needs_human,
            decision_rationale=rationale,
        )
        state.status = status
        self._record(
            state,
            "finalize_report",
            "已生成最终结构化报告。",
            state.report.model_dump(mode="json"),
            role="planner_agent",
        )
        return state

    @staticmethod
    def _record(state: WorkflowState, stage: str, summary: str, payload: dict[str, Any], role: str | None = None) -> None:
        state.trace.append(StageRecord(stage=stage, role=role, summary=summary, payload=payload))

    def _with_llm_debug(self, payload: dict[str, Any], task: str) -> dict[str, Any]:
        debug = self.reasoner.get_last_debug(task)
        if not debug:
            return payload
        return {**payload, "llm_debug": debug}

    def _execute_planned_tool(
        self,
        *,
        tool_name: str,
        case_id: str,
        severity,
        summary: str,
        reason: str,
        args: dict[str, Any],
        dry_run: bool,
    ) -> ToolExecution | None:
        if tool_name == "create_safety_ticket":
            return self.tools.create_safety_ticket(case_id=case_id, severity=severity, summary=summary, dry_run=dry_run)
        if tool_name == "notify_human_reviewer":
            return self.tools.notify_human_reviewer(case_id=case_id, reason=reason or summary, dry_run=dry_run)
        if tool_name == "preserve_evidence_snapshot":
            return self.tools.preserve_evidence_snapshot(case_id=case_id, summary=reason or summary, dry_run=dry_run)
        return None

    @staticmethod
    def _route_flag_label(flag: str) -> str:
        mapping = {
            "night_trip": "夜间行程",
            "route_deviation_detected": "检测到路线偏移",
            "multiple_post_trip_calls": "行程后多次联系",
            "road_closure": "道路封闭",
        }
        return mapping.get(flag, flag)

    def _format_order_context(self, order_context: dict[str, Any]) -> str:
        route_flags = [self._route_flag_label(str(flag)) for flag in order_context.get("route_flags", [])]
        return (
            f"上车点={order_context.get('pickup', '未知')}，"
            f"下车点={order_context.get('dropoff', '未知')}，"
            f"开始时间={order_context.get('start_time', '未知')}，"
            f"结束时间={order_context.get('end_time', '未知')}，"
            f"路线标记={route_flags or ['无']}，"
            f"司机既往投诉数={order_context.get('prior_driver_complaints', 0)}"
        )

    @staticmethod
    def _case_type_label(case_type: str) -> str:
        mapping = {
            "harassment": "骚扰",
            "threat": "威胁",
            "route_deviation": "偏航/绕路",
            "late_night_contact": "深夜联系",
            "fare_dispute": "费用纠纷",
            "fraud": "诈骗",
            "property_loss": "遗失物品",
            "suspicious_behavior": "可疑行为",
            "uncertain": "待确定",
        }
        return mapping.get(case_type, case_type)

    @staticmethod
    def _severity_label(severity: str) -> str:
        mapping = {"low": "低风险", "medium": "中风险", "high": "高风险"}
        return mapping.get(severity, severity)

    @staticmethod
    def _action_label(action: str) -> str:
        mapping = {
            "notify_human_reviewer": "转人工审核",
            "create_safety_ticket": "创建安全工单",
            "request_more_information": "请求补充信息",
            "route_to_customer_support": "转客服处理",
            "close_with_monitoring": "关闭并持续观察",
            "monitor_case": "持续观察",
            "preserve_evidence": "保留证据",
            "no_op": "无需动作",
        }
        return mapping.get(action, action)
