"""Measure positions (scores/<key>.measures.json) and recording measure times."""

import json
from pathlib import Path
import sys

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_scores
from publish_scores import has_measures, link_measures, measure_times, mpos_measures
from test_publish_scores import fake_tools, two_track_gp5

LINK = "https://measure.rocky.invalid/"


def skia_pdf(pages: list[list[tuple[int, int, list[float]]]]) -> bytes:
    """A PDF laid out like Chrome's (Skia): plain dictionaries, one link annotation per measure.
    pages: per page, (track, measure, [left, bottom, right, top]) links."""
    objects, kids, number = {}, [], 3
    for links in pages:
        annots = []
        for track, measure, rect in links:
            objects[number] = (f"<</Type /Annot\n/Subtype /Link\n/Rect [{' '.join(map(str, rect))}]\n"
                               f"/A <</Type /Action\n/S /URI\n/URI ({LINK}{track}/{measure})>>>>")
            annots.append(f"{number} 0 R")
            number += 1
        objects[number] = (f"<</Type /Page\n/MediaBox [0 0 595 842]\n/Annots [{' '.join(annots)}]\n"
                           f"/Parent 2 0 R>>")
        kids.append(f"{number} 0 R")
        number += 1
    objects[2] = f"<</Type /Pages\n/Count {len(kids)}\n/Kids [{' '.join(kids)}]>>"
    objects[1] = "<</Type /Catalog\n/Pages 2 0 R>>"
    body = "".join(f"{n} 0 obj\n{text}\nendobj\n" for n, text in sorted(objects.items()))
    return ("%PDF-1.4\n" + body + "trailer\n<</Root 1 0 R>>\n%%EOF\n").encode()


def test_links_become_top_left_boxes_and_are_blanked(tmp_path):
    pdf = tmp_path / "guitar.pdf"
    pdf.write_bytes(skia_pdf([[(0, 0, [57, 660, 292.5, 755]), (1, 0, [57, 300, 292.5, 395])],
                              [(0, 1, [57, 742, 200, 842])]]))
    size = pdf.stat().st_size

    boxes, sizes = link_measures(pdf)

    assert sizes == [[595.0, 842.0], [595.0, 842.0]]
    # two tracks give two boxes for measure 0, first track first; y is measured from the top
    assert boxes == [[[0, 57.0, 87.0, 235.5, 95.0], [0, 57.0, 447.0, 235.5, 95.0]],
                     [[1, 57.0, 0.0, 143.0, 100.0]]]
    data = pdf.read_bytes()
    assert b"/Annots" not in data and pdf.stat().st_size == size  # blanked in place


def test_pdf_without_links_gives_nothing(tmp_path):
    pdf = tmp_path / "plain.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<</Type /Catalog\n/Pages 2 0 R>>\nendobj\n")
    assert link_measures(pdf) == ([], [])


@pytest.mark.parametrize("broken", [
    lambda d: d.replace(b"/Type /Catalog", b"/Type /Katalog"),          # no catalog
    lambda d: d.replace(b"/Pages 2 0 R>>", b">>"),                      # catalog without /Pages
    lambda d: d.replace(b"/Kids [", b"/Kids [99 0 R "),                 # kid that does not exist
    lambda d: d.replace(b"/Kids [", b"/Type /Pages /Kids [2 0 R "),     # pages tree points at itself
])
def test_broken_pdfs_raise_and_publish_catches_them(tmp_path, broken):
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(broken(skia_pdf([[(0, 0, [57, 660, 292.5, 755])]])))
    with pytest.raises(Exception):
        link_measures(pdf)


def test_mpos_elements_become_boxes_in_points(tmp_path):
    mpos = tmp_path / "full_band.mpos"
    mpos.write_text('<score><elements>'
                    '<element id="1" x="13222.4" y="3167.32" sx="3667.37" sy="11500" page="0"/>'
                    '<element id="0" x="5752.32" y="3167.32" sx="7470.12" sy="11500" page="0"/>'
                    '</elements></score>')
    assert mpos_measures(mpos) == [[[0, 115.05, 63.35, 149.4, 230.0]], [[0, 264.45, 63.35, 73.35, 230.0]]]


def test_measure_times_follow_the_beats_the_notes_were_placed_on():
    alignment = {"beat_times": [0.2, 0.54, 0.92, 1.26, 1.6, 1.96, 2.3], "beats_per_bar": 4,
                 "beat_offset": 1, "beat_period": 0.35}
    # score beat k is recorded beat k - 1: measure 0 starts one beat before the first detected beat,
    # measure 1 at recorded beat 3, measure 2 past the last beat
    assert measure_times(alignment, 3) == [-0.15, 1.26, 2.65]
    assert measure_times({}, 3) == []


def publish_two_guitar_song(tmp_path, monkeypatch, calls):
    pytest.importorskip("guitarpro")
    run = tmp_path / "run"
    (run / "guitar").mkdir(parents=True)
    score = pretty_midi.PrettyMIDI()
    for name in ("Guitar 1 (lead)", "Guitar 2 (rhythm)"):
        track = pretty_midi.Instrument(program=29, name=name)
        track.notes.append(pretty_midi.Note(90, 64, 0, 1))
        score.instruments.append(track)
    score.write(str(run / "full_score.mid"))
    two_track_gp5(run / "guitar" / "skyline lead+rhythm.gp5")
    (run / "manifest.json").write_text(json.dumps({"status": "complete", "guitar_score_dir": "guitar"}))

    def counting_tools(command, check):
        calls.append(Path(command[3] if command[0] == "node" else command[2]).name)
        return fake_tools(command, check)

    monkeypatch.setattr(publish_scores.subprocess, "run", counting_tools)
    monkeypatch.setattr(publish_scores.shutil, "which", lambda name: name)
    monkeypatch.setattr(publish_scores, "pdf_pages", lambda path, pdfinfo: 1)
    monkeypatch.setattr(publish_scores, "pdf_page_sizes", lambda path, pdfinfo, pages: [[595.0, 842.0]])
    converter = tmp_path / "convert.js"
    converter.write_text("")
    return run, lambda: publish_scores.publish(run, "musescore3", "node", converter, "pdfinfo", False)


def test_failed_positions_never_fail_publishing_or_repeat(tmp_path, monkeypatch):
    calls = []
    run, publish = publish_two_guitar_song(tmp_path, monkeypatch, calls)

    def explode(pdf):
        raise StopIteration  # not an OSError/ValueError: must still be caught

    monkeypatch.setattr(publish_scores, "link_measures", explode)
    contract = publish()  # fake .mpos files are not XML either

    assert publish_scores.publication_ready(run)
    assert all("measures" not in item for item in [contract["full_band"], *contract["instruments"].values()])
    assert not list((run / "scores").glob("*.mpos"))  # removed even after a failed parse
    layout = json.loads((run / "scores" / "guitar_1.measures.json").read_text())
    assert layout["measures"] == [] and "StopIteration" in layout["error"]
    assert not has_measures(run / "scores" / "guitar_1.measures.json")

    calls.clear()
    publish()  # same inputs: nothing redrawn and no .mpos export run again
    assert not [name for name in calls if name.endswith((".pdf", ".mpos"))]


def test_found_positions_are_listed_in_the_contract(tmp_path, monkeypatch):
    calls = []
    run, publish = publish_two_guitar_song(tmp_path, monkeypatch, calls)
    monkeypatch.setattr(publish_scores, "link_measures", lambda pdf: ([[[0, 1.0, 2.0, 3.0, 4.0]]], [[595.0, 842.0]]))

    contract = publish()

    assert contract["instruments"]["guitar_1"]["measures"] == "scores/guitar_1.measures.json"
    assert has_measures(run / "scores" / "guitar_1.measures.json")
    assert "measures" not in contract["full_band"]  # the fake .mpos is not XML
