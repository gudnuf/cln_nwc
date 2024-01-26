"""Defines classes for interacting with relays"""

import asyncio
import json
import uuid
from pyln.client import Plugin
import websockets
from .nip47 import NIP47Response, NIP47Request


class Relay:
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
        # TODO: create responses more dynamically
        self._responses = {
            'UNAUTHORIZED': {
                "result_type": None,
                "error": {
                    "code": "UNAUTHORIZED"
                }
            },
            'OTHER': {
                "result_type": None,
                "error": {
                    "code": "OTHER"
                }
            }
        }

        self._method_handlers = {
            "pay_invoice": self._pay_invoice
        }

        # this is the current event that the relay is handling
        # TODO: make event handlign seperate, probably in nip47 class
        self._current_event_id: str = None

    async def run(self):
        """connect and subscribe to the relay"""
        self._listen = True
        await self.connect()  # TODO: error handling

        self._running = True

    def start(self):
        """start the asyncio event loop"""
        asyncio.run(self.run())

    async def connect(self):
        """connect to the relay, subscribe to the nwc filter, and start listening"""
        async with websockets.connect(self.uri) as ws:
            self.ws = ws

            # TODO, connect should just connect to the relay
            await self.subscribe(filter={
                "kinds": [23194],
                "#p": [self._plugin.pub_key]
            }, ws=ws)

            while self._listen:
                message = await ws.recv()
                data = json.loads(message)

                if data[0] == "EVENT":
                    await self.on_event(data=data[2])
                elif data[0] == "OK":
                    self._plugin.log(f"OK received {data}")
                elif data[0] == "CLOSED":
                    self._plugin.log(f"CLOSED received {data}")

    async def disconnect(self):
        """close websocket connection"""
        if self._running:
            asyncio.get_event_loop().run_until_complete(self.ws.close())

    async def subscribe(self, filter, ws):
        """subscribe to a filter"""
        self._plugin.log(f"SUBSCRIBING: {filter}")
        sub_id = str(uuid.uuid4())[:64]
        await ws.send(json.dumps(["REQ", sub_id, filter]))

        self.subscriptions[sub_id] = filter
        return sub_id

    async def publish(self, event):
        """send and event to the relay"""
        await self.ws.send(json.dumps(["EVENT", event]))

    async def send_event(self, event_data):
        """send a nip47 response event"""
        try:
            event = json.dumps(["EVENT", event_data])
            self._plugin.log(
                f"SENDING EVENT: \n {event} \n")
            self._plugin.log(f"WS{self.ws}")
            await self.ws.send(event)
        # TODO: make sure this is the right exception to catch
        except websockets.exceptions.WebSocketException as e:
            print(f"Error broadcasting {e}")

    async def on_event(self, data: str):
        """handle incoming NIP47 requestevents"""
        request = NIP47Request.from_JSON(evt_json=data, relay=self)
        # event = Event.from_JSON(evt_json=data)
        response = await request.process_request(
            plugin=self._plugin, 
            dh_priv_key_hex=self._plugin.priv_key.hex()
            )
        
        self._plugin.log(f"RESPOSNE: {response}")
        # decrypted_payload = request.decrypt_content(self._plugin.priv_key)
        response_event = NIP47Response(
            content=json.dumps(response),
            nip04_pub_key=request._pub_key,
            referenced_event_id=request._id,
            priv_key=self._plugin.priv_key.hex()
        )

        response_event.sign()

        await self.send_event(response_event.event_data())

    async def _pay_invoice(self, params):
        # TODO: validate params for this method
        invoice = params.get("invoice")
        if not invoice:
            raise LookupError("no invoice found when trying to pay :(")
        self._plugin.rpc.pay(bolt11=invoice)
