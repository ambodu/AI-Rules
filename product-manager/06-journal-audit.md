# 06 — Journal 审计日志：不可变追踪

## OS 类比

Journaling File System（如 ext4, NTFS）的核心机制：
1. **Write-Ahead Logging** — 在实际写数据之前，先把"我要做什么"写入日志
2. **Crash Recovery** — 崩溃后重放日志，系统回到一致状态
3. **Append-Only** — 日志只能追加，不能修改或删除
4. **Immutable History** — 任何时间点都能回溯到之前的任何一个状态

AI PM 的 Journal 实现完全相同的目标：**每一个产品决策、每一次 AI 产出、每一次验收、每一次回滚——都可以被追溯、被复盘、被学习。**

## 一、Write-Ahead Logging → 决策前记录

### OS 中

在修改文件数据之前，先写日志："我即将把块 42 从 X 改为 Y"。如果系统在修改过程中崩溃，重启后重放日志就能恢复。

### AI PM 中

在任何产品变更生效之前，先记录：**谁、什么时间、基于什么理由、做了什么决定。**

```
Journal Entry {
  id: "txn-789",
  timestamp: "2026-06-13T14:32:17Z",
  agent_id: "agent-456",
  task_id: "task-234",
  decision: "修改登录按钮颜色从 #0044CC 到 #0066FF",
  evidence: {
    ac_ref: "AC-3: 按钮颜色使用 Design System Token btn-primary",
    design_system_version: "v2.3.1",
    verification: "L1: PASS (Schema), L2: PASS (Policy), L3: PASS (Score 4/5)",
    verifier_agent: "verifier-agent-12 (Claude Sonnet 4.6)",
  },
  parent_txn: "txn-780", // 这个修改依赖的上一个事务
}
```

### 记录什么

| 必须记录 | 为什么 |
|----------|--------|
| **谁做的决定** | Agent ID + 模型 + 版本 |
| **什么时候** | 时间戳 |
| **基于什么输入** | AC / Spec / 用户反馈的引用 |
| **产出是什么** | Diff / Content Hash / Artifact Ref |
| **谁验证的** | 验收 Agent ID + 模型 |
| **验证结果 + 分数** | Pass/Fail + 详细评分 |
| **验证理由** | 为什么 Pass / 为什么 Fail |
| **父事务** | 这个决策依赖的上一个决策 |

## 二、Crash Recovery → 失败回滚

### OS 中

系统崩溃 → 启动时检查 Journal → 重放已完成但未写入的事务 → 丢弃未完成的事务 → 文件系统回到一致状态。

### AI PM 中

产品决策出错 → 查看 Journal → 找到出错的事务 → 回滚该事务及其所有依赖事务 → 产品回到一致状态。

```
场景：某次 AI 修改了 3 个关联组件，上线后发现第 2 个有 Bug。

Recovery：
  1. Journal 查询：txn-789, txn-790, txn-791 是同一批修改
  2. txn-790 被标记为 BUG（用户反馈 #1234）
  3. 回滚 txn-790 及其依赖 txn-791（因为 791 依赖 790 的修改）
  4. txn-789 可以保留（独立修改，不依赖 790）
  5. Journal 追加 txn-792: "回滚 txn-790, txn-791。原因：Bug #1234"
```

### 回滚粒度

| 粒度 | 回滚单位 | 使用场景 |
|------|----------|----------|
| **单事务** | 一个 AI 产出 + 验证 + 合并 | 单一 Bug，独立修改 |
| **事务组** | 同一批关联修改 | 一个功能的多文件修改 |
| **版本** | 一个发布版本的全部事务 | Sev-0 缺陷，紧急回滚整个版本 |
| **时间点** | 某时间之前的所有事务 | "回到上周五的状态" |

## 三、Append-Only → 不可变性

### OS 中

Journal 只追加，永远不修改或删除已有记录。这提供了完整性保证。

### AI PM 中的 Append-Only

```
错误做法：
  "我觉得之前那个决策不对，删掉重新记录一个对的"
  
正确做法：
  Journal.append({
    type: "CORRECTION",
    references: "txn-789",       // 指向被纠正的决策
    reason: "AC 理解有误：设计要求是 8px 圆角而非 12px",
    new_decision: "修改圆角为 8px",
    corrected_by: "PM-fffh"      // 谁纠正的
  })

Journal 中的记录永远不删除。纠正 = 追加一条 CORRECTION。
```

**为什么这很重要**：
- 6 个月后你可以回溯"我们当时为什么做了那个决定"
- 你可以统计"AI 做的决策中有多少被后来纠正了"
- 你可以在新成员加入时说"看 Journal，从 3 月到 6 月的所有决策都在里面"

## 四、Merkle Chain → 防篡改

### OS 中

一些现代文件系统使用 Merkle Tree 确保数据完整性。每个块的哈希被包含在父节点的哈希中，根哈希一旦改变整个树都能检测到。

### AI PM 中的链式验证

```
每个 Journal Entry 包含：
  hash(entry) = SHA-256(
    prev_entry_hash +  // 链上前一个 Entry 的哈希
    timestamp +
    agent_id +
    artifact_hash +    // 产出的内容哈希
    verification_hash  // 验收结果的哈希
  )

Entry N 的哈希 → 包含在 Entry N+1 的 prev_entry_hash 中
Entry N+1 的哈希 → 包含在 Entry N+2 中
...

篡改任何一个 Entry → 所有后续 Entry 的哈希失效 → 可以被检测
```

这确保了从产品第一天到现在的完整决策链都是可验证的。

## 五、可回放性：事后学习

### OS 中

Journal 可以重放，精确再现系统状态的变化过程。

### AI PM 中的回放

```
回放 2026 年 Q1：
  → 提取 Q1 的所有 Journal Entry
  → 按时间线重放每一个决策
  → 统计：
    · AI 做了多少决策？
    · 其中多少被纠正了？（纠正率）
    · 哪些类型的决策最容易出错？
    · 哪位 PM / 哪个验收 Agent 的通过率异常？
    · 从发现 Bug 到修复的平均时间？
    · 从用户反馈到产品变更的平均闭环时间？
```

### PM 可以从 Journal 中学习的问题

| 问题 | 查询的 Journal 数据 |
|------|-------------------|
| 我们的 AC 写得够清楚吗？ | L3 评分分布 — 如果大量在 3 分左右，AC 太模糊 |
| 验收 Agent 校准了吗？ | L3 评分 vs 后续人工纠正 — 差距太大 = 校准偏移 |
| 哪个阶段最慢？ | 各阶段时间分布 — fork→exec→run→verify→merge |
| Bug 从哪里来？ | Bug 修复事务的 parent_txn — 找出哪个决策链导致了 Bug |
| AI 在变好吗？ | L3 均分趋势 + 纠正率趋势 — 应该持续改善 |

## 六、隐私与保留策略

### 需要保留的

- 决策本身（架构、设计、产品方向）
- 验收结果和理由
- 纠正记录
- Agent ID + 模型版本

### 需要脱敏的

- 用户个人数据（如果出现在上下文中）
- 内部密钥/Token
- 个人身份信息

### 保留期限

| 数据 | 保留期 |
|------|--------|
| 完整 Journal | 永久（产品知识资产） |
| Agent Hot 层快照 | 30 天 |
| 验收 Agent 的完整上下文 | 90 天（用于校准审计） |
| 预算/成本记录 | 1 年（财务审计需求） |

## 七、自检清单

- [ ] 每个产品变更是否有 Write-Ahead 记录（变更前已记录决策）？
- [ ] 是否支持按事务/事务组/版本/时间点粒度的回滚？
- [ ] Journal 是否是 Append-Only（永不可篡改）？
- [ ] 纠正是否以 CORRECTION Entry 形式追加（而非删除原记录）？
- [ ] 是否有哈希链保证完整性和防篡改？
- [ ] 是否支持按时间线回放复盘？
- [ ] 是否从 Journal 中定期提取统计（纠正率、L3 趋势、闭环时间）？
