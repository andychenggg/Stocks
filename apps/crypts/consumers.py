from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .broadcaster import GROUP_NAME
from .config import RECENT_ALERT_LIMIT
from .monitor import ensure_monitor_started
from .state import get_monitor


class CryptoStreamConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        await ensure_monitor_started()
        await self.channel_layer.group_add(GROUP_NAME, self.channel_name)
        await self.accept()
        monitor = get_monitor()
        if monitor:
            alerts = await monitor.store.fetch_recent_alerts(limit=RECENT_ALERT_LIMIT)
            await self.send_json(
                {"type": "snapshot", "data": monitor.snapshot(), "alerts": alerts}
            )
        else:
            await self.send_json({"type": "snapshot", "data": {}, "alerts": []})

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(GROUP_NAME, self.channel_name)

    async def receive_json(self, content, **kwargs) -> None:
        return

    async def broadcast_message(self, event: dict) -> None:
        await self.send_json(event["payload"])
