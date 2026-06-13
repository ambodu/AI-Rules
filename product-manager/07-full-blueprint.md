# 07 — AI Product OS：完整蓝图

## 架构总览

AI Product OS 由 6 个 Kernel 子系统 + Userspace 执行层组成：

```
USERSPACE (Ring 3):
  Agent A (功能开发)  Agent B (Bug修复)  Agent C (设计审查)
        |                  |                  |
        +------------------+------------------+
                           |
                    IPC / Signal Bus
                           |
=============== SYSTEM CALL GATE ===============
                           |
             KERNEL SPACE (Ring 0):
                           |
    +----------+----------+----------+----------+
    | VERIFY   | SCHEDULER|SUPERVISOR| WATCHDOG |
    | (01)     | (02)     | (05)     | (04)     |
    |          |          |          |          |
    | L1 Schema| MLFQ     | fork/exec| Circuit  |
    | L2 Policy| Zombie   | wait/kill| Breaker  |
    | L3 Judge | Reaper   | Signal   | Limit    |
    | L4 Human | Admission| Checkpt  | Checker  |
    +----------+----------+----------+----------+
    | MEMORY   |CAPABILITY| JOURNAL  | IPC BUS  |
    | (03)     | SYSTEM   | (06)     |          |
    |          |          |          |          |
    | Hot/Warm | Min Priv | Append-  | Agent2Ag |
    | /Cold    | Access   | Only     | Signal   |
    | LRU      | Control  | Merkle   | Pub/Sub  |
    +----------+----------+----------+----------+

CROSS-CUTTING: Governance . Observability . Metrics . Alerts
```

## 完整数据流：一个 Bug 修复从开始到结束

```
1. 用户反馈 Bug -> 自动分类为 Sev-1 -> 进入 MLFQ P1 队列

2. Supervisor.fork(task: "修复支付金额计算错误")
   Capability: read src/payment/*, write src/payment/*, read test/*
   Budget: 50K tokens, $1.50, 30min, 5 iterations
   Context: AC + 错误日志 + 相关代码 + 类似 Bug 的修复历史 (Cold->Hot)

3. Agent.exec() -> RUN state

   Iteration 1:
   - Agent 产出修复
   - Syscall: submit(artifact, evidence)
   - VERIFY Gate:
       L1: Schema OK
       L2: Policy OK (没有修改 payment/ 外的文件)
       L3: LLM Judge (GPT-4o) 评分 4/5 - "修复了计算错误，但没加单元测试"
       -> PARTIAL_PASS - 需要补充测试
   - Journal: append(txn-790, status: PARTIAL_PASS, score: 4)
   - Agent 收到反馈，进入 Iteration 2

   Iteration 2:
   - Agent 补充单元测试
   - Syscall: submit(artifact_v2, evidence)
   - VERIFY Gate:
       L1: Schema OK
       L2: Policy OK
       L3: LLM Judge 评分 5/5 - "修复正确，测试覆盖了边缘情况"
       -> PASS
   - Journal: append(txn-791, status: PASS, score: 5, parent: txn-790)
   - Agent EXIT_OK

4. Supervisor.wait() -> 回收 Agent，释放预算槽位

5. 产出合并 -> 灰度发布 -> A/B 验证 -> 全量
   Journal 全程追加: txn-792 (灰度), txn-793 (全量)

6. 全量后 7 天无异常 -> 相关 Memory 从 Hot 降级到 Warm
   全量后 30 天 -> Bug #1234 正式关闭

7. 下次类似 Bug：从 Cold 层召回 txn-790-793 -> "上次类似的 Bug 是这样修的"
```

## 子系统交互矩阵

|  | VERIFY | SCHEDULER | SUPERVISOR | WATCHDOG | MEMORY | CAPABILITY | JOURNAL |
|--|--------|-----------|------------|----------|--------|------------|---------|
| **VERIFY** | - | 通知优先级 | 返回结果 | 报告异常 | 读AC/Rubric | 检查权限 | 写结果 |
| **SCHEDULER** | - | - | fork/kill | 接收熔断 | - | - | - |
| **SUPERVISOR** | 提交验证 | 请求调度 | - | 收SIGKILL | 读/写上下文 | 注册Cap | 读/写 |
| **WATCHDOG** | 覆盖裁决 | 发送优先 | 发SIGKILL | - | 监控泄漏 | 监控越权 | 写告警 |
| **MEMORY** | 提供Rubric | - | 提供上下文 | 报告泄漏 | - | - | 写归档 |
| **CAPABILITY** | 每次调检 | - | fork分配 | 检测越权 | - | - | 写授权 |
| **JOURNAL** | 读历史 | 读耗时 | 读历史 | 读告警 | 读归档 | 读变更 | - |

## 分级部署模型

### Level 1: 最小可行 (1人 + AI)

```
你的笔记本
- Kernel: Python/TS Rule Engine 脚本
- Verify: L1(JSON Schema) + L2(Regex) + L3(独立 LLM API 调用)
- Scheduler: 你手动 + 简单超时检测
- Supervisor: 你手动管理
- Watchdog: 简单 Token/时间计数器
- Memory: Markdown 知识库 (Hot=当前, Warm=本周, Cold=归档)
- Journal: Git (每个决策 = 一个 commit/PR)
- PM Console: 终端 + Git + 你的判断
```

### Level 2: 团队 (3-10人)

```
团队服务器
- Kernel: 自动化 Rule Engine + CI/CD Pipeline
- Verify: 完整 L1-L4 Gate + 独立验收 Agent Pool
- Scheduler: MLFQ 自动化 + PM 手动覆盖
- Supervisor: Agent Pool Manager (10-50 并发)
- Watchdog: 熔断器 + 降级策略 + 多维度预算
- Memory: 向量数据库 + 关系型存储
- Journal: 专用 Append-Only DB + Merkle 验证
- PM Console: Grafana Dashboard
```

### Level 3: 企业 (20+人, 多产品线)

```
Kubernetes 集群
- 每个产品线独立 Kernel Namespace (上下文隔离)
- 共享: 模型池、工具注册中心、审计系统
- 组织级 Policy -> 产品级 Policy
- Agent 可在产品线间迁移 (带 Capability 限制)
- 跨产品线 Eval 基准对比
```

## 回到你的两个核心问题

### Q1: 反馈机制怎么设计才能保证正确?

反馈不是事后追加。反馈是 Kernel 的内置能力。

```
反馈机制 = VERIFY Gate + WATCHDOG + JOURNAL

VERIFY: 把关每一次产出 (Syscall Gate — 不过关的产出无法进入产品)
WATCHDOG: 持续监控运行时 (心跳 + 熔断 + 循环检测 + 预算执行)
JOURNAL: 记录一切 (可追溯、可回滚、可复盘、可学习)

反馈不是"做好后检查"，而是"从设计上就无法产出未经验证的结果"。
就像 OS 不允许用户态程序直接写磁盘——你必须经过内核的 Syscall Gate。
```

### Q2: 产品怎么设计才能保证正确性?

好的产品不是"做对了功能"。是设计了一个"让错误难以发生"的系统。

```
产品正确性 = CAPABILITY + POLICY + CHECKPOINT

CAPABILITY: 最小权限 — Agent 只能做被允许的事，其他操作被 Kernel 拒绝
POLICY: 硬编码底线 — 不是 Prompt 里的"请勿..."，是代码层的 if(violates){deny();}
CHECKPOINT: 可回滚 — 每个迭代前自动保存状态，错了可以回到正确状态

正确的产品不是"没有 Bug 的产品"。
正确的产品是:
  Bug 发生了 -> 被 Gate 拦截 -> 被 Watchdog 发现
  -> 被 Journal 记录 -> 被 Checkpoint 回滚 -> 被学会不再犯
```

## 最终类比

| 传统 App 开发 | AI Product OS |
|--------------|---------------|
| 你写代码 | 你设计 Kernel |
| 你测试 | VERIFY Gate 自动测试每个产出 |
| 你审查 | WATCHDOG 持续监控 |
| 你记住上次怎么错 | MEMORY 自动召回 + 防重复 |
| 你决定先做什么 | SCHEDULER 按 MLFQ 自动调度 |
| 你盯着 Agent 别跑偏 | SUPERVISOR 管理生命周期 |
| 你回忆当时为什么这样做 | JOURNAL 不可变记录一切 |

---

**AI PM 的工作不是"用 AI 做产品"。**

**AI PM 的工作是"设计一个操作系统，让 AI 在里面安全地做产品"。**

就像 Linus Torvalds 不写应用程序。他写 Kernel。
应用程序成千上万，跑在 Kernel 之上——但 Kernel 只有一个。

这就是你的工作。设计那个 Kernel。
