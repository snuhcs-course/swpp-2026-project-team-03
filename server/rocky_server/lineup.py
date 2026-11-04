"""App part names -> unified.py --original / --requested values.

The app uses piano, drums, bass, guitar, guitar2 (guitar2 = a second guitar).
unified.py (ml/unified-pipeline, contract 8) takes keyboard, bass, drums and
exactly one of guitar1 / guitar2, where guitar1/guitar2 is the guitar COUNT.
An empty original means the user chose "I don't know" -> "unknown".
"""

from __future__ import annotations

APP_PARTS = ("piano", "drums", "bass", "guitar", "guitar2")


class LineupError(ValueError):
    pass


def guitar_count(parts: list[str]) -> int:
    return 2 if "guitar2" in parts else 1 if "guitar" in parts else 0


def pipeline_lineup(parts: list[str]) -> str:
    """['piano','guitar','guitar2','drums'] -> 'keyboard,bass?,guitar2,drums' (only present ones)."""
    unknown = [p for p in parts if p not in APP_PARTS]
    if unknown:
        raise LineupError(f"unknown parts: {','.join(unknown)}")
    tokens = []
    if "piano" in parts:
        tokens.append("keyboard")
    if "bass" in parts:
        tokens.append("bass")
    n = guitar_count(parts)
    if n:
        tokens.append(f"guitar{n}")
    if "drums" in parts:
        tokens.append("drums")
    return ",".join(tokens)


def pipeline_args(lineup: list[str], original: list[str]) -> tuple[str, str]:
    """(original, requested) for unified.py; raises LineupError for what it rejects."""
    requested = pipeline_lineup(lineup)
    if not requested:
        raise LineupError("choose at least one instrument for your band")
    if not original:
        return "unknown", requested
    orig = pipeline_lineup(original)
    if not orig:
        return "unknown", requested
    if guitar_count(original) == 0 and guitar_count(lineup) == 2:
        raise LineupError("two guitars cannot be generated when the original has no guitar")
    return orig, requested
