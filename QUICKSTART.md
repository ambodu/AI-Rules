# 5 分钟上手 AI Product OS

## 一句话

你设计一个"操作系统"，AI Agent 在里面安全地做产品。所有 AI 产出必须经过 Kernel 的 Gate 验证，被 Journal 记录，被 UX 数据回验。

## 不要按顺序读

14 份文档，别从 01 开始。按这个顺序：

### 如果想理解"为什么"

1. **[14-daily-workflow.md](product-manager/14-daily-workflow.md)** — 三个真实场景，5 分钟读完就知道这个系统怎么用
2. **[08-critical-review.md](product-manager/08-critical-review.md)** — 这个系统目前有什么缺陷
3. **[09-ux-north-star.md](product-manager/09-ux-north-star.md)** — 为什么 UX 是一切的基础

### 如果想跑起来

1. **[10-bootstrap-day1.md](product-manager/10-bootstrap-day1.md)** — 10 分钟跑起第一个 Gate
2. **[12-integration-capability.md](product-manager/12-integration-capability.md)** — 完整系统 + 7 个 E2E 测试
3. **[13-claude-judge.md](product-manager/13-claude-judge.md)** — 双模型并行验收

### 如果想深入理论

01-07 是 OS 隐喻的完整展开。但说实话——**先跑代码，再回来看理论。**

## 5 分钟跑起来

```bash
git clone https://github.com/ambodu/AI-Rules.git
cd AI-Rules

# 把 product-manager/10 到 13 里的 Python 代码复制出来
# 安装依赖
pip install jsonschema openai anthropic

# 跑测试
python test_e2e.py
# 7/7 tests passed
```

## 核心模型（30 秒版）

```
AI Agent 产出
    │
    ▼
L0: 你有权限做这个吗？       ← Capability
L1: 格式对吗？               ← JSON Schema
L2: 包含禁止内容吗？          ← 正则规则
L3: 独立 AI 觉得合格吗？      ← GPT-4o + Claude 双模型
    │
    ▼
通过 → Journal 记录 → 等 UX 数据回来验证
失败 → 带着反馈回 Agent 修改
```

每周五：`calibrate.py` 告诉你 Gate 的 PASS/FAIL 判断和真实 UX 结果的一致率。一致率 < 85% → 你的反馈机制有问题。

## 这个系统的唯一定义

> Gate 告诉你"没有明显错误"。UX 数据告诉你"用户真的满意"。
> 两者一致 → 反馈机制正确。两者不一致 → 修反馈机制。

一句话：**Gate 处理"有没有错"，你处理"有没有好"，UX 数据判断谁对。**
