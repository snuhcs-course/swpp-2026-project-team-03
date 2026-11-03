"""The four stems share one MuScriptor model without changing stem options."""

import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pretty_midi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transcribe_with_progress  # noqa: E402


def test_batch_reuses_one_model_and_resumes_valid_outputs(tmp_path, monkeypatch):
    score = pretty_midi.PrettyMIDI()
    buffer = io.BytesIO()
    score.write(buffer)
    midi_bytes = buffer.getvalue()
    calls = []

    class ProgressEvent:
        def __init__(self, completed, total):
            self.completed, self.total = completed, total

    class Model:
        def transcribe(self, audio, **kwargs):
            calls.append(("transcribe", Path(audio).name, kwargs["instruments"]))
            yield ProgressEvent(0, 1)
            yield ProgressEvent(1, 1)

        def events_to_midi_bytes(self, events, **kwargs):
            list(events)
            return midi_bytes

    def load_model(**kwargs):
        calls.append(("load", kwargs["weights_path"], kwargs["device"]))
        return Model()

    monkeypatch.setitem(sys.modules, "muscriptor", ModuleType("muscriptor"))
    monkeypatch.setitem(sys.modules, "muscriptor.events", SimpleNamespace(ProgressEvent=ProgressEvent))
    monkeypatch.setitem(sys.modules, "muscriptor.transcription_model",
                        SimpleNamespace(TranscriptionModel=SimpleNamespace(load_model=load_model)))
    monkeypatch.setitem(sys.modules, "muscriptor.utils", ModuleType("muscriptor.utils"))
    monkeypatch.setitem(sys.modules, "muscriptor.utils.midi",
                        SimpleNamespace(ExportOptions=lambda: object()))

    jobs = [{"stem": stem, "audio": str(tmp_path / f"{stem}.wav"),
             "output": str(tmp_path / f"{stem}.mid"), "instruments": stem,
             "progress": str(tmp_path / f"{stem}.progress.jsonl")}
            for stem in ("drums", "bass", "guitar", "piano")]
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["transcribe_with_progress.py", "--jobs-file",
                                  str(jobs_path), "--model", "large", "--device", "cuda",
                                  "--resume-existing"])
    transcribe_with_progress.main()
    assert [call for call in calls if call[0] == "load"] == [("load", "large", "cuda")]
    assert [call[1] for call in calls if call[0] == "transcribe"] == [
        "drums.wav", "bass.wav", "guitar.wav", "piano.wav"]
    assert all(Path(job["output"]).read_bytes() == midi_bytes for job in jobs)
    assert all(len(Path(job["progress"]).read_text().splitlines()) == 2 for job in jobs)

    transcribe_with_progress.main()
    assert len([call for call in calls if call[0] == "load"]) == 1
