from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import RunStatus, StoredRun, WorkflowState


class RunStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, state: WorkflowState) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs(run_id, status, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (state.run_id, state.status.value, state.model_dump_json(), now, now),
            )

    def load(self, run_id: str) -> WorkflowState:
        with self._connect() as conn:
            row = conn.execute("SELECT state_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Run {run_id} not found")
        return WorkflowState.model_validate_json(row[0])

    def get_record(self, run_id: str) -> StoredRun:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id, status, state_json, created_at, updated_at FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Run {run_id} not found")
        return StoredRun(
            run_id=row[0],
            status=RunStatus(row[1]),
            state=WorkflowState.model_validate_json(row[2]).model_dump(mode="json"),
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
        )
