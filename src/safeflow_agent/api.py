from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException

from .models import CaseInput, ClarificationRequest, ExecuteRequest
from .service import SafeFlowService


service = SafeFlowService()
app = FastAPI(title="SafeFlow-Agent", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/demo/cases")
def demo_cases() -> list[dict]:
    return [item.model_dump(mode="json") for item in service.demo_cases()]


@app.post("/cases/evaluate")
def evaluate_case(case_input: CaseInput) -> dict:
    return service.evaluate_case(case_input).model_dump(mode="json")


@app.post("/cases/clarify")
def clarify_case(request: ClarificationRequest) -> dict:
    try:
        return service.clarify_case(request).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/cases/execute")
def execute_case(request: ExecuteRequest) -> dict:
    try:
        return service.execute_case(request).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return service.get_run(run_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def run() -> None:
    uvicorn.run("safeflow_agent.api:app", host="127.0.0.1", port=8018, reload=False)

# 8000 端口号由8000改为8007