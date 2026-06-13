# 13 — Claude Judge：模型多样性的反馈正确性

## 为什么需要这份文档

doc 01 说：**"L3 验收模型必须不同于执行 Agent 的模型，消除共享盲点。"**

但如果你的 judge.py 只有 OpenAI，而执行 Agent 也用 OpenAI——那所谓"独立验收"就是自己审自己换了个名字。

**同一个提供商的模型共享训练数据、RLHF 偏好、安全对齐——盲点是相关的。**

## 模型多样性的价值

MSR'26 研究：不同提供商的模型在同一 Code Review 任务上的不一致率高达 38%。GPT-4o 和 Claude Sonnet 在以下维度经常意见不同：

| 维度 | GPT-4o 倾向 | Claude 倾向 |
|------|-----------|------------|
| 代码风格 | 宽松，"这样可以工作" | 严格，"不符合最佳实践" |
| 安全性 | 标记明显危险 | 标记明显危险 + 潜在滥用场景 |
| 边界情况 | 关注 happy path | 更关注边缘和错误状态 |
| 可维护性 | 基本过关就行 | 对可读性要求更高 |

**你同时使用两者时，盲区被覆盖。单一模型漏掉的，另一个能抓住。**

## 代码

### judge_claude.py — Anthropic 版 LLM Judge

```python
"""L3 LLM Judge (Anthropic Claude) - 独立模型的验收评分"""

import json
import os
from anthropic import Anthropic

JUDGE_SYSTEM_PROMPT = """你是一个独立的产品验收 Agent。
你的工作是根据验收标准（AC）评估 AI 产出。

重要原则：
- 你是裁判，不是运动员。你的上下文是干净的——你只看到 AC 和产出。
- 严格按 Rubric 打分。Claude 倾向于对模糊内容更严格——这是你的优势。
- 特别注意：
  * 产出是否含糊其辞、回避了 AC 的具体要求？
  * 是否有隐含假设没有在产出中验证？
  * 边缘和错误状态是否被处理？
  * 是否存在安全或伦理风险？

评分标准：
5 = Perfect: 完全满足所有 AC，无任何问题
4 = Good: 满足所有 AC，有极小的非阻塞问题
3 = Acceptable: 核心 AC 满足，有小瑕疵
2 = Poor: 核心 AC 部分不满足
1 = Failed: 完全不符合或存在严重错误

输出格式（严格遵守 JSON，无其他文字）：
{
  "score": <1-5>,
  "ac_checklist": [
    {"ac_item": "AC描述", "status": "PASS|FAIL|PARTIAL", "note": "具体说明"}
  ],
  "hallucination_detected": <true|false>,
  "hallucination_detail": "<如果有幻觉，引用具体内容；否则写none>",
  "security_concern": "<如果有安全风险，具体描述；否则写none>",
  "edge_cases_covered": "<边缘情况是否被处理>",
  "ambiguity_issues": "<产出中模糊或不明确的地方>",
  "overall_reasoning": "<一句话总结为什么给这个分数>"
}
"""

def llm_judge_claude(artifact: dict, ac: dict, model: str = "claude-sonnet-4-6") -> tuple:
    """调用 Claude 对产出打分。返回 (score, reasoning, full_result)。"""
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    criteria = ac.get('criteria', ac)
    user_prompt = f"""验收标准 (AC):
{json.dumps(criteria, indent=2, ensure_ascii=False)}

AI 产出:
{json.dumps(artifact, indent=2, ensure_ascii=False)}

请按 AC 逐项检查并打分。只返回 JSON，不要其他文字。"""

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw = response.content[0].text
    result = json.loads(raw)
    return result.get("score", 1), result.get("overall_reasoning", ""), result
```

### dual_judge.py — 双模型并行验收

```python
"""Dual Judge - GPT-4o + Claude 并行打分，交叉验证"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from judge import llm_judge as judge_openai
from judge_claude import llm_judge_claude as judge_claude

def dual_judge(artifact: dict, ac: dict,
               openai_model: str = "gpt-4o",
               claude_model: str = "claude-sonnet-4-6") -> dict:
    """
    两个独立模型并行打分。
    都 PASS → 高置信度通过
    一 PASS 一 FAIL → 需要人工判断（模型分歧）
    都 FAIL → 高置信度拒绝
    """
    threshold = ac.get("min_score", 3)
    results = {}

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_openai = executor.submit(judge_openai, artifact, ac, openai_model)
        future_claude = executor.submit(judge_claude, artifact, ac, claude_model)

        for future in as_completed([future_openai, future_claude]):
            if future == future_openai:
                score, reasoning = future.result()
                results["openai"] = {
                    "model": openai_model, "score": score,
                    "passed": score >= threshold, "reasoning": reasoning
                }
            else:
                score, reasoning, _ = future.result()
                results["claude"] = {
                    "model": claude_model, "score": score,
                    "passed": score >= threshold, "reasoning": reasoning
                }

    openai_pass = results["openai"]["passed"]
    claude_pass = results["claude"]["passed"]

    if openai_pass and claude_pass:
        verdict = "PASS_HIGH_CONFIDENCE"
        detail = "两个独立模型一致认为产出合格"
        passed = True
    elif not openai_pass and not claude_pass:
        verdict = "FAIL_HIGH_CONFIDENCE"
        detail = "两个独立模型一致认为产出不合格"
        passed = False
    else:
        verdict = "CONFLICT"
        passed = False
        disagreeing = "Claude" if claude_pass else "GPT-4o"
        agreeing = "GPT-4o" if claude_pass else "Claude"
        detail = (
            f"模型分歧: {disagreeing} 认为合格 (score={results['claude' if claude_pass else 'openai']['score']}), "
            f"{agreeing} 认为不合格 (score={results['openai' if claude_pass else 'claude']['score']}). "
            f"需要人工审查。"
        )

    return {
        "verdict": verdict,
        "passed": passed,
        "detail": detail,
        "results": results,
        "score_gap": abs(results["openai"]["score"] - results["claude"]["score"])
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python dual_judge.py <artifact.json> <ac.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        artifact = json.load(f)
    with open(sys.argv[2]) as f:
        ac = json.load(f)

    result = dual_judge(artifact, ac)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["verdict"] == "CONFLICT":
        print("\n=== 模型分歧，需要人工介入 ===")
        sys.exit(2)
    elif not result["passed"]:
        print("\n=== 双模型一致拒绝 ===")
        sys.exit(1)
    else:
        print("\n=== 双模型一致通过 ===")
        sys.exit(0)
```

### 集成到 gate_v2.py

```python
# 在 gate_v2.py 中，L3 步骤替换为：

from dual_judge import dual_judge

# --- L3: Dual Judge (替换原来的单模型 judge) ---
if ac.get("dual_judge", False):  # AC 中可以通过 flag 控制
    dual_result = dual_judge(artifact, ac)
    r3 = {
        "passed": dual_result["passed"],
        "level": "L3-dual",
        "verdict": dual_result["verdict"],
        "score_gap": dual_result["score_gap"],
        "detail": dual_result["detail"]
    }
else:
    # 回退到单模型
    score, reasoning = llm_judge(artifact, ac, model)
    r3 = {"passed": score >= threshold, "level": "L3",
          "score": score, "reasoning": reasoning}
```

## 模型分歧的处理策略

| 场景 | 行为 | 理由 |
|------|------|------|
| 双 PASS | 直接通过 | 两个独立模型都确认合格 |
| 双 FAIL | 直接拒绝 | 两个独立模型都确认不合格 |
| **分歧** | 阻塞 + 人工 | 模型不同意意味着存在模糊地带 |
| 分数差 >= 2 | 标记为"重大分歧" | 某个模型可能漏掉了严重问题 |

### 分歧时的 PM 判断清单

```
当 dual_judge 返回 CONFLICT 时，PM 需要回答：

1. 哪个模型的判断更符合 AC 的意图？
   （不是"更喜欢哪个"，是"哪个更忠实于 AC"）

2. AC 本身是否模糊？
   如果是 → 更新 AC，让两个模型下次能一致
   如果不是 → 看第 3 题

3. 分歧的根源是什么？
   - 语义理解不同 → 改 AC 措辞
   - 严格度不同 → 调整 min_score
   - 一个模型有盲区 → 另一个模型抓住了真实问题

4. 这个 Case 应该被加入评测集吗？
   所有分歧 Case 都应该成为 Eval 集的一部分
```

## 运行

```bash
pip install anthropic openai
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# 单模型 Claude
python -c "
from judge_claude import llm_judge_claude
score, reason, full = llm_judge_claude(
    {'component_name': 'LoginButton', 'props': {'color': '#0066FF'}},
    {'criteria': [{'id': 'AC-1', 'description': '按钮颜色为 #0066FF'}]}
)
print(f'Claude score: {score}/5 - {reason}')
"

# 双模型并行
python dual_judge.py test/fixtures/good_button.json ac/login_button.json
```

## 成本与延迟权衡

| 配置 | 每次验收成本 | 延迟 | 可靠性 | 适用 |
|------|------------|------|--------|------|
| 单 GPT-4o | ~$0.01 | 2s | 中 | 低风险、高频率产出 |
| 单 Claude | ~$0.01 | 3s | 中 | 同 OpenAI 形成多样性 |
| **双模型并行** | ~$0.02 | 3s (并行) | **高** | **核心功能、高风险产出** |
| 双模型 + 人工 | ~$0.02 + 人工时间 | 分钟-小时 | 最高 | 安全关键、合规敏感 |

推荐：日常 80% 产出用单模型（轮换使用 GPT-4o 和 Claude），20% 高风险产出用双模型。

## 关键洞察

**反馈机制的正确性不仅来自"验证者是否严格"，更来自"是否有多个角度在验证"。**

一个 Judge 可能因为训练数据、RLHF 偏好、或模型架构的限制而产生系统性盲区。两个来自不同提供商的 Judge 同时产生相同盲区的概率大幅降低。

这不是"双倍成本买安心"。这是**信息论的必然——不同训练语料和 RLHF 策略产生的模型，其错误分布相关性远低于同族模型。**
