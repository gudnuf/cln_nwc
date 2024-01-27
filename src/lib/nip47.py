import json
import time
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
from pyln.client import Plugin, RpcError, Millisatoshi
from coincurve import PublicKey
from .event import Event
from .utils import get_hex_pub_key
from . import nip04

@dataclass
class URIOptions:
    """defines options for creating a new NWC instance"""
    relay_url: str = None
    secret: str = None
    wallet_pubkey: str = None
    nostr_wallet_connect_url: str = None
    expiry_unix: int = None
    budget_msat: Millisatoshi = None
    spent_msat: Millisatoshi = None


ISSUED_URI_BASE_KEY = ["nwc", "uri"]


class NIP47URI:
    """handle nostr wallet connects"""
    @staticmethod
    def parse_wallet_connect_url(url: str):
        parsed = urlparse(url=url)
        options = URIOptions()
        options.wallet_pubkey = parsed.hostname

        query_params = parse_qs(parsed.query)
        options.secret = query_params.get("secret", [None])[0]
        options.relay_url = query_params.get("relay", [None])[0]

        return options

    @staticmethod
    def find_unique(plugin, pub_key):
        """find the nostr wallet connection in db"""

        # TODO: this probably shouldn't be on the Event class
        connection_key = ISSUED_URI_BASE_KEY.copy()
        connection_key.append(pub_key)
        connection_record = plugin.rpc.listdatastore(
            key=connection_key)["datastore"]  # TODO: error handling
        if connection_record:
            connection_data = json.loads(connection_record[0].get("string"))

            return NIP47URI(options=URIOptions(
                secret=connection_data.get("secret"),
                budget_msat=connection_data.get("budget_msat"),
                spent_msat=connection_data.get("spent_msat"),
                expiry_unix=connection_data.get("expiry_unix"),
                # TODO: figure out how to not have to pass relay and wallet pubkey for this
                relay_url="wss://relay.getalby.com/v1",
                wallet_pubkey="placeholder"
            ))
        return None

    @staticmethod
    def construct_wallet_connect_url(options: URIOptions):
        """builds and returns the nwc uri"""
        if options.nostr_wallet_connect_url:
            return options.nostr_wallet_connect_url

        if not options.relay_url:
            raise ValueError("relay url is required")
        if not options.secret:
            raise ValueError("secret is require")
        if not options.wallet_pubkey:
            raise ValueError("wallet pubkey is required")

        return f'nostr+walletconnect://{options.wallet_pubkey}?relay={options.relay_url}&secret={options.secret}'

    def __init__(self, options: URIOptions):
        self.url = options.nostr_wallet_connect_url
        if self.url:
            options = self.parse_wallet_connect_url(self.url)
        else:
            self.url = self.construct_wallet_connect_url(options)

        self.relay_url = options.relay_url
        self.secret = options.secret
        self.pubkey = PublicKey.from_secret(
            bytes.fromhex(self.secret)).format().hex()[2:]
        self.wallet_pubkey = options.wallet_pubkey
        self.expiry_unix = options.expiry_unix or float('inf')
        self.budget_msat = options.budget_msat or float('inf')
        self.spent_msat = options.spent_msat

    @property
    def datastore_key(self):
        """get the key for handling connections in the db"""
        key = ISSUED_URI_BASE_KEY.copy()
        key.append(self.pubkey)
        return key

    @property
    def remaining_budget(self):
        total_budget = Millisatoshi(
            self.budget_msat) if self.budget_msat else float('inf')
        spent = Millisatoshi(self.spent_msat)
        return total_budget - spent

    def expired(self):
        now = int(time.time())
        print("NOW", now, "\nEXPIRE", self.expiry_unix)
        if now > self.expiry_unix:
            return True
        return False


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


class NWCError(Exception):
    def __init__(self, code):
        super().__init__()
        self.code = code


class NIP47RequestHandler:
    def __init__(self, request: str, connection: NIP47URI,  plugin: Plugin):
        self._plugin = plugin
        self._method_handlers = {
            "pay_invoice": self._pay_invoice,
        }

        self.request = request
        self.connection = connection

        method = request.get("method")

        if method not in self._method_handlers:
            raise ValueError(f"Unknown method: {method}")

        self.handler = self._method_handlers[method]

    async def execute(self, params):
        if self.connection.expired():
            return {
                "code": "UNAUTHORIZED",
                "message": "expired"
            }
        return await self.handler(params)

    async def _pay_invoice(self, params):
        invoice = params.get("invoice")
        if not invoice:
            raise LookupError("No invoice found when trying to pay :(")
        invoice_msat = self._plugin.rpc.decodepay(
            bolt11=invoice).get("amount_msat", 0)

        if self.connection.remaining_budget < invoice_msat:
            return {
                "code": "QUOTA_EXCEEDED"
            }

        try:
            preimage = await self._plugin.rpc.pay(bolt11=invoice)
            return {
                "preimage": preimage
            }
        except RpcError as e:
            # TODO: include INSUFFICIENT_BALANCE
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

        connection = NIP47URI.find_unique(plugin=plugin, pub_key=self._pub_key)

        print(f"CONNECTION {connection}")

        code = None
        if not connection:
            code = "UNAUTHORIZED"

        request_handler = NIP47RequestHandler(connection=connection, request=request_payload, plugin=plugin)

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
        return nip04.decrypt(
            secret_key=dh_priv_key_hex,
            pubkey_hex=self._pub_key,
            data=self._content
            )
    