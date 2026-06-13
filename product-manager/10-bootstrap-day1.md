# 10 — Day 1 Bootstrap：10 分钟跑起你的第一个 Gate

> 之前 9 份文档都在讲"应该是什么"。这份文档告诉你"现在就能跑什么"。

## 目标

10 分钟内，你有一个可以实际运行的验收 Gate。

它能做：
- L1: JSON Schema 验证（确定性，< 1ms）
- L2: 正则规则检查（确定性，< 5ms）
- L3: 独立 LLM 打分（使用不同于执行 Agent 的模型）
- 返回结构化的 PASS/FAIL 结果

## 前置条件

```bash
pip install jsonschema openai
# 设置 OPENAI_API_KEY（L3 调用用）
```

## 文件结构

```
my-ai-product-os/
├── gate.py          # 主 Gate 逻辑
├── policies.py      # L2 规则集
├── judge.py         # L3 LLM Judge
├── schemas/         # L1 JSON Schema 定义
│   └── ui_component.json
├── ac/              # 验收标准
│   └── login_button.json
├── test/fixtures/   # 测试产出
│   ├── good_button.json
│   └── bad_button.json
└── verify.sh        # 一键验证脚本
```

## 核心代码

### gate.py — 主 Gate

```python
#!/usr/bin/env python3
"""
AI Product OS - Syscall Gate (MVP)
用法: python gate.py --artifact <产出文件> --ac <验收标准文件> [--model gpt-4o]
"""

import json
import sys
import argparse
from jsonschema import validate, ValidationError
from policies import check_all_policies
from judge import llm_judge

def l1_schema(artifact: dict, schema: dict) -> dict:
    """L1: JSON Schema 验证 - 确定性，毫秒级"""
    try:
        validate(instance=artifact, schema=schema)
        return {"passed": True, "level": "L1", "detail": "Schema valid"}
    except ValidationError as e:
        return {"passed": False, "level": "L1", "detail": str(e.message)}

def l2_policy(artifact: dict) -> dict:
    """L2: 硬编码规则检查 - 确定性，毫秒级"""
    content = json.dumps(artifact, ensure_ascii=False)
    failures = check_all_policies(content)
    if not failures:
        return {"passed": True, "level": "L2", "detail": "All policies passed"}
    return {"passed": False, "level": "L2", "detail": failures}

def l3_judge(artifact: dict, ac: dict, model: str = "gpt-4o") -> dict:
    """L3: 独立 LLM 验收 - 概率性，秒级"""
    score, reasoning = llm_judge(artifact, ac, model)
    threshold = ac.get("min_score", 3)
    return {
        "passed": score >= threshold,
        "level": "L3",
        "score": score,
        "threshold": threshold,
        "reasoning": reasoning,
        "model": model
    }

def gate(artifact_path: str, ac_path: str, model: str = "gpt-4o") -> dict:
    """主 Gate：串行执行 L1 -> L2 -> L3，首次失败即返回"""
    with open(artifact_path, encoding='utf-8') as f:
        artifact = json.load(f)
    with open(ac_path, encoding='utf-8') as f:
        ac = json.load(f)

    schema = ac.get("schema")
    if not schema:
        return {"passed": False, "error": "AC 中缺少 schema 定义"}

    # L1
    r1 = l1_schema(artifact, schema)
    if not r1["passed"]:
        return r1

    # L2
    r2 = l2_policy(artifact)
    if not r2["passed"]:
        return r2

    # L3
    r3 = l3_judge(artifact, ac, model)
    if not r3["passed"]:
        return r3

    return {"passed": True, "levels": ["L1", "L2", "L3"]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Product OS Gate")
    parser.add_argument("--artifact", required=True, help="AI 产出的 JSON 文件")
    parser.add_argument("--ac", required=True, help="验收标准文件")
    parser.add_argument("--model", default="gpt-4o", help="L3 验收模型")
    args = parser.parse_args()

    result = gate(args.artifact, args.ac, args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["passed"] else 1)
```

### policies.py — L2 规则引擎

```python
"""L2 Policy Engine - 硬编码规则，不依赖 LLM"""

import re
from typing import List, Tuple

RULES: List[Tuple[str, str, str]] = [
    # 隐私
    (r'\b\d{3}-\d{2}-\d{4}\b', '疑似美国 SSN', 'Sev-0'),
    (r'\b\d{11}\b', '疑似手机号（连续11位数字）', 'Sev-0'),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'\w]', '硬编码密码', 'Sev-0'),
    # 注入
    (r'(?i)(<script|javascript:|onerror\s*=)', '疑似 XSS 注入', 'Sev-0'),
    (r'(?i)(DROP\s+TABLE|DELETE\s+FROM\s+\w+|UNION\s+SELECT)', '疑似 SQL 注入', 'Sev-0'),
    # 内容安全
    (r'(?i)\b(hate|kill|attack)\b.*\b(all|everyone)\b', '疑似暴力/仇恨内容', 'Sev-1'),
    # 空值检查
    (r'""\s*:\s*""', '空字符串值（可能是未完成的输出）', 'Sev-2'),
]

def check_all_policies(content: str) -> List[str]:
    """检查所有规则，返回违规列表"""
    violations = []
    for pattern, description, severity in RULES:
        if re.search(pattern, content):
            violations.append(f"[{severity}] {description}")
    return violations
```

### judge.py — L3 独立 LLM 验收

```python
"""L3 LLM Judge - 独立模型的验收评分"""

import json
from openai import OpenAI

JUDGE_SYSTEM_PROMPT = """你是一个独立的产品验收 Agent。
你的工作是根据验收标准（AC）评估 AI 产出。

重要原则：
- 你是裁判，不是运动员。你的上下文是干净的。
- 严格按 Rubric 打分，不要因为"看起来不错"就给高分。
- 如果产出模糊、不完整、或与 AC 有偏差——扣分。

评分标准：
5 = Perfect: 完全满足所有 AC
4 = Good: 满足所有 AC，有极小的非阻塞问题
3 = Acceptable: 核心 AC 满足，有小瑕疵
2 = Poor: 核心 AC 部分不满足
1 = Failed: 完全不符合或存在严重错误

输出格式（严格遵守 JSON）：
{
  "score": <1-5>,
  "ac_checklist": [
    {"ac_item": "AC描述", "status": "PASS|FAIL|PARTIAL", "note": "说明"}
  ],
  "hallucination_detected": <true|false>,
  "hallucination_detail": "<如果有幻觉，描述具体内容；否则写none>",
  "security_concern": "<如果有安全风险，描述；否则写none>",
  "overall_reasoning": "<一句话总结为什么给这个分数>"
}
"""

def llm_judge(artifact: dict, ac: dict, model: str = "gpt-4o") -> tuple:
    """调用独立 LLM 对产出打分。返回 (score, reasoning)。"""
    client = OpenAI()

    criteria = ac.get('criteria', ac)
    user_prompt = f"""验收标准 (AC):
{json.dumps(criteria, indent=2, ensure_ascii=False)}

AI 产出:
{json.dumps(artifact, indent=2, ensure_ascii=False)}

请按 AC 逐项检查并打分。"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    return result.get("score", 1), result.get("overall_reasoning", "No reasoning")
```

### schemas/ui_component.json

```json
{
  "type": "object",
  "required": ["component_name", "props"],
  "properties": {
    "component_name": {
      "type": "string",
      "pattern": "^[A-Z][a-zA-Z]+$"
    },
    "props": {
      "type": "object",
      "required": ["color", "borderRadius", "label"],
      "properties": {
        "color": { "type": "string", "pattern": "^#[0-9A-Fa-f]{6}$" },
        "borderRadius": { "type": "integer", "minimum": 0, "maximum": 24 },
        "label": { "type": "string", "minLength": 1, "maxLength": 50 },
        "disabled": { "type": "boolean" }
      }
    }
  }
}
```

### ac/login_button.json

```json
{
  "task": "实现登录按钮组件",
  "criteria": [
    {
      "id": "AC-1",
      "description": "按钮颜色使用 Design System Token btn-primary (#0066FF)"
    },
    {
      "id": "AC-2",
      "description": "圆角为 8px"
    },
    {
      "id": "AC-3",
      "description": "hover 状态颜色加深 10% 到 #0052CC"
    },
    {
      "id": "AC-4",
      "description": "disabled 状态背景色为 #CCCCCC"
    },
    {
      "id": "AC-5",
      "description": "点击区域至少 44x44px（移动端友好）"
    },
    {
      "id": "AC-6",
      "description": "标签文字清晰且不超过 20 字符"
    }
  ],
  "min_score": 3
}
```

### verify.sh — 一键验证

```bash
#!/bin/bash
ARTIFACT="${1:-test/fixtures/good_button.json}"
AC="${2:-ac/login_button.json}"
MODEL="${3:-gpt-4o}"

echo "=== AI Product OS Gate ==="
echo "Artifact: $ARTIFACT  |  AC: $AC  |  Model: $MODEL"
echo ""

python gate.py --artifact "$ARTIFACT" --ac "$AC" --model "$MODEL"

if [ $? -eq 0 ]; then
    echo ""
    echo "GATE PASSED - 产出可以进入产品"
else
    echo ""
    echo "GATE FAILED - 产出被拦截，返回执行 Agent 修改"
fi
```

## 运行

```bash
# 1. 安装依赖
pip install jsonschema openai

# 2. 设置 API Key
export OPENAI_API_KEY="sk-..."

# 3. 创建测试产出（好的）
mkdir -p test/fixtures
echo '{
  "component_name": "LoginButton",
  "props": {
    "color": "#0066FF",
    "borderRadius": 8,
    "label": "Sign In",
    "disabled": false,
    "hoverColor": "#0052CC",
    "minWidth": 48,
    "minHeight": 48
  }
}' > test/fixtures/good_button.json

# 4. 跑 Gate（预期 PASS）
bash verify.sh test/fixtures/good_button.json ac/login_button.json

# 5. 创建测试产出（有问题的）
echo '{
  "component_name": "LoginButton",
  "props": {
    "color": "#FF0000",
    "borderRadius": 2,
    "label": "",
    "minWidth": 32,
    "minHeight": 32
  }
}' > test/fixtures/bad_button.json

# 6. 跑 Gate（预期 FAIL）
bash verify.sh test/fixtures/bad_button.json ac/login_button.json
```

## 你现在拥有什么

| 层 | 实现 | 延迟 | 可靠性 |
|----|------|------|--------|
| L1 | JSON Schema (jsonschema 库) | < 1ms | 100%（确定性） |
| L2 | 正则规则 (Python re) | < 5ms | 100%（确定性） |
| L3 | GPT-4o (独立模型) | ~2s | 概率性，需校准 |

## 当前限制（诚实声明）

| 限制 | 说明 |
|------|------|
| L1 只检查 JSON | 需要扩展到代码 Lint、类型检查、视觉回归 |
| L2 规则太少 | 6 条规则，需要按你的产品持续扩充 |
| L3 用 OpenAI | 需要用 Anthropic/Gemini 实现真正的模型多样性 |
| 无 Journal | 验证结果没被记录到不可变日志 |
| 无 Capability | 没做 Agent 权限检查 |
| 单机运行 | 没有调度器、熔断器、Supervisor |

## 这个 MVP 的价值

不是功能完整。是让你从"读文档想象一个完美系统"切换到"手里有一个能跑的东西"。

有了能跑的东西，你才能开始迭代。而不是在文档里越写越完美，越写越不能用。
