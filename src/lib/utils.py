"""utility functions"""

from coincurve import PublicKey

def get_hex_pub_key(priv_key: str):
    """
    Compute the x-only public key from a private key
    """
    priv_key_bytes = bytes.fromhex(priv_key)
    compressed_hex_pub_key = PublicKey.from_secret(
        priv_key_bytes).format().hex()
    x_only_hex_pub_key = compressed_hex_pub_key[2:]
    return x_only_hex_pub_key
