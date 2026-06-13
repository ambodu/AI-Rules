# 05 — Supervisor 生命周期治理

## OS 类比

Unix 中 `init` (PID 1) 是所有进程的祖先。Supervisor 负责：
- `fork()` — 创建子进程
- `exec()` — 加载新程序
- `wait()` — 等待子进程结束
- `kill()` — 终止进程 + 信号传播整棵进程树
- `checkpoint/restore` — 保存/恢复进程状态

AI PM 的 Supervisor 对每个 AI Agent 执行完全相同的生命周期管理。

## 一、Agent 生命周期

```
        ┌─────────┐
        │  INIT   │  ← Agent 在 Capability Table 中注册
        └────┬────┘
             │
        ┌────▼────┐
        │  FORK   │  ← 分配上下文空间 + 预算切片 + 时间片
        └────┬────┘
             │
        ┌────▼────┐
        │  EXEC   │  ← 加载 Spec + AC + Eval Rubric + Tool Capability
        └────┬────┘
             │
        ┌────▼────┐
        │  RUN    │  ← Agent 执行 Loop
        │  ◄──►   │     每轮: 产出 → Gate 验证 → 通过/返回修改
        └────┬────┘
             │
     ┌───────┼───────┐
     ▼       ▼       ▼
  EXIT_OK  EXIT_ERR  KILLED
  (正常)   (失败)    (SIGKILL)
     │       │       │
     └───────┼───────┘
             ▼
        ┌─────────┐
        │  WAIT   │  ← Supervisor 回收 Agent，释放资源
        └─────────┘
             │
        ┌─────────▼
        │  LOG    │  ← 完整执行记录写入 Journal
        └─────────┘
```

## 二、FORK：Agent 创建

### OS 中的 fork()

子进程继承父进程的内存副本（CoW）、文件描述符、环境变量。但有自己的 PID、自己的地址空间。

### AI PM 中的 fork()

```
Parent Agent 调用 fork(task_spec):
  
  child = {
    agent_id: "agent-456",
    parent_id: "agent-123",
    task: "修复登录页面按钮样式与 Design System 不一致的问题",
    inherit_from_parent: {
      // CoW — 只在子 Agent 需要修改时才复制
      ac: "按钮颜色 #0066FF，圆角 8px，hover 加深 10%",
      design_system_ref: "v2.3.1",
      eval_rubric: "视觉回归 + AC 逐项检查",
      capability: "读取 src/components/Button/*，写入同目录",
    },
    own: {
      budget_slice: { tokens: 30K, cost: $0.80, time: 20min, max_iter: 5 },
      context_hot: [], // 空白的 Hot 层
    }
  }
  
  Supervisor: register(child) → schedule(child) → run(child)
```

### Fork 预算继承

```
父 Agent 预算: $5.00
  ├─ 子 Agent A: $1.50 (从父继承)
  ├─ 子 Agent B: $1.50 (从父继承)
  └─ 父 Agent 保留: $2.00

子 Agent 超预算 → 父 Agent 预算也被扣减 → 父也必须管理子 Agent 的预算
```

## 三、EXEC：加载任务上下文

### OS 中的 exec()

`exec()` 用新程序替换当前进程的代码和数据，但保留 PID 和文件描述符。

### AI PM 中的 exec()

```
Agent.exec(task_spec):
  
  加载到 Hot 层：
  ├─ Spec（完整的功能规格，包含 AC）
  ├─ Eval Rubric（什么算 Pass）
  ├─ Design System 引用（约束）
  ├─ 相关代码/设计的当前状态（上下文）
  ├─ 历史上类似问题的解决方案（从 Cold 层召回）
  └─ 已知的失败模式（从 Cold 层召回）："上次类似任务在 XX 卡住了"
  
  加载 Capability：
  ├─ 允许读取的目录/API
  ├─ 允许写入的目录
  └─ 允许调用的 Tool

  exec() 完成后 → Agent 进入 RUN 状态
```

## 四、WAIT：等待结束

### OS 中的 wait()

父进程阻塞直到子进程结束，回收其资源（PID、内存、进程描述符）。

### AI PM 中的 wait()

```
result = Supervisor.wait(agent_id, timeout=30min)

Possible outcomes:

1. EXIT_OK:
   result = {
     status: "completed",
     artifact: <产出>,
     evidence: <验证通过的证据>,
     iterations: 3,
     cost: $0.65,
     time: 12min
   }
   → 产出进入下一流程（合并/发布/进一步审查）

2. EXIT_ERR:  // Agent 自己判定无法完成任务
   result = {
     status: "failed",
     reason: "当前模型能力不足以完成此任务",
     partial_output: <已完成的 60%>,
     blocking_issue: "需要人工提供额外的设计规范"
   }
   → 打包上下文 + 人工介入

3. KILLED:  // 被 Watchdog/PM 终止
   result = {
     status: "killed",
     killed_by: "Watchdog.LimitChecker",
     reason: "Token 预算耗尽 (30001/30000)",
     partial_output: <超限前最后一轮的结果>
   }
   → 评估剩余价值 + 决定是否分配更多预算重试
```

## 五、KILL + 信号传播树

### OS 中的进程树

`kill(-pid, SIGKILL)` 发送信号给整个进程组。父进程被 kill → 所有子进程级联终止。

### AI PM 中的 Kill 传播

```
功能 A 开发（父 Agent 1）
  ├─ 子 Agent 1.1: 前端组件开发（被 KILL ← Watchdog 检测到循环）
  │   └─ 孙 Agent 1.1.1: 单元测试生成（级联 KILL）
  ├─ 子 Agent 1.2: 后端 API 开发（级联 KILL — 前端改了什么影响后端契约）
  └─ 子 Agent 1.3: 文档更新（级联 KILL）

Kill 规则：
├─ 父被 KILL → 所有子孙被 KILL
├─ 子被 KILL → 父被通知（可以决定 fork 新子还是改变策略）
└─ 被 KILL 的 Agent 资源立即释放（预算、并发槽位、审查槽位）
```

## 六、Checkpoint / Restore：容错

### OS 中 CRIU (Checkpoint/Restore In Userspace)

将进程的完整状态（内存、寄存器、文件描述符、网络连接）保存到磁盘。之后可以从这个时间点恢复。

### AI PM 中的 Checkpoint

每次 Loop 迭代前自动保存检查点：

```
Checkpoint {
  agent_id: "agent-456",
  iteration: 3,
  state: {
    context_hot_snapshot: <当前 Hot 层完整快照>,
    attempted_fixes: [fix1, fix2],
    eval_results: [fail, fail],
    budget_remaining: { tokens: 18000, cost: $0.45, time: 14min },
  },
  restore_point: "iteration_3"
}
```

使用场景：
- Agent 后续迭代让情况变差 → 回滚到上一个 Checkpoint
- Agent 被 KILL → 有新预算后从最后一个 Checkpoint 恢复（而非重新开始）
- 人工审查后发现需要不同方向 → 回滚到某个早期 Checkpoint 重来

## 七、Supervisor 面板

PM 需要的视图（类比 `htop`）：

```
PID    AGENT          TASK                    STATE    ITER  COST    TIME
456    fix-btn-style  修复登录按钮样式         RUNNING  3/5   $0.45   12m
457    add-filter     添加搜索筛选功能         WAITING  0/5   $0.00    0m
458    fix-sev0-bug   修复支付金额计算错误     RUNNING  1/3   $0.12    3m  [P0]
459    explore-perf   探索列表页性能优化       PAUSED   2/20  $0.80   45m  [SIGPAUSE]

[P0] = 硬实时，抢占其他
[SIGPAUSE] = 被 PM 手动暂停
```

## 八、自检清单

- [ ] 每个 Agent 是否有清晰的创建 (fork) → 执行 (exec) → 回收 (wait) 生命周期？
- [ ] fork 时是否正确隔离了上下文（子不污染父）？
- [ ] 是否有 Kill 传播规则（父被 kill → 子孙级联终止）？
- [ ] 每次 Loop 迭代前是否自动 Checkpoint？
- [ ] 被 KILL 的 Agent 是否可以从 Checkpoint 恢复？
- [ ] PM 是否有"信号"能力随时干预 Agent（暂停/重定向/查看进度）？
- [ ] 是否有 Supervisor 面板能看到所有 Agent 状态？
