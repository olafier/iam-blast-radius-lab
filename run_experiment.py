#!/usr/bin/env python3
"""
Run the Fixed Action Set (100 actions) against each identity (Policy A / B / C)
and record SUCCESS / DENIED for every action.

Modes:

  --mock  (default)  No AWS needed. A small local IAM policy evaluator decides
                     Allow/Deny by matching each action against the policy JSON.
                     Use this to develop and validate the whole pipeline first.

  --simulate         Uses the REAL AWS IAM Policy Simulator
                     (iam:SimulateCustomPolicy) to evaluate each policy JSON
                     against all 100 actions. This is AWS's own decision engine
                     -- but it needs NO S3/EC2/IAM resources and makes NO real
                     changes, so it is free and safe. Recommended path for a
                     100-action set. Requires: pip install boto3 + AWS creds
                     with iam:SimulateCustomPolicy permission.

(Full real-invocation mode -- actually calling all 100 APIs -- is intentionally
 not implemented: at 100 actions it would create/destroy real resources and is
 unnecessary when the simulator returns the same Allow/Deny decision.)

Output: results/results_raw.json  (one row per identity x action)

Examples:
  python run_experiment.py --mock
  python run_experiment.py --simulate --region us-east-1
"""
import argparse
import fnmatch
import json
import os
import datetime

from action_set import ACTIONS

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY_DIR = os.path.join(HERE, "policies")
RESULTS_DIR = os.path.join(HERE, "results")

IDENTITIES = {
    "policy_a": "policy_a_narrow.json",
    "policy_b": "policy_b_moderate.json",
    "policy_c": "policy_c_broad.json",
}


def load_policy_doc(policy_file):
    with open(os.path.join(POLICY_DIR, policy_file)) as f:
        return f.read()


# ---------------------------------------------------------------------------
# MOCK MODE -- a minimal local IAM evaluator
# ---------------------------------------------------------------------------
def load_allowed_patterns(policy_file):
    doc = json.loads(load_policy_doc(policy_file))
    patterns = []
    statements = doc.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]
    for st in statements:
        if st.get("Effect") != "Allow":
            continue
        actions = st.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]
        patterns.extend(actions)
    return patterns


def mock_is_allowed(iam_action, patterns):
    return any(fnmatch.fnmatch(iam_action, p) for p in patterns)


def run_mock():
    rows = []
    for identity, policy_file in IDENTITIES.items():
        patterns = load_allowed_patterns(policy_file)
        for a in ACTIONS:
            ok = mock_is_allowed(a["iam_action"], patterns)
            rows.append({
                "identity": identity, "n": a["n"], "action": a["name"],
                "iam_action": a["iam_action"], "category": a["category"],
                "service": a["service"],
                "result": "SUCCESS" if ok else "DENIED", "mode": "mock",
            })
    return rows


# ---------------------------------------------------------------------------
# SIMULATE MODE -- real AWS IAM Policy Simulator, no resources needed
# ---------------------------------------------------------------------------
def run_simulate(region):
    import boto3
    from botocore.exceptions import ClientError

    iam = boto3.Session(region_name=region).client("iam")
    all_actions = [a["iam_action"] for a in ACTIONS]
    rows = []

    for identity, policy_file in IDENTITIES.items():
        policy_doc = load_policy_doc(policy_file)
        decisions = {}
        # SimulateCustomPolicy accepts many actions; chunk to stay well within limits.
        for i in range(0, len(all_actions), 25):
            chunk = all_actions[i:i + 25]
            try:
                resp = iam.simulate_custom_policy(
                    PolicyInputList=[policy_doc],
                    ActionNames=chunk,
                )
            except ClientError as e:
                raise SystemExit(f"Simulator error for {identity}: "
                                 f"{e.response['Error']['Code']} - {e.response['Error']['Message']}")
            for r in resp["EvaluationResults"]:
                decisions[r["EvalActionName"]] = r["EvalDecision"]

        for a in ACTIONS:
            decision = decisions.get(a["iam_action"], "implicitDeny")
            ok = decision == "allowed"
            rows.append({
                "identity": identity, "n": a["n"], "action": a["name"],
                "iam_action": a["iam_action"], "category": a["category"],
                "service": a["service"],
                "result": "SUCCESS" if ok else "DENIED",
                "detail": decision, "mode": "simulate",
            })
    return rows


def main():
    ap = argparse.ArgumentParser(description="Run IAM blast-radius fixed action set (100 actions).")
    ap.add_argument("--mode", choices=["mock", "simulate"], default="mock")
    ap.add_argument("--mock", dest="mode", action="store_const", const="mock")
    ap.add_argument("--simulate", dest="mode", action="store_const", const="simulate")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args()

    rows = run_simulate(args.region) if args.mode == "simulate" else run_mock()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": args.mode,
        "n_actions": len(ACTIONS),
        "rows": rows,
    }
    path = os.path.join(RESULTS_DIR, "results_raw.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"[{args.mode}] wrote {len(rows)} result rows -> {path}\n")
    for identity in IDENTITIES:
        s = sum(1 for r in rows if r["identity"] == identity and r["result"] == "SUCCESS")
        t = sum(1 for r in rows if r["identity"] == identity)
        print(f"  {identity:10s}  SUCCESS={s:3d}  DENIED={t - s:3d}")


if __name__ == "__main__":
    main()
