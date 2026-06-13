"""L3 LLM Judge - Anthropic Claude based verification."""

import json
import os
from anthropic import Anthropic

JUDGE_SYSTEM_PROMPT = """You are an independent product verification agent.
Your job is to evaluate AI output against acceptance criteria (AC).

Key principles:
- You are the referee, not the athlete. Your context is clean.
- Score strictly against the rubric. Claude tends to be stricter on ambiguity - use this.
- Pay special attention to: vague statements, unvalidated assumptions,
  missing edge cases, unhandled error states, security/ethics risks.

Scoring rubric:
5 = Perfect: All AC met, no issues
4 = Good: All AC met, very minor non-blocking issues
3 = Acceptable: Core AC met, small flaws
2 = Poor: Core AC partially unmet
1 = Failed: Completely off or contains serious errors

Output format (strict JSON only, no other text):
{
  "score": <1-5>,
  "ac_checklist": [{"ac_item": "desc", "status": "PASS|FAIL|PARTIAL", "note": "detail"}],
  "hallucination_detected": <true|false>,
  "hallucination_detail": "<specific quote or 'none'>",
  "security_concern": "<specific concern or 'none'>",
  "edge_cases_covered": "<assessment of edge case handling>",
  "ambiguity_issues": "<vague or unclear parts of the output>",
  "overall_reasoning": "<one sentence why this score>"
}"""


def llm_judge_claude(artifact: dict, ac: dict, model: str = "claude-sonnet-4-6") -> tuple:
    """Score artifact against AC using Claude. Returns (score, reasoning, full_result)."""
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    criteria = ac.get('criteria', ac)
    user_prompt = f"""Acceptance Criteria (AC):
{json.dumps(criteria, indent=2, ensure_ascii=False)}

AI Output:
{json.dumps(artifact, indent=2, ensure_ascii=False)}

Check each AC item and score. Return ONLY the JSON object, no other text."""

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
