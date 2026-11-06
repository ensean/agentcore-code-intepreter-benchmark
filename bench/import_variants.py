"""Compare import strategies in a fresh Code Interpreter kernel, and test background pre-warm.

Usage: python import_variants.py <ci_id> <n_sessions_per_variant>
"""
from __future__ import annotations

import json
import statistics as st
import sys
import threading
import time

import boto3
from botocore.config import Config

ci = boto3.client("bedrock-agentcore", config=Config(region_name="ap-northeast-1", max_pool_connections=20))

FULL = "import numpy, pandas, matplotlib.pyplot as plt"
VARIANTS = {
    "baseline_pyplot": FULL,
    "agg_then_pyplot": "import matplotlib; matplotlib.use('Agg'); import numpy, pandas, matplotlib.pyplot as plt",
    "oo_figure_no_pyplot": "import numpy, pandas; from matplotlib.figure import Figure; from matplotlib.backends.backend_agg import FigureCanvasAgg",
}
DIAG = ("import sys,json;print(json.dumps({'trace':repr(sys.gettrace()),'profile':repr(sys.getprofile()),"
        "'meta_path':[type(m).__name__ for m in sys.meta_path],'audit_hooks':hasattr(sys,'audit'),"
        "'mpl_backend_env':__import__('os').environ.get('MPLBACKEND')}))")


def exec_code(ci_id: str, sid: str, code: str) -> tuple:
    t = time.time()
    r = ci.invoke_code_interpreter(codeInterpreterIdentifier=ci_id, sessionId=sid, name="executeCode",
                                   arguments={"language": "python", "code": code})
    res = {}
    for ev in r["stream"]:
        res = ev.get("result", res)
    sc = res.get("structuredContent", {})
    return time.time() - t, float(sc.get("executionTime") or 0), sc.get("stdout", "")


def session(ci_id: str, name: str) -> str:
    return ci.start_code_interpreter_session(codeInterpreterIdentifier=ci_id, name=name, sessionTimeoutSeconds=120)["sessionId"]


def stop(ci_id: str, sid: str) -> None:
    ci.stop_code_interpreter_session(codeInterpreterIdentifier=ci_id, sessionId=sid)


def main() -> None:
    ci_id, n = sys.argv[1], int(sys.argv[2])
    out: dict = {}
    sid = session(ci_id, "diag")
    print("diag", exec_code(ci_id, sid, DIAG)[2].strip())
    stop(ci_id, sid)

    for name, code in VARIANTS.items():
        xs = []
        for i in range(n):
            sid = session(ci_id, f"{name}-{i}")
            try:
                xs.append(exec_code(ci_id, sid, code)[1])
            finally:
                stop(ci_id, sid)
        out[name] = xs
        print(name, "server executionTime p50=%.3f mean=%.3f" % (st.median(xs), st.mean(xs)), flush=True)

    # Pre-warm: fire FULL import in background right after Start, simulate a 5 s LLM turn,
    # then measure the agent's first real executeCode (which imports the same libs).
    xs = []
    for i in range(n):
        sid = session(ci_id, f"prewarm-{i}")
        try:
            th = threading.Thread(target=exec_code, args=(ci_id, sid, FULL))
            th.start()
            time.sleep(5)  # stands in for the first LLM turn (real turns were 16-75 s)
            th.join()
            wall, srv, _ = exec_code(ci_id, sid, FULL + "\nprint(pandas.__version__)")
            xs.append(srv)
        finally:
            stop(ci_id, sid)
    out["prewarm_then_first_exec"] = xs
    print("prewarm_then_first_exec server executionTime p50=%.3f mean=%.3f" % (st.median(xs), st.mean(xs)), flush=True)
    json.dump(out, open("import_variants.json", "w"), indent=2)


if __name__ == "__main__":
    main()
