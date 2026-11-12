import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from kubernetes import client

from rocky_server.runners import KubernetesRunner, RunnerError


def runner():
    r = KubernetesRunner.__new__(KubernetesRunner)  # no cluster needed to build specs
    import threading
    r.cancel_lock, r.cancelled = threading.Lock(), set()
    r.client, r.claim, r.node, r.namespace = client, "muscriptor-data", "ferrari", "ws-test"
    r.pipeline_image, r.pdf_image, r.timeout_sec = "uv-image", "pw-image", 60
    return r


def test_midi_pod_matches_example_yaml():
    pod = runner().midi_pod("abc123abc123", Path("/data/input/app/x.wav"), Path("/data/rocky-unified/runs/x"),
                            "keyboard,drums", "unknown")
    spec = pod.spec
    c = spec.containers[0]
    env = {e.name: e.value for e in c.env}
    assert pod.kind == "Pod" and pod.metadata.name == "rocky-midi-abc123abc123"
    assert spec.restart_policy == "Never"
    assert spec.node_selector == {"kubernetes.io/hostname": "ferrari"}
    assert c.resources.limits["nvidia.com/gpu"] == "1"
    assert c.resources.requests == {"cpu": "0", "memory": "0"}
    assert env["ROCKY_REQUESTED"] == "keyboard,drums" and env["ROCKY_ORIGINAL"] == "unknown"
    for part in ("/data/pipeline/unified.py", "--original", "--resume", "--no-publish", "--bsroformer-models-dir"):
        assert part in c.args[0]
    assert spec.volumes[0].persistent_volume_claim.claim_name == "muscriptor-data"


def test_pdf_pod_has_no_gpu():
    pod = runner().pdf_pod("abc123abc123", Path("/data/rocky-unified/runs/x"))
    c = pod.spec.containers[0]
    assert "nvidia.com/gpu" not in c.resources.limits
    assert "publish_scores.py" in c.args[0]
    assert pod.spec.node_selector == {"kubernetes.io/hostname": "ferrari"}


def test_transpose_pod_is_cpu_only_and_uses_original_run():
    pod = runner().transpose_pod("abc123abc123-01p", Path("/data/runs/source"),
                                 Path("/data/runs/source/transpositions/+1"), 1)
    c = pod.spec.containers[0]
    env = {item.name: item.value for item in c.env}
    assert pod.kind == "Pod" and "nvidia.com/gpu" not in c.resources.limits
    assert env["ROCKY_SEMITONES"] == "1"
    assert env["ROCKY_SOURCE_DIR"].replace("\\", "/") == "/data/runs/source"
    assert "transpose_scores.py" in c.args[0] and "publish_scores.py" in c.args[0]


class FakeCore:
    """Refuses the first create with the quota error, then runs the pod to Succeeded."""

    def __init__(self, quota_refusals=1, final="Succeeded"):
        self.quota_refusals, self.final = quota_refusals, final
        self.pods, self.deleted = {}, []

    def create_namespaced_pod(self, ns, pod):
        if self.quota_refusals:
            self.quota_refusals -= 1
            raise _quota()
        self.pods[pod.metadata.name] = 0

    def read_namespaced_pod_status(self, name, ns):
        if name not in self.pods:
            raise client.exceptions.ApiException(status=404)
        self.pods[name] += 1
        phase = "Pending" if self.pods[name] == 1 else ("Running" if self.pods[name] == 2 else self.final)
        cond = [SimpleNamespace(reason="Unschedulable")] if phase == "Pending" else []
        return SimpleNamespace(status=SimpleNamespace(phase=phase, conditions=cond))

    def read_namespaced_pod_log(self, name, ns, tail_lines):
        return "log text"

    def delete_namespaced_pod(self, name, ns, grace_period_seconds):
        if name not in self.pods:
            raise client.exceptions.ApiException(status=404)
        self.deleted.append(name)
        del self.pods[name]


def _quota():
    e = client.exceptions.ApiException(status=403, reason="Forbidden")
    e.body = 'pods "rocky-midi-x" is forbidden: exceeded quota: gpu, requested: requests.nvidia.com/gpu=1'
    return e


def test_waits_for_gpu_quota_then_runs_and_deletes(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    r = runner()
    r.core = FakeCore(quota_refusals=2)
    notes = []
    r.run_midi("abc123abc123", Path("/a.wav"), tmp_path, "keyboard", tmp_path / "log", note=notes.append)
    assert "GPU를 다른 작업이 쓰고 있어서 기다리는 중" in notes
    assert "GPU 차례를 기다리는 중" in notes
    assert notes[-1] is None
    assert r.core.deleted == ["rocky-midi-abc123abc123"]  # GPU released
    assert "log text" in (tmp_path / "log").read_text()


def test_failed_pod_raises_and_is_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    r = runner()
    r.core = FakeCore(quota_refusals=0, final="Failed")
    with pytest.raises(RunnerError):
        r.run_pdf("abc123abc123", tmp_path, tmp_path / "log")
    assert r.core.deleted == ["rocky-pdf-abc123abc123"]


def test_other_refusals_fail_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    r = runner()
    core = FakeCore(quota_refusals=0)

    def refuse(ns, pod):
        e = client.exceptions.ApiException(status=403, reason="Forbidden")
        e.body = 'pods is forbidden: User "system:serviceaccount:ws:rocky-api" cannot create resource "pods"'
        raise e
    core.create_namespaced_pod = refuse
    r.core = core
    with pytest.raises(RunnerError, match="cannot create"):
        r.run_midi("abc123abc123", Path("/a.wav"), tmp_path, "keyboard", tmp_path / "log")


@pytest.mark.parametrize("make", [
    lambda r: r.pdf_pod("abc123abc123", Path("/data/rocky-unified/runs/x")),
    lambda r: r.transpose_pod("abc123abc123-01p", Path("/data/rocky-unified/runs/x"),
                              Path("/data/rocky-unified/runs/x/transpose/+1"), 1),
])
def test_score_pods_install_pdf_tools_from_the_volume_before_the_mirror(make):
    script = make(runner()).spec.containers[0].args[0]
    local = script.index("dpkg -i /data/cache/pdf-debs/*.deb")
    mirror = script.index("apt-get -o Acquire::Retries=5 install")
    assert local < mirror < script.index("publish_scores.py")
    assert "musescore3 poppler-utils" in script


def test_pdf_tools_folder_can_be_moved(monkeypatch):
    monkeypatch.setenv("ROCKY_PDF_DEBS", "/data/other-debs")
    script = runner().pdf_pod("abc123abc123", Path("/data/rocky-unified/runs/x")).spec.containers[0].args[0]
    assert "dpkg -i /data/other-debs/*.deb" in script


# ---- the install snippet itself, run in bash with fake dpkg / apt-get / musescore3 / pdftoppm ----

def _fake(bin_dir, name, body):
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)


def _run_install(tmp_path, monkeypatch, *, cache_has_tools, mirror_ok=True):
    import shutil
    import subprocess
    from rocky_server.runners import pdf_tools_install
    bash = shutil.which("bash")
    if bash is None or sys.platform == "win32":
        pytest.skip("needs a POSIX bash")
    debs, bin_dir = tmp_path / "debs", tmp_path / "bin"
    debs.mkdir(); bin_dir.mkdir()
    for tool in ("cat", "chmod"):  # the fake installers below need these; nothing else is on PATH
        (bin_dir / tool).symlink_to(shutil.which(tool))
    (debs / "some-library.deb").write_bytes(b"deb")
    calls = tmp_path / "calls"
    tools = f'cat > {bin_dir}/musescore3 <<X\n#!/bin/sh\nX\nchmod +x {bin_dir}/musescore3\n' \
            f'cat > {bin_dir}/pdftoppm <<X\n#!/bin/sh\nX\nchmod +x {bin_dir}/pdftoppm'
    _fake(bin_dir, "dpkg", f'echo dpkg >> {calls}\n' + (tools if cache_has_tools else "true"))
    _fake(bin_dir, "apt-get", f'echo "apt-get $*" >> {calls}\n' + (tools if mirror_ok else "exit 100"))
    monkeypatch.setenv("ROCKY_PDF_DEBS", str(debs))
    script = "set -euo pipefail\n" + "\n".join(pdf_tools_install()) + "\necho DONE"
    r = subprocess.run([bash, "-c", script], capture_output=True, text=True,
                       env={"PATH": str(bin_dir)})
    return r, (calls.read_text() if calls.exists() else "")


def test_a_complete_cache_is_used_without_the_mirror(tmp_path, monkeypatch):
    r, calls = _run_install(tmp_path, monkeypatch, cache_has_tools=True)
    assert r.returncode == 0 and "installed from" in r.stdout and "DONE" in r.stdout
    assert "apt-get" not in calls


def test_a_partial_cache_falls_back_to_the_mirror(tmp_path, monkeypatch):
    # dpkg -i succeeds, but MuseScore / Poppler are not among the files
    r, calls = _run_install(tmp_path, monkeypatch, cache_has_tools=False)
    assert r.returncode == 0 and "downloading from the mirror" in r.stdout and "DONE" in r.stdout
    assert "apt-get" in calls and "install" in calls


def test_a_mirror_failure_is_marked_transient(tmp_path, monkeypatch):
    from rocky_server.runners import TRANSIENT_MARKER
    r, _ = _run_install(tmp_path, monkeypatch, cache_has_tools=False, mirror_ok=False)
    assert r.returncode == 75 and TRANSIENT_MARKER in r.stdout and "DONE" not in r.stdout
