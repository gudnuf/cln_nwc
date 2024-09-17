"""Main wallet functionality"""

import asyncio
import json
import uuid
import websockets
from .nip47 import NIP47Response, NIP47Request, InfoEvent
from utilities.rpc_plugin import plugin


class Wallet:
    """connect to a relay, subscribe to filters, and publish events"""

    def __init__(self, uri: str):
        self.uri = uri
        self.ws = None
        self.subscriptions = {}
        self._first_time_connected = True
        self._listen = None
        self._running = False

    def listen_for_nip47_requests(self):
        """start the asyncio event loop"""
        asyncio.run(self.run())

    async def run(self):
        """connect, subscribe, and listen for incoming events"""
        self._listen = True
        while self._listen:
            try:
                await self.connect()  # Connect to the relay
                if self._first_time_connected:
                    await self.send_info_event()  # publish kind 13194 info event
                    self._first_time_connected = False  # Update the flag
                # subscribe to nwc requests
                await self.subscribe(filter={"kinds": [23194], "#p": [plugin.pubkey]})
                await self.listen()
            except websockets.exceptions.ConnectionClosedError as e:
                plugin.log(
                    f"NWC relay connection closed with: {e}. Attempting to reconnect...", 'debug')
                # Wait for 5 seconds before trying to reconnect
                await asyncio.sleep(5)
            except Exception as e:
                plugin.log(f"An unexpected error occurred: {e}", 'error')
                self._listen = False  # Stop the loop if an unexpected error occurs
            finally:
                self._running = False

    async def connect(self):
        self.ws = await websockets.connect(self.uri)
        self._running = True

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
                plugin.log(f"OK received {data}", 'debug')
            elif data[0] == "CLOSED":
                plugin.log(f"CLOSED received {data}", 'debug')

    async def subscribe(self, filter):
        """subscribe to a filter"""
        plugin.log(f"nwc subscription: {filter}", 'info')

        sub_id = str(uuid.uuid4())[:64]
        await self.ws.send(json.dumps(["REQ", sub_id, filter]))

        self.subscriptions[sub_id] = filter

        return sub_id

    async def send_info_event(self):
        supported_methods = ["pay_invoice",
                             "make_invoice", "get_info", "pay_keysend", "lookup_invoice", "get_balance", "list_transactions"]
        nip47_info_event = InfoEvent(supported_methods)

        nip47_info_event.sign(privkey=plugin.privkey.hex())

        plugin.log(
            f"sending info event. Supported methods: {supported_methods}", 'info')

        await self.send_event(nip47_info_event.event_data())

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
        request = NIP47Request.from_JSON(evt_json=data)

        response_content = await request.process_request(
            dh_privkey_hex=plugin.privkey.hex()
        )

        plugin.log(f"nwc request exectuted: {response_content}", 'debug')

        response_event = NIP47Response(
            content=json.dumps(response_content),
            nip04_pubkey=request._pubkey,
            referenced_event_id=request._id,
            privkey=plugin.privkey.hex()
        )

        response_event.sign()

        await self.send_event(response_event.event_data())
