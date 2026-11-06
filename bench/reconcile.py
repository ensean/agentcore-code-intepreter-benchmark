"""Compare benchmark-script timings with USAGE_LOGS per session, and check a client-only cost estimate.

Usage: python3 bench/reconcile.py   (reads results/runs.jsonl, results/usage_logs_full_day.json)
"""
from __future__ import annotations

import json
import statistics as st

VCPU_HR, GB_HR = 0.0895, 0.00945
runs = [json.loads(l) for l in open("results/runs.jsonl")]
usage: dict = {}
for m in json.load(open("results/usage_logs_full_day.json")):
    e = json.loads(m)
    d = usage.setdefault(e["attributes"]["session.id"], {"sec": 0.0, "v": 0.0, "g": 0.0})
    d["sec"] += float(e["attributes"]["time_elapsed_seconds"])
    d["v"] += e["metrics"]["codeInterpreter.vcpu.hours.used"]
    d["g"] += e["metrics"]["codeInterpreter.memory.gb_hours.used"]

rows = []
for r in runs:
    d = usage[r["session_id"]]
    actual = d["v"] * VCPU_HR + d["g"] * GB_HR
    naive = r["session_wall_s"] * 1.42 * GB_HR / 3600 + r["code_exec_reported_s"] * VCPU_HR / 3600
    rows.append({"case": r["case"], "wall": r["session_wall_s"], "billed": d["sec"], "exec": r["code_exec_reported_s"],
                 "vcpu_s": d["v"] * 3600, "actual": actual, "naive": naive})


def s(xs: list) -> str:
    return f"mean={st.mean(xs):.2f} min={min(xs):.2f} max={max(xs):.2f}"


print(f"matched sessions: {len(rows)}/{len(runs)}")
print("billed_s - wall_s:          ", s([x["billed"] - x["wall"] for x in rows]))
print("vCPU-s / executionTime:     ", s([x["vcpu_s"] / x["exec"] for x in rows if x["exec"] > 0]))
print("naive client estimate/actual:", s([x["naive"] / x["actual"] for x in rows]))
for c in ["csv_gen", "csv_to_html_report", "static_html"]:
    xs = [x for x in rows if x["case"] == c]
    print(f"{c:20} wall={st.mean(x['wall'] for x in xs):5.1f} billed={st.mean(x['billed'] for x in xs):5.1f} "
          f"exec={st.mean(x['exec'] for x in xs):4.2f} vCPU-s={st.mean(x['vcpu_s'] for x in xs):4.2f} "
          f"naive=${st.mean(x['naive'] for x in xs):.6f} actual=${st.mean(x['actual'] for x in xs):.6f}")
