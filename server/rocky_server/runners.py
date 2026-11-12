"""Ways to run the ROCKY pipeline for one job.

KubernetesRunner (used on SGS): the API pod has no GPU. For each song it
creates the same two Pods as ml/pipeline/sgs/*-pod.example.yaml: a GPU Pod
that runs unified.py, then a CPU Pod that runs publish_scores.py. The GPU is
held only while the GPU Pod runs, so the 30-minute idle rule never applies to
the API pod.

SubprocessRunner: runs the same two commands directly. For a machine that
has the pipeline installed locally (or for trying the server by hand).
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path


class RunnerError(RuntimeError):
    pass


class TransientPodFailure(RunnerError):
    """A Pod that failed for a reason worth one more try (it printed TRANSIENT_MARKER)."""


# Printed (and exit 75) by a Pod script when it fails for a passing reason, e.g. the Ubuntu
# mirror resetting the connection while installing the PDF tools. Only these failures are retried.
TRANSIENT_MARKER = "ROCKY_TRANSIENT_FAILURE"


def pod_failure(what: str, phase: str | None, pod_log: str, log_name: str) -> RunnerError:
    """The error for a finished Pod that did not succeed."""
    cls = TransientPodFailure if TRANSIENT_MARKER in (pod_log or "") else RunnerError
    return cls(f"{what} {phase or 'failed'}; see {log_name}")


def to_wav(source: Path) -> Path:
    """Decode mp3/m4a/flac to 44.1 kHz stereo WAV when ffmpeg is available.

    unified.py reads the song length with soundfile, which cannot open every
    compressed format. WAV input avoids that. Without ffmpeg the file is
    passed through unchanged.
    """
    if source.suffix.lower() == ".wav" or shutil.which("ffmpeg") is None:
        return source
    target = source.with_suffix(".wav")
    result = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(source),
                             "-ar", "44100", "-ac", "2", str(target)], capture_output=True, text=True)
    if result.returncode or not target.is_file():
        raise RunnerError(f"Could not decode the audio file: {result.stderr.strip()[-300:]}")
    return target


class SubprocessRunner:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.processes: dict[str, subprocess.Popen] = {}
        self.cancelled: set[str] = set()
        self.midi_cmd = os.environ.get(
            "ROCKY_MIDI_CMD",
            "/data/rocky-unified/.venv/bin/python /data/pipeline/unified.py {audio} {run} "
            "--original {original} --requested {requested} "
            "--bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib "
            "--resume --no-publish")
        self.pdf_cmd = os.environ.get(
            "ROCKY_PDF_CMD",
            "/data/rocky-unified/.venv/bin/python /data/pipeline/publish_scores.py {run}")
        self.transpose_cmd = os.environ.get(
            "ROCKY_TRANSPOSE_CMD",
            "/data/rocky-unified/.venv/bin/python /data/server/rocky_server/transpose_scores.py "
            "{audio} {run} {requested} && "
            "/data/rocky-unified/.venv/bin/python /data/pipeline/publish_scores.py {run}")

    def cancel(self, job_id: str) -> None:
        with self.lock:
            self.cancelled.add(job_id)
            process = self.processes.get(job_id)
            if process is not None and process.poll() is None:
                if os.name == "nt":
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)

    def forget(self, job_id: str) -> None:
        with self.lock:
            self.cancelled.discard(job_id)

    def _run(self, job_id: str, template: str, audio: Path, run: Path, requested: str, log: Path,
             original: str = "unknown") -> None:
        cmd = template.format(audio=shlex.quote(str(audio)), run=shlex.quote(str(run)),
                              requested=shlex.quote(requested), original=shlex.quote(original))
        with log.open("a", encoding="utf-8") as out:
            with self.lock:
                if job_id in self.cancelled:
                    raise RunnerError(f"job {job_id} was cancelled")
                process = subprocess.Popen(cmd, shell=True, stdout=out, stderr=subprocess.STDOUT,
                                           start_new_session=os.name != "nt")
                self.processes[job_id] = process
            try:
                code = process.wait()
            finally:
                with self.lock:
                    self.processes.pop(job_id, None)
        if code:
            raise RunnerError(f"command exited {code}; see {log.name}")

    def run_midi(self, job_id: str, audio: Path, run: Path, requested: str, log: Path,
                 note=lambda _msg: None, original: str = "unknown") -> None:
        self._run(job_id, self.midi_cmd, audio, run, requested, log, original)

    def run_pdf(self, job_id: str, run: Path, log: Path, note=lambda _msg: None) -> None:
        self._run(job_id, self.pdf_cmd, run, run, "", log)

    def run_transpose(self, job_id: str, source: Path, target: Path, semitones: int,
                      log: Path, note=lambda _msg: None) -> None:
        self._run(job_id, self.transpose_cmd, source, target, str(semitones), log)


# MuseScore 3 and Poppler for the PDF / key-change Pods. The Playwright image does not have them,
# and downloading them from the Ubuntu mirror on every Pod start failed on 2026-11-12
# ("Connection reset by peer") after the GPU stage had already finished. So the .deb files are
# kept on the volume once (server/k8s/pdf-debs-pod.yaml) and installed from there; the mirror is
# only the fallback when that folder is missing or does not install.
PDF_TOOLS = "musescore3 poppler-utils"


def pdf_tools_install() -> list[str]:
    debs = os.environ.get("ROCKY_PDF_DEBS", "/data/cache/pdf-debs")
    have_tools = "command -v musescore3 > /dev/null && command -v pdftoppm > /dev/null"
    return [
        # the cache counts only if it installs AND both programs are there afterwards
        f'if compgen -G "{debs}/*.deb" > /dev/null && dpkg -i {debs}/*.deb > /tmp/pdf-tools-dpkg.log 2>&1 && {have_tools}; then',
        f'  echo "PDF tools: installed from {debs}"',
        "else",
        f'  echo "PDF tools: {debs} missing or incomplete, downloading from the mirror"',
        "  if ! { apt-get -o Acquire::Retries=5 update -qq &&",
        f"         apt-get -o Acquire::Retries=5 install -y -qq -f --no-install-recommends {PDF_TOOLS}; }}; then",
        f'    echo "{TRANSIENT_MARKER}: could not install the PDF tools from the mirror"',
        "    exit 75",
        "  fi",
        "fi",
        f'{have_tools} || {{ echo "PDF tools: musescore3 or pdftoppm still missing"; exit 1; }}',
    ]


class KubernetesRunner:
    """Create one GPU Pod and then one CPU Pod per song in the workspace namespace.

    SGS asks for Pods rather than Jobs (TA guidance, 2026-11), so each stage is
    a bare Pod with restartPolicy Never, like ml/pipeline/sgs/*-pod.example.yaml.
    The volume is a hostpath on one node, so every Pod is pinned to it.
    The workspace quota allows one GPU, counting Pending pods: when it is taken
    (a teammate's pod, or the previous song), creating the GPU Pod is refused and
    this runner waits and tries again instead of failing the song.
    """

    POLL_SEC = 5
    QUOTA_RETRY_SEC = 30

    def __init__(self) -> None:
        from kubernetes import client, config  # imported here so tests need no cluster
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self.core = client.CoreV1Api()
        self.client = client
        self.namespace = os.environ.get("ROCKY_NAMESPACE") or Path(
            "/var/run/secrets/kubernetes.io/serviceaccount/namespace").read_text().strip()
        self.claim = os.environ.get("ROCKY_PVC", "muscriptor-data")
        self.node = os.environ.get("ROCKY_NODE", "ferrari")
        self.pipeline_image = os.environ.get("ROCKY_PIPELINE_IMAGE", "ghcr.io/astral-sh/uv:python3.13-bookworm-slim")
        self.pdf_image = os.environ.get("ROCKY_PDF_IMAGE", "mcr.microsoft.com/playwright:v1.62.1-noble")
        self.timeout_sec = int(os.environ.get("ROCKY_JOB_TIMEOUT_SEC", "5400"))
        self.cancelled: set[str] = set()
        self.cancel_lock = threading.Lock()

    def _was_cancelled(self, job_id: str) -> bool:
        with self.cancel_lock:
            return job_id in self.cancelled

    def cancel(self, job_id: str) -> None:
        with self.cancel_lock:
            self.cancelled.add(job_id)
        for stage in ("midi", "pdf"):
            self._delete(f"rocky-{stage}-{job_id}")

    def forget(self, job_id: str) -> None:
        with self.cancel_lock:
            self.cancelled.discard(job_id)

    # ---- Pod specs (same as ml/pipeline/sgs/*-pod.example.yaml) ----
    def _pod(self, name: str, image: str, script: str, env: dict[str, str], limits: dict[str, str],
             working_dir: str | None = None):
        c = self.client
        container = c.V1Container(
            name="main", image=image, command=["/bin/bash", "-lc"], args=[script],
            working_dir=working_dir,
            env=[c.V1EnvVar(name=k, value=v) for k, v in env.items()],
            # the workspace has no guaranteed CPU or memory, so requests must be 0
            resources=c.V1ResourceRequirements(requests={"cpu": "0", "memory": "0"}, limits=limits),
            volume_mounts=[c.V1VolumeMount(name="data", mount_path="/data")])
        spec = c.V1PodSpec(
            restart_policy="Never", termination_grace_period_seconds=1,
            node_selector={"kubernetes.io/hostname": self.node} if self.node else None,
            containers=[container],
            volumes=[c.V1Volume(name="data", persistent_volume_claim=c.V1PersistentVolumeClaimVolumeSource(
                claim_name=self.claim))],
            dns_config=c.V1PodDNSConfig(options=[c.V1PodDNSConfigOption(name="ndots", value="1")]))
        return c.V1Pod(api_version="v1", kind="Pod",
                       metadata=c.V1ObjectMeta(name=name, labels={"app": "rocky", "rocky-stage": name.split("-")[1]}),
                       spec=spec)

    def midi_pod(self, job_id: str, audio: Path, run: Path, requested: str, original: str = "unknown"):
        script = (
            "set -euo pipefail; "
            "export HF_HOME=/data/cache/hf TORCH_HOME=/data/cache/torch "
            "UV_CACHE_DIR=/data/cache/uv UV_TOOL_DIR=/data/cache/uv-tools "
            "UV_PYTHON_INSTALL_DIR=/data/cache/python XDG_CACHE_HOME=/data/cache/xdg; "
            'exec /data/rocky-unified/.venv/bin/python /data/pipeline/unified.py '
            '"$ROCKY_INPUT_AUDIO" "$ROCKY_OUTPUT_DIR" '
            '--original "$ROCKY_ORIGINAL" --requested "$ROCKY_REQUESTED" '
            '--bsroformer-models-dir /data/bsrofo/models --bsroformer-lib-dir /data/bsrofo/pylib '
            '--resume --no-publish')
        env = {"ROCKY_INPUT_AUDIO": str(audio), "ROCKY_OUTPUT_DIR": str(run),
               "ROCKY_ORIGINAL": original, "ROCKY_REQUESTED": requested,
               "NVIDIA_DRIVER_CAPABILITIES": "compute,utility"}
        return self._pod(f"rocky-midi-{job_id}", self.pipeline_image, script, env,
                         {"cpu": "8", "memory": "32Gi", "nvidia.com/gpu": "1"})

    def pdf_pod(self, job_id: str, run: Path):
        script = "\n".join([
            "set -euo pipefail",
            "export DEBIAN_FRONTEND=noninteractive QT_QPA_PLATFORM=offscreen",
            "export XDG_RUNTIME_DIR=/tmp/rocky-qt-runtime",
            'mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"',
            *pdf_tools_install(),
            '/data/rocky-unified/.venv/bin/python /data/pipeline/publish_scores.py "$ROCKY_OUTPUT_DIR" '
            "--musescore musescore3 --gp5-converter /data/rocky-unified/ml/gp5_to_pdf/convert.js",
        ])
        return self._pod(f"rocky-pdf-{job_id}", self.pdf_image, script, {"ROCKY_OUTPUT_DIR": str(run)},
                         {"cpu": "4", "memory": "8Gi"}, working_dir="/data/rocky-unified/ml/gp5_to_pdf")

    def transpose_pod(self, job_id: str, source: Path, target: Path, semitones: int):
        script = "\n".join([
            "set -euo pipefail",
            "export DEBIAN_FRONTEND=noninteractive QT_QPA_PLATFORM=offscreen",
            "export XDG_RUNTIME_DIR=/tmp/rocky-qt-runtime",
            'mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"',
            *pdf_tools_install(),
            '/data/rocky-unified/.venv/bin/python /data/server/rocky_server/transpose_scores.py '
            '"$ROCKY_SOURCE_DIR" "$ROCKY_OUTPUT_DIR" "$ROCKY_SEMITONES"',
            '/data/rocky-unified/.venv/bin/python /data/pipeline/publish_scores.py "$ROCKY_OUTPUT_DIR" '
            "--musescore musescore3 --gp5-converter /data/rocky-unified/ml/gp5_to_pdf/convert.js",
        ])
        env = {"ROCKY_SOURCE_DIR": str(source), "ROCKY_OUTPUT_DIR": str(target),
               "ROCKY_SEMITONES": str(semitones)}
        return self._pod(f"rocky-transpose-{job_id}", self.pdf_image, script, env,
                         {"cpu": "4", "memory": "8Gi"}, working_dir="/data/rocky-unified/ml/gp5_to_pdf")

    # ---- running ----
    def _create(self, pod, note) -> None:
        """Create the Pod; while the GPU quota is taken, wait and retry."""
        name = pod.metadata.name
        ApiException = self.client.exceptions.ApiException
        deadline = time.monotonic() + self.timeout_sec
        self._delete(name)  # a finished Pod left by an earlier try has the same name
        while True:
            if self._was_cancelled(name.rsplit("-", 1)[-1]):
                raise RunnerError(f"job {name} was cancelled before Pod creation")
            try:
                self.core.create_namespaced_pod(self.namespace, pod)
                return
            except ApiException as exc:
                body = str(exc.body or "")
                if exc.status == 403 and "exceeded quota" in body and time.monotonic() < deadline:
                    note("GPU를 다른 작업이 쓰고 있어서 기다리는 중")
                    time.sleep(self.QUOTA_RETRY_SEC)
                    continue
                raise RunnerError(f"could not create pod {name}: {exc.status} {exc.reason} {body[:300]}") from exc

    def _run_pod(self, pod, log: Path, note) -> None:
        name = pod.metadata.name
        self._create(pod, note)
        note(None)
        deadline = time.monotonic() + self.timeout_sec
        try:
            while time.monotonic() < deadline:
                if self._was_cancelled(name.rsplit("-", 1)[-1]):
                    raise RunnerError(f"job {name} was cancelled")
                status = self.core.read_namespaced_pod_status(name, self.namespace).status
                if status.phase == "Succeeded":
                    self._save_log(name, log)
                    note(None)
                    return
                if status.phase == "Failed":
                    raise pod_failure(f"pod {name}", "failed", self._save_log(name, log), log.name)
                if status.phase == "Pending":
                    waiting = any(c.reason == "Unschedulable" for c in (status.conditions or []))
                    note("GPU 차례를 기다리는 중" if waiting else None)
                time.sleep(self.POLL_SEC)
            raise RunnerError(f"pod {name} did not finish within {self.timeout_sec} s")
        finally:
            self._delete(name)  # frees the GPU quota even after a failure or timeout

    def _delete(self, name: str) -> None:
        try:
            self.core.delete_namespaced_pod(name, self.namespace, grace_period_seconds=0)
        except self.client.exceptions.ApiException as exc:
            if exc.status != 404:
                raise
        # wait until it is gone so the same name can be reused
        for _ in range(60):
            try:
                self.core.read_namespaced_pod_status(name, self.namespace)
            except self.client.exceptions.ApiException as exc:
                if exc.status == 404:
                    return
            time.sleep(1)

    def _save_log(self, name: str, log: Path) -> str:
        try:
            text = self.core.read_namespaced_pod_log(name, self.namespace, tail_lines=400)
            with log.open("a", encoding="utf-8") as out:
                out.write(f"===== {name} =====\n{text}\n")
            return text or ""
        except Exception as exc:  # the log is only for people; never fail the song over it
            with log.open("a", encoding="utf-8") as out:
                out.write(f"(could not read log of {name}: {exc})\n")
            return ""

    def run_midi(self, job_id: str, audio: Path, run: Path, requested: str, log: Path,
                 note=lambda _msg: None, original: str = "unknown") -> None:
        self._run_pod(self.midi_pod(job_id, audio, run, requested, original), log, note)

    def run_pdf(self, job_id: str, run: Path, log: Path, note=lambda _msg: None) -> None:
        self._run_pod(self.pdf_pod(job_id, run), log, note)

    def run_transpose(self, job_id: str, source: Path, target: Path, semitones: int,
                      log: Path, note=lambda _msg: None) -> None:
        self._run_pod(self.transpose_pod(job_id, source, target, semitones), log, note)


def make_runner(kind: str):
    if kind == "agent":
        from .agent_runner import AgentRunner
        return AgentRunner()
    if kind == "kubernetes":
        return KubernetesRunner()
    if kind == "subprocess":
        return SubprocessRunner()
    raise ValueError(f"unknown ROCKY_RUNNER {kind!r} (agent, kubernetes or subprocess)")
