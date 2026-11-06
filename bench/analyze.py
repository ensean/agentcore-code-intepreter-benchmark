"""Join benchmark runs with Code Interpreter USAGE_LOGS and estimate cost.

Usage: python3 bench/analyze.py   (reads results/runs.jsonl, results/usage_logs_full_day.json)
Writes results/per_session.csv and prints per-case summary + monthly extrapolation.
"""
from __future__ import annotations

import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

VCPU_HR = 0.0895    # USD per vCPU-hour, APN1-CodeInterpreter:Consumption-based:vCPU
GB_HR = 0.00945     # USD per GB-hour,  APN1-CodeInterpreter:Consumption-based:Memory
VOLUMES = [10_000, 100_000, 1_000_000]

R = Path("results")
runs = [json.loads(l) for l in open(R / "runs.jsonl")]
events = [json.loads(m) for m in json.load(open(R / "usage_logs_full_day.json"))]

usage: dict = defaultdict(lambda: {"vcpu_h": 0.0, "gb_h": 0.0, "secs": 0.0, "n": 0, "peak_gb": 0.0, "vcpu_s_series": []})
for e in events:
    sid = e["attributes"]["session.id"]
    u = usage[sid]
    v = e["metrics"]["codeInterpreter.vcpu.hours.used"]
    g = e["metrics"]["codeInterpreter.memory.gb_hours.used"]
    dt = float(e["attributes"]["time_elapsed_seconds"]) or 1.0
    u["vcpu_h"] += v
    u["gb_h"] += g
    u["secs"] += dt
    u["n"] += 1
    u["peak_gb"] = max(u["peak_gb"], g * 3600 / dt)

rows = []
for r in runs:
    u = usage.get(r["session_id"])
    if not u:
        print("no usage logs for", r["session_id"])
        continue
    cpu_cost = u["vcpu_h"] * VCPU_HR
    mem_cost = u["gb_h"] * GB_HR
    rows.append({
        "case": r["case"], "run": r["run"], "session_id": r["session_id"],
        "session_wall_s": r["session_wall_s"], "llm_wait_s": r["llm_wait_s"], "ci_api_s": r["ci_api_s"],
        "code_exec_calls": r["code_exec_calls"], "billed_seconds": round(u["secs"], 2),
        "vcpu_seconds": round(u["vcpu_h"] * 3600, 3), "gb_seconds": round(u["gb_h"] * 3600, 3),
        "avg_gb": round(u["gb_h"] * 3600 / u["secs"], 3), "peak_gb": round(u["peak_gb"], 3),
        "cpu_cost_usd": cpu_cost, "mem_cost_usd": mem_cost, "total_cost_usd": cpu_cost + mem_cost,
        "artifact_bytes": r.get("artifact_bytes"),
    })

with open(R / "per_session.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)


def pct(xs: list, p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


summary = {}
print(f"{'case':22} {'n':>3} {'wall_s':>7} {'llm_s':>6} {'billed_s':>8} {'vCPU_s':>7} {'avgGB':>6} {'peakGB':>6} {'cpu$':>10} {'mem$':>10} {'mean$/req':>10} {'p90$/req':>10}")
for case in ["csv_gen", "csv_to_html_report", "static_html"]:
    xs = [r for r in rows if r["case"] == case]
    m = lambda k: st.mean(r[k] for r in xs)
    tot = [r["total_cost_usd"] for r in xs]
    summary[case] = {"mean": st.mean(tot), "p50": pct(tot, .5), "p90": pct(tot, .9), "min": min(tot), "max": max(tot),
                     "cpu": m("cpu_cost_usd"), "mem": m("mem_cost_usd")}
    print(f"{case:22} {len(xs):>3} {m('session_wall_s'):7.1f} {m('llm_wait_s'):6.1f} {m('billed_seconds'):8.1f} {m('vcpu_seconds'):7.2f} "
          f"{m('avg_gb'):6.2f} {st.mean(r['peak_gb'] for r in xs):6.2f} {m('cpu_cost_usd'):10.6f} {m('mem_cost_usd'):10.6f} "
          f"{summary[case]['mean']:10.6f} {summary[case]['p90']:10.6f}")

allc = [r["total_cost_usd"] for r in rows]
print(f"\nall sessions: n={len(rows)} total=${sum(allc):.6f} mean/req=${st.mean(allc):.6f}")
print(f"sum vCPU-h={sum(r['vcpu_seconds'] for r in rows)/3600:.6f}  GB-h={sum(r['gb_seconds'] for r in rows)/3600:.6f}")
print("\nmonthly extrapolation (mean per request, USD):")
print(f"{'case':22} " + " ".join(f"{v:>12,}" for v in VOLUMES))
for case, s in summary.items():
    print(f"{case:22} " + " ".join(f"{s['mean']*v:12.2f}" for v in VOLUMES))
mix = st.mean(s["mean"] for s in summary.values())
print(f"{'equal mix (1/3 each)':22} " + " ".join(f"{mix*v:12.2f}" for v in VOLUMES))
json.dump(summary, open(R / "summary.json", "w"), indent=2)
