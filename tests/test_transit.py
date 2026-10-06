# -*- coding: utf-8 -*-
"""
Tests for KnowledgeDigest Transit Sync and Multi-Node Chunk Coordination.

Covers the 6 acceptance criteria specified in T-20260727-05:
1. Two isolated local nodes see the same chunk, but only one node obtains the claim.
2. The processing result ('done') converges onto both nodes exactly once after pull.
3. An expired claim lease allows safe takeover by another node.
4. Repeated pull operations are strictly idempotent.
5. Secret scanning blocks credential leaks, and PRAGMA quick_check stays ok.
6. New content versions produce independent chunk versions.
"""


from datetime import timedelta

import pytest

try:
    from sqlite_transit_sync import SyncError
except ImportError:  # optional dependency, see transit.py
    SyncError = None

from KnowledgeDigest.schema import ensure_schema
from KnowledgeDigest.transit import (
    TRANSIT_SYNC_AVAILABLE,
    generate_chunk_key,
    ChunkTaskManager,
    KnowledgeDigestMergePolicy,
    create_knowledge_sync,
    utc_now,
    iso_timestamp,
)

requires_transit_sync = pytest.mark.skipif(
    not TRANSIT_SYNC_AVAILABLE, reason="optional package sqlite-transit-sync not installed"
)


@pytest.fixture
def transit_environment(tmp_path):
    """Sets up two isolated nodes (Node A and Node B) with separate databases and a shared transit yard."""
    yard_dir = tmp_path / "transit_yard"
    yard_dir.mkdir()

    # Node A setup
    node_a_dir = tmp_path / "node_a"
    node_a_dir.mkdir()
    db_a_path = node_a_dir / "knowledge_a.db"
    conn_a = ensure_schema(db_a_path)

    sync_a = create_knowledge_sync(
        db_path=db_a_path,
        transit_dir=yard_dir,
        node_id="node_a",
        state_dir=node_a_dir / ".transit_state",
    )

    # Node B setup
    node_b_dir = tmp_path / "node_b"
    node_b_dir.mkdir()
    db_b_path = node_b_dir / "knowledge_b.db"
    conn_b = ensure_schema(db_b_path)

    sync_b = create_knowledge_sync(
        db_path=db_b_path,
        transit_dir=yard_dir,
        node_id="node_b",
        state_dir=node_b_dir / ".transit_state",
    )

    yield {
        "yard": yard_dir,
        "node_a": {"conn": conn_a, "db_path": db_a_path, "sync": sync_a, "id": "node_a"},
        "node_b": {"conn": conn_b, "db_path": db_b_path, "sync": sync_b, "id": "node_b"},
    }

    conn_a.close()
    conn_b.close()


def test_chunk_key_generation():
    """Stable chunk keys are deterministic and change when content_version changes."""
    key1 = generate_chunk_key("document", "reports/q1.pdf", "hash_abc_123", 0)
    key2 = generate_chunk_key("document", "reports/q1.pdf", "hash_abc_123", 0)
    assert key1 == key2
    assert key1.startswith("chunk:")

    # Different chunk index
    key_idx1 = generate_chunk_key("document", "reports/q1.pdf", "hash_abc_123", 1)
    assert key1 != key_idx1

    # Modified document (new content_version) produces a new chunk key
    key_modified = generate_chunk_key("document", "reports/q1.pdf", "hash_def_456", 0)
    assert key1 != key_modified


@requires_transit_sync
def test_t01_two_nodes_exclusive_claim(transit_environment):
    """Criterion 1: Both nodes see the same chunk, but only one node obtains the claim."""
    env = transit_environment
    conn_a = env["node_a"]["conn"]
    sync_a = env["node_a"]["sync"]
    conn_b = env["node_b"]["conn"]
    sync_b = env["node_b"]["sync"]

    # Register the same document chunk on Node A
    chunk_key = ChunkTaskManager.register_task(
        conn_a,
        source_type="document",
        canonical_id="spec.md",
        content_version="sha256_ver1",
        chunk_index=0,
    )

    # Node A claims the task with a 600-second lease
    claimed_a = ChunkTaskManager.claim_task(
        conn_a,
        chunk_key=chunk_key,
        node_id="node_a",
        agent_id="agent_alpha",
        lease_seconds=600,
    )
    assert claimed_a is True

    # Node A pushes snapshot
    snapshot_a = sync_a.push()
    assert snapshot_a.manifest_path.is_file()

    # Node B pulls snapshot
    pull_report_b = sync_b.pull()
    assert len(pull_report_b) == 1
    assert pull_report_b[0].inserted == 1

    # Node B verifies that the chunk is already claimed by Node A with active lease
    task_on_b = ChunkTaskManager.get_task(conn_b, chunk_key)
    assert task_on_b is not None
    assert task_on_b["status"] == "claimed"
    assert task_on_b["claimed_by_node"] == "node_a"

    # Node B attempts to claim the chunk -> must be REJECTED
    claimed_b = ChunkTaskManager.claim_task(
        conn_b,
        chunk_key=chunk_key,
        node_id="node_b",
        agent_id="agent_beta",
        lease_seconds=600,
    )
    assert claimed_b is False

    # Node A transitions to processing
    started = ChunkTaskManager.start_processing(conn_a, chunk_key, node_id="node_a")
    assert started is True


@requires_transit_sync
def test_t02_result_converges_once(transit_environment):
    """Criterion 2: Result appears after pull on both nodes exactly once."""
    env = transit_environment
    conn_a = env["node_a"]["conn"]
    sync_a = env["node_a"]["sync"]
    conn_b = env["node_b"]["conn"]
    sync_b = env["node_b"]["sync"]

    chunk_key = ChunkTaskManager.register_task(
        conn_a,
        source_type="document",
        canonical_id="manual.pdf",
        content_version="sha256_man_v1",
        chunk_index=0,
    )

    # Node A claims and completes task
    ChunkTaskManager.claim_task(conn_a, chunk_key, "node_a", "worker_a")
    completed = ChunkTaskManager.complete_task(
        conn_a,
        chunk_key=chunk_key,
        node_id="node_a",
        summary="This document explains distributed cluster coordination.",
        keywords="distributed,cluster,transit",
        domain="engineering",
        model="gemini-flash",
    )
    assert completed is True

    # Push from Node A, pull to Node B
    sync_a.push()
    pull_b = sync_b.pull()
    assert len(pull_b) == 1

    # Node B sees status == 'done' with the exact summary
    task_b = ChunkTaskManager.get_task(conn_b, chunk_key)
    assert task_b["status"] == "done"
    assert "distributed cluster coordination" in task_b["summary"]
    assert task_b["model"] == "gemini-flash"

    # Node B cannot re-claim or re-process the completed chunk
    claim_attempt = ChunkTaskManager.claim_task(conn_b, chunk_key, "node_b", "worker_b")
    assert claim_attempt is False


@requires_transit_sync
def test_t03_expired_claim_takeover(transit_environment):
    """Criterion 3: Expired claim can be safely taken over by another node."""
    env = transit_environment
    conn_a = env["node_a"]["conn"]
    sync_a = env["node_a"]["sync"]
    conn_b = env["node_b"]["conn"]
    sync_b = env["node_b"]["sync"]

    chunk_key = ChunkTaskManager.register_task(
        conn_a,
        source_type="skill",
        canonical_id="data-analysis",
        content_version="sha256_skill_v1",
        chunk_index=0,
    )

    # Node A claims with an expired lease in the past
    past_time = utc_now() - timedelta(minutes=15)
    past_lease = past_time + timedelta(minutes=5)  # expired 10 minutes ago
    with conn_a:
        conn_a.execute(
            """
            UPDATE chunk_tasks
            SET status = 'claimed',
                claimed_by_node = 'node_a',
                claimed_by_agent = 'stale_worker',
                claimed_at = ?,
                lease_expires_at = ?,
                heartbeat_at = ?,
                updated_at = ?
            WHERE chunk_key = ?
            """,
            (
                iso_timestamp(past_time),
                iso_timestamp(past_lease),
                iso_timestamp(past_time),
                iso_timestamp(past_time),
                chunk_key,
            ),
        )

    # Push Node A's stale state to Node B
    sync_a.push()
    sync_b.pull()

    # Node B sees the expired task
    task_b_before = ChunkTaskManager.get_task(conn_b, chunk_key)
    assert task_b_before["status"] == "claimed"
    assert task_b_before["claimed_by_node"] == "node_a"

    # Node B takes over the expired claim
    takeover_success = ChunkTaskManager.claim_task(
        conn_b,
        chunk_key=chunk_key,
        node_id="node_b",
        agent_id="rescuer_b",
        lease_seconds=300,
    )
    assert takeover_success is True

    # Node B now owns the claim
    task_b_after = ChunkTaskManager.get_task(conn_b, chunk_key)
    assert task_b_after["claimed_by_node"] == "node_b"
    assert task_b_after["claimed_by_agent"] == "rescuer_b"

    # Node B completes the work
    ChunkTaskManager.complete_task(
        conn_b,
        chunk_key=chunk_key,
        node_id="node_b",
        summary="Analysis completed by Node B after Node A went silent.",
    )

    # Sync back to Node A
    sync_b.push()
    pull_a = sync_a.pull()
    assert len(pull_a) == 1

    # Node A now reflects 'done' from Node B
    task_a_final = ChunkTaskManager.get_task(conn_a, chunk_key)
    assert task_a_final["status"] == "done"
    assert task_a_final["claimed_by_node"] == "node_b"


@requires_transit_sync
def test_t04_repeated_pull_is_idempotent(transit_environment):
    """Criterion 4: Repeated pull operations are strictly idempotent."""
    env = transit_environment
    conn_a = env["node_a"]["conn"]
    sync_a = env["node_a"]["sync"]
    conn_b = env["node_b"]["conn"]
    sync_b = env["node_b"]["sync"]

    # Populate multiple tasks on Node A
    for i in range(5):
        key = ChunkTaskManager.register_task(
            conn_a,
            source_type="document",
            canonical_id=f"doc_{i}.txt",
            content_version=f"hash_{i}",
            chunk_index=0,
        )
        if i % 2 == 0:
            ChunkTaskManager.claim_task(conn_a, key, "node_a", "worker_a")
            ChunkTaskManager.complete_task(conn_a, key, "node_a", f"Summary {i}")

    # Initial sync A -> B
    snap_a = sync_a.push()
    first_pull = sync_b.pull()
    assert len(first_pull) == 1
    assert first_pull[0].inserted == 5

    # Second pull without changes on A -> no pending snapshots
    second_pull = sync_b.pull()
    assert len(second_pull) == 0

    # Test merge policy idempotency directly against the same snapshot
    report = KnowledgeDigestMergePolicy().merge(
        local=conn_b,
        remote=conn_a,
        snapshot=snap_a,
    )
    assert report.inserted == 0
    assert report.updated == 0
    assert report.unchanged == 5


@requires_transit_sync
def test_t05_secret_negative_test_and_quick_check(transit_environment):
    """Criterion 5: Secret negative test blocks export, and PRAGMA quick_check stays ok."""
    env = transit_environment
    conn_a = env["node_a"]["conn"]
    sync_a = env["node_a"]["sync"]
    conn_b = env["node_b"]["conn"]

    # Verify PRAGMA quick_check on both nodes
    check_a = conn_a.execute("PRAGMA quick_check").fetchone()[0]
    check_b = conn_b.execute("PRAGMA quick_check").fetchone()[0]
    assert check_a == "ok"
    assert check_b == "ok"

    # Register task
    chunk_key = ChunkTaskManager.register_task(
        conn_a,
        source_type="document",
        canonical_id="credentials.txt",
        content_version="secret_hash",
        chunk_index=0,
    )
    ChunkTaskManager.claim_task(conn_a, chunk_key, "node_a", "worker_a")

    # Infiltrate a live API secret pattern into free-text summary
    with conn_a:
        conn_a.execute(
            """
            UPDATE chunk_tasks
            SET status = 'done',
                summary = 'Internal api key is AIzaSyD98765432101234567890abcdefghijklm',
                updated_at = ?
            WHERE chunk_key = ?
            """,
            (iso_timestamp(), chunk_key),
        )

    # Attempting to publish MUST fail closed due to secret scanner
    with pytest.raises(SyncError, match="[Cc]redential|[Ss]ecret"):
        sync_a.push()

    # Clean the secret
    with conn_a:
        conn_a.execute(
            """
            UPDATE chunk_tasks
            SET summary = 'Safe summary without secret keys.',
                updated_at = ?
            WHERE chunk_key = ?
            """,
            (iso_timestamp(), chunk_key),
        )

    # Now push succeeds
    pub_clean = sync_a.push()
    assert pub_clean.manifest_path.is_file()

    # Quick check remains ok
    check_a_after = conn_a.execute("PRAGMA quick_check").fetchone()[0]
    assert check_a_after == "ok"


# ---------------------------------------------------------------------------
# Lifecycle tests that run without the optional sqlite-transit-sync package
# ---------------------------------------------------------------------------


@pytest.fixture
def single_node(tmp_path):
    conn = ensure_schema(tmp_path / "knowledge.db")
    yield conn
    conn.close()


def test_iso_timestamp_is_fixed_width_utc():
    from datetime import datetime, timezone, timedelta as td

    whole = iso_timestamp(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    frac = iso_timestamp(datetime(2026, 1, 1, 12, 0, 0, 500, tzinfo=timezone.utc))
    shifted = iso_timestamp(datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone(td(hours=2))))
    assert len(whole) == len(frac)
    assert whole < frac
    assert shifted == whole


def test_register_task_is_idempotent(single_node):
    key1 = ChunkTaskManager.register_task(single_node, "document", "a.md", "v1", 0)
    key2 = ChunkTaskManager.register_task(single_node, "document", "a.md", "v1", 0)
    assert key1 == key2
    count = single_node.execute("SELECT COUNT(*) FROM chunk_tasks").fetchone()[0]
    assert count == 1


def test_lifecycle_claim_process_heartbeat_done(single_node):
    key = ChunkTaskManager.register_task(single_node, "document", "b.md", "v1", 0)
    assert ChunkTaskManager.claim_task(single_node, key, "n1", "agent") is True
    # second claim on an active lease is rejected
    assert ChunkTaskManager.claim_task(single_node, key, "n2", "agent") is False
    # only the owning node may start processing
    assert ChunkTaskManager.start_processing(single_node, key, "n2") is False
    assert ChunkTaskManager.start_processing(single_node, key, "n1") is True
    assert ChunkTaskManager.heartbeat(single_node, key, "n1") is True
    assert ChunkTaskManager.complete_task(single_node, key, "n1", "summary") is True
    task = ChunkTaskManager.get_task(single_node, key)
    assert task["status"] == "done"
    # done is terminal
    assert ChunkTaskManager.claim_task(single_node, key, "n2", "agent") is False
    assert ChunkTaskManager.heartbeat(single_node, key, "n1") is False


def test_get_task_does_not_change_row_factory(single_node):
    before = single_node.row_factory
    key = ChunkTaskManager.register_task(single_node, "wiki", "Page", "v1", 0)
    assert ChunkTaskManager.get_task(single_node, key)["chunk_key"] == key
    assert single_node.row_factory is before


def test_failed_task_can_be_reclaimed(single_node):
    key = ChunkTaskManager.register_task(single_node, "skill", "s", "v1", 0)
    ChunkTaskManager.claim_task(single_node, key, "n1", "agent")
    assert ChunkTaskManager.fail_task(single_node, key, "n1", "boom") is True
    assert ChunkTaskManager.get_task(single_node, key)["status"] == "error"
    assert ChunkTaskManager.claim_task(single_node, key, "n2", "agent") is True


def test_expired_lease_takeover_without_sync(single_node):
    key = ChunkTaskManager.register_task(single_node, "document", "c.md", "v1", 0)
    past = utc_now() - timedelta(minutes=10)
    assert ChunkTaskManager.claim_task(single_node, key, "n1", "agent", lease_seconds=60, now=past)
    assert ChunkTaskManager.claim_task(single_node, key, "n2", "agent") is True
    assert ChunkTaskManager.get_task(single_node, key)["claimed_by_node"] == "n2"


@pytest.mark.parametrize(
    "local, remote, expected",
    [
        ({"status": "done"}, {"status": "claimed"}, False),
        ({"status": "claimed", "lease_expires_at": "9999"}, {"status": "done"}, True),
        ({"status": "pending"}, {"status": "error"}, True),
        ({"status": "pending"}, {"status": "claimed", "lease_expires_at": "9999"}, True),
        (
            {"status": "claimed", "lease_expires_at": "9999", "claimed_at": "2026-01-02"},
            {"status": "claimed", "lease_expires_at": "9999", "claimed_at": "2026-01-01"},
            True,
        ),
        (
            {"status": "claimed", "lease_expires_at": "9999", "claimed_at": "x", "claimed_by_node": "a"},
            {"status": "claimed", "lease_expires_at": "9999", "claimed_at": "x", "claimed_by_node": "b"},
            False,
        ),
    ],
)
def test_resolve_chunk_conflict(local, remote, expected):
    remote_wins, _ = KnowledgeDigestMergePolicy._resolve_chunk_conflict(local, remote, iso_timestamp())
    assert remote_wins is expected


def test_create_knowledge_sync_reports_missing_dependency(tmp_path):
    if TRANSIT_SYNC_AVAILABLE:
        pytest.skip("sqlite-transit-sync installed")
    with pytest.raises(ImportError, match="sqlite-transit-sync"):
        create_knowledge_sync(tmp_path / "k.db", tmp_path / "yard", "n1")
