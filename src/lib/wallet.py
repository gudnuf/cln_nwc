"""Main wallet functionality"""

import asyncio
import json
import uuid
from pyln.client import Plugin
import websockets
from .nip47 import NIP47Response, NIP47Request


class Wallet:
    """connect to a relay, subscribe to filters, and publish events"""

    def __init__(self, plugin: Plugin, uri: str):
        self.uri = uri
        self.ws = None
        self.subscriptions = {}
        self._listen = None
        self._running = False
        # TODO: consider renaming self._plugin to self._rpc=plugin.rpc
        # TODO: make sure Plugin class has properties of priv and pubkeys
        self._plugin: Plugin = plugin
        if not self._plugin or not self._plugin.pub_key:
            raise ValueError()

    def listen_for_nip47_requests(self):
        """start the asyncio event loop"""
        asyncio.run(self.run())

    async def run(self):
        """connect, subscribe, and listen for incoming events"""
        self._listen = True
        await self.connect()  # TODO: error handling

        await self.subscribe(filter={
            "kinds": [23194],
            "#p": [self._plugin.pub_key]
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
                self._plugin.log(f"OK received {data}")
            elif data[0] == "CLOSED":
                self._plugin.log(f"CLOSED received {data}")

    async def subscribe(self, filter):
        """subscribe to a filter"""
        self._plugin.log(f"SUBSCRIBING: {filter}")

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
            plugin=self._plugin,
            dh_priv_key_hex=self._plugin.priv_key.hex()
        )

        self._plugin.log(f"RESPOSNE: {response_content}")

        response_event = NIP47Response(
            content=json.dumps(response_content),
            nip04_pub_key=request._pub_key,
            referenced_event_id=request._id,
            priv_key=self._plugin.priv_key.hex()
        )

        response_event.sign()

        await self.send_event(response_event.event_data())
