# 03 — 独立验证体系

## 核心原则

> **运动员不能兼任裁判。模型不能给自己打分。** — Lance Martin (Anthropic)

2025-2026 年 AI 验证领域最大的共识：单一模型自我审查在结构上是失败的验证策略。

## 一、为什么自我审查失效

### 四大失败模式

| 失败模式 | 描述 | 实例 |
|----------|------|------|
| **锚定偏差** | 审查自己的产出时"已经知道"为什么做了这些决策 | "我这个设计当然合理，因为..." |
| **沉没成本忠诚** | 对自己刚完成的产出没有兴趣找缺陷 | 倾向于 Pass 而非 Fail |
| **共享盲点** | 同家族模型会犯相同的错误 | Claude 生成的代码给 Claude 审查，两个都看不见盲区 |
| **沉默同意** | AI Agent 之间互相认同远多于互相挑战 | "Agent A 说的对，我同意" |

### 数据证据

MSR'26 研究 (Gong et al.) 分析了 23,247 个 AI Agent 生成的 PR：
- **45.4%** 的描述声称做了从未实际执行的变更
- 有这类不一致的 PR 被接受率低 **51.7%**
- 同一个 Agent 自查时，检出率 < 15%

## 二、2025-2026 年 8 种验证架构

### 架构 1：双盲评审 — Santa Method

Ronald Skelton (RapportScore.ai) 提出：

```
Generator → [Reviewer B ∥ Reviewer C] → Verdict Gate
              Both must PASS → SHIP
              Any FAIL → Fix cycle → Two FRESH reviewers
              Max 3 iterations → Human escalation
```

**关键设计：**
- 两个审查 Agent 之间零上下文共享
- 同一套 Rubric，独立打分
- 修复后必须换新审查者（防止"修复就行"的心态）
- 最大 3 轮，超时人工介入

### 架构 2：冷验证 — Cold Validation Architecture

raxe.ai 提出：

```
Builder Agent ──仅传递制品──→ Cold Reviewer Agent
  (Claude Code)   (plan/diff/test)    (Codex CLI)
                        ←──结构化裁决──
```

**关键设计：**
- 审查者只收到制品（Plan、Diff、测试结果），不收到对话历史
- 审查者不知道 Builder 的推理过程、意图、假设
- 类似学术界的双盲同行评审应用于 AI Agent
- 使用附加式发现账本（finding ledger），基于指纹去重

### 架构 3：四模型委员会 — Multi-Model Council

Aetherneum Faculty Pipeline：

```
Faculty Chair    (Claude Sonnet 4.5, Anthropic)
Velocity         (Llama 3.3 70B, Groq)
Reasoning        (Qwen 3 235B, Cerebras)
Long Context     (Kimi K2, Moonshot)
        ↓
   All four vote independently
        ↓
  Any veto = FAIL (no human override)
```

**关键设计：**
- 四个来自不同提供商的模型
- 每个审查结果以公开 JSON 提交到 git
- `synthetic_transparency < 9` → 自动否决，不可被人覆盖
- 人工仅在没有明确胜出方时介入

### 架构 4：对抗验证 — Red + Blue Team

Audison Framework：

```
Brain One (GPT-4o) ──主审计──→
Opponent Brain ──5个对抗姿态攻击──→  Cross-Verification
  · Attacker（攻击者）
  · Edge-case Hunter（边界猎手）
  · Assumption Breaker（假设破坏者）
  · Spec Lawyer（规格律师）
  · Logic Checker（逻辑检查器）

共识 → CONFIRMED
分歧 → UNCERTAIN（标记 + 证据链 SHA-256 + 时间戳）
```

### 架构 5 — Hook 执行的角色墙：8-Eyes

AgentBuildersApp 提出 — 不只是提示词，是工具层的物理隔离：

| 角色 | 关注面 | 执行机制 |
|------|--------|----------|
| skeptic | 锚定偏差、回滚风险 | 盲审（无实现者上下文） |
| security | 认证绕过、注入、密钥泄露 | 只读 + 仅批准扫描命令 |
| verifier | 缺少证据的信心声明 | 只读 + 仅批准验证命令 |
| performance | N+1 查询、算法爆炸 | 只读 + 仅批准基准测试 |
| scope | 范围蠕变、无关变更 | 只读 + diff 对比原始需求 |
| style | 一致性、可维护性 | 只读 + linter/类型检查 |
| dependency | 供应链、许可证 | 只读 + SBOM 检查 |
| docs | 内联文档匹配实际行为 | 只读 + diff-based 验证 |

**关键设计**：Hook（`PreToolUse`, `PostToolUse`）在物理层阻止越界操作。提示词可以被覆盖；Hook 不能。

### 架构 6：确定性验证 — 不用 LLM 的验证

非 LLM 方法验证产出，避免"用一个概率系统验证另一个概率系统"的循环：

| 工具 | 方法 |
|------|------|
| **groundtruth** | 从 Agent 摘要提取声明，对照 git diff 逐条核实。零 LLM 调用 |
| **loop-guard** | 3层：L1 重执行代码/检索引用源（确定性）、L2 模式匹配/健全性检查（规则）、L3 LLM 辅助软标记 |
| **AgentClaimGuard** | 证据门 — 所有声明必须有证据支持。"没有证据，不输出声明" |

### 架构 7：治理基板 — Nexus Agents

位于工程 Agent 之上的治理层：

- 5 角色对抗式 PR 审查（architect, security, devex, catfish, scope_steward）
- 6 种共识策略（简单多数、超级多数、一致同意、贝叶斯、按意见加权、学习证明）
- 漂移检测章程 + 阻断 CI 关卡
- 不可变审计追踪，hash-chained、追加式存储
- 闭环遥测，从上线结果中学习

### 架构 8：Vibeguard — 9 规则关卡

9 个确定性检查器，Hook 执行：

| 检查器 | 检测内容 |
|--------|----------|
| scope_creep | diff 中是否有需求之外的文件变更 |
| unexplained_deletion | 删除的代码是否有解释 |
| magic_number | 是否引入了无文档的硬编码常量 |
| todo_drift | TODO 注释是否追溯到了 Ticket |
| dependency_drift | 依赖是否被意外更改 |
| test_gap | 新逻辑是否缺少对应测试 |
| error_swallow | 是否静默吞掉了错误 |
| config_leak | 是否引入硬编码的环境特定值 |
| schema_drift | 数据模型是否向后兼容 |

## 三、验证架构选型指南

| 场景 | 推荐架构 | 理由 |
|------|----------|------|
| 单人开发 + AI | 冷验证 (Cold Validation) | 简单、有效、无需多人 |
| 小团队 (2-5人) | Santa Method | 双盲足够、成本可控 |
| 中型团队 (5-20人) | 8-Eyes 或 Vibeguard | Hook 执行、角色化审查 |
| 企业级 (20+人) | 四模型委员会 + Nexus | 跨提供商、完整治理 |
| 安全关键场景 | 对抗验证 (Audison) | 红蓝对抗、证据不可变 |
| 高合规要求 | 确定性验证 (groundtruth) | 零 LLM 调用、完全可审计 |

## 四、最小可行验证方案

如果你只能做一件事：

```
1. 执行 Agent 生成产出
2. 用不同的模型做验收 Agent
3. 验收 Agent 不接收执行 Agent 的对话历史
4. 基于预设 Rubric 打分
5. 不通过 → 带着具体理由回执行 Agent
6. 最大 3 轮 → 人工决策
```

**成本**：每次产出额外 1 次 LLM 调用（验收 Agent）

**收益**：消除自我审查偏差，大幅降低 Sev-0/Sev-1 逃逸率

## 五、自检清单

- [ ] 生成和评审是否使用不同的模型/Agent？
- [ ] 评审 Agent 是否在干净上下文中工作（不接触执行推理）？
- [ ] 是否有预设的量化 Rubric（不是"感觉对不对"）？
- [ ] 是否有最大迭代限制和人工升级机制？
- [ ] 是否有审计追踪（谁评审的、什么理由、什么结果）？
- [ ] 是否在做定期校准（AI 评审 vs 人工评审的一致率）？
- [ ] 是否检测到了"审查疲劳"（通过率异常的审查者）？
