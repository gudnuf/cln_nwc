#!/usr/bin/env python3
from pyln.client import Plugin, Millisatoshi
from coincurve import PrivateKey
import json
from lib import NWCOptions, NWC

DEFAULT_RELAY = 'wss://relay.damus.io'

plugin = Plugin()

@plugin.init()
def init(options, configuration, plugin, **kwargs):
    plugin.log("NWC plugin initialized")

# https://github.com/benthecarman/nips/blob/nwc-extensions/47.md#nostr-wallet-connect-uri
@plugin.method("nwc-create")
def create_nwc_uri(plugin: Plugin, expiry_unix: int = None, budget_msat: int = None):
    wallet_pubkey = plugin.rpc.getinfo().get("id")[2:] # QUESTION: is this okay or should the pubkey be different from node pubkey for privacy reasons??
    relay_url = DEFAULT_RELAY

    # 32-byte hex encoded secret to sign/encrypt
    sk = PrivateKey()
    secret = sk.secret.hex()

    options = NWCOptions(
        relay_url=relay_url,
        secret=secret,
        wallet_pubkey=wallet_pubkey,
        expiry_unix=expiry_unix,
        budget_msat=Millisatoshi(budget_msat)
    )

    nwc = NWC(options=options)

    data_string = json.dumps({
        "secret": nwc.secret,
        "budget_msat": nwc.budget_msat,
        "expiry_unix": nwc.expiry_unix,
        "spent_msat": Millisatoshi(0)
    })
    plugin.rpc.datastore(key=nwc.datastore_key, string=data_string)

    return {
        "url": nwc.url,
        "pubkey": nwc.pubkey
    }
    
plugin.run()
