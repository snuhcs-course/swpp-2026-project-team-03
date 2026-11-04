"""Run the pipeline Pods through a laptop agent (ROCKY_RUNNER=agent).

The team accounts on SGS may create Pods but may not create Roles or
RoleBindings, so the API pod's ServiceAccount cannot be allowed to create
the GPU Pod itself. Instead the API pod (CPU, has /data) asks for a Pod and
waits; server/agent/rocky_agent.py runs on a laptop that is logged in with
kubectl, takes the request through the same port-forward the phone uses,
creates the Pod with the laptop's own permission, watches it, deletes it
when it ends, and reports the result back.

The Pod spec is the same as KubernetesRunner's (ml/pipeline/sgs/*-pod.example.yaml).
Requests live in memory: after an API restart the worker queues the song
again and unified.py --resume continues from the last finished stage.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .runners import KubernetesRunner, RunnerError

WAIT_FOR_AGENT = "노트북 연결(agent)을 기다리는 중"


@dataclass
class PodRequest:
    rid: str
    job_id: str
    kind: str                      # "midi" or "pdf"
    pod: dict
    created: float = field(default_factory=time.time)
    agent: str | None = None       # who took it
    last_seen: float = 0.0         # last heartbeat from that agent
    note: str | None = None
    phase: str | None = None       # Succeeded / Failed once done
    log: str = ""
    done: threading.Event = field(default_factory=threading.Event)


def spec_builder() -> KubernetesRunner:
    """A KubernetesRunner used only to build Pod specs (no cluster access)."""
    from kubernetes import client
    b = KubernetesRunner.__new__(KubernetesRunner)
    b.client = client
    b.claim = os.environ.get("ROCKY_PVC", "muscriptor-data")
    b.node = os.environ.get("ROCKY_NODE", "ferrari")
    b.pipeline_image = os.environ.get("ROCKY_PIPELINE_IMAGE", "ghcr.io/astral-sh/uv:python3.13-bookworm-slim")
    b.pdf_image = os.environ.get("ROCKY_PDF_IMAGE", "mcr.microsoft.com/playwright:v1.62.1-noble")
    return b


class AgentRunner:
    POLL_SEC = 2.0
    STALE_SEC = 90.0  # an agent that stops sending heartbeats loses the request

    def __init__(self, builder: KubernetesRunner | None = None, timeout_sec: float | None = None) -> None:
        self.builder = builder or spec_builder()
        self.timeout_sec = timeout_sec or float(os.environ.get("ROCKY_JOB_TIMEOUT_SEC", "5400"))
        self.lock = threading.Lock()
        self.requests: dict[str, PodRequest] = {}

    # ---- called by the worker ----
    def _pod_dict(self, pod, suffix: str) -> dict:
        from kubernetes import client
        body = client.ApiClient().sanitize_for_serialization(pod)
        # a new name for every attempt, so an old finished Pod is never mistaken for this one
        body["metadata"]["name"] = f'{body["metadata"]["name"]}-{suffix}'
        return body

    def _run(self, job_id: str, kind: str, pod, log: Path, note) -> None:
        suffix = f"{int(time.time()) % 1000000:06d}"
        req = PodRequest(rid=f"{kind}-{job_id}-{suffix}", job_id=job_id, kind=kind,
                         pod=self._pod_dict(pod, suffix))
        with self.lock:
            self.requests[req.rid] = req
        deadline = time.monotonic() + self.timeout_sec
        try:
            while not req.done.wait(self.POLL_SEC):
                with self.lock:
                    if req.agent and time.time() - req.last_seen > self.STALE_SEC:
                        req.agent = None          # agent went away: let another one take it
                    msg = req.note if req.agent else WAIT_FOR_AGENT
                note(msg)
                if time.monotonic() > deadline:
                    raise RunnerError(f"{kind} pod did not finish within {int(self.timeout_sec)} s")
        finally:
            with self.lock:
                self.requests.pop(req.rid, None)
        note(None)
        with log.open("a", encoding="utf-8") as out:
            out.write(f"===== {req.pod['metadata']['name']} ({req.phase}, agent {req.agent}) =====\n{req.log}\n")
        if req.phase != "Succeeded":
            raise RunnerError(f"{kind} pod {req.phase or 'failed'}; see {log.name}")

    def run_midi(self, job_id: str, audio: Path, run: Path, requested: str, log: Path,
                 note=lambda _msg: None, original: str = "unknown") -> None:
        self._run(job_id, "midi", self.builder.midi_pod(job_id, audio, run, requested, original), log, note)

    def run_pdf(self, job_id: str, run: Path, log: Path, note=lambda _msg: None) -> None:
        self._run(job_id, "pdf", self.builder.pdf_pod(job_id, run), log, note)

    # ---- called through the API by the agent ----
    def next_request(self, agent: str) -> dict | None:
        """Give the oldest request nobody (alive) is handling to this agent."""
        now = time.time()
        with self.lock:
            free = [r for r in self.requests.values()
                    if not r.done.is_set() and (r.agent is None or now - r.last_seen > self.STALE_SEC)]
            if not free:
                return None
            req = min(free, key=lambda r: r.created)
            req.agent, req.last_seen, req.note = agent, now, None
            return {"rid": req.rid, "kind": req.kind, "job_id": req.job_id, "pod": req.pod}

    def heartbeat(self, rid: str, agent: str, note: str | None) -> bool:
        """False when the request is gone or belongs to another agent: the agent should stop."""
        with self.lock:
            req = self.requests.get(rid)
            if req is None or req.agent != agent or req.done.is_set():
                return False
            req.last_seen, req.note = time.time(), note
            return True

    def finish(self, rid: str, agent: str, phase: str, log: str) -> bool:
        with self.lock:
            req = self.requests.get(rid)
            if req is None or req.agent != agent or req.done.is_set():
                return False
            req.phase, req.log = phase, log[-20000:]
            req.done.set()
            return True
