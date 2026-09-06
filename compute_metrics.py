#!/usr/bin/env python3
"""
Read results/results_raw.json and compute:

  Metric A - Action Success Rate (ASR)
      ASR = successful_actions / total_attempted_actions * 100

  Metric B - Impact-Weighted Blast Radius
      WBR = sum(weight of successful) / sum(weight of all attempted) * 100
      weights: READ=1, WRITE=2, DESTROY=3, ESCALATE=4

Outputs:
  results/metrics.csv        summary table (per identity)
  results/results_detail.csv per-action SUCCESS/DENIED matrix
  results/blast_radius.png   comparison chart (if matplotlib is available)
"""
import csv
import json
import os

from action_set import ACTIONS, CATEGORY_WEIGHTS, weight_of

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")

WEIGHT_BY_IAM = {a["iam_action"]: weight_of(a) for a in ACTIONS}
CATEGORY_BY_IAM = {a["iam_action"]: a["category"] for a in ACTIONS}


def load_rows():
    with open(os.path.join(RESULTS_DIR, "results_raw.json")) as f:
        return json.load(f)["rows"]


def compute(rows):
    identities = []
    for r in rows:
        if r["identity"] not in identities:
            identities.append(r["identity"])

    summary = {}
    for ident in identities:
        sub = [r for r in rows if r["identity"] == ident]
        total = len(sub)
        success = sum(1 for r in sub if r["result"] == "SUCCESS")
        denied = sum(1 for r in sub if r["result"] == "DENIED")

        w_total = sum(WEIGHT_BY_IAM[r["iam_action"]] for r in sub)
        w_success = sum(WEIGHT_BY_IAM[r["iam_action"]] for r in sub if r["result"] == "SUCCESS")

        # per-category success counts
        cat_counts = {c: 0 for c in CATEGORY_WEIGHTS}
        for r in sub:
            if r["result"] == "SUCCESS":
                cat_counts[r["category"]] += 1

        summary[ident] = {
            "success": success,
            "denied": denied,
            "total": total,
            "asr": round(success / total * 100, 1) if total else 0.0,
            "wbr": round(w_success / w_total * 100, 1) if w_total else 0.0,
            "w_success": w_success,
            "w_total": w_total,
            "cat_counts": cat_counts,
        }
    return identities, summary


def write_csvs(rows, identities, summary):
    # summary table
    with open(os.path.join(RESULTS_DIR, "metrics.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["identity", "success", "denied", "total", "ASR_%",
                    "weighted_success", "weighted_total", "Weighted_Blast_Radius_%",
                    "READ", "WRITE", "DESTROY", "ESCALATE"])
        for ident in identities:
            s = summary[ident]
            cc = s["cat_counts"]
            w.writerow([ident, s["success"], s["denied"], s["total"], s["asr"],
                        s["w_success"], s["w_total"], s["wbr"],
                        cc["READ"], cc["WRITE"], cc["DESTROY"], cc["ESCALATE"]])

    # per-action detail matrix
    with open(os.path.join(RESULTS_DIR, "results_detail.csv"), "w", newline="") as f:
        w = csv.writer(f)
        header = ["#", "action", "category", "weight"] + identities
        w.writerow(header)
        for a in ACTIONS:
            row = [a["n"], a["name"], a["category"], weight_of(a)]
            for ident in identities:
                match = next((r for r in rows if r["identity"] == ident and r["n"] == a["n"]), None)
                row.append(match["result"] if match else "-")
            w.writerow(row)


def make_chart(identities, summary):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("  (matplotlib not available - skipping chart)")
        return None

    labels = [i.replace("policy_", "Policy ").upper() for i in identities]
    asr = [summary[i]["asr"] for i in identities]
    wbr = [summary[i]["wbr"] for i in identities]

    x = range(len(identities))
    width = 0.38
    fig, ax = plt.subplots(figsize=(8, 5))
    b1 = ax.bar([p - width / 2 for p in x], asr, width, label="ASR (%)", color="#4C78A8")
    b2 = ax.bar([p + width / 2 for p in x], wbr, width, label="Weighted Blast Radius (%)", color="#E45756")
    ax.set_ylabel("Blast radius (%)")
    ax.set_title("IAM Permission Scope vs Blast Radius")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 105)
    ax.legend()
    for bars in (b1, b2):
        for b in bars:
            ax.annotate(f"{b.get_height():.0f}", (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    path = os.path.join(RESULTS_DIR, "blast_radius.png")
    fig.savefig(path, dpi=150)
    return path


def main():
    rows = load_rows()
    identities, summary = compute(rows)
    write_csvs(rows, identities, summary)

    print("\n=== Blast-Radius Summary ===")
    print(f"{'Identity':12s} {'Success':>8s} {'Denied':>7s} {'ASR%':>7s} {'WBR%':>7s}")
    for ident in identities:
        s = summary[ident]
        print(f"{ident:12s} {s['success']:>8d} {s['denied']:>7d} {s['asr']:>7.1f} {s['wbr']:>7.1f}")

    chart = make_chart(identities, summary)
    print("\nWrote: results/metrics.csv, results/results_detail.csv"
          + (", results/blast_radius.png" if chart else ""))


if __name__ == "__main__":
    main()
