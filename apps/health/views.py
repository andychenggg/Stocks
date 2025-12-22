from django.db import connection
from django.http import JsonResponse


REQUIRED_TABLES = ("klines", "window_stats", "alerts")


def db_schema_status(request):
    try:
        existing = set(connection.introspection.table_names())
        missing = [name for name in REQUIRED_TABLES if name not in existing]
        return JsonResponse(
            {
                "ok": not missing,
                "required": list(REQUIRED_TABLES),
                "missing": missing,
            }
        )
    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "required": list(REQUIRED_TABLES),
                "error": str(exc),
            },
            status=500,
        )
