"""Journal - append-only decision log with SHA-256 chain integrity."""

import sqlite3
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "journal.db"


def init(db_path: str = None) -> sqlite3.Connection:
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            artifact_hash TEXT NOT NULL,
            ac_hash TEXT NOT NULL,
            gate_result TEXT NOT NULL,
            ux_outcome TEXT,
            ux_recorded_at TEXT,
            discrepancy TEXT,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_gate_passes INTEGER,
            gate_pass_ux_bad INTEGER,
            total_gate_fails INTEGER,
            gate_fail_ux_ok INTEGER,
            consistency_rate REAL,
            report TEXT
        )
    """)
    conn.commit()
    return conn


def _hash(*args) -> str:
    return hashlib.sha256("|".join(str(a) for a in args).encode()).hexdigest()[:16]


def append(conn: sqlite3.Connection, agent_id: str, task_id: str,
           artifact: dict, ac: dict, gate_result: dict) -> str:
    txn_id = _hash(agent_id, task_id, datetime.now(timezone.utc).isoformat())
    artifact_hash = _hash(json.dumps(artifact, sort_keys=True))
    ac_hash = _hash(json.dumps(ac, sort_keys=True))

    last = conn.execute(
        "SELECT entry_hash FROM journal ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = last[0] if last else "GENESIS"

    timestamp = datetime.now(timezone.utc).isoformat()
    entry_hash = _hash(txn_id, timestamp, artifact_hash, ac_hash, prev_hash)

    conn.execute("""
        INSERT INTO journal (txn_id, timestamp, agent_id, task_id,
            artifact_hash, ac_hash, gate_result, prev_hash, entry_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (txn_id, timestamp, agent_id, task_id, artifact_hash, ac_hash,
          json.dumps(gate_result, ensure_ascii=False), prev_hash, entry_hash))
    conn.commit()
    return txn_id


def record_ux(conn: sqlite3.Connection, txn_id: str, ux_data: dict):
    conn.execute("""
        UPDATE journal SET ux_outcome = ?, ux_recorded_at = ?
        WHERE txn_id = ?
    """, (json.dumps(ux_data, ensure_ascii=False),
          datetime.now(timezone.utc).isoformat(), txn_id))
    conn.commit()


def analyze_discrepancy(conn: sqlite3.Connection, txn_id: str) -> dict:
    row = conn.execute(
        "SELECT gate_result, ux_outcome FROM journal WHERE txn_id = ?", (txn_id,)
    ).fetchone()
    if not row or not row[1]:
        return {"status": "pending", "reason": "UX data not yet available"}

    gate = json.loads(row[0])
    ux = json.loads(row[1])
    gate_pass = gate.get("passed", False)
    ux_good = ux.get("task_completed", False) and ux.get("user_satisfaction", 0) >= 3

    if gate_pass == ux_good:
        return {"status": "consistent", "gate_pass": gate_pass, "ux_good": ux_good,
                "detail": "Gate and UX agree"}
    elif gate_pass and not ux_good:
        return {"status": "discrepancy", "type": "FALSE_POSITIVE",
                "gate_pass": True, "ux_good": False,
                "detail": "Gate PASS but UX bad - Gate has a blind spot"}
    else:
        return {"status": "discrepancy", "type": "FALSE_NEGATIVE",
                "gate_pass": False, "ux_good": True,
                "detail": "Gate FAIL but UX OK - Gate may be too strict"}


def calibrate(conn: sqlite3.Connection, start_date: str, end_date: str) -> dict:
    rows = conn.execute("""
        SELECT txn_id, gate_result, ux_outcome FROM journal
        WHERE timestamp BETWEEN ? AND ? AND ux_outcome IS NOT NULL
    """, (start_date, end_date)).fetchall()

    total = len(rows)
    if total == 0:
        return {"error": "No UX data for this period"}

    gate_pass_ux_bad = 0
    gate_fail_ux_ok = 0
    consistent = 0

    for _, gate_json, ux_json in rows:
        gate = json.loads(gate_json)
        ux = json.loads(ux_json)
        gate_pass = gate.get("passed", False)
        ux_good = ux.get("task_completed", False) and ux.get("user_satisfaction", 0) >= 3
        if gate_pass == ux_good:
            consistent += 1
        elif gate_pass and not ux_good:
            gate_pass_ux_bad += 1
        else:
            gate_fail_ux_ok += 1

    rate = consistent / total if total > 0 else 0
    report = {
        "period": f"{start_date} ~ {end_date}",
        "total_ux_samples": total,
        "consistent": consistent,
        "consistency_rate": round(rate, 3),
        "false_positive": gate_pass_ux_bad,
        "false_negative": gate_fail_ux_ok,
        "health": "HEALTHY" if rate >= 0.85 else "WARNING" if rate >= 0.70 else "CRITICAL"
    }

    conn.execute("""
        INSERT INTO calibrations (timestamp, period_start, period_end,
            total_gate_passes, gate_pass_ux_bad, total_gate_fails,
            gate_fail_ux_ok, consistency_rate, report)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now(timezone.utc).isoformat(), start_date, end_date,
          total - gate_fail_ux_ok, gate_pass_ux_bad,
          gate_fail_ux_ok + (total - consistent - gate_pass_ux_bad),
          gate_fail_ux_ok, rate, json.dumps(report, ensure_ascii=False)))
    conn.commit()
    return report


def verify_chain(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT id, entry_hash, prev_hash FROM journal ORDER BY id").fetchall()
    broken = []
    for i, (row_id, entry_hash, prev_hash) in enumerate(rows):
        if i == 0 and prev_hash != "GENESIS":
            broken.append(row_id)
        elif i > 0 and prev_hash != rows[i-1][1]:
            broken.append(row_id)
    return {
        "total_entries": len(rows),
        "integrity": "INTACT" if not broken else "BROKEN",
        "broken_at": broken if broken else None
    }
