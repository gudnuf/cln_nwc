import json
import time
import uuid
from enum import Enum
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
    def find_all():
        """find all nostr wallet connections in db"""
        key = ISSUED_URI_BASE_KEY.copy()
        records = plugin.rpc.listdatastore(key=key)["datastore"]

        if not records:
            return []

        connections: list[NIP47URI] = []

        for record in records:
            connection_data = json.loads(record.get("string"))
            budget_msat = connection_data.get("budget_msat", None)
            spent_msat = connection_data.get("spent_msat")
            expiry_unix = connection_data.get("expiry_unix", None)

            connection = NIP47URI(options=URIOptions(
                secret=connection_data.get("secret"),
                budget_msat=Millisatoshi(budget_msat) if budget_msat else None,
                spent_msat=Millisatoshi(spent_msat),
                expiry_unix=expiry_unix,
                relay_url="wss://relay.getalby.com/v1",
                wallet_pubkey="placeholder"
            ))
            connections.append(connection)

        return connections

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

    def delete(self):
        try:
            plugin.rpc.deldatastore(key=self.datastore_key)
        except RpcError as e:
            plugin.log(f"ERROR: {e}", 'error')
            raise e


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


class ErrorCodes(Enum):
    RATE_LIMITED = "RATE_LIMITED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    RESTRICTED = "RESTRICTED"
    UNAUTHORIZED = "UNAUTHORIZED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    INTERNAL = "INTERNAL"
    OTHER = "OTHER"
    NOT_FOUND = "NOT_FOUND"


class NWCError(Exception):
    """
    Base class for NWC errors.

    code: NWC error codes
    message: human readable error message
    """

    def __init__(self, code, message=None):
        super().__init__()
        self.code = code
        self.message = message


class ParameterValidationError(NWCError):
    def __init__(self, missing_param):
        code = ErrorCodes.OTHER
        message = f"missing parameter: {missing_param}"
        super().__init__(code, message)


class QuotaExceededError(NWCError):
    def __init__(self):
        code = ErrorCodes.QUOTA_EXCEEDED
        super().__init__(code)


class UnauthorizedError(NWCError):
    def __init__(self, message=None):
        code = ErrorCodes.UNAUTHORIZED
        super().__init__(code, message)


class NotImplementedError(NWCError):
    def __init__(self, message=None):
        code = ErrorCodes.NOT_IMPLEMENTED
        super().__init__(code, message)


class NIP47RequestHandler:
    method_params_schema = {
        "pay_invoice": {
            "required": ["invoice"],
            "optional": ["amount"]
        },
        "multi_pay_invoice": {
            "required": ["invoices"],
            "optional": []
        },
        "pay_keysend": {
            "required": ["amount", "pubkey"],
            "optional": ["preimage", "tlv_records"]
        },
        "multi_pay_keysend": {
            "required": ["keysends"],
            "optional": []
        },
        "make_invoice": {
            "required": ["amount"],
            "optional": ["description", "expiry", "description_hash"]
        },
        "lookup_invoice": {
            "required": [],
            "optional": ["payment_hash", "invoice"]
        },
        "list_transactions": {
            "required": [],
            "optional": ["limit", "offset", "from", "until", "unpaid", "type"]
        },
        "get_balance": {
            "required": [],
            "optional": []
        },
        "get_info": {
            "required": [],
            "optional": []
        }
    }

    @property
    def result_type(self):
        return self.request.get("method")

    def __init__(self, request: str, connection: NIP47URI):
        self._method_handlers = {
            "pay_invoice": self._pay_invoice,
            "make_invoice": self._make_invoice,
            "pay_keysend": self._pay_keysend,
            "get_info": self._get_info,
            "lookup_invoice": self._lookup_invoice,
            "get_balance": self._get_balance,
        }

        self.request = request
        self.connection = connection

        self.method = request.get("method")

        self.handler = self._method_handlers.get(self.method, None)

    def validate_params(self, params):
        required_params = self.method_params_schema[self.method]["required"]
        optional_params = self.method_params_schema[self.method]["optional"]

        for param in required_params:
            if not params.get(param):
                raise ParameterValidationError(param)

        return {key: params.get(key, None) for key in required_params + optional_params}

    async def execute(self, params):
        if self.connection.expired():
            raise UnauthorizedError("connection expired")

        validated_params = self.validate_params(params)
        return await self.handler(validated_params)

    async def _get_info(self, params):
        node_info = plugin.rpc.getinfo()
        return {
            "alias": node_info.get("alias"),
            "color": node_info.get("color"),
            "pubkey": node_info.get("id"),
            "network": node_info.get("network"),
            "block_height": node_info.get("blockheight"),
            "block_hash": None,
            "methods": list(self._method_handlers.keys())
        }

    def handle_pay_result(self, pay_result):
        preimage = pay_result.get("payment_preimage", None)
        if not preimage:
            raise NWCError(ErrorCodes.INTERNAL)

        amount_sent_msat = pay_result.get("amount_sent_msat")
        self.add_to_spent(amount_sent_msat)

        return {
            "preimage": preimage
        }

    async def _pay_invoice(self, params):
        invoice = params.get("invoice")
        amount = params.get("amount", None)

        invoice_msat = plugin.rpc.decodepay(
            bolt11=invoice).get("amount_msat", 0)

        if amount and invoice_msat:
            raise NWCError(ErrorCodes.OTHER,
                           "amount and invoice amount cannot both be specified")

        if self.connection.budget_msat and self.connection.remaining_budget < invoice_msat:
            plugin.log(
                f"nwc quota exceded for {self.connection.pubkey}", 'info')
            raise QuotaExceededError()

        pay_result = plugin.rpc.pay(bolt11=invoice, amount_msat=amount)

        plugin.log(f"nwc pay result: {pay_result}", 'debug')

        return self.handle_pay_result(pay_result)

    async def _pay_keysend(self, params):
        amount_msat = params.get("amount")
        pubkey = params.get("pubkey")
        tlv_records = params.get("tlv_records")
        preimage = params.get("preimage")

        if preimage:
            # pretty sure cln doesn't support specifying preimage
            raise NWCError(ErrorCodes.NOT_IMPLEMENTED,
                           "preimage not supported")
        if tlv_records:
            raise NWCError(ErrorCodes.NOT_IMPLEMENTED,
                           "tlv records not supported")

        pay_result = plugin.rpc.keysend(destination=pubkey,
                                        amount_msat=amount_msat)

        return self.handle_pay_result(pay_result)

    async def _make_invoice(self, params):
        amount_msat = params.get("amount")
        description = params.get("description") or "CLN NWC Plugin"
        # description_hash = params.get("description_hash", None)
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

    async def _get_balance(self, params):
        peer_channels = plugin.rpc.listpeerchannels()["channels"]

        node_balance = sum([Millisatoshi(channel.get("spendable_msat"))
                           for channel in peer_channels])

        return {
            "balance": int(node_balance),
        }

    async def _lookup_invoice(self, params):
        payment_hash = params.get("payment_hash")
        invoice = params.get("invoice")

        if invoice and payment_hash:
            raise NWCError(ErrorCodes.OTHER,
                           "payment_hash and invoice cannot both be specified")

        invoices = []
        if payment_hash:
            invoices = plugin.rpc.listinvoices(
                payment_hash=payment_hash).get("invoices", None)
        if invoice:
            invoices = plugin.rpc.listinvoices(
                invstring=invoice).get("invoices", None)

        invoice = invoices[0] if invoices else None
        if not invoice:
            raise NWCError(ErrorCodes.NOT_FOUND)
        else:
            return {
                "type": "incoming",
                "invoice": invoice.get("bolt11"),
                "description": invoice.get("description"),
                # "description_hash": invoice.get("description_hash"),
                "preimage": invoice.get("payment_preimage", None),
                "payment_hash": invoice.get("payment_hash"),
                "amount": invoice.get("amount_msat"),
                # "fees_paid":
                "created_at": int(time.time()),
                "expires_at": invoice.get("expires_at"),
                "settled_at": invoice.get("paid_at"),
            }

    def add_to_spent(self, amount_sent_msat):
        key = self.connection.datastore_key
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
        try:
            request_payload = json.loads(self.decrypt_content(dh_privkey_hex))
            method = request_payload.get("method", None)

            plugin.log(f"nwc request received: {request_payload}", 'debug')

            connection = NIP47URI.find_unique(pubkey=self._pubkey)

            if not connection:
                raise UnauthorizedError()

            request_handler = NIP47RequestHandler(
                connection=connection, request=request_payload)

            if not request_handler.handler:
                raise NotImplementedError()

            execution_result = await request_handler.execute(request_payload.get("params"))

            return self.success_response(result_type=method, result=execution_result)

        except NWCError as e:
            plugin.log(f"NWC ERROR: {e}", 'debug')
            return self.error_response(result_type=method, code=e.code, message=e.message)

        except RpcError as e:
            plugin.log(f"RPC ERROR: {e}", 'error')
            message = e.error.get("message", None)
            return self.error_response(
                result_type=method, code=ErrorCodes.INTERNAL, message=message)

        except json.JSONDecodeError as e:
            return self.error_response(result_type=method, code=ErrorCodes.OTHER, message=str(e.msg))

        except Exception as e:
            plugin.log(f"ERROR: {e}", 'error')
            return self.error_response(result_type=method, code=ErrorCodes.INTERNAL)

    def success_response(self, result_type, result):
        """Formats a successful response."""
        return {
            "result_type": result_type,
            "result": result,
            "error": None
        }

    def error_response(self, result_type, code: ErrorCodes, message=""):
        """Formats an error response."""
        return {
            "result_type": result_type,
            "result": None,
            "error": {
                "code": code.value,
                "message": message
            }
        }

    def decrypt_content(self, dh_privkey_hex: str):
        """Use nip04 to decrypt the event content"""
        return nip04.decrypt(
            secret_key=dh_privkey_hex,
            pubkey_hex=self._pubkey,
            data=self._content
        )


class InfoEvent(Event):
    def __init__(self, supported_methods: list[str]):
        # create kind 23195 (nwc response) event with encrypted payload
        content = ' '.join(supported_methods)

        super().__init__(
            content=content,
            kind=13194)
