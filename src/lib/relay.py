"""Defines classes for interacting with relays"""

import asyncio
import json
import uuid
import websockets
from pyln.client import Plugin, RpcError
from .event import Event, NIP47Response


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

    # TODO: make this part of NIP47 class
    # TODO: make this accepts the response coneent
    async def send_response(self, code: str, nip04_pub_key: str):
        """send a nip47 response event"""
        self._plugin.log(f"nip47 error code: {code}")

        content = self._responses.get(code, None)
        if not content:
            content = self._responses.get("OTHER")
        content_str = json.dumps(content)
        response = NIP47Response(
            content_str,
            nip04_pub_key,
            referenced_event_id=self._current_event_id,
            priv_key=self._plugin.priv_key.hex()
        )
        response.sign()
        try:
            event = json.dumps(["EVENT", response.event_data()])
            self._plugin.log(
                f"SENDING EVENT: \n {event} \n PAYLOAD: {content}")
            await self.ws.send(event)
        # TODO: make sure this is the right exception to catch
        except websockets.exceptions.WebSocketException as e:
            print(f"Error broadcasting {e}")

    async def on_event(self, data: str):
        """handle incoming events"""
        event = Event.from_JSON(evt_json=data)

        decrypted_payload = event.nip04.decrypt(
            secret_key=self._plugin.priv_key.hex(),  # TODO: handle _plugin.priv_key
            pubkey_hex=event._pub_key,
            data=event._content
        )

        # TODO: implement NIP47 request
        request = json.loads(decrypted_payload)

        self._plugin.log(f"DECRYPTED {request}")

        connection = Event.find_unique(
            plugin=self._plugin, pub_key=event._pub_key)

        self._current_event_id = event._id

        if not connection:  # connection not found
            # send UNAUTHORIZED error response
            await self.send_response("UNAUTHORIZED", nip04_pub_key=event._pub_key)
            return

        nip47_method = request.get("method")
        nip47_event_handler = self._method_handlers.get(nip47_method)

        if not nip47_event_handler:
            # send NOT_IMPLEMENTED error response
            await self.send_response("NOT_IMPLEMENTED", nip04_pub_key=event._pub_key)
            return

        try:
            # execute the function
            await nip47_event_handler(params=request.get("params"))
            # TODO: validate connection. ie. budget, expiry, status?
        except RpcError as e:
            self._plugin.log(f"Error executing nip47 request: {e.error}")
            await self.send_response("OTHER", nip04_pub_key=event._pub_key)

    # async def listen(self):
    #     """"""
    #     self._listen = True
    #     try:
    #         while self._listen:
    #             message = await self.ws.recv()
    #             data = json.loads(message)
    #             if data[0] == "EVENT":
    #                 await self.on_event(data[2])
    #             elif data[0] == "OK":
    #                 pass
    #             elif data[0] == "CLOSED":
    #                 break
    #     except Exception as e:
    #         print(f"WebSocket error: {e}")

    async def _pay_invoice(self, params):
        # TODO: validate params for this method
        invoice = params.get("invoice")
        if not invoice:
            raise LookupError("no invoice found when trying to pay :(")
        self._plugin.rpc.pay(bolt11=invoice)
