from channels.layers import get_channel_layer


GROUP_NAME = "crypt_updates"


class ChannelBroadcaster:
    def __init__(self, group_name: str = GROUP_NAME) -> None:
        self.group_name = group_name
        self.channel_layer = get_channel_layer()

    async def broadcast(self, payload: dict) -> None:
        if not self.channel_layer:
            return
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast.message",
                "payload": payload,
            },
        )
