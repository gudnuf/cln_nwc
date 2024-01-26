"""utility functions"""

from coincurve import PublicKey
from .lib import ISSUED_URI_BASE_KEY

def get_hex_pub_key(priv_key: str):
    """
    Compute the x-only public key from a private key
    """
    priv_key_bytes = bytes.fromhex(priv_key)
    compressed_hex_pub_key = PublicKey.from_secret(
        priv_key_bytes).format().hex()
    x_only_hex_pub_key = compressed_hex_pub_key[2:]
    return x_only_hex_pub_key

def find_connection(plugin, pub_key):
    """find the nostr wallet connection in db"""

    # TODO: this probably shouldn't be on the Event class
    connection_key = ISSUED_URI_BASE_KEY.copy()
    connection_key.append(pub_key)
    connection_record = plugin.rpc.listdatastore(
        key=connection_key)["datastore"]  # TODO: error handling
    return connection_record
