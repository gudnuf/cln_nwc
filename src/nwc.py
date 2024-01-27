#!/usr/bin/env python3

"""
Entry point for this plugin
"""

try:
    from pyln.client import Plugin, Millisatoshi
    from coincurve import PrivateKey, PublicKey
    import threading
    import json
    from lib.nip47 import URIOptions, NIP47URI
    from lib.relay import Relay
except ImportError as e:
    # TODO: if something isn't installed then disable the plugin
    print("BAD STUFF", f"{e}")

# TODO: use the same format language for private and public keys, ie.
# priv_key vs privkey vs private_key, etc...

DEFAULT_RELAY = 'wss://relay.getalby.com/v1'

plugin = Plugin()


@plugin.init()
def init(options, configuration, plugin: Plugin):
    """initialize the plugin"""
    # TODO: create a Main class that implements Keys, Relay, Plugin
    plugin.priv_key = bytes.fromhex("000001")  # TODO: set a real privkey
    plugin.pub_key = PublicKey.from_secret(plugin.priv_key).format().hex()[2:]

    uri = DEFAULT_RELAY
    relay = Relay(plugin, uri)

    # for now this also handles all the event handling logic
    # TODO: move the event handling logic to a NWC class that is the class for
    # this protocol
    # start a new thread for the relay
    relay_thread = threading.Thread(target=relay.listen_for_nip47_requests)
    relay_thread.start()

    plugin.log(f"connected to {uri}", 'info')


# https://github.com/nostr-protocol/nips/blob/master/47.md#example-connection-string
@plugin.method("nwc-create")
def create_nwc_uri(plugin: Plugin, expiry_unix: int = None,
                   budget_msat: int = None):
    """Create a new nostr wallet connection"""
    wallet_pubkey = plugin.pub_key
    relay_url = DEFAULT_RELAY

    # 32-byte hex encoded secret to sign/encrypt
    sk = PrivateKey()
    secret = sk.secret.hex()

    options = URIOptions(
        relay_url=relay_url,
        secret=secret,
        wallet_pubkey=wallet_pubkey,
        expiry_unix=expiry_unix,
        budget_msat=Millisatoshi(budget_msat) if budget_msat else None
    )

    nwc = NIP47URI(options=options)

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
