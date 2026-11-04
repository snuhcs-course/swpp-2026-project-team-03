#!/usr/bin/env python3
"""ROCKY laptop agent: starts the pipeline Pods on SGS for the ROCKY server.

Run it on a laptop that is logged in to SGS with kubectl and has the API
reachable (kubectl port-forward pod/rocky-api 8000:8000):

    python3 server/agent/rocky_agent.py
    python3 server/agent/rocky_agent.py --kubeconfig ~/.kube/gpu22.yaml   # another account

It asks the API for Pods to start (GET /agent/next), creates each one with
`kubectl create`, waits while the workspace GPU quota is taken, watches the
Pod, reports progress notes and the final result, and deletes the Pod so
the GPU is released. Only the Python standard library and kubectl are used.
Two laptops may run it at the same time; each request goes to one agent.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

QUOTA_WAIT = "GPU를 다른 작업이 쓰고 있어서 기다리는 중"
NODE_WAIT = "GPU 차례를 기다리는 중"


def say(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Api:
    def __init__(self, base: str, key: str, agent: str) -> None:
        self.base, self.key, self.agent = base.rstrip("/"), key, agent

    def call(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.key:
            req.add_header("X-Rocky-Key", self.key)
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else None)

    def next(self):
        status, body = self.call("GET", f"/agent/next?agent={urllib.parse.quote(self.agent)}")
        return body if status == 200 else None

    def heartbeat(self, rid: str, note: str | None) -> bool:
        try:
            self.call("POST", f"/agent/requests/{rid}/heartbeat", {"agent": self.agent, "note": note})
            return True
        except urllib.error.HTTPError as e:
            if e.code == 409:
                return False
            raise

    def done(self, rid: str, phase: str, log: str) -> None:
        for _ in range(10):  # the port-forward may drop for a moment
            try:
                self.call("POST", f"/agent/requests/{rid}/done", {"agent": self.agent, "phase": phase, "log": log})
                return
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    return
            except OSError:
                pass
            time.sleep(3)


class Kubectl:
    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd

    def run(self, *args: str, stdin: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run([*self.cmd, *args], input=stdin, capture_output=True, text=True, timeout=timeout)

    def pod(self, name: str) -> dict | None:
        r = self.run("get", "pod", name, "-o", "json")
        if r.returncode:
            if "NotFound" in r.stderr or "not found" in r.stderr:
                return None
            raise RuntimeError(r.stderr.strip())
        return json.loads(r.stdout)

    def create(self, pod: dict) -> subprocess.CompletedProcess:
        return self.run("create", "-f", "-", stdin=json.dumps(pod))

    def logs(self, name: str) -> str:
        r = self.run("logs", name, "--tail", "400")
        return r.stdout + (r.stderr if r.returncode else "")

    def delete(self, name: str) -> None:
        self.run("delete", "pod", name, "--ignore-not-found", "--wait=true", "--timeout=90s", timeout=150)


def handle(api: Api, kube: Kubectl, req: dict, beat_sec: float, quota_retry_sec: float) -> None:
    rid, pod = req["rid"], req["pod"]
    name = pod["metadata"]["name"]
    say(f"[{name}] 시작 ({req['kind']}, 곡 {req['job_id']})")
    note = None
    try:
        # create the Pod (or keep watching it if this request was taken over from another agent)
        while kube.pod(name) is None:
            r = kube.create(pod)
            if r.returncode == 0:
                say(f"[{name}] Pod 생성")
                break
            if "exceeded quota" in r.stderr:
                if note != QUOTA_WAIT:
                    say(f"[{name}] GPU 할당량이 차 있어서 기다림 (다른 GPU Pod가 끝나야 함)")
                note = QUOTA_WAIT
                if not api.heartbeat(rid, note):
                    say(f"[{name}] 서버가 요청을 취소함")
                    return
                time.sleep(quota_retry_sec)
                continue
            if "AlreadyExists" in r.stderr:
                continue
            api.done(rid, "Failed", "kubectl create 실패:\n" + r.stderr)
            say(f"[{name}] 생성 실패: {r.stderr.strip()[:300]}")
            return
        # watch it
        while True:
            p = kube.pod(name)
            phase = (p or {}).get("status", {}).get("phase", "Unknown") if p else "Gone"
            if phase in ("Succeeded", "Failed", "Gone"):
                log = kube.logs(name) if p else "(Pod가 사라짐 — SGS가 지웠을 수 있음)"
                api.done(rid, "Succeeded" if phase == "Succeeded" else "Failed", log)
                say(f"[{name}] 끝: {phase}")
                return
            conds = (p or {}).get("status", {}).get("conditions") or []
            waiting = phase == "Pending" and any(c.get("reason") == "Unschedulable" for c in conds)
            new_note = NODE_WAIT if waiting else None
            if new_note != note:
                say(f"[{name}] {phase}" + (f" — {new_note}" if new_note else ""))
            note = new_note
            if not api.heartbeat(rid, note):
                say(f"[{name}] 서버가 요청을 취소함")
                return
            time.sleep(beat_sec)
    except Exception as e:  # report and release; never leave the GPU Pod running
        say(f"[{name}] 오류: {e}")
        api.done(rid, "Failed", f"agent 오류: {e}")
    finally:
        kube.delete(name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000", help="ROCKY API (through kubectl port-forward)")
    ap.add_argument("--key", default="", help="X-Rocky-Key, if the server uses one")
    ap.add_argument("--kubeconfig", default="", help="kubeconfig file (default: ~/.kube/config)")
    ap.add_argument("--kubectl", default="kubectl", help="kubectl command")
    ap.add_argument("--name", default=socket.gethostname(), help="this agent's name")
    ap.add_argument("--poll", type=float, default=3.0)
    ap.add_argument("--beat", type=float, default=5.0)
    ap.add_argument("--quota-retry", type=float, default=20.0)
    ap.add_argument("--once", action="store_true", help="handle at most one request, then exit (tests)")
    args = ap.parse_args(argv)

    cmd = [args.kubectl] + (["--kubeconfig", args.kubeconfig] if args.kubeconfig else [])
    api, kube = Api(args.api, args.key, args.name), Kubectl(cmd)
    say(f"ROCKY agent '{args.name}' 시작 — {args.api} 에서 할 일을 기다려요 (끝내려면 Ctrl+C)")
    warned = False
    while True:
        try:
            req = api.next()
            warned = False
        except OSError as e:
            if not warned:
                say(f"서버에 연결할 수 없어요 ({e}). kubectl port-forward 가 켜져 있는지 확인하세요")
                warned = True
            time.sleep(args.poll)
            continue
        if req is None:
            time.sleep(args.poll)
            continue
        t = threading.Thread(target=handle, args=(api, kube, req, args.beat, args.quota_retry), daemon=True)
        t.start()
        if args.once:
            t.join()
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # A running GPU Pod is left alone: it exits by itself when the song is done
        # (releasing the GPU), and the next agent that starts picks the request up again.
        say("agent 종료. 진행 중이던 Pod는 끝까지 돌고, agent를 다시 켜면 이어서 확인해요")
