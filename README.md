# AI-Rules

以**操作系统架构**为心智模型的 AI 产品开发方法论。

## 核心命题

1. **反馈机制** — 什么样的设计能保证反馈本身正确，最终产品正确？
2. **产品设计** — 如何设计产品来保证正确性，最终达成更好用户体验？

## v3: AI Product OS

> 好的产品经理设计的是"操作系统"，不是"应用程序"。

| OS 概念 | AI PM 映射 |
|---------|-----------|
| Kernel / Userspace | 独立验收层 / 执行层 |
| System Call Gate | 所有 AI 产出的验证关口 |
| MLFQ Scheduler | 任务优先级 + 僵尸回收 |
| Virtual Memory | 分层上下文管理 (Hot/Warm/Cold) |
| Watchdog Timer | 熔断器 + 预算执行 + 循环检测 |
| Supervisor (init) | Agent 生命周期治理 (fork/exec/kill) |
| Journaling FS | 不可变审计追踪 |
| Signals / IPC | Agent 间事件驱动通信 |

## 目录

```
AI-Rules/
├── product-manager/         # AI Product OS (7 份文档)
│   ├── 01-kernel-userspace.md        # Kernel/Userspace: 独立验收架构
│   ├── 02-scheduler.md               # MLFQ Scheduler: 任务治理
│   ├── 03-memory-management.md       # Memory: 知识分层管理
│   ├── 04-watchdog.md                # Watchdog: 运行时安全与反馈
│   ├── 05-supervisor-lifecycle.md    # Supervisor: Agent 生命周期
│   ├── 06-journal-audit.md           # Journal: 不可变审计追踪
│   └── 07-full-blueprint.md          # AI Product OS 完整蓝图
├── coding/                  # 编码开发规则
├── life/                    # 人生思考
└── research/                # 本地调研
```
