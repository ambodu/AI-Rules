#!/usr/bin/env python3
"""End-to-end tests for AI Product OS."""

import json
import tempfile
import os
import sys
from pathlib import Path

os.chdir(Path(__file__).parent)

from capability import issue_token
from journal import init, calibrate, analyze_discrepancy, record_ux, verify_chain
from gate import gate


def test_capability_token():
    """Token issuance and permission checks work."""
    token = issue_token("agent-1", [
        {"resource": "product/artifact", "ops": ["submit"]}
    ])
    assert not token.is_expired(), "Token should not be expired"
    assert token.can("product/artifact", "submit"), "Should have submit"
    assert not token.can("product/artifact", "delete"), "Should NOT have delete"
    print("  PASS test_capability_token")


def test_gate_happy_path():
    """Full gate pipeline passes for valid artifact."""
    artifact = {
        "component_name": "SearchBar",
        "props": {"color": "#333333", "borderRadius": 6, "label": "Search"}
    }
    ac = {
        "task": "search-bar",
        "schema": {
            "type": "object",
            "required": ["component_name", "props"],
            "properties": {
                "component_name": {"type": "string"},
                "props": {
                    "type": "object",
                    "required": ["label"],
                    "properties": {"label": {"type": "string", "minLength": 1}}
                }
            }
        },
        "criteria": [{"id": "AC-1", "description": "has label"}],
        "min_score": 1  # Low threshold since no real LLM call
    }
    result = gate("agent-1", artifact, ac)
    assert result["passed"], f"Gate should pass: {result}"
    assert result["txn_id"], "Should have transaction ID"
    print("  PASS test_gate_happy_path")


def test_l0_denies_unauthorized():
    """L0 blocks agents without tokens."""
    artifact = {"test": "data"}
    ac = {"task": "test", "min_score": 1}
    result = gate("unauthorized-agent", artifact, ac)
    assert not result["passed"], "Should be denied"
    assert result["failed_at"] == "L0"
    print("  PASS test_l0_denies_unauthorized")


def test_l2_blocks_sql_injection():
    """L2 blocks artifacts containing SQL injection patterns."""
    issue_token("agent-2", [{"resource": "product/artifact", "ops": ["submit"]}])
    artifact = {"query": "DROP TABLE users; SELECT * FROM admins"}
    ac = {"task": "test", "min_score": 1}
    result = gate("agent-2", artifact, ac)
    assert not result["passed"], "Should be blocked"
    assert result["failed_at"] == "L2", f"Should fail at L2, got: {result}"
    print("  PASS test_l2_blocks_sql_injection")


def test_journal_integrity():
    """Journal chain is intact after operations."""
    conn = init()
    # Run a gate to create entries
    issue_token("agent-3", [{"resource": "product/artifact", "ops": ["submit"]}])
    gate("agent-3", {"name": "Test"}, {"task": "journal-test", "min_score": 1})

    chain = verify_chain(conn)
    assert chain["integrity"] == "INTACT", f"Chain broken: {chain}"
    assert chain["total_entries"] >= 1
    print("  PASS test_journal_integrity")


def test_ux_calibration():
    """Gate-UX calibration detects discrepancies."""
    conn = init()
    issue_token("agent-4", [{"resource": "product/artifact", "ops": ["submit"]}])

    # Create a passing artifact
    gate("agent-4", {"name": "Good"}, {"task": "ux-test", "min_score": 1})

    # Find the txn and inject fake UX
    row = conn.execute(
        "SELECT txn_id FROM journal ORDER BY id DESC LIMIT 1"
    ).fetchone()
    record_ux(conn, row[0], {"task_completed": True, "user_satisfaction": 5})

    diff = analyze_discrepancy(conn, row[0])
    assert diff["status"] == "consistent", f"Should be consistent: {diff}"
    print("  PASS test_ux_calibration")


if __name__ == "__main__":
    print("AI Product OS - E2E Tests\n")
    tests = [
        test_capability_token,
        test_gate_happy_path,
        test_l0_denies_unauthorized,
        test_l2_blocks_sql_injection,
        test_journal_integrity,
        test_ux_calibration,
    ]
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  FAIL {test.__name__}: {e}")
            sys.exit(1)

    print(f"\n{len(tests)}/{len(tests)} tests passed.")
