"""Break down first-import cost inside a fresh Code Interpreter session.

Usage: python import_probe.py <ci_id> <n_sessions>
"""
from __future__ import annotations

import json
import sys
import time

import boto3

ci = boto3.client("bedrock-agentcore", region_name="ap-northeast-1")

STEPS = [
    ("numpy", "import numpy"),
    ("pandas", "import pandas"),
    ("matplotlib", "import matplotlib"),
    ("pyplot", "import matplotlib.pyplot as plt"),
    ("first_plot", "fig=plt.figure(); plt.plot([1,2,3]); import io; fig.savefig(io.BytesIO(), format='png'); plt.close(fig)"),
]
ENV = r'''
import os, sys, glob, matplotlib as _m
cache = _m.get_cachedir()
print(json.dumps({
  "py": sys.version.split()[0], "kernel": "ipykernel" in sys.modules,
  "mpl_cachedir": cache, "fontlist_cached": bool(glob.glob(os.path.join(cache, "fontlist*.json"))),
  "site_writable": os.access(os.path.dirname(os.__file__) + "/site-packages", os.W_OK),
  "pandas_pyc": bool(glob.glob(os.path.dirname(__import__("pandas").__file__) + "/__pycache__/*.pyc")),
}))
'''


def run(ci_id: str, sid: str, code: str) -> tuple:
    t = time.time()
    r = ci.invoke_code_interpreter(codeInterpreterIdentifier=ci_id, sessionId=sid, name="executeCode",
                                   arguments={"language": "python", "code": code})
    res = {}
    for ev in r["stream"]:
        res = ev.get("result", res)
    sc = res.get("structuredContent", {})
    return round(time.time() - t, 3), round(float(sc.get("executionTime") or 0), 3), sc.get("stdout", ""), sc.get("stderr", "")


def main() -> None:
    ci_id, n = sys.argv[1], int(sys.argv[2])
    for i in range(n):
        sid = ci.start_code_interpreter_session(codeInterpreterIdentifier=ci_id, name=f"imp-{i}", sessionTimeoutSeconds=120)["sessionId"]
        try:
            row = {}
            for name, code in STEPS:
                row[name] = run(ci_id, sid, code)[1]
            row["env"] = run(ci_id, sid, "import json\n" + ENV)[2].strip()
            # cold import of a fresh interpreter process (not the kernel), with -X importtime top entries
            cmd = ("import subprocess,time;t=time.time();p=subprocess.run(['python3','-X','importtime','-c',"
                   "'import numpy,pandas,matplotlib.pyplot'],capture_output=True,text=True);"
                   "print(round(time.time()-t,3));"
                   "rows=[l.split('|') for l in p.stderr.splitlines() if l.startswith('import time:') and 'self' not in l];"
                   "rows=sorted(rows,key=lambda r:-int(r[1].strip()))[:8];"
                   "print('\\n'.join(r[2].strip()+' '+str(int(r[1].strip())//1000)+'ms' for r in rows))")
            row["subprocess_cold"] = run(ci_id, sid, cmd)[2].strip()
            row["subprocess_again"] = run(ci_id, sid, cmd)[2].strip().splitlines()[0]
            print(json.dumps(row), flush=True)
        finally:
            ci.stop_code_interpreter_session(codeInterpreterIdentifier=ci_id, sessionId=sid)


if __name__ == "__main__":
    main()
