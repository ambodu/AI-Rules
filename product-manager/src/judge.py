"""L3 LLM Judge - OpenAI GPT-4o based verification."""

import json
import os
from openai import OpenAI

JUDGE_SYSTEM_PROMPT = """You are an independent product verification agent.
Your job is to evaluate AI output against acceptance criteria (AC).

Key principles:
- You are the referee, not the athlete. Your context is clean.
- Score strictly against the rubric. Do not inflate scores.
- If output is vague, incomplete, or deviates from AC - deduct.

Scoring rubric:
5 = Perfect: All AC met, no issues
4 = Good: All AC met, very minor non-blocking issues
3 = Acceptable: Core AC met, small flaws
2 = Poor: Core AC partially unmet
1 = Failed: Completely off or contains serious errors

Output format (strict JSON only):
{
  "score": <1-5>,
  "ac_checklist": [{"ac_item": "desc", "status": "PASS|FAIL|PARTIAL", "note": "detail"}],
  "hallucination_detected": <true|false>,
  "hallucination_detail": "<specific quote or 'none'>",
  "security_concern": "<specific concern or 'none'>",
  "overall_reasoning": "<one sentence why this score>"
}"""


def llm_judge(artifact: dict, ac: dict, model: str = "gpt-4o") -> tuple:
    """Score artifact against AC using GPT-4o. Returns (score, reasoning)."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    criteria = ac.get('criteria', ac)
    user_prompt = f"""Acceptance Criteria (AC):
{json.dumps(criteria, indent=2, ensure_ascii=False)}

AI Output:
{json.dumps(artifact, indent=2, ensure_ascii=False)}

Check each AC item and score."""

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
