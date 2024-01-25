"""nwc and random things. TODO: most of the things in here can probably go elsewhere"""

from typing import Optional
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs, urlencode
from coincurve import PublicKey
from pyln.client import Millisatoshi

ISSUED_URI_BASE_KEY = ["nwc", "uri"]


@dataclass
class NWCOptions:
    """defines options for creating a new NWC instance"""
    relay_url: Optional[str] = None
    secret: Optional[str] = None
    wallet_pubkey: Optional[str] = None
    nostr_wallet_connect_url: Optional[str] = None
    expiry_unix: Optional[int] = None
    budget_msat: Optional[Millisatoshi] = None


class NWC:
    """handle nostr wallet connects"""
    @staticmethod
    def parse_wallet_connect_url(url: str):
        parsed = urlparse(url=url)
        options = NWCOptions()
        options.wallet_pubkey = parsed.hostname

        query_params = parse_qs(parsed.query)
        options.secret = query_params.get("secret", [None])[0]
        options.relay_url = query_params.get("relay", [None])[0]

        return options

    @staticmethod
    def construct_wallet_connect_url(options: NWCOptions):
        """builds and returns the nwc uri"""
        if options.nostr_wallet_connect_url:
            return options.nostr_wallet_connect_url

        return f'nostr+walletconnect://{options.wallet_pubkey}?relay={options.relay_url}&secret={options.secret}'

    def __init__(self, options: NWCOptions):
        self.url = options.nostr_wallet_connect_url
        if self.url:
            options = self.parse_wallet_connect_url(self.url)
        else:
            if not options.relay_url:
                raise ValueError("relay url is required")
            if not options.secret:
                raise ValueError("secret is require")
            if not options.wallet_pubkey:
                raise ValueError("wallet pubkey is required")
            self.url = self.construct_wallet_connect_url(options)

        self.relay_url = options.relay_url
        self.secret = options.secret
        self.pubkey = PublicKey.from_secret(
            bytes.fromhex(self.secret)).format().hex()[2:]
        self.wallet_pubkey = options.wallet_pubkey
        self.expiry_unix = options.expiry_unix
        self.budget_msat = options.budget_msat

    @property
    def datastore_key(self):
        """get the key for handling connections in the db"""
        key = ISSUED_URI_BASE_KEY.copy()
        key.append(self.pubkey)
        return key
