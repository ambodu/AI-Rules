"""L2 Policy Engine - hardcoded rules, no LLM dependency."""

import re
from typing import List, Tuple

RULES: List[Tuple[str, str, str]] = [
    # Privacy
    (r'\b\d{3}-\d{2}-\d{4}\b', 'Possible SSN detected', 'Sev-0'),
    (r'\b\d{11}\b', 'Possible phone number (11 consecutive digits)', 'Sev-0'),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'\w]', 'Hardcoded password', 'Sev-0'),
    # Injection
    (r'(?i)(<script|javascript:|onerror\s*=)', 'Possible XSS injection', 'Sev-0'),
    (r'(?i)(DROP\s+TABLE|DELETE\s+FROM\s+\w+|UNION\s+SELECT)', 'Possible SQL injection', 'Sev-0'),
    # Content safety
    (r'(?i)\b(hate|kill|attack)\b.*\b(all|everyone)\b', 'Possible violent/hate content', 'Sev-1'),
    # Empty values
    (r'""\s*:\s*""', 'Empty string value (possibly incomplete output)', 'Sev-2'),
]


def check_all_policies(content: str) -> List[str]:
    """Run all rules, return list of violations."""
    violations = []
    for pattern, description, severity in RULES:
        if re.search(pattern, content):
            violations.append(f"[{severity}] {description}")
    return violations
