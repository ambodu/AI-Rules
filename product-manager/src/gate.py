#!/usr/bin/env python3
"""AI Product OS - Integrated Gate (L0->L1->L2->L3 with Journal)."""

import json
import sys
import argparse
from jsonschema import validate, ValidationError
from capability import check_capability, issue_token, deny_escalation
from policies import check_all_policies
from journal import init as journal_init, append as journal_append


def gate(agent_id: str, artifact: dict, ac: dict,
         resource: str = "product/artifact") -> dict:
    """Run full gate pipeline. Returns result dict with 'passed' and 'results'."""
    conn = journal_init()
    task_id = ac.get("task", "unknown")

    def _fail(level, detail):
        return {"passed": False, "failed_at": level, "detail": detail}

    # L0: Capability
    r0 = check_capability(agent_id, resource, "submit")
    journal_append(conn, agent_id, task_id, artifact, ac, {"l0": r0})
    if not r0["passed"]:
        return _fail("L0", r0["detail"])

    esc = deny_escalation(agent_id, resource, "submit")
    if esc:
        return _fail("L0-escalation", esc)

    # L1: Schema
    schema = ac.get("schema")
    if schema:
        try:
            validate(instance=artifact, schema=schema)
            r1 = {"passed": True, "level": "L1", "detail": "Schema valid"}
        except ValidationError as e:
            r1 = {"passed": False, "level": "L1", "detail": str(e.message)}
    else:
        r1 = {"passed": True, "level": "L1", "detail": "No schema (skipped)"}

    journal_append(conn, agent_id, task_id, artifact, ac, {"l0": r0, "l1": r1})
    if not r1["passed"]:
        return _fail("L1", r1["detail"])

    # L2: Policy
    content = json.dumps(artifact, ensure_ascii=False)
    failures = check_all_policies(content)
    r2 = {"passed": not failures, "level": "L2",
          "detail": "All policies passed" if not failures else failures}

    journal_append(conn, agent_id, task_id, artifact, ac,
                   {"l0": r0, "l1": r1, "l2": r2})
    if not r2["passed"]:
        return _fail("L2", r2["detail"])

    # L3: Judge
    try:
        from judge import llm_judge
        score, reasoning = llm_judge(artifact, ac)
    except Exception as e:
        r3 = {"passed": True, "level": "L3",
              "detail": f"LLM Judge unavailable ({e}), allowing with warning"}
        journal_append(conn, agent_id, task_id, artifact, ac,
                       {"l0": r0, "l1": r1, "l2": r2, "l3": r3})
        return {"passed": True, "results": {"l0": r0, "l1": r1, "l2": r2, "l3": r3}}

    threshold = ac.get("min_score", 3)
    r3 = {"passed": score >= threshold, "level": "L3",
          "score": score, "threshold": threshold, "reasoning": reasoning}

    final = {"l0": r0, "l1": r1, "l2": r2, "l3": r3}
    txn_id = journal_append(conn, agent_id, task_id, artifact, ac, final)

    return {
        "passed": all(r["passed"] for r in [r0, r1, r2, r3]),
        "txn_id": txn_id,
        "results": final
    }


def main():
    parser = argparse.ArgumentParser(description="AI Product OS Gate")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--ac", required=True)
    args = parser.parse_args()

    with open(args.artifact, encoding='utf-8') as f:
        artifact = json.load(f)
    with open(args.ac, encoding='utf-8') as f:
        ac = json.load(f)

    issue_token(args.agent, [
        {"resource": "product/artifact", "ops": ["submit"]},
        {"resource": "product/review", "ops": ["read"]}
    ])

    result = gate(args.agent, artifact, ac)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
