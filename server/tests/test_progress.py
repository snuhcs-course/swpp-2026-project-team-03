from rocky_server.progress import (allowed_paths, current_app_stage, overall_fraction, result_files,
                                  run_progress)

from fake_pipeline import STEMS, write_manifest, write_outputs, write_progress


def test_weights_match_the_app():
    # app/.../progress/JobProgress.kt: SEPARATE .10, TRANSCRIBE .75, BEATS .05, ARRANGE .10
    assert overall_fraction("SEPARATE", 0, 1) == 0
    assert overall_fraction("TRANSCRIBE", 0, 1) == 0.10
    assert abs(overall_fraction("BEATS", 0, 1) - 0.85) < 1e-9
    assert abs(overall_fraction("ARRANGE", 1, 1) - 1.0) < 1e-9


def test_stage_follows_first_unfinished_pipeline_stage():
    assert current_app_stage([]) == "SEPARATE"
    assert current_app_stage(["demucs", "muscriptor_drums"]) == "TRANSCRIBE"
    assert current_app_stage(["demucs", *[f"muscriptor_{s}" for s in STEMS]]) == "BEATS"
    assert current_app_stage(["demucs", *[f"muscriptor_{s}" for s in STEMS],
                              "merge_stems", "beat_this", "align"]) == "ARRANGE"


def test_no_manifest_yet_is_separation_without_eta(tmp_path):
    p = run_progress(tmp_path / "missing", elapsed_sec=10)
    assert p == {"stage": "SEPARATE", "completed": 0, "total": 1, "fraction": 0.0, "eta_sec": None}


def test_transcription_counts_chunks_of_all_four_stems(tmp_path):
    write_manifest(tmp_path, ["bs_roformer", "muscriptor_drums"])
    write_progress(tmp_path, "drums", 30, 30)
    write_progress(tmp_path, "bass", 15, 30)
    p = run_progress(tmp_path, elapsed_sec=100)
    assert (p["stage"], p["completed"], p["total"]) == ("TRANSCRIBE", 45, 120)
    assert abs(p["fraction"] - (0.10 + 0.75 * 45 / 120)) < 1e-3
    assert p["eta_sec"] == round(100 * (1 - p["fraction"]) / p["fraction"])


def test_half_written_progress_line_is_ignored(tmp_path):
    write_manifest(tmp_path, ["bs_roformer"])
    write_progress(tmp_path, "drums", 3, 30)
    with (tmp_path / "stem_midi" / "drums.progress.jsonl").open("a") as f:
        f.write('{"stage": "transc')
    assert run_progress(tmp_path, 5)["completed"] == 3


def test_eta_waits_for_first_chunk(tmp_path):
    write_manifest(tmp_path, ["bs_roformer"])
    assert run_progress(tmp_path, elapsed_sec=40)["eta_sec"] is None


def test_result_lists_pdf_and_midi_per_part(tmp_path):
    write_outputs(tmp_path)
    r = result_files(tmp_path)
    assert {k: r["full_band"][k] for k in ("pdf", "pages", "midi")} == \
        {"pdf": "scores/full_band.pdf", "pages": 5, "midi": "full_score.mid"}
    assert r["instruments"]["guitar"] == {"pdf": "scores/guitar.pdf", "pages": 2,
                                          "midi": "scores/guitar.mid", "mp3": "scores/guitar.mp3"}
    assert r["full_band"]["mp3"] == "scores/band.mp3"
    assert r["instruments"]["piano"]["midi"] == "scores/piano.mid"
    assert r["generated_parts"] == ["piano"]
    assert "manifest.json" not in allowed_paths(r)


def test_arrange_progress_moves_forward_and_ends_at_100(tmp_path):
    from rocky_server.progress import arrange_steps
    base = ["bs_roformer", *[f"muscriptor_{s}" for s in STEMS], "merge_stems", "beat_this", "align"]
    seen = []
    for extra in ([], ["guitar_tab"], ["guitar_tab", "bass_tab", "midigpt", "normalize_generated"],
                  ["guitar_tab", "bass_tab", "midigpt", "normalize_generated", "assemble"]):
        d, t = arrange_steps({"completed": base + extra})
        seen.append(d / t)
    assert seen == sorted(seen) and seen[-1] < 1
    d, t = arrange_steps({"completed": base + ["assemble", "publish_outputs"], "score_publication": "complete"})
    assert d == t


def test_only_declared_original_stems_are_waited_for(tmp_path):
    # original = guitar,drums: unified.py transcribes only those two stems
    write_manifest(tmp_path, ["bs_roformer", "muscriptor_drums", "muscriptor_guitar"],
                   config={"original": ["drums", "guitar"]})
    assert run_progress(tmp_path, 10)["stage"] == "BEATS"


def test_contract_8_separation_stage_name(tmp_path):
    write_manifest(tmp_path, ["bs_roformer"])
    assert run_progress(tmp_path, 10)["stage"] == "TRANSCRIBE"


def test_extra_guitar_parts_are_listed(tmp_path):
    write_outputs(tmp_path, extra_guitar=True)
    r = result_files(tmp_path)
    assert {"guitar_1", "guitar_2"} <= set(r["instruments"])
    assert r["instruments"]["guitar_2"]["mp3"] == "scores/guitar_2.mp3"


def test_contract_10_batch_transcription_stage(tmp_path):
    # contract 10 transcribes all stems in one "muscriptor_batch" stage
    write_manifest(tmp_path, ["bs_roformer"])
    for s in STEMS:
        write_progress(tmp_path, s, 10, 30)
    p = run_progress(tmp_path, 10)
    assert (p["stage"], p["completed"], p["total"]) == ("TRANSCRIBE", 40, 120)
    write_manifest(tmp_path, ["bs_roformer", "muscriptor_batch"])
    assert run_progress(tmp_path, 10)["stage"] == "BEATS"
    write_manifest(tmp_path, ["bs_roformer", "muscriptor_batch", "merge_stems", "beat_this", "align",
                              "guitar_tab", "bass_tab"])
    p = run_progress(tmp_path, 10)
    assert p["stage"] == "ARRANGE" and p["completed"] == 2   # batch stage is not counted as arrange work


def test_rule_gate_stages_are_not_counted_as_arrange_steps():
    from rocky_server.progress import arrange_steps, current_app_stage
    completed = ["bs_roformer", "input_check", "muscriptor_batch", "note_gate",
                 "merge_stems", "beat_this", "align", "guitar_tab"]
    assert current_app_stage(completed[:2]) == "TRANSCRIBE"
    assert arrange_steps({"completed": completed}) == (1, 4)
