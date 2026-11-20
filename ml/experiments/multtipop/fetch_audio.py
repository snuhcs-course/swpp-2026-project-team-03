#!/usr/bin/env python3
"""Fetch only the listed time range of each audio_manifest.csv row as WAV.

The team decided to use these short segments for private evaluation only.
Nothing here is committed: data/ and *.wav are ignored by Git.  Do not share
the audio, and do not use it for training.

Rows whose audio_path already exists are skipped, so audio obtained another
way can simply be placed at that path.
"""
from __future__ import annotations

import argparse, csv, shutil, subprocess, sys
from pathlib import Path

import yt_dlp

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]


def ffmpeg_binary():
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg  # bundled binary, used when ffmpeg is not installed
    return imageio_ffmpeg.get_ffmpeg_exe()


def fetch(row, ffmpeg):
    output = PROJECT_ROOT / row["audio_path"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with yt_dlp.YoutubeDL({"format": "bestaudio/best", "quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(row["youtube_url"], download=False)
    headers = "".join(f"{key}: {value}\r\n" for key, value in info.get("http_headers", {}).items())
    # -ss/-to before -i with re-encoding to PCM gives a sample-accurate cut and
    # reads only the requested range from the remote stream.
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-headers", headers,
               "-ss", row["start_sec"], "-to", row["end_sec"], "-i", info["url"],
               "-vn", "-ac", "2", "-ar", "44100", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        output.unlink(missing_ok=True)  # never leave a truncated file behind
        raise RuntimeError(result.stderr.strip().splitlines()[-1][:200])
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=HERE / "audio_manifest.csv")
    args = parser.parse_args()
    ffmpeg, failed = ffmpeg_binary(), []
    with args.manifest.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        label = f"{row['id']}  {row['artist']} - {row['name']}"
        if (PROJECT_ROOT / row["audio_path"]).exists():
            print(f"skip   {label} (already present)")
            continue
        try:
            print(f"ok     {label} -> {fetch(row, ffmpeg).relative_to(PROJECT_ROOT)}")
        except Exception as error:  # keep going; report every failure at the end
            failed.append(row["id"])
            print(f"FAILED {label}: {str(error).splitlines()[0]}", file=sys.stderr)
    if failed:
        sys.exit(f"{len(failed)} of {len(rows)} segments failed: {' '.join(failed)}")


if __name__ == "__main__":
    main()
