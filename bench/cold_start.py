"""Code Interpreter cold-start benchmark (no LLM).

Per session: Start -> executeCode print(1) immediately (cold) -> print(1) again (warm)
-> import pandas+matplotlib (first import) -> same import again -> Stop.
Usage: python cold_start.py <ci_id_or_builtin> <n_sequential> <burst_concurrency>
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import boto3
from botocore.config import Config

cfg = Config(region_name="ap-northeast-1", retries={"mode": "adaptive", "max_attempts": 8}, max_pool_connections=50)
ci = boto3.client("bedrock-agentcore", config=cfg)
IMPORTS = "import pandas, numpy, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; print('ok')"


def exec_code(ci_id: str, sid: str, code: str) -> tuple:
    t = time.time()
    r = ci.invoke_code_interpreter(codeInterpreterIdentifier=ci_id, sessionId=sid, name="executeCode",
                                   arguments={"language": "python", "code": code})
    res = {}
    for ev in r["stream"]:
        res = ev.get("result", res)
    return time.time() - t, float(res.get("structuredContent", {}).get("executionTime") or 0)


def one(ci_id: str, mode: str, idx: int) -> dict:
    t0 = time.time()
    sid = ci.start_code_interpreter_session(codeInterpreterIdentifier=ci_id, name=f"cold-{mode}-{idx}",
                                            sessionTimeoutSeconds=120)["sessionId"]
    t_start = time.time() - t0
    try:
        first_exec, _ = exec_code(ci_id, sid, "print(1)")
        warm_exec, _ = exec_code(ci_id, sid, "print(1)")
        imp_first, imp_first_srv = exec_code(ci_id, sid, IMPORTS)
        imp_again, _ = exec_code(ci_id, sid, IMPORTS)
    finally:
        ci.stop_code_interpreter_session(codeInterpreterIdentifier=ci_id, sessionId=sid)
    rec = {"ci": ci_id, "mode": mode, "idx": idx, "session_id": sid, "utc": datetime.now(timezone.utc).isoformat(),
           "start_api_s": t_start, "first_exec_s": first_exec, "time_to_first_result_s": t_start + first_exec,
           "warm_exec_s": warm_exec, "import_first_s": imp_first, "import_first_server_s": imp_first_srv,
           "import_again_s": imp_again}
    print(json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in rec.items()}), flush=True)
    return rec


def main() -> None:
    ci_id, n, burst = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    recs = [one(ci_id, "sequential", i) for i in range(n)]
    with ThreadPoolExecutor(max_workers=burst) as ex:
        recs += list(ex.map(lambda i: one(ci_id, f"burst{burst}", i), range(burst)))
    with open("cold_start.jsonl", "a") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
