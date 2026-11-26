"""Run only BS-RoFormer separation; retain piano/other WAV for each input."""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import soundfile as sf

ROOT = Path('/work/piano_other_20261123')
TMP = ROOT / 'tmp'
RESULTS = ROOT / 'results'
LOGS = ROOT / 'logs'
PYTHON = '/data/rocky-unified/.venv/bin/python'
SEPARATE = '/data/pipeline/separate_bs_roformer.py'


def valid(path: Path) -> bool:
    try:
        info = sf.info(str(path))
        return info.frames > 0 and info.channels == 2 and info.samplerate > 0
    except (OSError, RuntimeError):
        return False


def main() -> None:
    LOGS.mkdir(exist_ok=True)
    with (ROOT / 'manifest.tsv').open(newline='', encoding='utf-8') as handle:
        items = list(csv.reader(handle, delimiter='\t'))
    failures = 0
    for index, (folder, file_id, ext) in enumerate(items, 1):
        source = ROOT / 'inputs' / folder / f'{file_id}{ext}'
        dest_dir = RESULTS / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        outputs = {part: dest_dir / f'{file_id}__{part}.wav' for part in ('piano', 'other')}
        if all(valid(path) for path in outputs.values()):
            print(f'SKIP {index}/{len(items)} {folder}/{file_id}', flush=True)
            continue
        work = TMP / file_id
        if not work.resolve().is_relative_to(TMP.resolve()):
            raise RuntimeError('unsafe temporary path')
        if work.exists():
            shutil.rmtree(work)
        started = time.monotonic()
        record = {'index': index, 'folder': folder, 'id': file_id}
        try:
            if not source.is_file():
                raise FileNotFoundError(source)
            with (LOGS / f'{file_id}.log').open('w', encoding='utf-8') as log:
                subprocess.run([PYTHON, SEPARATE, str(source), str(work),
                                '--models-dir', '/data/bsrofo/models',
                                '--lib-dir', '/data/bsrofo/pylib'],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            for part, target in outputs.items():
                stem = work / f'{part}.wav'
                if not valid(stem):
                    raise RuntimeError(f'invalid {part} stem')
                os.replace(stem, target)
            record.update(status='complete',
                          bytes={part: path.stat().st_size for part, path in outputs.items()})
            print(f'DONE {index}/{len(items)} {folder}/{file_id}', flush=True)
        except Exception as exc:
            failures += 1
            record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            print(f'FAILED {index}/{len(items)} {folder}/{file_id}: {exc}', flush=True)
        finally:
            record['seconds'] = round(time.monotonic() - started, 2)
            with (ROOT / 'progress.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(record, ensure_ascii=False) + '\n')
            if work.exists():
                shutil.rmtree(work)
    print(f'BATCH_FINISHED total={len(items)} failed={failures}', flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
