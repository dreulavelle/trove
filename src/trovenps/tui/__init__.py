"""Trove's Textual TUI."""

from __future__ import annotations


def main() -> None:
    from ..observability import setup

    setup(console=False)  # TUI owns the screen; no stdout logging

    from .app import TroveApp

    TroveApp().run()


if __name__ == "__main__":
    main()
