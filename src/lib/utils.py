"""utility functions"""

from coincurve import PublicKey


def get_hex_pubkey(privkey: str):
    """
    Compute the x-only public key from a private key
    """
    privkey_bytes = bytes.fromhex(privkey)
    compressed_hex_pubkey = PublicKey.from_secret(
        privkey_bytes).format().hex()
    x_only_hex_pubkey = compressed_hex_pubkey[2:]
    return x_only_hex_pubkey
