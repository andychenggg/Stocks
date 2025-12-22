import os
import sys

from django.apps import AppConfig


def _should_autostart() -> bool:
    return os.getenv("CRYPTO_MONITOR_AUTOSTART", "").lower() in {"1", "true", "yes"}


def _is_server_process() -> bool:
    if os.environ.get("RUN_MAIN") == "true":
        return True
    argv = " ".join(sys.argv).lower()
    return "daphne" in argv


class CryptsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crypts"

    def ready(self) -> None:
        if _should_autostart() and _is_server_process():
            from .monitor import start_monitor_background

            start_monitor_background()
