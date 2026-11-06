"""Probe Code Interpreter response shapes (one short session)."""
from __future__ import annotations

import json
import sys

import boto3

REGION = "ap-northeast-1"
CI_ID = sys.argv[1]
c = boto3.client("bedrock-agentcore", region_name=REGION)

s = c.start_code_interpreter_session(codeInterpreterIdentifier=CI_ID, name="probe", sessionTimeoutSeconds=300)
sid = s["sessionId"]
print("session", sid)


def call(name, args):
    r = c.invoke_code_interpreter(codeInterpreterIdentifier=CI_ID, sessionId=sid, name=name, arguments=args)
    out = [ev for ev in r["stream"]]
    print(name, json.dumps(out, default=str)[:1500])


try:
    call("executeCode", {"language": "python", "code": "import sys, pandas, os; print(sys.version, pandas.__version__, os.getcwd(), os.cpu_count())"})
    call("writeFiles", {"content": [{"path": "a.csv", "text": "x,y\n1,2\n"}]})
    call("listFiles", {"path": ""})
    call("readFiles", {"paths": ["a.csv"]})
    call("executeCode", {"language": "python", "code": "import subprocess;print(subprocess.run(['sh','-c','cat /proc/meminfo | head -3; nproc'],capture_output=True,text=True).stdout)"})
finally:
    c.stop_code_interpreter_session(codeInterpreterIdentifier=CI_ID, sessionId=sid)
    print("stopped")
