# 14 — PM 的日常工作流：三个真实场景

> 前 13 份文档描述了系统。这份文档展示你怎么用这个系统做一天的 PM。

## 角色设定

你是产品经理。你的 AI Product OS 已经在跑：
- Gate (L0→L3) 验收所有 AI 产出
- Journal 记录所有决策
- Watchdog 监控运行时
- 每周 calibrate.py 检查反馈机制健康度

以下是你的三天。

## 场景 1：周三 9:00 AM — Bug 修复验收

AI 执行 Agent 昨晚修了一个 Bug。你早上打开 PM Console。

### 你看到的

```
$ python gate_v2.py --agent agent-fix-42 --artifact fix_output.json --ac ac/payment_bug.json

{
  "passed": true,
  "txn_id": "txn-8a3f",
  "results": {
    "l0": {"passed": true, "detail": "Capability check passed"},
    "l1": {"passed": true, "detail": "Schema valid"},
    "l2": {"passed": true, "detail": "All policies passed"},
    "l3": {
      "passed": true,
      "score": 4,
      "reasoning": "修复正确，边界情况处理良好。只缺少一个非关键的日志语句。"
    }
  }
}
```

Gate 全绿。L3 得分 4/5。

### 你会做什么

1. **快速意图审查**（5 分钟）— 不是审查代码，是审查产品意图：
   - 这个修复真的解决了用户报告的问题吗？→ 对照原始 Bug 描述
   - Scope 是否受控？Agent 是否偷偷改了不相干的东西？→ Journal 可以查 diff 范围
   - 有没有引入新的 UX 问题？→ 在本地跑一下，体验 30 秒

2. **决定**：Approve。产出进入灰度。

3. **Journal 记录**：
```
$ python -c "
from journal import append, init
conn = init()
# PM 的决定作为新的 Journal Entry
append(conn, 'pm-fffh', 'task-42-review', 
       {'action': 'approve', 'txn_id': 'txn-8a3f'},
       {'review': 'intent-match, scope-controlled, ux-ok'})
"
```

### 如果 L3 得分只有 2/5

你不会 Approve。你会：
1. 看 L3 的 reasoning："修复了计算错误，但没有处理空输入的边缘情况"
2. 把这个反馈发回执行 Agent："补充空输入处理，再次 submit"
3. Agent 跑第二轮 → 你 30 分钟后再次审查

**关键**：你没有修代码。你没有写详细的修改建议。你只做了 PM 该做的事——判断。

## 场景 2：周四 2:00 PM — 新功能 Spec 评审

AI 被要求为"搜索筛选"功能写 Spec。产出是一份结构化的 PRD。

### 验收流程

```bash
$ python gate_v2.py --agent agent-spec-7 --artifact search_filter_spec.json --ac ac/prd_standard.json

# L0: PASS
# L1: PASS (符合 PRD Schema)
# L2: PASS (没有安全/隐私问题)
# L3: GPT-4o score=3, Claude score=3 → DUAL PASS (低置信度)
```

两个模型都给 3 分。"基本可用，有小瑕疵"。

### 你会做什么

1. **读 Spec**（15 分钟）— Gate 只能告诉你"格式正确、无明显错误"。不能告诉你"这是一个好 Spec 吗"。

2. **PM 的判断清单**：
   - 用户场景是否清晰？→ "作为一个用户，我想..."有没有写清楚？
   - AC 是否可被 AI 逐字执行？→ 用 doc 05 的 AC 标准检查
   - 是否遗漏了边界状态？→ 空结果、网络错误、权限不足
   - 是否有 UX 考量？→ doc 09 的 UX 维度
   - 是否和已有功能冲突？→ Memory 的 Warm 层可以查近期功能变更

3. **决定**：Reject with feedback。
   ```
   反馈给 Agent：
   - AC-3 "筛选结果实时更新"需要明确延迟要求（<200ms? <500ms?）
   - 缺少移动端的交互描述（底部抽屉 vs 侧边栏？）
   - 没有定义筛选无结果时的行为（空态设计）
   修改后重新 submit。
   ```

4. Agent 第二轮给你更好的 Spec → 你再审 → Approve → 进入开发流水线

### 时间线

```
2:00 PM  Agent submit Spec
2:01 PM  Gate 自动验完（L0-L3 PASS, 3/5）
2:20 PM  PM 完成意图审查，发出 3 条反馈
3:00 PM  Agent 提交修改后的 Spec
3:01 PM  Gate L0-L3 PASS, 4/5
3:15 PM  PM Approve
3:16 PM  Journal 记录完整决策链
```

**整个循环用了 1 小时 16 分钟。** 传统流程下这个循环是 2-3 天。

## 场景 3：周五 4:30 PM — 周度 Eval 会议

每周五下午 4:30。你看三样东西。

### 1. 校准报告

```bash
$ python calibrate.py

=== 周度反馈机制校准报告 ===
周期: 2026-06-07 ~ 2026-06-14
UX样本数: 47
Gate-UX 一致率: 87.2%
假阳性(Gate PASS但UX差): 3
假阴性(Gate FAIL但UX OK): 3
健康度: HEALTHY
```

87.2% 一致率。在健康范围内（>85%）。但假阳性有 3 个。

### 2. 假阳性深度分析

```bash
$ python -c "
from journal import init
conn = init()
# 找到本周假阳性的 txn
rows = conn.execute('''
    SELECT txn_id, gate_result, ux_outcome, task_id
    FROM journal
    WHERE timestamp BETWEEN '2026-06-07' AND '2026-06-14'
      AND ux_outcome IS NOT NULL
''').fetchall()

for txn_id, gate_json, ux_json, task_id in rows:
    gate = json.loads(gate_json)
    ux = json.loads(ux_json)
    gate_pass = gate.get('passed', False)
    ux_good = ux.get('task_completed') and ux.get('user_satisfaction', 0) >= 3
    if gate_pass and not ux_good:
        print(f'FALSE POSITIVE: {txn_id} | Task: {task_id}')
        print(f'  Gate: PASS | UX: {ux}')
"
```

输出：
```
FALSE POSITIVE: txn-5c12 | Task: search-filter-ui
  Gate: PASS | UX: task_completed=False, satisfaction=2, rage_clicks=8
FALSE POSITIVE: txn-6d34 | Task: onboarding-flow
  Gate: PASS | UX: task_completed=False, satisfaction=1, bounced=True
FALSE POSITIVE: txn-8f91 | Task: settings-export
  Gate: PASS | UX: task_completed=True, satisfaction=2, time_to_complete=240s
```

### 3. Eval 会议决策

看假阳性的具体 Case：

- **txn-5c12 (搜索筛选)**：Gate 通过但用户愤怒点击 8 次。去 UX 回放看 → 筛选面板在移动端被折叠了，用户找不到。AC 里有"筛选面板在搜索结果上方"，但没写"移动端也必须可见"。**→ 更新 AC：增加移动端可见性要求。**

- **txn-6d34 (引导流程)**：用户直接跳出。看回放 → 引导流程 5 个步骤，用户可以跳过，但"跳过"按钮在页面底部，用户没看到。AC 没要求"跳过按钮可见性"。**→ 更新 AC + 更新 UX Lint 规则："退出路径必须在首屏可见"**

- **txn-8f91 (设置导出)**：用户完成了但很慢（4 分钟），满意度低。预期是 30 秒。AC 有功能要求但没性能要求。**→ 更新 AC："导出操作 < 30 秒完成"**

### 会议结论

```
本周更新：
1. AC: search-filter 增加移动端可见性
2. AC: onboarding 退出路径首屏可见
3. AC: settings-export 增加性能要求（<30s）
4. UX Lint: 新增规则 "退出/跳过路径必须在首屏 400px 内可见"
5. 评测集: 新增 3 个 Case（从假阳性中提取）
```

**这不是在修 Bug。这是在修反馈机制本身。** 下周一相同的问题不会再被 Gate 放行。

## 三个场景的共性

| | Bug 修复 | Spec 评审 | Eval 会议 |
|---|---|---|---|
| Gate 做什么 | 自动验证 | 自动验证 | 不参与 |
| PM 做什么 | 意图审查 | 深度审查 + 反馈 | 分析 + 修反馈机制 |
| 产出 | Approve/Reject | 结构化的修改意见 | 更新的 AC/规则/评测集 |
| 耗时 | 5-15 min | 15-30 min | 30 min |
| 频率 | 每天 3-5 次 | 每周 2-3 次 | 每周 1 次 |

## 你不是工程师，你不是 QA

这三天的核心信息：

- Gate 让你不用手动检查格式、安全、基本正确性 → **省掉 80% 的机械审查**
- 你的时间花在：意图审查、UX 判断、反馈机制修复 → **PM 真正该做的事**
- 假阳性不是"失败"，是"反馈机制进化所需的燃料" → **越早发现越好**

**系统处理"有没有错误"。你处理"有没有做好"。**

这就是 AI Product OS 里的 PM 工作——你不是在操作 AI，你是在操作一个让 AI 安全工作的系统。
