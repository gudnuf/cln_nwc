from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import base64

def decrypt(secret_key: str, pubkey_hex: str, data: str) -> str:
    pubkey_bytes = bytes.fromhex('02'+pubkey_hex)

    # convert pubkey to ec EllipticCurvePublicKey instance 
    ec_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pubkey_bytes)

    # convert secret to ec EllipticCurvePrivateKey instance
    sk = ec.derive_private_key(int(secret_key, 16), ec.SECP256K1())

    #perform elliptic curve Diffie-Helman key exchange
    shared_key = sk.exchange(ec.ECDH(), ec_key)

    # Split and decode encrypted data and IV from base64
    encrypted_message_b64, iv_b64 = data.split('?iv=')
    encrypted_message = base64.b64decode(encrypted_message_b64)
    iv = base64.b64decode(iv_b64)

    # Decrypt the message
    cipher = Cipher(algorithms.AES(shared_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    ret = decryptor.update(encrypted_message)
    padder = padding.PKCS7(128).unpadder()
    ret = padder.update(ret)
    ret += padder.finalize()

    # return as a string
    return ret.decode()