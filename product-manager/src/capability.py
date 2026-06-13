"""L0 Capability System - agent permission checks at kernel level."""

import fnmatch
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta


class Capability:
    def __init__(self, resource: str, ops: List[str]):
        self.resource = resource
        self.ops = ops


class CapabilityToken:
    def __init__(self, agent_id: str, capabilities: List[Capability],
                 max_budget_usd: float, expires_at: str):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.max_budget_usd = max_budget_usd
        self.expires_at = expires_at
        self.spent_usd = 0.0

    def is_expired(self) -> bool:
        return datetime.fromisoformat(self.expires_at) < datetime.now(timezone.utc)

    def can(self, resource: str, operation: str) -> bool:
        for cap in self.capabilities:
            if fnmatch.fnmatch(resource, cap.resource):
                if operation in cap.ops:
                    return True
        return False


_TOKEN_REGISTRY: Dict[str, CapabilityToken] = {}

DANGEROUS_OPS = {"delete", "drop", "truncate", "rm", "purge"}


def issue_token(agent_id: str, capabilities: List[dict],
                max_budget_usd: float = 5.0, ttl_minutes: int = 60) -> CapabilityToken:
    caps = [Capability(c['resource'], c.get('ops', ['read'])) for c in capabilities]
    expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    token = CapabilityToken(agent_id, caps, max_budget_usd, expires)
    _TOKEN_REGISTRY[agent_id] = token
    return token


def check_capability(agent_id: str, resource: str, operation: str) -> dict:
    token = _TOKEN_REGISTRY.get(agent_id)
    if not token:
        return {"passed": False, "level": "L0",
                "detail": f"Agent '{agent_id}' has no valid Capability Token"}
    if token.is_expired():
        return {"passed": False, "level": "L0",
                "detail": f"Token expired at {token.expires_at}"}
    if not token.can(resource, operation):
        return {"passed": False, "level": "L0",
                "detail": f"Agent '{agent_id}' cannot '{operation}' on '{resource}'"}
    return {"passed": True, "level": "L0",
            "detail": f"Capability OK: {resource}:{operation}"}


def is_dangerous(operation: str) -> bool:
    return operation.lower() in DANGEROUS_OPS


def deny_escalation(agent_id: str, resource: str, operation: str) -> Optional[dict]:
    if is_dangerous(operation):
        return {
            "blocked": True,
            "reason": f"Dangerous operation '{operation}' requires human approval",
            "required_action": "PM must APPROVE or DENY within 5 minutes"
        }
    return None
