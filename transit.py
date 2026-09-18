# -*- coding: utf-8 -*-
"""
KnowledgeDigest -- Cross-System Transit Sync & Work Coordination Adapter.

Implements verified transit synchronization and chunk processing coordination
using sqlite-transit-sync for distributed nodes (e.g. ASUS-GEI <-> WORKSTATION-LG).

Key Invariants:
1. Stable Chunk Identifiers: Canonical key derived from source_type, canonical_id,
   content_version (content_hash) and chunk_index.
2. Lease-Based Work Claims: Atomic state transitions:
   pending -> claimed -> processing -> done / error.
3. Conflict Resolution & Idempotency:
   - 'done' status is terminal and always wins over transient states.
   - Prevents duplicate execution of already-completed chunks across nodes.
   - Active leases protect ongoing work; expired leases allow fail-soft takeover.
4. Privacy & Secret Safety:
   - Credentials and secrets are blocked from transit snapshots.
   - No direct synchronization of WAL/SHM or open live database files.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlite_transit_sync import (
    SyncConfig,
    TransitSync,
    Snapshot,
    MergeReport,
)


def utc_now() -> datetime:
    """Returns current UTC timestamp with timezone."""
    return datetime.now(timezone.utc)


def iso_timestamp(dt: Optional[datetime] = None) -> str:
    """Formats a datetime as ISO 8601 string."""
    t = dt or utc_now()
    return t.isoformat()


def parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    """Parses an ISO 8601 string into a datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def generate_chunk_key(
    source_type: str,
    canonical_id: str,
    content_version: str,
    chunk_index: int,
) -> str:
    """Generates a stable, canonical chunk key across systems.

    Args:
        source_type: 'document', 'skill', or 'wiki'.
        canonical_id: Unique relative path or canonical entity name.
        content_version: Content hash (e.g. sha256) of the document/skill.
        chunk_index: Zero-based index of the chunk within the document.

    Returns:
        Deterministic SHA-256 prefixed identifier.
    """
    normalized = f"{source_type.strip().lower()}:{canonical_id.strip()}:{content_version.strip()}:{chunk_index}"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"chunk:{digest}"


class ChunkTaskManager:
    """Manages atomic chunk task registration, claims, leases, and state transitions."""

    @staticmethod
    def register_task(
        conn: sqlite3.Connection,
        source_type: str,
        canonical_id: str,
        content_version: str,
        chunk_index: int,
        created_at: Optional[datetime] = None,
    ) -> str:
        """Registers a chunk task as 'pending' if it does not already exist."""
        chunk_key = generate_chunk_key(source_type, canonical_id, content_version, chunk_index)
        now_str = iso_timestamp(created_at)
        with conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chunk_tasks (
                    chunk_key, source_type, canonical_id, content_version,
                    chunk_index, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (chunk_key, source_type, canonical_id, content_version, chunk_index, now_str, now_str),
            )
        return chunk_key

    @staticmethod
    def claim_task(
        conn: sqlite3.Connection,
        chunk_key: str,
        node_id: str,
        agent_id: str,
        lease_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> bool:
        """Atomically claims a chunk task if pending or if its existing lease has expired.

        Returns True if claim succeeded, False if already claimed by active lease or completed.
        """
        current_time = now or utc_now()
        current_iso = iso_timestamp(current_time)
        lease_expires = current_time + timedelta(seconds=lease_seconds)
        lease_iso = iso_timestamp(lease_expires)

        with conn:
            cur = conn.execute(
                """
                UPDATE chunk_tasks
                SET status = 'claimed',
                    claimed_by_node = ?,
                    claimed_by_agent = ?,
                    claimed_at = ?,
                    lease_expires_at = ?,
                    heartbeat_at = ?,
                    updated_at = ?
                WHERE chunk_key = ?
                  AND (
                      status = 'pending'
                      OR (status IN ('claimed', 'processing') AND lease_expires_at <= ?)
                      OR (status = 'error')
                  )
                """,
                (
                    node_id,
                    agent_id,
                    current_iso,
                    lease_iso,
                    current_iso,
                    current_iso,
                    chunk_key,
                    current_iso,
                ),
            )
            return cur.rowcount > 0

    @staticmethod
    def start_processing(
        conn: sqlite3.Connection,
        chunk_key: str,
        node_id: str,
        extend_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> bool:
        """Transitions a claimed task to 'processing' and extends lease."""
        current_time = now or utc_now()
        current_iso = iso_timestamp(current_time)
        lease_expires = current_time + timedelta(seconds=extend_seconds)
        lease_iso = iso_timestamp(lease_expires)

        with conn:
            cur = conn.execute(
                """
                UPDATE chunk_tasks
                SET status = 'processing',
                    heartbeat_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE chunk_key = ?
                  AND claimed_by_node = ?
                  AND status IN ('claimed', 'processing')
                """,
                (current_iso, lease_iso, current_iso, chunk_key, node_id),
            )
            return cur.rowcount > 0

    @staticmethod
    def heartbeat(
        conn: sqlite3.Connection,
        chunk_key: str,
        node_id: str,
        extend_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> bool:
        """Refreshes heartbeat and extends lease for an active task."""
        current_time = now or utc_now()
        current_iso = iso_timestamp(current_time)
        lease_expires = current_time + timedelta(seconds=extend_seconds)
        lease_iso = iso_timestamp(lease_expires)

        with conn:
            cur = conn.execute(
                """
                UPDATE chunk_tasks
                SET heartbeat_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE chunk_key = ?
                  AND claimed_by_node = ?
                  AND status = 'processing'
                """,
                (current_iso, lease_iso, current_iso, chunk_key, node_id),
            )
            return cur.rowcount > 0

    @staticmethod
    def complete_task(
        conn: sqlite3.Connection,
        chunk_key: str,
        node_id: str,
        summary: str,
        keywords: Optional[str] = None,
        domain: Optional[str] = None,
        model: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Marks a task as 'done' and records the generated summary/results."""
        current_time = now or utc_now()
        current_iso = iso_timestamp(current_time)

        with conn:
            cur = conn.execute(
                """
                UPDATE chunk_tasks
                SET status = 'done',
                    summary = ?,
                    keywords = ?,
                    domain = ?,
                    model = ?,
                    error_msg = NULL,
                    updated_at = ?
                WHERE chunk_key = ?
                  AND claimed_by_node = ?
                  AND status IN ('claimed', 'processing')
                """,
                (summary, keywords, domain, model, current_iso, chunk_key, node_id),
            )
            return cur.rowcount > 0

    @staticmethod
    def fail_task(
        conn: sqlite3.Connection,
        chunk_key: str,
        node_id: str,
        error_msg: str,
        now: Optional[datetime] = None,
    ) -> bool:
        """Marks a task as 'error' with diagnostic failure message."""
        current_time = now or utc_now()
        current_iso = iso_timestamp(current_time)

        with conn:
            cur = conn.execute(
                """
                UPDATE chunk_tasks
                SET status = 'error',
                    error_msg = ?,
                    updated_at = ?
                WHERE chunk_key = ?
                  AND claimed_by_node = ?
                  AND status IN ('claimed', 'processing')
                """,
                (error_msg, current_iso, chunk_key, node_id),
            )
            return cur.rowcount > 0

    @staticmethod
    def get_task(conn: sqlite3.Connection, chunk_key: str) -> Optional[dict[str, Any]]:
        """Fetches a task by chunk_key as dict."""
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM chunk_tasks WHERE chunk_key = ?", (chunk_key,))
        row = cur.fetchone()
        return dict(row) if row else None


class KnowledgeDigestMergePolicy:
    """Domain merge policy for KnowledgeDigest transit synchronization.

    Enforces:
    1. 'done' status is terminal and idempotent: once completed, no work is re-done.
    2. Active leases are preserved during merge.
    3. Conflicting active claims resolve deterministically:
       earliest claim timestamp wins; tie-breaker is lexicographical node_id.
    4. Expired leases on local nodes yield to active claims from remote snapshots.
    5. Clean sync report metrics per table.
    """

    def __init__(self, exclude_tables: Sequence[str] = ("secrets", "sqlite_sequence")):
        self.exclude_tables = set(exclude_tables)

    def merge(
        self,
        local: sqlite3.Connection,
        remote: sqlite3.Connection,
        snapshot: Snapshot,
    ) -> MergeReport:
        local.row_factory = sqlite3.Row
        remote.row_factory = sqlite3.Row

        report = MergeReport(snapshot=snapshot.path.name, source_node=snapshot.node_id)
        now = utc_now()
        now_iso = iso_timestamp(now)

        # 1. Merge chunk_tasks table
        tables_remote = {
            r[0]
            for r in remote.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }

        if "chunk_tasks" in tables_remote and "chunk_tasks" not in self.exclude_tables:
            t_stats = {"inserted": 0, "updated": 0, "unchanged": 0}
            remote_rows = remote.execute("SELECT * FROM chunk_tasks").fetchall()

            for r_row in remote_rows:
                r_dict = dict(r_row)
                chunk_key = r_dict["chunk_key"]

                l_row = local.execute(
                    "SELECT * FROM chunk_tasks WHERE chunk_key = ?", (chunk_key,)
                ).fetchone()

                if l_row is None:
                    # New chunk task from remote snapshot: insert directly
                    cols = list(r_dict.keys())
                    placeholders = ", ".join("?" for _ in cols)
                    col_names = ", ".join(cols)
                    values = [r_dict[c] for c in cols]
                    local.execute(
                        f"INSERT INTO chunk_tasks ({col_names}) VALUES ({placeholders})",
                        values,
                    )
                    t_stats["inserted"] += 1
                else:
                    l_dict = dict(l_row)
                    remote_wins, reason = self._resolve_chunk_conflict(l_dict, r_dict, now_iso)

                    if remote_wins:
                        cols = [
                            "status",
                            "claimed_by_node",
                            "claimed_by_agent",
                            "claimed_at",
                            "lease_expires_at",
                            "heartbeat_at",
                            "summary",
                            "keywords",
                            "domain",
                            "model",
                            "error_msg",
                            "updated_at",
                        ]
                        set_clause = ", ".join(f"{c} = ?" for c in cols)
                        values = [r_dict[c] for c in cols] + [chunk_key]
                        local.execute(
                            f"UPDATE chunk_tasks SET {set_clause} WHERE chunk_key = ?",
                            values,
                        )
                        t_stats["updated"] += 1
                    else:
                        t_stats["unchanged"] += 1

            report.tables["chunk_tasks"] = t_stats
            report.inserted += t_stats["inserted"]
            report.updated += t_stats["updated"]
            report.unchanged += t_stats["unchanged"]

        # 2. Merge summaries table idempotently
        if "summaries" in tables_remote and "summaries" not in self.exclude_tables:
            s_stats = {"inserted": 0, "updated": 0, "unchanged": 0}
            remote_summaries = remote.execute("SELECT * FROM summaries").fetchall()
            for r_s in remote_summaries:
                s_dict = dict(r_s)
                # Check for existing summary
                existing = local.execute(
                    """
                    SELECT id FROM summaries
                    WHERE source_type = ? AND source_id = ? AND chunk_index = ?
                    """,
                    (s_dict["source_type"], s_dict["source_id"], s_dict["chunk_index"]),
                ).fetchone()

                if existing is None:
                    local.execute(
                        """
                        INSERT INTO summaries (
                            source_type, source_id, chunk_index, summary,
                            keywords, domain, model, input_tokens, output_tokens, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            s_dict["source_type"],
                            s_dict["source_id"],
                            s_dict["chunk_index"],
                            s_dict["summary"],
                            s_dict["keywords"],
                            s_dict["domain"],
                            s_dict["model"],
                            s_dict.get("input_tokens", 0),
                            s_dict.get("output_tokens", 0),
                            s_dict["created_at"],
                        ),
                    )
                    s_stats["inserted"] += 1
                else:
                    s_stats["unchanged"] += 1

            report.tables["summaries"] = s_stats
            report.inserted += s_stats["inserted"]
            report.updated += s_stats["updated"]
            report.unchanged += s_stats["unchanged"]

        return report

    @staticmethod
    def _resolve_chunk_conflict(
        local_dict: dict[str, Any],
        remote_dict: dict[str, Any],
        now_iso: str,
    ) -> tuple[bool, str]:
        """Determines whether the remote row wins over local.

        Returns (remote_wins: bool, rationale: str).
        """
        l_status = local_dict.get("status", "pending")
        r_status = remote_dict.get("status", "pending")

        # 1. 'done' is terminal and immutable
        if l_status == "done":
            return False, "local_already_done"
        if r_status == "done":
            return True, "remote_done_terminal"

        # 2. Both are actively claimed or processing
        l_active = l_status in ("claimed", "processing")
        r_active = r_status in ("claimed", "processing")

        l_lease = local_dict.get("lease_expires_at") or ""
        r_lease = remote_dict.get("lease_expires_at") or ""

        l_expired = l_lease <= now_iso
        r_expired = r_lease <= now_iso

        if l_active and r_active:
            if l_expired and not r_expired:
                return True, "local_lease_expired_remote_active"
            if not l_expired and r_expired:
                return False, "remote_lease_expired_local_active"
            if not l_expired and not r_expired:
                # Both have active leases: resolve conflict deterministically
                l_claimed_at = local_dict.get("claimed_at") or ""
                r_claimed_at = remote_dict.get("claimed_at") or ""
                if r_claimed_at != l_claimed_at:
                    return r_claimed_at < l_claimed_at, "earlier_claim_wins"
                l_node = local_dict.get("claimed_by_node") or ""
                r_node = remote_dict.get("claimed_by_node") or ""
                return r_node < l_node, "node_id_tie_breaker"

        # 3. Remote active claim vs Local pending/error/expired
        if r_active and not r_expired:
            if l_status in ("pending", "error") or l_expired:
                return True, "remote_active_claim_over_pending_or_expired"

        # 4. Error state handling
        if r_status == "error" and l_status == "pending":
            return True, "remote_error_propagated"

        # Default: local remains unchanged
        return False, "local_retains_priority"


def create_knowledge_sync(
    db_path: Path,
    transit_dir: Path,
    node_id: str,
    state_dir: Optional[Path] = None,
    namespace: str = "wissensdb",
) -> TransitSync:
    """Creates a configured TransitSync instance with KnowledgeDigestMergePolicy.

    Args:
        db_path: Path to the local knowledge.db database.
        transit_dir: Path to the transit yard (e.g. in .SYNC or local test yard).
        node_id: Stable identifier of this system (e.g. 'ASUS-GEI', 'WORKSTATION-LG').
        state_dir: Directory for local sync state (defaults to ~/.wissensdb-transit).
        namespace: Logical namespace for transit snapshots.
    """
    if state_dir is None:
        state_dir = db_path.parent / ".transit_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{node_id}.sync-state.json"

    config = SyncConfig(
        database=Path(db_path),
        transit=Path(transit_dir),
        state=state_path,
        node_id=node_id,
        namespace=namespace,
        snapshot_exclude_tables=("secrets", "sqlite_sequence"),
        scan_snapshot_for_secrets=True,
    )

    policy = KnowledgeDigestMergePolicy()
    return TransitSync(config=config, policy=policy)
