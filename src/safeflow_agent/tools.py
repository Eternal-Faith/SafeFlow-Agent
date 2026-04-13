from __future__ import annotations

from typing import Any

from .models import RetrievedDoc, Severity, ToolExecution
from .retrieval import KnowledgeBase
from .seeds import seeded_orders


class ToolRegistry:
    def __init__(self, knowledge_base: KnowledgeBase, top_k_retrieval: int = 4) -> None:
        self.knowledge_base = knowledge_base
        self.orders = seeded_orders()
        self.top_k_retrieval = top_k_retrieval

    def get_order_context(self, order_id: str) -> dict[str, Any]:
        return self.orders.get(
            order_id,
            {
                "pickup": "未知",
                "dropoff": "未知",
                "start_time": "未知",
                "end_time": "未知",
                "route_flags": [],
                "prior_driver_complaints": 0,
            },
        )

    def retrieve_policy(self, query: str, case_type: str | None = None, top_k: int = 4) -> list[RetrievedDoc]:
        return self.knowledge_base.query(query, case_type=case_type, top_k=top_k)

    def create_safety_ticket(self, case_id: str, severity: Severity, summary: str, dry_run: bool = True) -> ToolExecution:
        return ToolExecution(
            tool_name="create_safety_ticket",
            success=True,
            details={
                "工单号": f"TICKET-{case_id[-6:].upper()}",
                "风险等级": severity.value,
                "摘要": summary,
                "是否沙箱": dry_run,
            },
        )

    def notify_human_reviewer(self, case_id: str, reason: str, dry_run: bool = True) -> ToolExecution:
        return ToolExecution(
            tool_name="notify_human_reviewer",
            success=True,
            details={
                "通知单号": f"REVIEW-{case_id[-6:].upper()}",
                "原因": reason,
                "是否沙箱": dry_run,
            },
        )

    def preserve_evidence_snapshot(self, case_id: str, summary: str, dry_run: bool = True) -> ToolExecution:
        return ToolExecution(
            tool_name="preserve_evidence_snapshot",
            success=True,
            details={
                "快照号": f"EVID-{case_id[-6:].upper()}",
                "摘要": summary,
                "是否沙箱": dry_run,
            },
        )
