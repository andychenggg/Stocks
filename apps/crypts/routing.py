from django.urls import path

from .consumers import CryptoStreamConsumer

websocket_urlpatterns = [
    path("ws/crypt/", CryptoStreamConsumer.as_asgi()),
]
