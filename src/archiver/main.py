"""Process entrypoint.

Wires the CLI. Later phases will assemble the scheduler, workers, and storage
here behind the ``run`` command; Phase 1 only exposes introspection commands.
"""

from __future__ import annotations

from archiver.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
