import json
from pyln.client import Plugin, RpcError
from .event import Event
from .utils import get_hex_pub_key, find_connection
from . import nip04


class NIP47Response(Event):
    def __init__(self, content: str, nip04_pub_key,
                 referenced_event_id: str, priv_key: str):
        # encrypt response payload
        encrypted_content = nip04.encrypt(
            secret_key=priv_key,
            pubkey_hex=nip04_pub_key,
            data=content
        )

        event_pub_key = get_hex_pub_key(priv_key=priv_key)
        p_tag = ['p', nip04_pub_key]
        e_tag = ['e', referenced_event_id]
        # create kind 23195 (nwc response) event with encrypted payload
        super().__init__(
            content=encrypted_content,
            pub_key=event_pub_key,
            tags=[
                p_tag,
                e_tag],
            kind=23195)

        self._priv_key = priv_key  # QUESTION: bad idea to set the priv key on the class?

    def sign(self):
        return super().sign(priv_key=self._priv_key)
    

class NIP47RequestHandler:
    def __init__(self, method: str, plugin: Plugin):
        self._plugin = plugin
        self._method_handlers = {
            "pay_invoice": self._pay_invoice,
        }

        if method not in self._method_handlers:
            raise ValueError(f"Unknown method: {method}")

        self.handler = self._method_handlers[method]

    async def execute(self, params):
        return await self.handler(params)

    async def _pay_invoice(self, params):
        invoice = params.get("invoice")
        if not invoice:
            raise LookupError("No invoice found when trying to pay :(")
        try:
            preimage = await self._plugin.rpc.pay(bolt11=invoice)
            return {
                "preimage": preimage
            }
        except RpcError as e:
            return {
                "code": "OTHER",
                "message": e.error
            }

class NIP47Request(Event):
    """Implements all the NIP47 stuff we need"""
    
    def __init__(self, event: Event, relay):
        if event._kind != 23194:
            raise ValueError("NIP47 Requests must be kind 23194")

        super().__init__(
            id=event._id,
            sig=event._sig,
            kind=event._kind,
            content=event._content,
            tags=event._tags,
            pub_key=event._pub_key,
            created_at=event._created_at
        )

        self.relay = relay

    @staticmethod
    def from_JSON(evt_json, relay):
        # Create an Event instance from JSON
        event = Event(
            id=evt_json['id'],
            sig=evt_json['sig'],
            kind=evt_json['kind'],
            content=evt_json['content'],
            tags=evt_json['tags'],
            pub_key=evt_json['pubkey'],
            created_at=evt_json['created_at']
        )

        # Return a new NIP47Request instance
        return NIP47Request(event=event, relay=relay)

    async def process_request(self, plugin: Plugin, dh_priv_key_hex: str):
        request_payload = json.loads(self.decrypt_content(dh_priv_key_hex))

        connection = find_connection(plugin=plugin, pub_key=self._pub_key)

        print(f"CONNECTION {connection}")

        if not connection:
            code = "UNAUTHORIZED"

        request_handler = NIP47RequestHandler(method=request_payload.get("method"), plugin=plugin)

        if not request_handler:
            code = "NOT_IMPLEMENTED"

        if not code:
            execution_result = await request_handler.execute(request_payload.get("params"))
        else:
            execution_result = {
                "code": code,
                "message": None
            }

        return {
            "result_type": self._pub_key,
            "result": execution_result if not execution_result.get("code", None) else None,
            "error": execution_result if execution_result.get("code", None) else None,
        }

    def decrypt_content(self, dh_priv_key_hex: str):
        """Use nip04 to decrypt the event content"""
        return self.nip04.decrypt(
            secret_key=dh_priv_key_hex,
            pubkey_hex=self._pub_key,
            data=self._content
            )