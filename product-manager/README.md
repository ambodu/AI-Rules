# AI 产品操作系统 (AI Product OS) v3

以操作系统架构为心智模型，重新设计 AI 产品经理的反馈机制与产品正确性体系。

## 核心类比

| OS 概念 | AI PM 映射 |
|---------|-----------|
| **Kernel / Userspace** | 独立验收层 / 执行层 |
| **System Call Gate** | 所有 AI 产出的验证关口 |
| **MLFQ Scheduler** | 任务优先级 + 僵尸回收 |
| **Virtual Memory** | 分层上下文管理 (Hot/Warm/Cold) |
| **Watchdog Timer** | 熔断器 + 预算执行 + 循环检测 |
| **Supervisor (init)** | Agent 生命周期治理 (fork/exec/kill) |
| **Journaling FS** | 不可变审计追踪 |
| **Signals / IPC** | Agent 间事件驱动通信 |
| **POSIX** | 标准化验收接口 |

## 文档索引

| 序号 | 文档 | 解决的核心问题 |
|------|------|---------------|
| 01 | [Kernel 与 Userspace](./01-kernel-userspace.md) | 独立验收架构 — 你的反馈机制第 1 问 |
| 02 | [Scheduler 调度器](./02-scheduler.md) | 任务治理 — 优先级、防死锁、僵尸回收 |
| 03 | [Memory 记忆管理](./03-memory-management.md) | 知识分层 — Hot/Warm/Cold + 遗忘曲线 |
| 04 | [Watchdog 看门狗](./04-watchdog.md) | 运行时安全 — 熔断、预算、循环检测 |
| 05 | [Supervisor 生命周期](./05-supervisor-lifecycle.md) | Agent 治理 — fork/exec/wait/kill/signal |
| 06 | [Journal 审计日志](./06-journal-audit.md) | 不可变追踪 — 你的产品正确性第 2 问 |
| 07 | [AI Product OS 完整蓝图](./07-full-blueprint.md) | 全部子系统组装为完整架构 |

## 设计哲学

> **好的产品经理设计的是"操作系统"，不是"应用程序"。**
>
> 应用程序跑完就结束。操作系统永远在后台运行，管理资源、调度任务、处理异常、保障安全、记录一切。
>
> AI PM 的工作不是写 Prompt（那是写应用程序），而是设计让 Prompt/Agent/模型在上面安全运行的整个操作系统。
