#!/usr/bin/env python3
"""A tiny stand-in for kubectl, for testing rocky_agent.py without a cluster.

State lives in $FAKE_KUBE_DIR. `create -f -` stores the Pod and starts
ci_fake_pipeline.py with the Pod's env (midi or pdf stage); the Pod is
Running until that process exits. $FAKE_KUBE_QUOTA_REFUSALS refuses that
many creates with the SGS quota error first.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
state = Path(os.environ["FAKE_KUBE_DIR"])
state.mkdir(parents=True, exist_ok=True)
args = sys.argv[1:]
if args[:1] == ["--kubeconfig"]:
    args = args[2:]


def pod_file(name):
    return state / f"{name}.json"


if args[:3] == ["create", "-f", "-"]:
    refusals = state / "quota_refusals"
    left = int(refusals.read_text()) if refusals.exists() else int(os.environ.get("FAKE_KUBE_QUOTA_REFUSALS", "0"))
    if left > 0:
        refusals.write_text(str(left - 1))
        sys.stderr.write('Error from server (Forbidden): pods "x" is forbidden: exceeded quota: gpu, '
                         'requested: requests.nvidia.com/gpu=1, used: requests.nvidia.com/gpu=1, limited: requests.nvidia.com/gpu=1\n')
        sys.exit(1)
    refusals.write_text("0")
    pod = json.load(sys.stdin)
    name = pod["metadata"]["name"]
    env = {e["name"]: e["value"] for e in pod["spec"]["containers"][0].get("env", [])}
    if "ROCKY_INPUT_AUDIO" in env:
        cmd = [sys.executable, str(HERE / "ci_fake_pipeline.py"), "midi", env["ROCKY_INPUT_AUDIO"], env["ROCKY_OUTPUT_DIR"]]
    else:
        cmd = [sys.executable, str(HERE / "ci_fake_pipeline.py"), "pdf", env["ROCKY_OUTPUT_DIR"]]
    log = open(state / f"{name}.log", "w")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    pod["_pid"] = proc.pid
    pod_file(name).write_text(json.dumps(pod))
    print(f"pod/{name} created")
elif args[:2] == ["get", "pod"]:
    f = pod_file(args[2])
    if not f.exists():
        sys.stderr.write(f'Error from server (NotFound): pods "{args[2]}" not found\n')
        sys.exit(1)
    pod = json.loads(f.read_text())
    try:
        pid, status = os.waitpid(pod["_pid"], os.WNOHANG)
        if pid:
            pod["_exit"] = os.waitstatus_to_exitcode(status)
            f.write_text(json.dumps(pod))
    except ChildProcessError:
        pass
    if "_exit" in pod:
        phase = "Succeeded" if pod["_exit"] == 0 else "Failed"
    else:
        try:
            os.kill(pod["_pid"], 0)
            phase = "Running"
        except ProcessLookupError:
            phase = "Succeeded"
    pod["status"] = {"phase": phase, "conditions": []}
    print(json.dumps(pod))
elif args[:1] == ["logs"]:
    f = state / f"{args[1]}.log"
    print(f.read_text() if f.exists() else "")
elif args[:2] == ["delete", "pod"]:
    pod_file(args[2]).unlink(missing_ok=True)
    print(f'pod "{args[2]}" deleted')
else:
    sys.stderr.write(f"fake kubectl: unsupported {args}\n")
    sys.exit(2)
