# 01 — Kernel 与 Userspace：独立验收架构

## OS 类比

```
传统 OS:                      AI Product OS:
┌──────────────┐             ┌──────────────────┐
│  Userspace   │             │  Execution Layer  │ ← AI 执行产出
│  (Ring 3)    │             │  (不可信)          │
├──────────────┤             ├──────────────────┤
│  Syscall     │             │  Verification     │
│  Gate        │             │  Gate             │ ← 所有产出必须过
├──────────────┤             ├──────────────────┤
│  Kernel      │             │  Trusted Core     │ ← 独立验收 Agent
│  (Ring 0)    │             │  (可信)            │
└──────────────┘             └──────────────────┘
```

操作系统的核心设计原则：**用户态程序不可信，内核是唯一的信任基 (TCB, Trusted Computing Base)。**

AI PM 同样：**执行 Agent 不可信，验收 Agent 是唯一的信任基。**

## 一、为什么需要 Kernel 层

### OS 历史上的教训

在 UNIX 引入 kernel/userspace 分离之前，任何程序都能直接访问硬件、修改内存、写磁盘。一个 Bug 就能让整个系统崩溃。

AI 开发的现状正好在这个"前 OS 时代"：
- Prompt 直接输出给用户，没有验证层
- Agent 自己检查自己的工作
- 没有权限分离——生成代码的 Agent 也能删文件
- 反馈依赖人工"看看行不行"

### Kernel 层的职责

| Kernel 子系统 | AI PM 实现 | 解决的问题 |
|--------------|-----------|-----------|
| **Syscall Gate** | 所有 AI 产出必须通过验证 Gate 才能"写回"产品 | 防止未经验证的产出进入用户视野 |
| **Capability System** | Agent 只能访问被授权的工具/数据 | 防止范围蠕变和越权操作 |
| **Policy Engine** | 硬编码的规则（非 LLM 判断）执行底线检查 | 确定性安全，不依赖概率系统 |
| **Audit Trail** | 每次验证的完整记录 | 可追溯、可复盘、可归因 |

## 二、Syscall Gate：每一个产出都必须过

### 类比

在 OS 中，用户程序想写文件必须调用 `write(fd, buf, n)`——这个调用会经过内核的权限检查、文件系统检查、磁盘配额检查。

在 AI Product OS 中，Agent 想产出一个功能/内容/设计，必须调用 `submit(artifact, evidence)`——这个调用会经过验收 Gate。

### Gate 的检查流程

```
Agent 产出
  │
  ├─ L1: 格式检查 (确定性，通常 < 10ms)
  │   · Schema 是否符合预设？
  │   · 字段类型是否正确？
  │   · 长度/大小是否超限？
  │   → PASS: 进入 L2
  │   → FAIL: 立即拒绝 + 具体错误信息
  │
  ├─ L2: 规则检查 (确定性，通常 < 50ms)
  │   · 是否包含禁止内容（黑名单正则）？
  │   · 是否有明显的注入攻击？
  │   · 敏感数据是否被脱敏？
  │   → PASS: 进入 L3
  │   → FAIL: 立即拒绝 + 安全警报
  │
  ├─ L3: AI 验收 (概率性，通常 < 5s)
  │   · 独立模型按 Rubric 打分
  │   · 对照 AC 逐项检查
  │   · 幻觉检测（事实一致性）
  │   · 安全性审查
  │   → PASS (score >= threshold): 进入 L4
  │   → FAIL: 带着具体反馈回执行 Agent
  │
  └─ L4: 人工确认 (高成本，仅高风险场景)
      · 涉及资金、隐私、合规的产出
      · AI 验收不确定的边界 Case
      → APPROVE / REJECT / NEEDS_MORE_INFO
```

### 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| L1/L2 用什么？ | **规则引擎，不用 LLM** | 确定性、零幻觉、毫秒级 |
| L3 用什么模型？ | **不同于执行 Agent 的模型** | 消除共享盲点 |
| L3 的上下文？ | **仅接收制品 + AC，不接收执行推理** | 消除锚定偏差（冷验证） |
| L4 什么时候触发？ | **仅高风险 + 低置信度** | 人工是最稀缺的资源 |

## 三、Capability System：权限即安全

### 类比

OS 中，程序不能随意访问任何文件。它必须在启动时声明需要的权限（capabilities），内核只授予最小必要权限。

AI Product OS 同样：每个 Agent 在启动时声明需要的 Tool，内核只授予最小必要集合。

### 实现

```
Agent 声明：
  "我需要读取 design-system/ 目录，写入 src/components/ 目录"
  
Kernel 授予 Capability Token：
  {
    agent_id: "agent-123",
    capabilities: [
      { resource: "design-system/*",   ops: ["read"] },
      { resource: "src/components/*",  ops: ["write"] },
      { resource: "src/components/*.test.*", ops: ["write"] }
    ],
    expires: "2026-06-13T18:00:00Z",
    max_budget_usd: 5.00
  }

每次 Tool 调用时 Gate 检查：
  → Capability 是否覆盖此操作？
  → Token 是否过期？
  → 预算是否耗尽？
  → 任意一项不满足 → DENY
```

### 默认拒绝原则

- 没有显式授权的操作 = 拒绝
- 写操作需要比读操作更严格的授权
- 删除操作需要人工确认
- 网络出站需要显式声明目标

## 四、Policy Engine：硬性约束

### 类比

OS 内核有硬编码的安全策略（如 SELinux），不依赖任何外部程序。这些策略在编译时就确定，无法被绕过。

AI Product OS 同样需要硬编码的 Policy，不依赖 LLM 判断：

| Policy 类型 | 示例 | 违反后果 |
|------------|------|----------|
| **禁止内容** | 不输出任何形式的个人信息 | 立即拒绝 |
| **格式约束** | JSON 必须是合法 JSON | 立即拒绝 |
| **范围约束** | 不能修改指定目录外的文件 | Tool 调用被拦截 |
| **预算约束** | Token/成本/时间超限 | 任务中止 |
| **伦理约束** | 不生成有害/歧视性内容 | 立即拒绝 + 警报 |

**关键**：这些 Policy 不是 Prompt 里的"请勿..."，而是代码层的 `if (violates_policy) { deny(); }`。Prompt 可以被覆盖；代码不能。

## 五、信任基 (TCB) 最小化原则

OS 设计中，TCB 越小越安全。同样，AI Product OS 的 TCB 也应当最小化。

### TCB 应该包括什么

- L1/L2 验证逻辑（代码）
- Policy Engine（代码）
- Capability 检查逻辑（代码）
- 独立验收模型的调用逻辑（代码）

### TCB 不应该包括什么

- 执行 Agent 的任何输出
- 任何 LLM 对安全性的判断（用 LLM 检查 LLM 不构成 TCB）
- 用户的直接输入（在 Gate 验证之前）

## 六、自检清单

- [ ] 所有 AI 产出是否都经过了 Syscall Gate（L1→L2→L3→L4）？
- [ ] L1/L2 是否使用确定性规则而非 LLM？
- [ ] L3 验收模型是否独立于执行模型？
- [ ] L3 是否在干净上下文中工作（冷验证）？
- [ ] 每个 Agent 是否有最小 Capability 声明？
- [ ] 硬性 Policy 是否在代码层执行（不在 Prompt 层）？
- [ ] TCB 是否足够小（减少信任表面积）？
