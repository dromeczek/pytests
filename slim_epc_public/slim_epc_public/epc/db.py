"""SQLite-backed EPC repository."""

import os
import sqlite3

from .models import BearerConfig, ThroughputStats, UEState

# Default path: file in cwd. Tests should use a dedicated tempfile.
EPC_DB_PATH = os.getenv("EPC_DB_PATH", "epc.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ue_state (
    ue_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL
);
"""


class EPCRepository:
    """Repository for UE state and bearers, backed by SQLite (file path)."""

    def __init__(self, db_path: str | None = None):
        self._path = db_path if db_path is not None else EPC_DB_PATH
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def list_ues(self):
        with self._conn() as c:
            for row in c.execute("SELECT ue_id FROM ue_state ORDER BY ue_id"):
                yield int(row["ue_id"])

    def ue_exists(self, ue_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("SELECT 1 FROM ue_state WHERE ue_id = ?", (ue_id,))
            return cur.fetchone() is not None

    def attach_ue(self, ue_id: int) -> None:
        if self.ue_exists(ue_id):
            raise ValueError("UE already attached")
        state = UEState(ue_id=ue_id)
        state.bearers[9] = BearerConfig(bearer_id=9)
        with self._conn() as c:
            c.execute(
                "INSERT INTO ue_state (ue_id, data) VALUES (?, ?)",
                (ue_id, state.model_dump_json()),
            )

    def detach_ue(self, ue_id: int) -> None:
        if not self.ue_exists(ue_id):
            raise ValueError("UE not found")
        with self._conn() as c:
            c.execute("DELETE FROM ue_state WHERE ue_id = ?", (ue_id,))

    def get_ue(self, ue_id: int) -> UEState:
        with self._conn() as c:
            cur = c.execute("SELECT data FROM ue_state WHERE ue_id = ?", (ue_id,))
            row = cur.fetchone()
        if not row:
            raise ValueError("UE not found")
        raw = row["data"]
        return UEState.model_validate_json(raw)

    def save_ue(self, state: UEState) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO ue_state (ue_id, data) VALUES (?, ?)",
                (state.ue_id, state.model_dump_json()),
            )

    def add_bearer(self, ue_id: int, bearer_id: int) -> None:
        state = self.get_ue(ue_id)
        if bearer_id in state.bearers:
            raise ValueError("Bearer already exists")
        state.bearers[bearer_id] = BearerConfig(bearer_id=bearer_id)
        self.save_ue(state)

    def update_bearer(self, ue_id: int, bearer: BearerConfig) -> None:
        state = self.get_ue(ue_id)
        state.bearers[bearer.bearer_id] = bearer
        self.save_ue(state)

    def update_stats(self, ue_id: int, stats: ThroughputStats) -> None:
        state = self.get_ue(ue_id)
        state.stats[stats.bearer_id] = stats
        self.save_ue(state)

    def reset_all(self) -> None:
        for ue_id in list(self.list_ues()):
            self.detach_ue(ue_id)

    def delete_bearer(self, ue_id: int, bearer_id: int) -> None:
        if bearer_id == 9:
            raise ValueError("Cannot remove default bearer")
        state = self.get_ue(ue_id)
        if bearer_id not in state.bearers:
            raise ValueError("Bearer not found")
        state.bearers.pop(bearer_id, None)
        state.stats.pop(bearer_id, None)
        self.save_ue(state)
