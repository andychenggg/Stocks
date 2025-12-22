from __future__ import annotations

_monitor = None


def set_monitor(monitor) -> None:
    global _monitor
    _monitor = monitor


def get_monitor():
    return _monitor
