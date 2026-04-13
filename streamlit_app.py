from __future__ import annotations

import base64
import json

import streamlit as st

from safeflow_agent.models import Attachment, AttachmentModality, CaseInput, ClarificationRequest, ExecuteRequest
from safeflow_agent.service import SafeFlowService


STAGE_LABELS = {
    "normalize_input": {"zh": "输入标准化", "en": "Normalize Input"},
    "parse_multimodal": {"zh": "多模态解析", "en": "Parse Multimodal"},
    "extract_facts": {"zh": "事实抽取", "en": "Extract Facts"},
    "clarify_gate": {"zh": "澄清门控", "en": "Clarification Gate"},
    "retrieve_knowledge": {"zh": "知识检索", "en": "Retrieve Knowledge"},
    "assess_risk": {"zh": "风险评估", "en": "Assess Risk"},
    "plan_actions": {"zh": "动作规划", "en": "Plan Actions"},
    "verify_plan": {"zh": "二次校验", "en": "Verify Plan"},
    "finalize_report": {"zh": "结构化报告", "en": "Finalize Report"},
    "execute_actions": {"zh": "沙箱执行", "en": "Execute Sandbox Actions"},
}

STAGE_SEQUENCE = [
    "normalize_input",
    "parse_multimodal",
    "extract_facts",
    "clarify_gate",
    "retrieve_knowledge",
    "assess_risk",
    "plan_actions",
    "verify_plan",
    "finalize_report",
    "execute_actions",
]

STAGE_DESCRIPTIONS = {
    "normalize_input": {
        "zh": "统一投诉、聊天、订单上下文和附件文本",
        "en": "Merge complaint, chat, order context, and attachments",
    },
    "parse_multimodal": {
        "zh": "解析图片/音频附件，并将结果并入案件上下文",
        "en": "Parse image/audio inputs and fold them into the case context",
    },
    "extract_facts": {
        "zh": "识别案件类型、证据片段和缺失信息",
        "en": "Extract case type, evidence spans, and missing facts",
    },
    "clarify_gate": {
        "zh": "判断是否需要先补充说明",
        "en": "Decide whether clarification is needed",
    },
    "retrieve_knowledge": {
        "zh": "检索 SOP 和历史案例做 grounding",
        "en": "Retrieve SOPs and historical cases for grounding",
    },
    "assess_risk": {
        "zh": "结合事实和订单上下文评估风险",
        "en": "Assess risk from facts and order context",
    },
    "plan_actions": {
        "zh": "输出推荐动作和候选动作排序",
        "en": "Rank candidate actions and choose one",
    },
    "verify_plan": {
        "zh": "复核动作是否安全、是否需要降级",
        "en": "Verify safety and downgrade conditions",
    },
    "finalize_report": {
        "zh": "生成结构化结论与解释",
        "en": "Produce the final structured report",
    },
    "execute_actions": {
        "zh": "模拟工单和人工审核通知",
        "en": "Simulate ticketing and human review",
    },
}

STATUS_LABELS = {
    "awaiting_clarification": {"zh": "等待补充说明", "en": "Awaiting Clarification"},
    "evaluated": {"zh": "已评估", "en": "Evaluated"},
    "ready_for_execution": {"zh": "可执行", "en": "Ready for Execution"},
    "executed": {"zh": "已执行", "en": "Executed"},
    "downgraded": {"zh": "已降级", "en": "Downgraded"},
}

SEVERITY_LABELS = {
    "low": {"zh": "低风险", "en": "Low"},
    "medium": {"zh": "中风险", "en": "Medium"},
    "high": {"zh": "高风险", "en": "High"},
}

CASE_TYPE_LABELS = {
    "harassment": {"zh": "骚扰", "en": "Harassment"},
    "threat": {"zh": "威胁", "en": "Threat"},
    "route_deviation": {"zh": "偏航/绕路", "en": "Route Deviation"},
    "late_night_contact": {"zh": "深夜联系", "en": "Late-night Contact"},
    "fare_dispute": {"zh": "费用纠纷", "en": "Fare Dispute"},
    "fraud": {"zh": "诈骗", "en": "Fraud"},
    "property_loss": {"zh": "遗失物品", "en": "Property Loss"},
    "suspicious_behavior": {"zh": "可疑行为", "en": "Suspicious Behavior"},
    "uncertain": {"zh": "待确定", "en": "Uncertain"},
}

ACTION_LABELS = {
    "notify_human_reviewer": {"zh": "转人工审核", "en": "Notify Human Reviewer"},
    "create_safety_ticket": {"zh": "创建安全工单", "en": "Create Safety Ticket"},
    "request_more_information": {"zh": "请求补充信息", "en": "Request More Information"},
    "route_to_customer_support": {"zh": "转客服处理", "en": "Route to Customer Support"},
    "close_with_monitoring": {"zh": "关闭并持续观察", "en": "Close With Monitoring"},
    "monitor_case": {"zh": "持续观察", "en": "Monitor Case"},
    "preserve_evidence": {"zh": "保留证据", "en": "Preserve Evidence"},
    "no_op": {"zh": "无需动作", "en": "No Operation"},
}

ATTACHMENT_MODE_LABELS = {
    "none": {"zh": "不添加", "en": "None"},
    "image": {"zh": "OCR 文本", "en": "OCR Text"},
    "audio": {"zh": "ASR 文本", "en": "ASR Transcript"},
    "text": {"zh": "纯文本备注", "en": "Plain Text Note"},
}

DOC_TYPE_LABELS = {
    "policy": {"zh": "策略文档", "en": "Policy"},
    "historical_case": {"zh": "历史案例", "en": "Historical Case"},
    "unknown": {"zh": "未知类型", "en": "Unknown"},
}

LLM_MODE_LABELS = {
    "llm_success": {"zh": "LLM 成功返回", "en": "LLM Success"},
    "llm_fallback": {"zh": "LLM 回退到 Heuristic", "en": "LLM Fallback"},
    "heuristic_only": {"zh": "仅 Heuristic", "en": "Heuristic Only"},
}

TEXTS = {
    "zh": {
        "hero_title": "SafeFlow-Agent 演示台",
        "hero_subtitle": "面向网约车安全场景的多阶段研判与自动化处置 Agent Demo",
        "hero_caption": "中文默认展示，保留英文切换，可按步骤演示高风险、低风险与澄清追问三类场景。",
        "language_label": "界面语言",
        "runtime_label": "当前推理模式",
        "runtime_api": "LLM API 模式",
        "runtime_offline": "离线 Heuristic 模式",
        "sidebar_title": "演示控制台",
        "sample_label": "示例案件",
        "load_sample": "载入当前样例",
        "reset_run": "清空当前运行",
        "demo_order_title": "推荐演示顺序",
        "demo_order_body": "1. 先演示高风险样例 `ORD-1002`\n2. 再演示低风险样例 `ORD-1003`\n3. 再演示多模态样例 `ORD-1004`\n4. 最后演示澄清追问样例 `ORD-1001`",
        "input_title": "案件输入",
        "input_caption": "左侧负责输入和操作，右侧负责结论、证据与 workflow trace。",
        "order_id": "订单 ID",
        "complaint": "投诉文本",
        "chat": "聊天记录",
        "chat_help": "每行一条，格式示例：`passenger: 我有点害怕`",
        "attachment_mode": "附加证据类型",
        "attachment_text": "附加证据文本",
        "attachment_placeholder": "可选。你可以贴 OCR、ASR 或补充说明，用于展示多模态文本入口。",
        "attachment_file": "上传原始附件",
        "attachment_file_help": "图片会优先走视觉解析，音频会优先走转写；若同时填写文本，会作为 OCR/ASR fallback。",
        "evaluate": "开始评估",
        "clarify_title": "补充说明",
        "clarify_help": "当系统判断证据不足时，会先追问而不是直接下结论。",
        "clarify_input": "补充信息",
        "clarify_button": "提交补充信息",
        "execute_title": "沙箱执行",
        "execute_help": "只模拟创建安全工单和人工审核通知，不会产生真实业务影响。",
        "execute_button": "执行沙箱动作",
        "summary_title": "结果总览",
        "workflow_map_title": "工作流地图",
        "workflow_map_caption": "这里把后端 workflow 直接可视化，能一眼看出系统当前推进到哪一步、为什么停在这里。",
        "workflow_roles_title": "Agent 角色视图",
        "workflow_roles_caption": "虽然底层是一个受控 workflow，但可以把它理解成事实抽取、检索、决策和复核四个角色在接力工作。",
        "current_focus_title": "当前卡点",
        "focus_idle": "还没有开始运行。载入一个案例后，系统会沿着工作流逐步推进。",
        "focus_clarify": "系统已经完成基础事实抽取，但发现关键证据仍缺失，因此停在“补充说明”节点，等待用户补充后再继续检索和决策。",
        "focus_report": "系统已经完成事实抽取、检索、风险评估、动作规划和复核。当前你可以查看最终报告，或继续执行沙箱动作。",
        "focus_execute": "系统已经完成沙箱动作模拟，当前 run 已形成完整的“理解 -> 判断 -> 执行”闭环。",
        "focus_unknown": "系统正在推进工作流，请结合下方阶段地图和 trace 查看当前状态。",
        "role_fact_title": "事实抽取器",
        "role_retrieval_title": "检索器",
        "role_decision_title": "决策器",
        "role_verifier_title": "Verifier",
        "role_fact_empty": "等待输入",
        "role_retrieval_empty": "未启动",
        "role_decision_empty": "待判断",
        "role_verifier_empty": "待复核",
        "role_fact_caption_empty": "先把非结构化投诉转成案件类型、证据片段和待补充信息。",
        "role_retrieval_caption_empty": "只有在证据足够时，系统才会检索 SOP 和历史案例。",
        "role_decision_caption_empty": "风险评估和动作规划会在检索之后进行。",
        "role_verifier_caption_empty": "Verifier 会检查当前动作是否真的被证据和策略支撑。",
        "stage_done": "已完成",
        "stage_current": "当前节点",
        "stage_pending": "待执行",
        "empty_title": "等待一次评估",
        "empty_body": "先在左侧载入一个示例案件，点击“开始评估”，再从右侧查看风险结论、证据引用和多阶段 trace。",
        "summary_tab": "结论摘要",
        "evidence_tab": "证据与策略",
        "trace_tab": "流程明细",
        "raw_tab": "原始 JSON",
        "llm_tab": "LLM 调试",
        "status": "运行状态",
        "severity": "风险等级",
        "action": "推荐动作",
        "human": "人工介入",
        "risk_score": "风险分数",
        "case_type": "案件类型",
        "run_id": "运行 ID",
        "rationale": "决策说明",
        "evidence": "证据片段",
        "policy": "策略引用",
        "retrieved_docs": "检索到的文档",
        "tools": "沙箱执行结果",
        "multimodal": "多模态解析",
        "missing_info": "待补充信息",
        "clarification_questions": "系统追问",
        "no_evidence": "暂无证据片段",
        "no_policy": "暂无策略引用",
        "no_tools": "尚未执行沙箱动作",
        "no_multimodal": "当前没有多模态解析结果",
        "no_missing": "当前没有待补充信息",
        "no_questions": "当前没有追问",
        "waiting_retrieval": "当前处于补充说明阶段：系统已经完成事实抽取，但尚未进入知识检索和策略引用阶段。",
        "waiting_policy_refs": "当前尚未进入动作规划阶段，因此还没有策略引用。",
        "workflow_progress": "当前已记录 {done}/{total} 个阶段",
        "llm_usage_summary": "本次涉及 {total} 个推理阶段，其中 LLM 成功 {success} 个，回退 {fallback} 个，仅 heuristic {heuristic} 个。",
        "llm_debug_title": "大模型使用明细",
        "llm_debug_caption": "这里用于展示每个推理阶段到底是直接走了 LLM，还是回退到 heuristic，以及对应的 prompt 和返回预览。",
        "llm_stage_count": "推理阶段数",
        "llm_success_count": "LLM 成功",
        "llm_fallback_count": "LLM 回退",
        "llm_heuristic_count": "仅 Heuristic",
        "llm_mode": "实际方式",
        "llm_model": "模型",
        "llm_client": "客户端",
        "llm_system_prompt": "System Prompt",
        "llm_user_payload": "User Payload",
        "llm_raw_response": "模型原始回复",
        "llm_parsed_response": "解析后的结构化结果",
        "llm_error": "回退原因 / 调试信息",
        "no_llm_debug": "当前 run 还没有 LLM 调试信息。请先开始一次评估。",
        "llm_stage_selector": "选择要查看的推理阶段",
        "llm_stage_list": "阶段概览",
        "llm_detail_tab": "阶段详情",
        "llm_prompt_tab": "Prompt",
        "llm_response_tab": "Response",
        "llm_selected_stage": "当前查看阶段",
        "yes": "需要",
        "no": "不需要",
        "loaded_notice": "已载入示例案件。",
        "evaluated_notice": "案件已完成评估。",
        "clarified_notice": "已提交补充说明并重新评估。",
        "executed_notice": "已完成沙箱动作模拟。",
        "raw_caption": "这里保留完整 JSON，方便你在演示时按需下钻。",
        "high_risk_card": "高风险案件应展示证据、策略引用和人工介入决策。",
        "low_risk_card": "低风险案件应体现系统不会把所有投诉都升级处理。",
        "clarify_card": "证据不足时先追问，是这个 workflow 的关键差异点。",
        "multimodal_card": "图片或音频附件会先经过多模态解析，再并入决策链。",
        "tag_workflow": "工作流",
        "tag_rag": "检索增强",
        "tag_verifier": "复核校验",
        "tag_sandbox": "沙箱执行",
        "high_risk_demo": "高风险演示",
        "low_risk_demo": "低风险演示",
        "multimodal_demo": "多模态演示",
        "clarify_demo": "澄清追问",
        "doc_score": "相关分数",
    },
    "en": {
        "hero_title": "SafeFlow-Agent Demo Console",
        "hero_subtitle": "A multi-stage safety triage and automation agent for ride-hailing incidents",
        "hero_caption": "Chinese-first presentation with an English switch. Best for interviews when walking through high-risk, low-risk, and clarification scenarios.",
        "language_label": "Language",
        "runtime_label": "Runtime Mode",
        "runtime_api": "LLM API Mode",
        "runtime_offline": "Offline Heuristic Mode",
        "sidebar_title": "Demo Controls",
        "sample_label": "Demo Case",
        "load_sample": "Load Selected Case",
        "reset_run": "Clear Current Run",
        "demo_order_title": "Suggested Demo Flow",
        "demo_order_body": "1. Start with high-risk case `ORD-1002`\n2. Then show low-risk case `ORD-1003`\n3. Then show multimodal case `ORD-1004`\n4. Finish with clarification case `ORD-1001`",
        "input_title": "Case Input",
        "input_caption": "Use the left side for input and actions, and the right side for decision summaries, evidence, and workflow trace.",
        "order_id": "Order ID",
        "complaint": "Complaint Text",
        "chat": "Chat Messages",
        "chat_help": "One message per line. Example: `passenger: I felt unsafe`",
        "attachment_mode": "Additional Evidence Type",
        "attachment_text": "Additional Evidence Text",
        "attachment_placeholder": "Optional. Paste OCR text, ASR transcript, or an extra note to demonstrate multimodal text input.",
        "attachment_file": "Upload Attachment",
        "attachment_file_help": "Images try vision parsing first, audio tries transcription first; text still works as OCR/ASR fallback.",
        "evaluate": "Evaluate Case",
        "clarify_title": "Clarification",
        "clarify_help": "When evidence is insufficient, the system asks follow-up questions instead of jumping to a final decision.",
        "clarify_input": "Clarification Answer",
        "clarify_button": "Submit Clarification",
        "execute_title": "Sandbox Execution",
        "execute_help": "This only simulates ticket creation and human-review notifications. It never touches real business systems.",
        "execute_button": "Run Sandbox Action",
        "summary_title": "Result Overview",
        "workflow_map_title": "Workflow Map",
        "workflow_map_caption": "This makes the backend workflow visible, so you can see exactly where the run is and why it pauses there.",
        "workflow_roles_title": "Agent Role View",
        "workflow_roles_caption": "The backend is a controlled workflow, but you can understand it through four relay roles: fact extraction, retrieval, decision, and verification.",
        "current_focus_title": "Current Focus",
        "focus_idle": "No run yet. Load a case and the workflow will move step by step.",
        "focus_clarify": "The system has already extracted basic facts, but key information is still missing, so it pauses at clarification before retrieval and final decision-making.",
        "focus_report": "Fact extraction, retrieval, risk assessment, action planning, and verification are done. You can now inspect the report or run sandbox execution.",
        "focus_execute": "Sandbox execution has completed. This run now demonstrates the full loop from understanding to decision to execution.",
        "focus_unknown": "The workflow is in progress. Use the stage map and trace below to inspect the current state.",
        "role_fact_title": "Fact Extractor",
        "role_retrieval_title": "Retriever",
        "role_decision_title": "Decision Agent",
        "role_verifier_title": "Verifier",
        "role_fact_empty": "Waiting",
        "role_retrieval_empty": "Not started",
        "role_decision_empty": "Pending",
        "role_verifier_empty": "Pending",
        "role_fact_caption_empty": "Turn unstructured complaints into case type, evidence spans, and missing facts.",
        "role_retrieval_caption_empty": "Retrieval only starts after evidence is considered sufficient.",
        "role_decision_caption_empty": "Risk assessment and action planning happen after retrieval.",
        "role_verifier_caption_empty": "The verifier checks whether the recommended action is really supported by evidence and policy.",
        "stage_done": "Done",
        "stage_current": "Current",
        "stage_pending": "Pending",
        "empty_title": "No Run Yet",
        "empty_body": "Load a demo case on the left, click Evaluate Case, and then inspect the risk conclusion, evidence grounding, and multi-stage trace on the right.",
        "summary_tab": "Summary",
        "evidence_tab": "Evidence & Policy",
        "trace_tab": "Workflow Trace",
        "raw_tab": "Raw JSON",
        "llm_tab": "LLM Debug",
        "status": "Status",
        "severity": "Severity",
        "action": "Recommended Action",
        "human": "Human Review",
        "risk_score": "Risk Score",
        "case_type": "Case Type",
        "run_id": "Run ID",
        "rationale": "Decision Rationale",
        "evidence": "Evidence Spans",
        "policy": "Policy References",
        "retrieved_docs": "Retrieved Documents",
        "tools": "Sandbox Execution Results",
        "multimodal": "Multimodal Findings",
        "missing_info": "Missing Information",
        "clarification_questions": "Clarification Questions",
        "no_evidence": "No evidence spans yet",
        "no_policy": "No policy references yet",
        "no_tools": "No sandbox actions executed yet",
        "no_multimodal": "No multimodal findings in this run",
        "no_missing": "No missing information at the moment",
        "no_questions": "No clarification questions at the moment",
        "waiting_retrieval": "The run is currently waiting for clarification. Facts have been extracted, but retrieval and policy grounding have not started yet.",
        "waiting_policy_refs": "The run has not entered action planning yet, so there are no policy references at this stage.",
        "workflow_progress": "{done}/{total} workflow stages recorded",
        "llm_usage_summary": "This run touched {total} reasoning stages: {success} LLM success, {fallback} fallback, and {heuristic} heuristic-only.",
        "llm_debug_title": "LLM Usage Details",
        "llm_debug_caption": "This panel shows whether each reasoning stage actually used the LLM, fell back to heuristics, and what prompt/response preview was involved.",
        "llm_stage_count": "Reasoning Stages",
        "llm_success_count": "LLM Success",
        "llm_fallback_count": "LLM Fallback",
        "llm_heuristic_count": "Heuristic Only",
        "llm_mode": "Execution Mode",
        "llm_model": "Model",
        "llm_client": "Client",
        "llm_system_prompt": "System Prompt",
        "llm_user_payload": "User Payload",
        "llm_raw_response": "Raw Model Response",
        "llm_parsed_response": "Parsed Structured Result",
        "llm_error": "Fallback Reason / Debug Info",
        "no_llm_debug": "No LLM debug information yet. Start an evaluation run first.",
        "llm_stage_selector": "Select a reasoning stage",
        "llm_stage_list": "Stage Overview",
        "llm_detail_tab": "Stage Detail",
        "llm_prompt_tab": "Prompt",
        "llm_response_tab": "Response",
        "llm_selected_stage": "Selected Stage",
        "yes": "Required",
        "no": "Not Required",
        "loaded_notice": "Demo case loaded.",
        "evaluated_notice": "Case evaluation completed.",
        "clarified_notice": "Clarification submitted and the case was re-evaluated.",
        "executed_notice": "Sandbox action completed.",
        "raw_caption": "The full JSON response is kept here for deeper walkthroughs when needed.",
        "high_risk_card": "A strong demo shows evidence grounding, policy references, and human escalation.",
        "low_risk_card": "A good low-risk demo proves the system does not over-escalate every complaint.",
        "clarify_card": "The clarification loop is the key difference from a single-turn classifier.",
        "multimodal_card": "Image or audio attachments are parsed before the case enters the decision chain.",
        "tag_workflow": "Workflow",
        "tag_rag": "RAG",
        "tag_verifier": "Verifier",
        "tag_sandbox": "Sandbox",
        "high_risk_demo": "High-risk Demo",
        "low_risk_demo": "Low-risk Demo",
        "multimodal_demo": "Multimodal Demo",
        "clarify_demo": "Clarify Loop",
        "doc_score": "Score",
    },
}

SAMPLE_META = {
    "ORD-1002": {
        "zh": "高风险：偏航与害怕",
        "en": "High risk: route deviation and passenger fear",
    },
    "ORD-1003": {
        "zh": "低风险：费用纠纷",
        "en": "Low risk: fare dispute",
    },
    "ORD-1001": {
        "zh": "澄清追问：信息不足",
        "en": "Clarification: insufficient detail",
    },
    "ORD-1004": {
        "zh": "多模态：音频线索",
        "en": "Multimodal: audio clue",
    },
}

CSS = """
<style>
html, body, [class*="css"] {
    font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
}
.stApp {
    background:
        radial-gradient(circle at top left, rgba(244, 192, 117, 0.22), transparent 24%),
        radial-gradient(circle at top right, rgba(145, 42, 29, 0.10), transparent 22%),
        linear-gradient(180deg, #f7f0e8 0%, #f4efe7 42%, #f0ece6 100%);
}
.sf-hero {
    padding: 1.4rem 1.6rem;
    border-radius: 24px;
    background: linear-gradient(135deg, #73291c 0%, #b85826 58%, #d38743 100%);
    color: #fffaf2;
    box-shadow: 0 18px 40px rgba(97, 39, 23, 0.18);
    margin-bottom: 1rem;
}
.sf-hero h1 {
    margin: 0 0 0.35rem 0;
    font-size: 2rem;
    font-weight: 800;
}
.sf-hero p {
    margin: 0.2rem 0;
    line-height: 1.6;
}
.sf-tag-row {
    margin-top: 0.9rem;
}
.sf-badge {
    display: inline-block;
    padding: 0.28rem 0.72rem;
    margin-right: 0.45rem;
    margin-bottom: 0.35rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
}
.sf-badge.warm {
    background: rgba(255, 243, 228, 0.22);
    color: #fff6ec;
    border: 1px solid rgba(255, 245, 232, 0.24);
}
.sf-card {
    min-height: 118px;
    padding: 1rem 1.05rem;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid rgba(133, 86, 58, 0.12);
    box-shadow: 0 8px 24px rgba(69, 49, 32, 0.08);
}
.sf-card-title {
    color: #80563a;
    font-size: 0.92rem;
    font-weight: 700;
}
.sf-card-value {
    margin-top: 0.45rem;
    color: #2a211b;
    font-size: 1.28rem;
    font-weight: 800;
}
.sf-card-caption {
    margin-top: 0.45rem;
    color: #6c6157;
    font-size: 0.85rem;
    line-height: 1.5;
}
.sf-panel {
    padding: 1rem 1.05rem;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.83);
    border: 1px solid rgba(133, 86, 58, 0.10);
    box-shadow: 0 8px 24px rgba(69, 49, 32, 0.06);
}
.sf-list {
    margin: 0.2rem 0 0 0;
    padding-left: 1.1rem;
}
.sf-doc {
    padding: 0.9rem 1rem;
    border-radius: 16px;
    background: rgba(247, 242, 236, 0.95);
    border: 1px solid rgba(144, 110, 72, 0.12);
    margin-bottom: 0.8rem;
}
.sf-doc-title {
    color: #4d3325;
    font-weight: 800;
    margin-bottom: 0.28rem;
}
.sf-stage-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 0.72rem;
    margin: 0.85rem 0 1rem 0;
}
.sf-stage-card {
    padding: 0.9rem 0.95rem;
    border-radius: 18px;
    border: 1px solid rgba(133, 86, 58, 0.10);
    background: rgba(255, 255, 255, 0.78);
    box-shadow: 0 8px 24px rgba(69, 49, 32, 0.05);
}
.sf-stage-card.done {
    background: rgba(239, 247, 238, 0.98);
    border-color: rgba(68, 128, 77, 0.18);
}
.sf-stage-card.current {
    background: linear-gradient(135deg, rgba(255, 245, 230, 0.98), rgba(255, 237, 213, 0.98));
    border-color: rgba(183, 101, 38, 0.24);
    box-shadow: 0 14px 32px rgba(165, 92, 36, 0.12);
}
.sf-stage-card.pending {
    opacity: 0.85;
}
.sf-stage-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.5rem;
}
.sf-stage-num {
    color: #9a6a4c;
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.02em;
}
.sf-stage-badge {
    border-radius: 999px;
    padding: 0.18rem 0.55rem;
    font-size: 0.73rem;
    font-weight: 700;
}
.sf-stage-badge.done {
    background: rgba(68, 128, 77, 0.12);
    color: #386743;
}
.sf-stage-badge.current {
    background: rgba(183, 101, 38, 0.16);
    color: #8a4d22;
}
.sf-stage-badge.pending {
    background: rgba(120, 105, 94, 0.10);
    color: #6e6259;
}
.sf-stage-title {
    color: #342720;
    font-size: 1rem;
    font-weight: 800;
    margin-bottom: 0.3rem;
}
.sf-stage-desc {
    color: #6c6157;
    font-size: 0.84rem;
    line-height: 1.5;
}
.sf-focus-box {
    padding: 0.95rem 1rem;
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(255, 248, 239, 0.98), rgba(249, 241, 232, 0.98));
    border: 1px solid rgba(183, 101, 38, 0.13);
    color: #533a2a;
    line-height: 1.65;
    margin-bottom: 1rem;
}
.sf-mini {
    color: #766a61;
    font-size: 0.84rem;
}
div[data-testid="stExpander"] {
    border: 1px solid rgba(133, 86, 58, 0.10);
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.76);
}
div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(255, 247, 238, 0.98), rgba(246, 239, 231, 0.98));
}
</style>
"""


def t(lang: str, key: str) -> str:
    return TEXTS[lang][key]


def pick_label(mapping: dict[str, dict[str, str]], key: str, lang: str) -> str:
    return mapping.get(key, {}).get(lang, key)


def parse_chat(blob: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in blob.splitlines():
        raw = line.strip()
        if not raw:
            continue
        if "：" in raw and ":" not in raw:
            speaker, text = raw.split("：", 1)
        elif ":" in raw:
            speaker, text = raw.split(":", 1)
        else:
            continue
        rows.append({"speaker": speaker.strip(), "text": text.strip()})
    return rows


def build_attachments(mode: str, text: str, uploaded_file) -> list[Attachment]:
    payload = text.strip()
    if mode == "none":
        return []
    media_base64 = None
    mime_type = None
    file_name = None
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        if file_bytes:
            media_base64 = base64.b64encode(file_bytes).decode("utf-8")
            mime_type = getattr(uploaded_file, "type", None)
            file_name = getattr(uploaded_file, "name", None)
    if not payload and not media_base64:
        return []
    if mode == "image":
        return [
            Attachment(
                modality=AttachmentModality.image,
                ocr_text=payload or None,
                mime_type=mime_type,
                file_name=file_name,
                media_base64=media_base64,
            )
        ]
    if mode == "audio":
        return [
            Attachment(
                modality=AttachmentModality.audio,
                transcript=payload or None,
                mime_type=mime_type,
                file_name=file_name,
                media_base64=media_base64,
            )
        ]
    if payload or media_base64:
        return [
            Attachment(
                modality=AttachmentModality.text,
                content=payload or None,
                mime_type=mime_type,
                file_name=file_name,
                media_base64=media_base64,
            )
        ]
    return []


def demo_label(case: CaseInput, lang: str) -> str:
    scenario = SAMPLE_META.get(case.order_id, {}).get(lang, case.complaint_text[:28])
    return f"{case.order_id} | {scenario}"


def load_demo_case(case: CaseInput) -> None:
    st.session_state.form_order_id = case.order_id
    st.session_state.form_complaint = case.complaint_text
    st.session_state.form_chat = "\n".join(f"{msg.speaker}: {msg.text}" for msg in case.chat_messages)
    if case.attachments:
        first = case.attachments[0]
        st.session_state.form_attachment_mode = first.modality.value
        st.session_state.form_attachment_text = first.ocr_text or first.transcript or first.content or ""
    else:
        st.session_state.form_attachment_mode = "none"
        st.session_state.form_attachment_text = ""
    st.session_state.form_clarification = "司机在结束后半夜一直给我打电话，还说想单独见面。"
    st.session_state.run_id = None


def ensure_state(demo_cases: list[CaseInput]) -> None:
    if "run_id" not in st.session_state:
        st.session_state.run_id = None
    if "notice" not in st.session_state:
        st.session_state.notice = None
    if "selected_sample_idx" not in st.session_state:
        st.session_state.selected_sample_idx = 0
    if "form_order_id" not in st.session_state:
        load_demo_case(demo_cases[0])


def get_trace_payload(run, stage: str) -> dict:
    for record in run.trace:
        if record.stage == stage:
            return record.payload
    return {}


def render_stat_card(title: str, value: str, caption: str = "") -> None:
    caption_html = f'<div class="sf-card-caption">{caption}</div>' if caption else ""
    st.markdown(
        f"""
        <div class="sf-card">
            <div class="sf-card-title">{title}</div>
            <div class="sf-card-value">{value}</div>
            {caption_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_list(items: list[str], empty_text: str) -> None:
    if not items:
        st.caption(empty_text)
        return
    st.markdown(
        "<ul class='sf-list'>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>",
        unsafe_allow_html=True,
    )


def unique_trace_stages(run) -> list[str]:
    stages: list[str] = []
    seen: set[str] = set()
    for record in run.trace:
        if record.stage not in seen:
            stages.append(record.stage)
            seen.add(record.stage)
    return stages


def get_current_stage(run) -> str | None:
    if run is None:
        return None
    if run.tool_executions:
        return "execute_actions"
    if run.status.value == "awaiting_clarification":
        return "clarify_gate"
    if run.report is not None:
        return "finalize_report"
    stages = unique_trace_stages(run)
    return stages[-1] if stages else None


def get_completed_stages(run, current_stage: str | None) -> set[str]:
    if run is None:
        return set()
    completed = set(unique_trace_stages(run))
    if current_stage in completed:
        completed.remove(current_stage)
    return completed


def render_workflow_map(run, lang: str) -> None:
    current_stage = get_current_stage(run)
    completed = get_completed_stages(run, current_stage)
    cards: list[str] = []
    for index, stage in enumerate(STAGE_SEQUENCE, start=1):
        if stage == current_stage:
            state_key = "current"
        elif stage in completed:
            state_key = "done"
        else:
            state_key = "pending"
        cards.append(
            (
                f'<div class="sf-stage-card {state_key}">'
                f'<div class="sf-stage-top">'
                f'<div class="sf-stage-num">STEP {index:02d}</div>'
                f'<div class="sf-stage-badge {state_key}">{t(lang, f"stage_{state_key}")}</div>'
                f"</div>"
                f'<div class="sf-stage-title">{pick_label(STAGE_LABELS, stage, lang)}</div>'
                f'<div class="sf-stage-desc">{pick_label(STAGE_DESCRIPTIONS, stage, lang)}</div>'
                f"</div>"
            )
        )
    st.markdown(f"<div class='sf-stage-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def build_focus_text(run, lang: str) -> str:
    if run is None:
        return t(lang, "focus_idle")
    if run.tool_executions:
        return t(lang, "focus_execute")
    if run.status.value == "awaiting_clarification":
        return t(lang, "focus_clarify")
    if run.report is not None:
        return t(lang, "focus_report")
    return t(lang, "focus_unknown")


def build_role_cards(run, lang: str) -> list[tuple[str, str, str]]:
    if run is None:
        return [
            (t(lang, "role_fact_title"), t(lang, "role_fact_empty"), t(lang, "role_fact_caption_empty")),
            (t(lang, "role_retrieval_title"), t(lang, "role_retrieval_empty"), t(lang, "role_retrieval_caption_empty")),
            (t(lang, "role_decision_title"), t(lang, "role_decision_empty"), t(lang, "role_decision_caption_empty")),
            (t(lang, "role_verifier_title"), t(lang, "role_verifier_empty"), t(lang, "role_verifier_caption_empty")),
        ]

    extract_payload = get_trace_payload(run, "extract_facts")
    retrieve_payload = get_trace_payload(run, "retrieve_knowledge")
    assess_payload = get_trace_payload(run, "assess_risk")
    plan_payload = get_trace_payload(run, "plan_actions")
    verify_payload = get_trace_payload(run, "verify_plan")

    evidence_count = len(extract_payload.get("evidence_spans", []))
    case_type = pick_label(CASE_TYPE_LABELS, str(extract_payload.get("case_type", "uncertain")), lang)
    missing = [str(item) for item in extract_payload.get("missing_information", [])]
    if lang == "zh":
        fact_caption = f"案件类型：{case_type}；待补充：{'、'.join(missing) if missing else '无'}"
    else:
        fact_caption = f"Case type: {case_type}; Missing: {', '.join(missing) if missing else 'None'}"

    docs = retrieve_payload.get("docs", [])
    if docs:
        retrieval_value = f"{len(docs)} {'份文档' if lang == 'zh' else 'docs'}"
        retrieval_caption = "、".join(str(doc.get("title", "")) for doc in docs[:2]) if lang == "zh" else ", ".join(
            str(doc.get("title", "")) for doc in docs[:2]
        )
    elif run.status.value == "awaiting_clarification":
        retrieval_value = t(lang, "role_retrieval_empty")
        retrieval_caption = t(lang, "waiting_retrieval")
    else:
        retrieval_value = t(lang, "role_retrieval_empty")
        retrieval_caption = t(lang, "role_retrieval_caption_empty")

    if assess_payload or plan_payload or run.report:
        severity_key = str(assess_payload.get("severity", run.report.severity.value if run.report else "low"))
        severity_value = pick_label(SEVERITY_LABELS, severity_key, lang)
        action_key = str(plan_payload.get("recommended_action", run.report.recommended_action if run.report else "no_op"))
        action_value = pick_label(ACTION_LABELS, action_key, lang)
        decision_caption = f"推荐动作：{action_value}" if lang == "zh" else f"Recommended action: {action_value}"
    else:
        severity_value = t(lang, "role_decision_empty")
        decision_caption = t(lang, "role_decision_caption_empty")

    if verify_payload:
        verifier_value = t(lang, "stage_done") if verify_payload.get("approved", False) else pick_label(
            STATUS_LABELS, run.status.value, lang
        )
        notes = [str(item) for item in verify_payload.get("notes", [])]
        verifier_caption = "；".join(notes[:2]) if lang == "zh" else "; ".join(notes[:2])
    else:
        verifier_value = t(lang, "role_verifier_empty")
        verifier_caption = t(lang, "role_verifier_caption_empty")

    return [
        (t(lang, "role_fact_title"), f"{evidence_count} {'条证据' if lang == 'zh' else 'evidence spans'}", fact_caption),
        (t(lang, "role_retrieval_title"), retrieval_value, retrieval_caption),
        (t(lang, "role_decision_title"), severity_value, decision_caption),
        (t(lang, "role_verifier_title"), verifier_value, verifier_caption),
    ]


def get_llm_debug_entries(run) -> list[dict[str, object]]:
    if run is None:
        return []
    entries: list[dict[str, object]] = []
    for record in run.trace:
        debug = record.payload.get("llm_debug")
        if isinstance(debug, dict):
            entries.append({"stage": record.stage, "summary": record.summary, "debug": debug})
    return entries


def llm_usage_counts(entries: list[dict[str, object]]) -> dict[str, int]:
    counts = {"llm_success": 0, "llm_fallback": 0, "heuristic_only": 0}
    for entry in entries:
        debug = entry.get("debug", {})
        if isinstance(debug, dict):
            mode = str(debug.get("mode", "heuristic_only"))
            if mode in counts:
                counts[mode] += 1
    return counts


def llm_stage_option_label(entry: dict[str, object], lang: str) -> str:
    stage = str(entry.get("stage", "unknown"))
    debug = entry.get("debug", {})
    mode = str(debug.get("mode", "heuristic_only")) if isinstance(debug, dict) else "heuristic_only"
    return f"{pick_label(STAGE_LABELS, stage, lang)} | {pick_label(LLM_MODE_LABELS, mode, lang)}"


st.set_page_config(page_title="SafeFlow-Agent Demo", layout="wide", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def get_service() -> SafeFlowService:
    return SafeFlowService()


service = get_service()
demo_cases = service.demo_cases()
ensure_state(demo_cases)

language_choice = st.sidebar.radio("Language / 语言", ["简体中文", "English"], index=0)
lang = "zh" if language_choice == "简体中文" else "en"

runtime_mode = t(lang, "runtime_api") if service.settings.has_openai else t(lang, "runtime_offline")

st.markdown(
    f"""
    <div class="sf-hero">
        <h1>{t(lang, "hero_title")}</h1>
        <p><strong>{t(lang, "hero_subtitle")}</strong></p>
        <p>{t(lang, "hero_caption")}</p>
        <div class="sf-tag-row">
            <span class="sf-badge warm">{t(lang, "tag_workflow")}</span>
            <span class="sf-badge warm">{t(lang, "tag_rag")}</span>
            <span class="sf-badge warm">{t(lang, "tag_verifier")}</span>
            <span class="sf-badge warm">{t(lang, "tag_sandbox")}</span>
            <span class="sf-badge warm">{runtime_mode}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.notice:
    level, message = st.session_state.notice
    if level == "success":
        st.success(message)
    elif level == "info":
        st.info(message)
    else:
        st.warning(message)

st.sidebar.subheader(t(lang, "sidebar_title"))
st.sidebar.caption(f"{t(lang, 'runtime_label')}: {runtime_mode}")

selected_idx = st.sidebar.selectbox(
    t(lang, "sample_label"),
    options=range(len(demo_cases)),
    key="selected_sample_idx",
    format_func=lambda idx: demo_label(demo_cases[idx], lang),
)

sidebar_left, sidebar_right = st.sidebar.columns(2)
if sidebar_left.button(t(lang, "load_sample"), use_container_width=True):
    load_demo_case(demo_cases[selected_idx])
    st.session_state.notice = ("info", t(lang, "loaded_notice"))
if sidebar_right.button(t(lang, "reset_run"), use_container_width=True):
    st.session_state.run_id = None
    st.session_state.notice = None

st.sidebar.markdown(f"### {t(lang, 'demo_order_title')}")
st.sidebar.markdown(t(lang, "demo_order_body"))

left, right = st.columns([1.02, 1.18], gap="large")

run = service.get_run(st.session_state.run_id) if st.session_state.run_id else None

with left:
    st.subheader(t(lang, "input_title"))
    st.caption(t(lang, "input_caption"))
    st.text_input(t(lang, "order_id"), key="form_order_id")
    st.text_area(t(lang, "complaint"), key="form_complaint", height=150)
    st.text_area(t(lang, "chat"), key="form_chat", height=130, help=t(lang, "chat_help"))
    st.selectbox(
        t(lang, "attachment_mode"),
        options=["none", "image", "audio", "text"],
        key="form_attachment_mode",
        format_func=lambda mode: pick_label(ATTACHMENT_MODE_LABELS, mode, lang),
    )
    uploaded_attachment = None
    if st.session_state.form_attachment_mode in {"image", "audio"}:
        upload_types = ["png", "jpg", "jpeg", "webp"] if st.session_state.form_attachment_mode == "image" else ["mp3", "wav", "m4a", "ogg"]
        uploaded_attachment = st.file_uploader(
            t(lang, "attachment_file"),
            type=upload_types,
            key=f"attachment_upload_{st.session_state.form_attachment_mode}",
            help=t(lang, "attachment_file_help"),
        )
    st.text_area(
        t(lang, "attachment_text"),
        key="form_attachment_text",
        height=90,
        placeholder=t(lang, "attachment_placeholder"),
    )

    if st.button(t(lang, "evaluate"), type="primary", use_container_width=True):
        run = service.evaluate_case(
            CaseInput.model_validate(
                {
                    "order_id": st.session_state.form_order_id,
                    "complaint_text": st.session_state.form_complaint,
                    "chat_messages": parse_chat(st.session_state.form_chat),
                    "attachments": [
                        item.model_dump(mode="json")
                        for item in build_attachments(
                            st.session_state.form_attachment_mode,
                            st.session_state.form_attachment_text,
                            uploaded_attachment,
                        )
                    ],
                }
            )
        )
        st.session_state.run_id = run.run_id
        st.session_state.notice = ("success", t(lang, "evaluated_notice"))

    if run and run.status.value == "awaiting_clarification":
        st.markdown("---")
        st.subheader(t(lang, "clarify_title"))
        st.caption(t(lang, "clarify_help"))
        clarification_payload = get_trace_payload(run, "clarify_gate")
        questions = clarification_payload.get("questions", run.clarification_questions)
        render_list([str(item) for item in questions], t(lang, "no_questions"))
        st.text_area(t(lang, "clarify_input"), key="form_clarification", height=100)
        if st.button(t(lang, "clarify_button"), use_container_width=True):
            run = service.clarify_case(
                ClarificationRequest(
                    run_id=run.run_id,
                    answers=[line.strip() for line in st.session_state.form_clarification.splitlines() if line.strip()],
                )
            )
            st.session_state.run_id = run.run_id
            st.session_state.notice = ("success", t(lang, "clarified_notice"))

    if run and run.report:
        st.markdown("---")
        st.subheader(t(lang, "execute_title"))
        st.caption(t(lang, "execute_help"))
        if st.button(t(lang, "execute_button"), use_container_width=True):
            run = service.execute_case(ExecuteRequest(run_id=run.run_id, dry_run=True))
            st.session_state.run_id = run.run_id
            st.session_state.notice = ("success", t(lang, "executed_notice"))

with right:
    st.subheader(t(lang, "summary_title"))
    st.markdown(f"### {t(lang, 'workflow_map_title')}")
    st.caption(t(lang, "workflow_map_caption"))
    render_workflow_map(run, lang)
    st.markdown(f"**{t(lang, 'current_focus_title')}**")
    st.markdown(f"<div class='sf-focus-box'>{build_focus_text(run, lang)}</div>", unsafe_allow_html=True)
    st.markdown(f"### {t(lang, 'workflow_roles_title')}")
    st.caption(t(lang, "workflow_roles_caption"))
    role_columns = st.columns(4)
    for column, (title, value, caption) in zip(role_columns, build_role_cards(run, lang)):
        with column:
            render_stat_card(title, value, caption)
    llm_entries = get_llm_debug_entries(run)
    llm_counts = llm_usage_counts(llm_entries)
    if run:
        st.caption(
            t(lang, "llm_usage_summary").format(
                total=len(llm_entries),
                success=llm_counts["llm_success"],
                fallback=llm_counts["llm_fallback"],
                heuristic=llm_counts["heuristic_only"],
            )
        )

    if not run:
        tip_a, tip_b, tip_c, tip_d = st.columns(4)
        with tip_a:
            render_stat_card(t(lang, "high_risk_demo"), "ORD-1002", t(lang, "high_risk_card"))
        with tip_b:
            render_stat_card(t(lang, "low_risk_demo"), "ORD-1003", t(lang, "low_risk_card"))
        with tip_c:
            render_stat_card(t(lang, "multimodal_demo"), "ORD-1004", t(lang, "multimodal_card"))
        with tip_d:
            render_stat_card(t(lang, "clarify_demo"), "ORD-1001", t(lang, "clarify_card"))
        st.info(f"{t(lang, 'empty_title')}: {t(lang, 'empty_body')}")
    else:
        report = run.report
        if report:
            row_a, row_b, row_c, row_d = st.columns(4)
            with row_a:
                render_stat_card(t(lang, "status"), pick_label(STATUS_LABELS, run.status.value, lang))
            with row_b:
                render_stat_card(t(lang, "severity"), pick_label(SEVERITY_LABELS, report.severity.value, lang))
            with row_c:
                render_stat_card(t(lang, "action"), pick_label(ACTION_LABELS, report.recommended_action, lang))
            with row_d:
                human_label = t(lang, "yes") if report.needs_human else t(lang, "no")
                render_stat_card(t(lang, "human"), human_label)
        else:
            row_a, row_b = st.columns(2)
            with row_a:
                render_stat_card(t(lang, "status"), pick_label(STATUS_LABELS, run.status.value, lang))
            with row_b:
                render_stat_card(t(lang, "human"), t(lang, "yes") if run.status.value == "awaiting_clarification" else t(lang, "no"))

        tabs = st.tabs(
            [t(lang, "summary_tab"), t(lang, "evidence_tab"), t(lang, "trace_tab"), t(lang, "raw_tab"), t(lang, "llm_tab")]
        )

        with tabs[0]:
            if report:
                meta_left, meta_right = st.columns(2)
                with meta_left:
                    render_stat_card(t(lang, "case_type"), pick_label(CASE_TYPE_LABELS, report.case_type.value, lang))
                with meta_right:
                    render_stat_card(t(lang, "risk_score"), f"{report.risk_score:.3f}")
                st.markdown(f"**{t(lang, 'run_id')}**")
                st.code(run.run_id)
                st.markdown(f"**{t(lang, 'rationale')}**")
                st.write(report.decision_rationale)
            else:
                st.info(pick_label(STATUS_LABELS, run.status.value, lang))

        with tabs[1]:
            extract_payload = get_trace_payload(run, "extract_facts")
            multimodal_payload = get_trace_payload(run, "parse_multimodal")
            retrieve_payload = get_trace_payload(run, "retrieve_knowledge")
            st.markdown(f"**{t(lang, 'multimodal')}**")
            findings = multimodal_payload.get("findings", [])
            if findings:
                for finding in findings:
                    title = str(finding.get("file_name") or finding.get("modality") or "attachment")
                    details = " | ".join(
                        part
                        for part in [
                            str(finding.get("summary") or ""),
                            str(finding.get("extracted_text") or ""),
                            "、".join(str(item) for item in finding.get("signals", [])) if finding.get("signals") else "",
                            str(finding.get("error") or ""),
                        ]
                        if part
                    )
                    st.markdown(
                        f"""
                        <div class="sf-doc">
                            <div class="sf-doc-title">{title}</div>
                            <div class="sf-mini">{finding.get("source", "")}</div>
                            <div style="margin-top:0.45rem; line-height:1.6;">{details or finding.get("text", "")}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.caption(t(lang, "no_multimodal"))

            st.markdown(f"**{t(lang, 'evidence')}**")
            if report:
                evidence_texts = [span.text for span in report.evidence_spans]
            else:
                evidence_texts = [str(span.get("text", "")) for span in extract_payload.get("evidence_spans", []) if span.get("text")]
            render_list(evidence_texts, t(lang, "no_evidence"))

            st.markdown(f"**{t(lang, 'missing_info')}**")
            render_list([str(item) for item in extract_payload.get("missing_information", [])], t(lang, "no_missing"))

            st.markdown(f"**{t(lang, 'policy')}**")
            policy_refs = report.policy_refs if report else []
            if policy_refs:
                render_list([str(item) for item in policy_refs], t(lang, "no_policy"))
            elif run.status.value == "awaiting_clarification":
                st.caption(t(lang, "waiting_policy_refs"))
            else:
                st.caption(t(lang, "no_policy"))

            st.markdown(f"**{t(lang, 'retrieved_docs')}**")
            docs = retrieve_payload.get("docs", [])
            if docs:
                for doc in docs:
                    st.markdown(
                        f"""
                        <div class="sf-doc">
                            <div class="sf-doc-title">{doc.get("title", "doc")}</div>
                            <div class="sf-mini">{pick_label(DOC_TYPE_LABELS, str(doc.get("doc_type", "unknown")), lang)} | {t(lang, "doc_score")}={doc.get("score", 0)}</div>
                            <div style="margin-top:0.45rem; line-height:1.6;">{doc.get("snippet", "")}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            elif run.status.value == "awaiting_clarification":
                st.info(t(lang, "waiting_retrieval"))
            else:
                st.caption(t(lang, "no_policy"))

            st.markdown(f"**{t(lang, 'tools')}**")
            if run.tool_executions:
                for tool in run.tool_executions:
                    details = json.dumps(tool.details, ensure_ascii=False, indent=2)
                    with st.expander(tool.tool_name, expanded=False):
                        st.code(details, language="json")
            else:
                st.caption(t(lang, "no_tools"))

        with tabs[2]:
            st.caption(
                t(lang, "workflow_progress").format(done=len(unique_trace_stages(run)), total=len(STAGE_SEQUENCE))
            )
            stage_progress = min(len(unique_trace_stages(run)) / float(len(STAGE_SEQUENCE)), 1.0)
            st.progress(stage_progress)
            for index, record in enumerate(run.trace, start=1):
                stage_title = pick_label(STAGE_LABELS, record.stage, lang)
                role_prefix = f"[{record.role}] " if getattr(record, "role", None) else ""
                with st.expander(f"{index}. {role_prefix}{stage_title}", expanded=index <= 2):
                    st.write(record.summary)
                    st.code(json.dumps(record.payload, ensure_ascii=False, indent=2), language="json")

        with tabs[3]:
            st.caption(t(lang, "raw_caption"))
            st.code(json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2), language="json")

        with tabs[4]:
            st.markdown(f"**{t(lang, 'llm_debug_title')}**")
            st.caption(t(lang, "llm_debug_caption"))
            if not llm_entries:
                st.info(t(lang, "no_llm_debug"))
            else:
                metric_a, metric_b, metric_c, metric_d = st.columns(4)
                with metric_a:
                    render_stat_card(t(lang, "llm_stage_count"), str(len(llm_entries)))
                with metric_b:
                    render_stat_card(t(lang, "llm_success_count"), str(llm_counts["llm_success"]))
                with metric_c:
                    render_stat_card(t(lang, "llm_fallback_count"), str(llm_counts["llm_fallback"]))
                with metric_d:
                    render_stat_card(t(lang, "llm_heuristic_count"), str(llm_counts["heuristic_only"]))
                st.markdown(f"**{t(lang, 'llm_stage_list')}**")
                overview_columns = st.columns(min(len(llm_entries), 4))
                for column, entry in zip(overview_columns, llm_entries[:4]):
                    debug = entry.get("debug", {})
                    stage = str(entry.get("stage", "unknown"))
                    mode = str(debug.get("mode", "heuristic_only")) if isinstance(debug, dict) else "heuristic_only"
                    with column:
                        render_stat_card(
                            pick_label(STAGE_LABELS, stage, lang),
                            pick_label(LLM_MODE_LABELS, mode, lang),
                            str(entry.get("summary", "")),
                        )

                selected_entry = st.selectbox(
                    t(lang, "llm_stage_selector"),
                    options=llm_entries,
                    format_func=lambda item: llm_stage_option_label(item, lang),
                    key=f"llm_debug_stage_{run.run_id}",
                )

                stage = str(selected_entry.get("stage", "unknown"))
                summary = str(selected_entry.get("summary", ""))
                debug = selected_entry.get("debug", {})
                if isinstance(debug, dict):
                    mode = str(debug.get("mode", "heuristic_only"))
                    mode_label = pick_label(LLM_MODE_LABELS, mode, lang)

                    st.markdown(f"**{t(lang, 'llm_selected_stage')}**")
                    st.info(f"{pick_label(STAGE_LABELS, stage, lang)} | {mode_label}")

                    info_a, info_b, info_c = st.columns(3)
                    with info_a:
                        render_stat_card(t(lang, "llm_mode"), mode_label)
                    with info_b:
                        render_stat_card(t(lang, "llm_model"), str(debug.get("model", "-")))
                    with info_c:
                        client_text = t(lang, "yes") if bool(debug.get("client_available")) else t(lang, "no")
                        render_stat_card(t(lang, "llm_client"), client_text)

                    if summary:
                        st.caption(summary)

                    error_text = str(debug.get("error", "") or "")
                    if error_text:
                        st.warning(f"{t(lang, 'llm_error')}: {error_text}")

                    llm_detail_tabs = st.tabs(
                        [t(lang, "llm_detail_tab"), t(lang, "llm_prompt_tab"), t(lang, "llm_response_tab")]
                    )

                    with llm_detail_tabs[0]:
                        parsed_response = debug.get("parsed_response", {})
                        st.markdown(f"**{t(lang, 'llm_parsed_response')}**")
                        st.code(json.dumps(parsed_response, ensure_ascii=False, indent=2), language="json")

                    with llm_detail_tabs[1]:
                        st.markdown(f"**{t(lang, 'llm_system_prompt')}**")
                        st.code(str(debug.get("system_prompt", "")), language="text")
                        with st.expander(t(lang, "llm_user_payload"), expanded=False):
                            st.code(
                                json.dumps(debug.get("user_payload", {}), ensure_ascii=False, indent=2),
                                language="json",
                            )

                    with llm_detail_tabs[2]:
                        st.markdown(f"**{t(lang, 'llm_raw_response')}**")
                        st.code(str(debug.get("raw_response", "")), language="json")
