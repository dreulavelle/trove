"""Pluggable progress reporting so the downloader stays UI-agnostic.

The CLI uses ``TqdmSink``; the TUI supplies a Textual-backed sink. Sinks are
keyed per download so concurrent transfers report independently.
"""

from __future__ import annotations

from typing import Protocol

from tqdm import tqdm


class ProgressSink(Protocol):
    def start(self, key: str, desc: str, total: int | None, initial: int = 0) -> None: ...
    def advance(self, key: str, amount: int) -> None: ...
    def finish(self, key: str) -> None: ...


class NullSink:
    def start(self, key: str, desc: str, total: int | None, initial: int = 0) -> None: ...
    def advance(self, key: str, amount: int) -> None: ...
    def finish(self, key: str) -> None: ...


class TqdmSink:
    """Console bars that reuse display rows so concurrent bars stay tidy."""

    def __init__(self) -> None:
        self._bars: dict[str, tqdm] = {}
        self._positions: dict[str, int] = {}
        self._free: list[int] = []
        self._next_position = 0

    def start(self, key: str, desc: str, total: int | None, initial: int = 0) -> None:
        self.finish(key, _release=False)  # a retry restarts the same key
        position = self._free.pop(0) if self._free else self._next_position
        if position == self._next_position:
            self._next_position += 1
        self._positions[key] = position
        self._bars[key] = tqdm(
            total=total, initial=initial, unit="B", unit_scale=True,
            unit_divisor=1024, desc=desc, position=position, leave=False,
        )

    def advance(self, key: str, amount: int) -> None:
        if bar := self._bars.get(key):
            bar.update(amount)

    def finish(self, key: str, _release: bool = True) -> None:
        if bar := self._bars.pop(key, None):
            bar.close()
        position = self._positions.pop(key, None)
        if _release and position is not None:
            self._free.append(position)
