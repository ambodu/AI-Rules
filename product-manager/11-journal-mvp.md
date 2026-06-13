# 11 — Journal MVP：用 Gate-UX 闭环验证反馈机制本身

## 解决的问题

08-critical-review 指出 v3 最大的未解问题：

> "反馈机制的最终锚点到底是什么？谁来看守看守者？"

这份文档给出一个具体的、可运行的答案：
**Gate 的每一次判断都记录在 Journal 中。当 UX 数据回来时，对比 Gate 预测与 UX 现实。Gate 判 PASS 但用户痛苦 → 反馈机制有问题。**

## 架构

```
Gate 判断 ──→ Journal (append-only) ──→ 等待 UX 反馈
                                              │
                                              对比
                                              │
                          ┌───────────────────┴───────────────────┐
                          ▼                                       ▼
                  Gate 预测 vs UX 现实一致                  Gate 预测 vs UX 现实不一致
                          │                                       │
                          ▼                                       ▼
                    反馈机制正确                              反馈机制有盲区
                                                                    │
                                                                    ▼
                                                           更新 Gate / AC / Eval
```

## 代码

### journal.py — Append-Only 日志

```python
"""Journal - 不可变的 Gate 决策 + UX 结果记录（SQLite MVP）"""

import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("journal.db")

def init():
    """初始化 Journal 数据库"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            artifact_hash TEXT NOT NULL,
            ac_hash TEXT NOT NULL,
            gate_result TEXT NOT NULL,       -- JSON: 完整的 Gate 输出
            ux_outcome TEXT,                  -- JSON: 后验 UX 数据，可能为 NULL
            ux_recorded_at TEXT,              -- UX 数据写入时间
            discrepancy TEXT,                 -- JSON: Gate vs UX 差异分析
            prev_hash TEXT NOT NULL,          -- 链上前一条记录的哈希
            entry_hash TEXT NOT NULL          -- 本条记录的哈希
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            total_gate_passes INTEGER,
            gate_pass_ux_bad INTEGER,        -- Gate说PASS但UX差
            total_gate_fails INTEGER,
            gate_fail_ux_ok INTEGER,         -- Gate说FAIL但UX其实能接受
            consistency_rate REAL,            -- Gate vs UX 一致率
            report TEXT                       -- 完整校准报告 JSON
        )
    """)
    conn.commit()
    return conn

def _hash(*args) -> str:
    """计算多个参数的 SHA-256"""
    return hashlib.sha256("|".join(str(a) for a in args).encode()).hexdigest()[:16]

def append(conn, agent_id: str, task_id: str, artifact: dict, ac: dict, gate_result: dict) -> str:
    """追加一条 Gate 决策记录。返回 txn_id。"""
    txn_id = _hash(agent_id, task_id, datetime.now(timezone.utc).isoformat())
    artifact_hash = _hash(json.dumps(artifact, sort_keys=True))
    ac_hash = _hash(json.dumps(ac, sort_keys=True))

    # 获取上一条的哈希（链式结构）
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
    """, (
        txn_id, timestamp, agent_id, task_id,
        artifact_hash, ac_hash,
        json.dumps(gate_result, ensure_ascii=False),
        prev_hash, entry_hash
    ))
    conn.commit()
    return txn_id

def record_ux(conn, txn_id: str, ux_data: dict):
    """记录 UX 后验数据"""
    conn.execute("""
        UPDATE journal
        SET ux_outcome = ?,
            ux_recorded_at = ?
        WHERE txn_id = ?
    """, (
        json.dumps(ux_data, ensure_ascii=False),
        datetime.now(timezone.utc).isoformat(),
        txn_id
    ))
    conn.commit()

def analyze_discrepancy(conn, txn_id: str) -> dict:
    """分析单条记录的 Gate vs UX 差异"""
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
        return {
            "status": "consistent",
            "gate_pass": gate_pass,
            "ux_good": ux_good,
            "detail": "Gate 判断与 UX 结果一致"
        }
    elif gate_pass and not ux_good:
        return {
            "status": "discrepancy",
            "type": "FALSE_POSITIVE",
            "gate_pass": True,
            "ux_good": False,
            "detail": "Gate 判 PASS 但用户不满意 — Gate 有盲区",
            "ux_detail": ux
        }
    else:
        return {
            "status": "discrepancy",
            "type": "FALSE_NEGATIVE",
            "gate_pass": False,
            "ux_good": True,
            "detail": "Gate 判 FAIL 但用户其实能接受 — Gate 可能过严",
            "gate_detail": gate
        }

def calibrate(conn, start_date: str, end_date: str) -> dict:
    """
    定期校准：统计一段时间内的 Gate vs UX 一致率。
    这是判断"反馈机制是否正确"的核心指标。
    """
    rows = conn.execute("""
        SELECT txn_id, gate_result, ux_outcome
        FROM journal
        WHERE timestamp BETWEEN ? AND ?
          AND ux_outcome IS NOT NULL
    """, (start_date, end_date)).fetchall()

    total = len(rows)
    if total == 0:
        return {"error": "No UX data available for this period"}

    gate_pass_ux_bad = 0    # 假阳性：Gate放行但用户不满意
    gate_fail_ux_ok = 0     # 假阴性：Gate拦截但用户其实OK
    consistent = 0

    for txn_id, gate_json, ux_json in rows:
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

    consistency_rate = consistent / total if total > 0 else 0

    report = {
        "period": f"{start_date} ~ {end_date}",
        "total_ux_samples": total,
        "consistent": consistent,
        "consistency_rate": round(consistency_rate, 3),
        "false_positive": gate_pass_ux_bad,
        "false_negative": gate_fail_ux_ok,
        "health": (
            "HEALTHY" if consistency_rate >= 0.85
            else "WARNING" if consistency_rate >= 0.70
            else "CRITICAL"
        )
    }

    # 保存校准记录
    conn.execute("""
        INSERT INTO calibrations (timestamp, period_start, period_end,
            total_gate_passes, gate_pass_ux_bad,
            total_gate_fails, gate_fail_ux_ok,
            consistency_rate, report)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        start_date, end_date,
        total - gate_fail_ux_ok, gate_pass_ux_bad,
        gate_fail_ux_ok + (total - consistent - gate_pass_ux_bad), gate_fail_ux_ok,
        consistency_rate,
        json.dumps(report, ensure_ascii=False)
    ))
    conn.commit()

    return report


def verify_chain(conn) -> dict:
    """验证整条哈希链的完整性"""
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
```

### ux_collector.py — UX 信号采集

```python
"""UX 信号采集 — 把用户行为转化为可对比的 UX 判断"""

def collect_ux_for_artifact(txn_id: str, user_session_data: dict) -> dict:
    """
    给定用户 session 数据，返回结构化的 UX 判断。
    在实际系统中，这些数据来自 Amplitude/Mixpanel/埋点。
    """
    return {
        "txn_id": txn_id,
        "task_completed": user_session_data.get("goal_achieved", False),
        "user_satisfaction": _infer_satisfaction(user_session_data),
        "frustration_signals": {
            "repeat_actions": user_session_data.get("repeat_same_action_count", 0),
            "rage_clicks": user_session_data.get("rapid_click_count", 0),
            "session_abandoned": user_session_data.get("bounced", False),
            "sought_help": user_session_data.get("clicked_help", False),
        },
        "efficiency": {
            "time_to_complete_seconds": user_session_data.get("task_duration_sec"),
            "steps_to_complete": user_session_data.get("steps_count"),
            "expected_steps": user_session_data.get("expected_steps", 3),
        }
    }

def _infer_satisfaction(data: dict) -> int:
    """
    从行为数据推断用户满意度（1-5）。
    在没有显式评分的情况下，用行为做代理指标。
    """
    score = 3  # 中性
    if data.get("goal_achieved"):
        score += 1
    if data.get("repeat_same_action_count", 0) > 2:
        score -= 1
    if data.get("rapid_click_count", 0) > 3:
        score -= 1
    if data.get("bounced"):
        score -= 2
    if data.get("task_duration_sec", 0) < 30 and data.get("goal_achieved"):
        score += 1
    return max(1, min(5, score))
```

### calibrate.py — 定期校准脚本

```python
#!/usr/bin/env python3
"""每周校准：检查反馈机制是否健康"""
import sys
from datetime import datetime, timedelta
from journal import init, calibrate

conn = init()

# 校准过去 7 天
end = datetime.utcnow().isoformat()
start = (datetime.utcnow() - timedelta(days=7)).isoformat()

report = calibrate(conn, start, end)
print("=== 周度反馈机制校准报告 ===")
print(f"周期: {report.get('period', 'N/A')}")
print(f"UX样本数: {report.get('total_ux_samples', 0)}")
print(f"Gate-UX 一致率: {report.get('consistency_rate', 0):.1%}")
print(f"假阳性(Gate PASS但UX差): {report.get('false_positive', 0)}")
print(f"假阴性(Gate FAIL但UX OK): {report.get('false_negative', 0)}")
print(f"健康度: {report.get('health', 'UNKNOWN')}")

if report.get('health') == 'CRITICAL':
    print("\nACTION REQUIRED: 反馈机制一致率低于 70%，Gate 需要重新设计。")
    print("1. 检查假阳性 Case → 找到 Gate 的盲区 → 升级 AC/Eval")
    print("2. 检查假阴性 Case → 判断是否 Gate 过严 → 调整阈值")
    sys.exit(1)
elif report.get('health') == 'WARNING':
    print("\nWARNING: 一致率低于 85%，关注趋势。")
    sys.exit(0)
else:
    print("\nHEALTHY: 反馈机制工作正常。")
    sys.exit(0)
```

## 运行

```bash
# 1. 启动 Journal
python -c "from journal import init; init(); print('Journal ready')"

# 2. 模拟一次 Gate 判断 + 后续 UX 反馈
python << 'PY'
from journal import init, append, record_ux, analyze_discrepancy

conn = init()

# Gate 判断
gate_result = {"passed": True, "levels": ["L1", "L2", "L3"]}
artifact = {"component_name": "LoginButton", "props": {"color": "#0066FF"}}
ac = {"criteria": [{"id": "AC-1", "description": "color is #0066FF"}]}

txn_id = append(conn, "agent-1", "task-42", artifact, ac, gate_result)
print(f"Recorded: {txn_id}")

# ... 几天后，UX 数据回来了 ...
ux_data = {
    "goal_achieved": False,
    "task_duration_sec": 85,
    "repeat_same_action_count": 4,
    "rapid_click_count": 6,
    "bounced": True,
    "clicked_help": True
}
record_ux(conn, txn_id, ux_data)

# 分析差异
diff = analyze_discrepancy(conn, txn_id)
print(f"Discrepancy: {diff}")
# 预期输出: FALSE_POSITIVE — Gate 说 PASS 但用户很痛苦
PY

# 3. 跑周度校准
python calibrate.py
```

## 关键洞察：Gate 正确 ≠ 产品正确

```
                    Gate 判断
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        PASS          PASS         FAIL
          │            │            │
    用户满意      用户痛苦      用户其实OK
    (一致)      (假阳性!)     (假阴性!)
                   │
                   ▼
           Gate 的盲区在这里
           你的 AC 没有覆盖用户真正关心的问题
```

**假阳性是最危险的。** 它意味着你的反馈机制在说"一切正常"，但用户在用行动告诉你"这个产品很烂"。

如果你的周度校准报告显示假阳性在上升，不是去修 Bug——是去修你的验收标准。**AC 没有覆盖用户真正关心的东西。**

## 反馈机制的健康度仪表盘

每个 PM 每周都应该看这三个数字：

| 指标 | 含义 | 健康值 |
|------|------|--------|
| **Gate-UX 一致率** | Gate 判断与最终 UX 结果的吻合度 | > 85% |
| **假阳性率** | Gate 放行但用户不满意的比例 | < 5% |
| **UX 数据覆盖率** | 有 UX 后验数据的 Gate 判断占比 | > 50% |

如果这三个指标持续恶化，不是执行 Agent 的问题——**是反馈机制设计有问题。**

## 诚实声明

| 限制 | 说明 |
|------|------|
| SQLite 单机 | 生产环境需要分布式 Journal，但 MVP 够了 |
| UX 数据依赖埋点 | 如果你的产品没有埋点，UX 数据需要手动导入 |
| 行为推断满意度不完美 | 用户可能完成了任务但仍然不满意（比如功能对了但太难用） |
| 需要一定样本量 | 单个 Case 的 Gate-UX 差异可能是噪音，需要聚合 |

## Bootstrap 与 Journal 的关系

10-bootstrap-day1 让你跑起 Gate。
11-journal-mvp 让 Gate 的每一个判断都被 UX 结果验证。

```
Bootstrap (10): Gate 能跑了
      +
Journal (11): Gate 的判断被 UX 检验
      =
反馈机制可以被验证其正确性
```

这才是用户问题的最终答案：**反馈机制是否正确，不是自己说了算——是用户的行为数据说了算。**
