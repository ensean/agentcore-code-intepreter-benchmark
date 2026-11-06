"""AgentCore Code Interpreter cost benchmark: LLM (Claude Opus 5.5) generates code, CI executes it.

One new Code Interpreter session per request, stopped right after the artifact is downloaded.
Writes one JSON line per request to results/runs.jsonl.

Usage: python run_bench.py <code_interpreter_id> [runs_per_case] [parallel]
"""
from __future__ import annotations

import csv
import io
import json
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

REGION = "ap-northeast-1"
MODEL_ID = "global.anthropic.claude-opus-5-5"
MAX_TURNS = 10
SESSION_TIMEOUT = 900

cfg = Config(region_name=REGION, retries={"mode": "adaptive", "max_attempts": 8}, read_timeout=300)
bedrock = boto3.client("bedrock-runtime", config=cfg)
ci = boto3.client("bedrock-agentcore", config=cfg)

OUT = Path("results")
ART = OUT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()

SYSTEM = (
    "You are a data/code assistant. You can run Python 3.12 in a sandbox via the execute_python tool "
    "(pandas, numpy and matplotlib are available, no internet access). Files you write in the current "
    "working directory are returned to the user. Write the requested file, verify it, then reply with a "
    "one-paragraph summary. Keep tool calls to what is necessary."
)

TOOLS = {
    "tools": [
        {
            "toolSpec": {
                "name": "execute_python",
                "description": "Execute Python code in a stateful sandbox. Returns stdout, stderr and exit code.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {"code": {"type": "string", "description": "Python source to execute"}},
                        "required": ["code"],
                    }
                },
            }
        }
    ]
}

CASES = {
    "csv_gen": {
        "prompt": (
            "Generate a synthetic e-commerce orders dataset with exactly 10,000 rows and these 10 columns: "
            "order_id, order_date (2025), region, country, product, category, quantity, unit_price, discount, revenue. "
            "Values should be realistic and revenue = quantity*unit_price*(1-discount). Save it as orders.csv, "
            "then print the row count, column list and the first 3 rows."
        ),
        "artifact": "orders.csv",
        "upload": False,
    },
    "csv_to_html_report": {
        "prompt": (
            "The file sales.csv (10,000 rows) is in the working directory. Analyse it with pandas and build a "
            "self-contained HTML report saved as report.html containing: KPI summary (total revenue, orders, AOV), "
            "monthly revenue by region (table + line chart), top 10 products by revenue (table + bar chart), and "
            "category revenue share (pie chart). Render charts with matplotlib and embed them as base64 PNG. "
            "Use simple inline CSS."
        ),
        "artifact": "report.html",
        "upload": True,
    },
    "static_html": {
        "prompt": (
            "Create a responsive single-file landing page for a fictional SaaS product 'CloudNote' with a hero "
            "section, a 6-item feature grid, a 3-tier pricing table, an FAQ section and a footer. Inline CSS only, "
            "no external assets. Write it with Python to index.html and validate it parses with html.parser."
        ),
        "artifact": "index.html",
        "upload": False,
    },
}


def make_sales_csv() -> str:
    rnd = random.Random(42)
    regions = ["APAC", "EMEA", "NA", "LATAM"]
    products = [(f"Product-{i:02d}", rnd.choice(["Electronics", "Home", "Sports", "Books", "Beauty"]), rnd.uniform(5, 500)) for i in range(40)]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order_id", "order_date", "region", "product", "category", "quantity", "unit_price", "discount", "revenue", "customer_segment"])
    for i in range(10000):
        p, cat, price = rnd.choice(products)
        q = rnd.randint(1, 10)
        d = rnd.choice([0, 0, 0.05, 0.1, 0.2])
        date = f"2025-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"
        w.writerow([f"O{i:06d}", date, rnd.choice(regions), p, cat, q, round(price, 2), d, round(q * price * (1 - d), 2), rnd.choice(["Consumer", "SMB", "Enterprise"])])
    return buf.getvalue()


SALES_CSV = make_sales_csv()


def ci_call(sid: str, ci_id: str, name: str, args: dict) -> dict:
    r = ci.invoke_code_interpreter(codeInterpreterIdentifier=ci_id, sessionId=sid, name=name, arguments=args)
    result: dict = {}
    for ev in r["stream"]:
        if "result" in ev:
            result = ev["result"]
    return result


def run_one(ci_id: str, case: str, idx: int) -> dict:
    spec = CASES[case]
    rec: dict = {"case": case, "run": idx, "model": MODEL_ID, "code_interpreter_id": ci_id}
    llm_s = tool_s = 0.0
    in_tok = out_tok = 0
    n_exec = 0
    exec_time_reported = 0.0
    t0 = time.time()
    s = ci.start_code_interpreter_session(
        codeInterpreterIdentifier=ci_id, name=f"{case}-{idx}-{uuid.uuid4().hex[:6]}", sessionTimeoutSeconds=SESSION_TIMEOUT
    )
    sid = s["sessionId"]
    t_started = time.time()
    rec.update(session_id=sid, start_utc=datetime.now(timezone.utc).isoformat(), start_session_api_s=round(t_started - t0, 3))
    ok = False
    err = None
    transcript: list = []
    try:
        if spec["upload"]:
            t = time.time()
            ci_call(sid, ci_id, "writeFiles", {"content": [{"path": "sales.csv", "text": SALES_CSV}]})
            tool_s += time.time() - t
        messages = [{"role": "user", "content": [{"text": spec["prompt"]}]}]
        for _turn in range(MAX_TURNS):
            t = time.time()
            resp = bedrock.converse(
                modelId=MODEL_ID, system=[{"text": SYSTEM}], messages=messages, toolConfig=TOOLS,
                inferenceConfig={"maxTokens": 16000},
            )
            llm_s += time.time() - t
            in_tok += resp["usage"]["inputTokens"]
            out_tok += resp["usage"]["outputTokens"]
            msg = resp["output"]["message"]
            messages.append(msg)
            if resp["stopReason"] != "tool_use":
                break
            results = []
            for block in msg["content"]:
                if "toolUse" not in block:
                    continue
                tu = block["toolUse"]
                t = time.time()
                r = ci_call(sid, ci_id, "executeCode", {"language": "python", "code": tu["input"].get("code", "")})
                tool_s += time.time() - t
                n_exec += 1
                sc = r.get("structuredContent", {})
                transcript.append({"step": n_exec, "code": tu["input"].get("code", ""), "stdout": sc.get("stdout", ""),
                                   "stderr": sc.get("stderr", ""), "exitCode": sc.get("exitCode"),
                                   "executionTime": sc.get("executionTime")})
                exec_time_reported += float(sc.get("executionTime") or 0)
                text = json.dumps({"stdout": sc.get("stdout", "")[-6000:], "stderr": sc.get("stderr", "")[-3000:], "exitCode": sc.get("exitCode")})
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"text": text}], "status": "error" if r.get("isError") else "success"}})
            messages.append({"role": "user", "content": results})
        # download the artifact (part of a real request)
        t = time.time()
        r = ci_call(sid, ci_id, "readFiles", {"paths": [spec["artifact"]]})
        tool_s += time.time() - t
        body = ""
        for c in r.get("content", []):
            res = c.get("resource") or {}
            body = res.get("text") or res.get("blob") or body
        if body:
            (ART / f"{case}-{idx}-{spec['artifact']}").write_text(body if isinstance(body, str) else str(body))
            ok = True
        rec["artifact_bytes"] = len(body)
    except Exception as e:  # keep the run record even if the agent fails
        err = repr(e)
    finally:
        t = time.time()
        ci.stop_code_interpreter_session(codeInterpreterIdentifier=ci_id, sessionId=sid)
        t_end = time.time()
        rec.update(stop_session_api_s=round(t_end - t, 3))
    rec.update(
        ok=ok, error=err, end_utc=datetime.now(timezone.utc).isoformat(),
        session_wall_s=round(t_end - t0, 2), llm_wait_s=round(llm_s, 2), ci_api_s=round(tool_s, 2),
        code_exec_calls=n_exec, code_exec_reported_s=round(exec_time_reported, 2),
        llm_turns=sum(1 for m in messages if m["role"] == "assistant") if "messages" in locals() else 0,
        input_tokens=in_tok, output_tokens=out_tok,
    )
    with lock:
        final_text = ""
        if "messages" in locals() and messages and messages[-1]["role"] == "assistant":
            final_text = "".join(b.get("text", "") for b in messages[-1]["content"])
        (OUT / "transcripts").mkdir(exist_ok=True)
        (OUT / "transcripts" / f"{case}-{idx}.json").write_text(json.dumps(
            {"case": case, "prompt": spec["prompt"], "system": SYSTEM, "steps": transcript, "final_answer": final_text},
            ensure_ascii=False, indent=2))
        with open(OUT / "runs.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{case} #{idx}] ok={ok} wall={rec['session_wall_s']}s llm={rec['llm_wait_s']}s ci={rec['ci_api_s']}s exec_calls={n_exec} err={err}", flush=True)
    return rec


def main() -> None:
    ci_id = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    par = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    jobs = [(case, i) for i in range(1, runs + 1) for case in CASES]
    with ThreadPoolExecutor(max_workers=par) as ex:
        list(ex.map(lambda j: run_one(ci_id, *j), jobs))


if __name__ == "__main__":
    main()
