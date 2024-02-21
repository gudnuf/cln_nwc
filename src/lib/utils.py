"""utility functions"""

from coincurve import PublicKey
from pyln.client import Plugin
import os


def get_hex_pubkey(privkey: str):
    """
    Compute the x-only public key from a private key
    """
    privkey_bytes = bytes.fromhex(privkey)
    compressed_hex_pubkey = PublicKey.from_secret(
        privkey_bytes).format().hex()
    x_only_hex_pubkey = compressed_hex_pubkey[2:]
    return x_only_hex_pubkey


def generate_keypair(plugin: Plugin) -> tuple[bytes, bytes]:
    """
    Use the node's hsm secret to generate a keypair

    Returns:
        privkey: bytes
        pubkey: bytes
    """

    random_hex = os.urandom(32).hex()

    privkey_hex = plugin.rpc.makesecret(hex=random_hex)["secret"]
    privkey_bytes = bytes.fromhex(privkey_hex)

    pubkey = PublicKey.from_secret(privkey_bytes).format()
    x_only_pubkey = pubkey[1:]

    return privkey_bytes, x_only_pubkey


def get_keypair(plugin: Plugin):
    """
    Get the privkey and pubkey from the plugin's datastore or generate a new one
    """
    datastore_key = ["nwc", "key", "v0"]

    datastore = plugin.rpc.listdatastore(key=datastore_key)["datastore"]

    privkey = None
    pubkey = None

    if len(datastore) is not 0:
        privkey = bytes.fromhex(datastore[0]["string"])
        pubkey = PublicKey.from_secret(privkey).format()[1:]

    else:
        privkey, pubkey = generate_keypair(plugin)
        plugin.rpc.datastore(key=datastore_key, string=privkey.hex())

    return privkey, pubkey
