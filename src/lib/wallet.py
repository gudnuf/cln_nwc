"""Main wallet functionality"""

import asyncio
import json
import uuid
import websockets
from .nip47 import NIP47Response, NIP47Request
from utilities.rpc_plugin import plugin


class Wallet:
    """connect to a relay, subscribe to filters, and publish events"""

    def __init__(self, uri: str):
        self.uri = uri
        self.ws = None
        self.subscriptions = {}
        self._listen = None
        self._running = False

    def listen_for_nip47_requests(self):
        """start the asyncio event loop"""
        asyncio.run(self.run())

    async def run(self):
        """connect, subscribe, and listen for incoming events"""
        self._listen = True
        await self.connect()  # TODO: error handling

        await self.subscribe(filter={
            "kinds": [23194],
            "#p": [plugin.pubkey]
        })

        await self.listen()

        self._running = True

    async def connect(self):
        self.ws = await websockets.connect(self.uri)

    async def disconnect(self):
        """close websocket connection"""
        if self._running:
            asyncio.get_event_loop().run_until_complete(self.ws.close())

    async def listen(self):
        """Listen for messages from the relay"""
        async for message in self.ws:
            data = json.loads(message)
            if data[0] == "EVENT":
                await self.on_event(data=data[2])
            elif data[0] == "OK":
                plugin.log(f"OK received {data}")
            elif data[0] == "CLOSED":
                plugin.log(f"CLOSED received {data}")

    async def subscribe(self, filter):
        """subscribe to a filter"""
        plugin.log(f"SUBSCRIBING: {filter}")

        sub_id = str(uuid.uuid4())[:64]
        await self.ws.send(json.dumps(["REQ", sub_id, filter]))

        self.subscriptions[sub_id] = filter

        return sub_id

    async def send_event(self, event_data):
        """send an event to the relay"""
        try:
            event = json.dumps(["EVENT", event_data])

            await self.ws.send(event)
        # TODO: make sure this is the right exception to catch
        except websockets.exceptions.WebSocketException as e:
            print(f"Error broadcasting {e}")

    async def on_event(self, data: str):
        """handle incoming NIP47 request events"""
        request = NIP47Request.from_JSON(evt_json=data, relay=self)

        response_content = await request.process_request(
            dh_privkey_hex=plugin.privkey.hex()
        )

        plugin.log(f"RESPOSNE: {response_content}")

        response_event = NIP47Response(
            content=json.dumps(response_content),
            nip04_pubkey=request._pubkey,
            referenced_event_id=request._id,
            privkey=plugin.privkey.hex()
        )

        response_event.sign()

        await self.send_event(response_event.event_data())
