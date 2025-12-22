from __future__ import annotations

from django.http import JsonResponse

from .config import RECENT_ALERT_LIMIT, RETENTION_SECONDS, WINDOW_SIZE_MINUTES
from .db import PostgresStore
from .state import get_monitor


async def alerts_recent(request):
    monitor = get_monitor()
    store = monitor.store if monitor else PostgresStore(
        retention_seconds=RETENTION_SECONDS,
        window_size_minutes=WINDOW_SIZE_MINUTES,
    )
    try:
        alerts = await store.fetch_recent_alerts(limit=RECENT_ALERT_LIMIT)
        return JsonResponse({"alerts": alerts})
    except Exception as exc:
        return JsonResponse({"alerts": [], "error": str(exc)}, status=500)
