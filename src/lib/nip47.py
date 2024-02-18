import json
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
from pyln.client import RpcError, Millisatoshi
from coincurve import PublicKey
from .event import Event
from .utils import get_hex_pubkey
from . import nip04
from utilities.rpc_plugin import plugin


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
    def find_unique(pubkey):
        """find the nostr wallet connection in db"""

        connection_key = ISSUED_URI_BASE_KEY.copy()
        connection_key.append(pubkey)
        connection_record = plugin.rpc.listdatastore(
            key=connection_key)["datastore"]  # TODO: error handling
        if connection_record:
            connection_data = json.loads(connection_record[0].get("string"))

            budget_msat = connection_data.get("budget_msat", None)
            spent_msat = connection_data.get("spent_msat")
            expiry_unix = connection_data.get("expiry_unix", None)

            return NIP47URI(options=URIOptions(
                secret=connection_data.get("secret"),
                budget_msat=Millisatoshi(budget_msat) if budget_msat else None,
                spent_msat=Millisatoshi(spent_msat),
                expiry_unix=expiry_unix,
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
        self.expiry_unix = options.expiry_unix or None
        self.budget_msat = options.budget_msat or None
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
            self.budget_msat)
        spent = Millisatoshi(self.spent_msat)
        return total_budget - spent

    def expired(self):
        if not self.expiry_unix:
            return False
        now = int(time.time())
        print("NOW", now, "\nEXPIRE", self.expiry_unix)
        if now > self.expiry_unix:
            return True
        return False


class NIP47Response(Event):
    def __init__(self, content: str, nip04_pubkey,
                 referenced_event_id: str, privkey: str):
        # encrypt response payload
        encrypted_content = nip04.encrypt(
            secret_key=privkey,
            pubkey_hex=nip04_pubkey,
            data=content
        )

        event_pubkey = get_hex_pubkey(privkey=privkey)
        p_tag = ['p', nip04_pubkey]
        e_tag = ['e', referenced_event_id]
        # create kind 23195 (nwc response) event with encrypted payload
        super().__init__(
            content=encrypted_content,
            pubkey=event_pubkey,
            tags=[
                p_tag,
                e_tag],
            kind=23195)

        self._privkey = privkey  # QUESTION: bad idea to set the priv key on the class?

    def sign(self):
        return super().sign(privkey=self._privkey)


class NWCError(Exception):
    def __init__(self, code):
        super().__init__()
        self.code = code


class NIP47RequestHandler:
    @property
    def result_type(self):
        return self.request.get("method")

    def __init__(self, request: str, connection: NIP47URI):
        self._method_handlers = {
            "pay_invoice": self._pay_invoice,
            "make_invoice": self._make_invoice,
        }

        self.request = request
        self.connection = connection

        method = request.get("method")

        self.handler = self._method_handlers.get(method, None)

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
        invoice_msat = plugin.rpc.decodepay(
            bolt11=invoice).get("amount_msat", 0)

        if self.connection.budget_msat and self.connection.remaining_budget < invoice_msat:
            return {
                "code": "QUOTA_EXCEEDED"
            }

        try:
            pay_result = plugin.rpc.pay(bolt11=invoice)
            preimage = pay_result.get("payment_preimage", None)
            if not preimage:
                return {
                    "code": "OTHER"
                }
            amount_sent_msat = pay_result.get("amount_sent_msat")
            self.add_to_spent(amount_sent_msat)
            return {
                "preimage": preimage
            }
        except RpcError as e:
            # TODO: include INSUFFICIENT_BALANCE
            return {
                "code": "OTHER",
                "message": e.error
            }

    async def _make_invoice(self, params):
        amount_msat = params.get("amount")
        if not amount_msat:
            return {
                "code": "OTHER",
                "message": "missing amount_msat"
            }
        description = params.get("description", None)
        description_hash = params.get("description_hash", None)
        expiry = params.get("expiry", None)
        invoice = plugin.rpc.invoice(
            amount_msat=amount_msat, label=f"nwc-invoice:{uuid.uuid4()}", description=description, expiry=expiry)
        return {
            "type": "incoming",
            "invoice": invoice.get("bolt11"),
            "amount": amount_msat,
            "created_at": int(time.time()),
            "expires_at": invoice.get("expires_at"),
            "payment_hash": invoice.get("payment_hash")
        }

    def add_to_spent(self, amount_sent_msat):
        key = self.connection.datastore_key
        print(
            f"SPENT: {self.connection.spent_msat} \n {Millisatoshi(amount_sent_msat)}")
        new_amount = self.connection.spent_msat + \
            Millisatoshi(amount_sent_msat)
        plugin.rpc.datastore(key=key, string=json.dumps({
            "secret": self.connection.secret,
            "budget_msat": self.connection.budget_msat,
            "expiry_unix": self.connection.expiry_unix,
            "spent_msat": new_amount
        }), mode="must-replace")


class NIP47Request(Event):
    """Implements all the NIP47 stuff we need"""

    def __init__(self, event: Event):
        if event._kind != 23194:
            raise ValueError("NIP47 Requests must be kind 23194")

        super().__init__(
            id=event._id,
            sig=event._sig,
            kind=event._kind,
            content=event._content,
            tags=event._tags,
            pubkey=event._pubkey,
            created_at=event._created_at
        )

    @staticmethod
    def from_JSON(evt_json):
        # Create an Event instance from JSON
        event = Event(
            id=evt_json['id'],
            sig=evt_json['sig'],
            kind=evt_json['kind'],
            content=evt_json['content'],
            tags=evt_json['tags'],
            pubkey=evt_json['pubkey'],
            created_at=evt_json['created_at']
        )

        # Return a new NIP47Request instance
        return NIP47Request(event=event)

    async def process_request(self, dh_privkey_hex: str):
        request_payload = json.loads(self.decrypt_content(dh_privkey_hex))

        connection = NIP47URI.find_unique(pubkey=self._pubkey)

        print(f"CONNECTION {connection}")

        code = None
        if not connection:
            code = "UNAUTHORIZED"

        request_handler = NIP47RequestHandler(
            connection=connection, request=request_payload)

        if not request_handler.handler:
            code = "NOT_IMPLEMENTED"

        if not code:
            try:
                execution_result = await request_handler.execute(request_payload.get("params"))
            except:
                execution_result = {
                    "code": "OTHER"
                }
        else:
            execution_result = {
                "code": code,
                "message": None
            }

        return {
            "result_type": request_handler.result_type,
            "result": execution_result if not execution_result.get("code", None) else None,
            "error": execution_result if execution_result.get("code", None) else None,
        }

    def decrypt_content(self, dh_privkey_hex: str):
        """Use nip04 to decrypt the event content"""
        return nip04.decrypt(
            secret_key=dh_privkey_hex,
            pubkey_hex=self._pubkey,
            data=self._content
        )
