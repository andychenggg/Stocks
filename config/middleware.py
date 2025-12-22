from __future__ import annotations

from django.http import HttpResponse


class AlertsCorsMiddleware:
    """Add permissive CORS headers for the alerts endpoint."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/alerts/recent"):
            if request.method == "OPTIONS":
                response = HttpResponse(status=204)
            else:
                response = self.get_response(request)
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type"
            response["Access-Control-Max-Age"] = "600"
            return response
        return self.get_response(request)
