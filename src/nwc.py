#!/nix/store/asiphbpiy2gmidfm3xbwcikayhs66289-python3-3.11.7/bin/python

"""
Entry point for this plugin
"""

try:
    from pyln.client import Plugin, Millisatoshi
    from coincurve import PrivateKey, PublicKey
    import threading
    import json
    from lib.nip47 import URIOptions, NIP47URI
    from lib.wallet import Wallet
    from lib.utils import get_keypair
    from utilities.rpc_plugin import plugin
except ImportError as e:
    # TODO: if something isn't installed then disable the plugin
    print("BAD STUFF", f"{e}")


DEFAULT_RELAY = 'wss://relay.getalby.com/v1'


@plugin.init()
def init(options, configuration, plugin: Plugin):
    """initialize the plugin"""
    # TODO: create a Main class that implements Keys, Wallet, Plugin

    privkey, pubkey = get_keypair(plugin)
    plugin.privkey = privkey
    plugin.pubkey = pubkey.hex()

    # create a Wallet instance to listent for incoming nip47 requests
    url = DEFAULT_RELAY
    wallet = Wallet(url)

    # start a new thread for the relay
    wallet_thread = threading.Thread(target=wallet.listen_for_nip47_requests)
    wallet_thread.start()

    plugin.log(f"connected to {url}", 'info')


# https://github.com/nostr-protocol/nips/blob/master/47.md#example-connection-string
@plugin.method("nwc-create")
def create_nwc_uri(plugin: Plugin, expiry_unix: int = None,
                   budget_msat: int = None):
    """Create a new nostr wallet connection"""
    wallet_pubkey = plugin.pubkey
    relay_url = DEFAULT_RELAY

    # 32-byte hex encoded secret to sign/encrypt
    sk = PrivateKey()
    secret = sk.secret.hex()

    options = URIOptions(
        relay_url=relay_url,
        secret=secret,
        wallet_pubkey=wallet_pubkey,
        expiry_unix=expiry_unix or None,
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


@plugin.method("nwc-list")
def list_nwc_uris(plugin: Plugin):
    """List all nostr wallet connections"""

    all_connections = NIP47URI.find_all()

    rtn = []
    for nwc in all_connections:
        remaining_budget_msat = None

        if nwc.budget_msat:
            try:
                remaining_budget_msat = nwc.budget_msat - nwc.spent_msat
            except:
                remaining_budget_msat = Millisatoshi(0)

        data = {
            "url": nwc.url,
            "pubkey": nwc.pubkey,
            "expiry_unix": nwc.expiry_unix,
            "remaining_budget_msat": remaining_budget_msat
        }
        rtn.append(data)

    return {
        "connections": rtn
    }


@plugin.method("nwc-revoke")
def revoke_nwc_uri(plugin: Plugin, pubkey: str):
    """Revoke a nostr wallet connection"""
    nwc = NIP47URI.find_unique(pubkey=pubkey)

    if not nwc:
        return {
            "error": f"No wallet connection found for pubkey {pubkey}"
        }

    nwc.delete()
    return True


plugin.run()
