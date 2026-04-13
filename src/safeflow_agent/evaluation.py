from __future__ import annotations

import time
from statistics import mean

from .config import settings
from .models import CaseInput
from .reasoning import SafetyReasoner
from .seeds import evaluation_samples
from .service import SafeFlowService


def severity_accuracy(rows: list[dict[str, object]]) -> float:
    correct = sum(1 for row in rows if row["predicted_severity"] == row["expected_severity"])
    return round(correct / max(len(rows), 1), 3)


def action_accuracy(rows: list[dict[str, object]]) -> float:
    correct = sum(1 for row in rows if row["predicted_action"] == row["expected_action"])
    return round(correct / max(len(rows), 1), 3)


def human_recall(rows: list[dict[str, object]]) -> float:
    positives = [row for row in rows if row["expected_needs_human"]]
    if not positives:
        return 0.0
    recalled = sum(1 for row in positives if row["predicted_needs_human"])
    return round(recalled / len(positives), 3)


def evidence_coverage(rows: list[dict[str, object]]) -> float:
    covered = sum(1 for row in rows if row["evidence_count"] > 0)
    return round(covered / max(len(rows), 1), 3)


def grounded_policy_coverage(rows: list[dict[str, object]]) -> float:
    grounded = sum(1 for row in rows if row["policy_ref_count"] > 0)
    return round(grounded / max(len(rows), 1), 3)


def clarification_resolution_rate(rows: list[dict[str, object]]) -> float:
    targets = [row for row in rows if row["expected_clarification"]]
    if not targets:
        return 0.0
    triggered = sum(1 for row in targets if row["predicted_clarification"])
    return round(triggered / len(targets), 3)


def multimodal_case_pass_rate(rows: list[dict[str, object]]) -> float:
    targets = [row for row in rows if row["is_multimodal"]]
    if not targets:
        return 0.0
    passed = sum(
        1
        for row in targets
        if row["predicted_severity"] == row["expected_severity"] and row["predicted_action"] == row["expected_action"]
    )
    return round(passed / len(targets), 3)


def rule_baseline(sample: dict[str, object], reasoner: SafetyReasoner) -> dict[str, object]:
    case_input = CaseInput.model_validate(sample["case_input"])
    narrative = case_input.complaint_text
    for attachment in case_input.attachments:
        if attachment.ocr_text:
            narrative += f" {attachment.ocr_text}"
        if attachment.transcript:
            narrative += f" {attachment.transcript}"
        if attachment.content:
            narrative += f" {attachment.content}"
    facts = reasoner.extract_facts(narrative, {})
    risk = reasoner.assess_risk(facts, {})
    if facts.missing_information:
        action = "request_more_information"
    elif risk.severity.value == "high":
        action = "notify_human_reviewer"
    elif facts.case_type.value == "fare_dispute":
        action = "route_to_customer_support"
    else:
        action = "close_with_monitoring"
    return {
        "predicted_severity": risk.severity.value,
        "predicted_action": action,
        "predicted_needs_human": risk.needs_human,
        "evidence_count": len(facts.evidence_spans),
        "policy_ref_count": 0,
        "predicted_clarification": bool(facts.missing_information),
        "used_multimodal": bool(case_input.attachments),
    }


def single_turn_baseline(sample: dict[str, object], reasoner: SafetyReasoner) -> dict[str, object]:
    case_input = CaseInput.model_validate(sample["case_input"])
    narrative = case_input.complaint_text
    if case_input.chat_messages:
        narrative += " " + " ".join(message.text for message in case_input.chat_messages)
    for attachment in case_input.attachments:
        if attachment.ocr_text:
            narrative += f" {attachment.ocr_text}"
        if attachment.transcript:
            narrative += f" {attachment.transcript}"
        if attachment.content:
            narrative += f" {attachment.content}"
    facts = reasoner.extract_facts(narrative, {})
    risk = reasoner.assess_risk(facts, {})
    plan = reasoner.plan_actions(facts, risk, [])
    return {
        "predicted_severity": risk.severity.value,
        "predicted_action": plan.recommended_action,
        "predicted_needs_human": risk.needs_human,
        "evidence_count": len(facts.evidence_spans),
        "policy_ref_count": 0,
        "predicted_clarification": bool(facts.missing_information),
        "used_multimodal": bool(case_input.attachments),
    }


def workflow_prediction(sample: dict[str, object], service: SafeFlowService) -> dict[str, object]:
    case_input = CaseInput.model_validate(sample["case_input"])
    response = service.evaluate_case(case_input)
    report = response.report
    return {
        "predicted_severity": report.severity.value if report else "medium",
        "predicted_action": report.recommended_action if report else "request_more_information",
        "predicted_needs_human": report.needs_human if report else False,
        "evidence_count": len(report.evidence_spans) if report else 0,
        "policy_ref_count": len(report.policy_refs) if report else 0,
        "predicted_clarification": response.status.value == "awaiting_clarification",
        "used_multimodal": any(record.stage == "parse_multimodal" and record.payload.get("使用多模态增强") for record in response.trace),
    }


def evaluate_variant(name: str, predictor, samples: list[dict[str, object]]) -> dict[str, object]:  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    rows: list[dict[str, object]] = []
    for sample in samples:
        pred = predictor(sample)
        rows.append(
            {
                **pred,
                "expected_severity": sample["expected_severity"],
                "expected_action": sample["expected_action"],
                "expected_needs_human": sample["expected_needs_human"],
                "expected_clarification": sample.get("expected_clarification", False),
                "is_multimodal": sample.get("is_multimodal", False),
            }
        )
    elapsed = time.perf_counter() - started
    return {
        "variant": name,
        "severity_accuracy": severity_accuracy(rows),
        "action_accuracy": action_accuracy(rows),
        "human_recall": human_recall(rows),
        "evidence_coverage": evidence_coverage(rows),
        "grounded_policy_coverage": grounded_policy_coverage(rows),
        "clarification_resolution_rate": clarification_resolution_rate(rows),
        "multimodal_case_pass_rate": multimodal_case_pass_rate(rows),
        "avg_latency_ms": round(1000 * elapsed / max(len(samples), 1), 2),
    }


def main() -> None:
    samples = evaluation_samples()
    service = SafeFlowService()
    reasoner = SafetyReasoner(settings.llm_model)
    results = [
        evaluate_variant("rule_baseline", lambda sample: rule_baseline(sample, reasoner), samples),
        evaluate_variant("single_turn_llm", lambda sample: single_turn_baseline(sample, reasoner), samples),
        evaluate_variant("workflow_agent", lambda sample: workflow_prediction(sample, service), samples),
    ]
    print("SafeFlow-Agent evaluation results")
    for result in results:
        print(result)
    print("Average severity accuracy:", round(mean(result["severity_accuracy"] for result in results), 3))


if __name__ == "__main__":
    main()
