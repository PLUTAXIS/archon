import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from archon.guardian.models import AuditEvent


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _verified_state(
    connection: sqlite3.Connection,
) -> tuple[bool, int, str]:
    previous_hash = ""
    expected_sequence = 1

    rows = connection.execute(
        "SELECT event_json FROM audit_events ORDER BY sequence"
    )

    for (event_json,) in rows:
        raw = json.loads(event_json)
        event = AuditEvent.model_validate(raw)

        if event.sequence != expected_sequence:
            return False, 0, ""

        if event.previous_hash != previous_hash:
            return False, 0, ""

        payload = event.model_dump(mode="json")
        payload.pop("event_hash")
        calculated = hashlib.sha256(_canonical(payload)).hexdigest()

        if calculated != event.event_hash:
            return False, 0, ""

        previous_hash = event.event_hash
        expected_sequence += 1

    return True, expected_sequence - 1, previous_hash


class AuditLogger:
    """Append transactional SQLite audit events with a verifiable hash chain."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def verify(self) -> bool:
        if not self.path.exists():
            return True

        try:
            with sqlite3.connect(self.path, timeout=30) as connection:
                table = connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name = 'audit_events'
                    """
                ).fetchone()

                if table is None:
                    return False

                valid, _, _ = _verified_state(connection)
                return valid

        except Exception:  # noqa: BLE001 -- verification must fail closed
            return False

    def append(
        self,
        actor: str,
        action: str,
        outcome: str,
        details: dict[str, str] | None = None,
    ) -> AuditEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.execute("PRAGMA busy_timeout = 30000")

            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        sequence INTEGER PRIMARY KEY,
                        event_json TEXT NOT NULL
                    )
                    """
                )

                # Serialize writers before checking the chain and allocating
                # the next sequence number.
                connection.execute("BEGIN IMMEDIATE")

                valid, last_sequence, previous_hash = _verified_state(
                    connection
                )

                if not valid:
                    raise ValueError("audit chain verification failed")

                payload: dict[str, object] = {
                    "sequence": last_sequence + 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "actor": actor,
                    "action": action,
                    "outcome": outcome,
                    "details": details or {},
                    "previous_hash": previous_hash,
                }

                event_hash = hashlib.sha256(_canonical(payload)).hexdigest()
                event = AuditEvent(**payload, event_hash=event_hash)

                connection.execute(
                    """
                    INSERT INTO audit_events (sequence, event_json)
                    VALUES (?, ?)
                    """,
                    (
                        event.sequence,
                        json.dumps(
                            event.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ),
                    ),
                )

            return event