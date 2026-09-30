from __future__ import annotations

SUPPORTED_GRID_COUNTS = (1, 4, 9, 16, 25, 36, 49, 64, 81, 100, 144)


def smallest_grid_for(required: int) -> int:
    """Return the smallest supported square-ish grid that can hold required slots."""
    required = max(1, int(required or 1))
    for count in SUPPORTED_GRID_COUNTS:
        if count >= required:
            return count
    return SUPPORTED_GRID_COUNTS[-1]


def next_empty_slot(sources: list[object | None], after_index: int = -1) -> int | None:
    """Find the next empty slot, wrapping once, without silently replacing a source."""
    if not sources:
        return None
    total = len(sources)
    start = (int(after_index) + 1) % total
    for offset in range(total):
        idx = (start + offset) % total
        if not sources[idx]:
            return idx
    return None
