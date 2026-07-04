# stage 9 - compliance / audit logging to sqlite.
# every transaction (allowed or rejected) writes exactly one row. on purpose the log stores
# counts + decisions, not raw pii or prompts, so the audit trail is itself privacy-preserving.
# set GATEWAY_STORE_REDACTED_PROMPT=true to also keep the scrubbed (pii-free) prompt for debugging.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    request_id        TEXT PRIMARY KEY,
    ts                TEXT NOT NULL,
    user_id           TEXT,
    client_ip         TEXT,
    decision          TEXT NOT NULL,      -- 'allowed' | 'rejected'
    terminating_stage TEXT,               -- stage that ended the req
    status_code       INTEGER NOT NULL,
    jwt_valid         INTEGER NOT NULL,
    rate_limited      INTEGER NOT NULL,
    ingress_hits      INTEGER NOT NULL,
    egress_hits       INTEGER NOT NULL,
    redaction_counts  TEXT,               -- json: {label: count}
    provider          TEXT,
    latency_ms        REAL,
    redacted_prompt   TEXT                 -- only if store_redacted_prompt
);
"""


@dataclass
class AuditRecord:
    request_id: str
    ts: str
    user_id: str | None = None
    client_ip: str | None = None
    decision: str = "rejected"
    terminating_stage: str | None = None
    status_code: int = 500
    jwt_valid: bool = False
    rate_limited: bool = False
    ingress_hits: int = 0
    egress_hits: int = 0
    redaction_counts: dict[str, int] = field(default_factory=dict)
    provider: str | None = None
    latency_ms: float | None = None
    redacted_prompt: str | None = None

    def as_row(self) -> tuple:
        return (
            self.request_id,
            self.ts,
            self.user_id,
            self.client_ip,
            self.decision,
            self.terminating_stage,
            self.status_code,
            int(self.jwt_valid),
            int(self.rate_limited),
            self.ingress_hits,
            self.egress_hits,
            json.dumps(self.redaction_counts),
            self.provider,
            self.latency_ms,
            self.redacted_prompt,
        )


class AuditLog:
    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def write(self, record: AuditRecord) -> None:
        assert self._db is not None, "AuditLog.connect() not called"
        await self._db.execute(
            """
            INSERT OR REPLACE INTO transactions VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            record.as_row(),
        )
        await self._db.commit()
