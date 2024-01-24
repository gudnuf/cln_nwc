from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import base64
import os

# NIP04 spec: https://github.com/nostr-protocol/nips/blob/master/04.md

# these functions are adapted from 
# https://github.com/monty888/monstr/blob/cb728f1710dc47c8289ab0994f15c24e844cebc4/src/monstr/encrypt.py

def get_ecdh_key(secret_key: str, pubkey_hex: str):
    """
    Perform an Elliptic Curve Diffie-Hellman key exchange to derive a shared secret.

    Parameters:
    secret_key (str): The private key in hexadecimal format.
    pubkey_hex (str): The public key in hexadecimal format.

    Returns:
    bytes: The shared secret derived from the ECDH key exchange.
    """
    
    pubkey_bytes = bytes.fromhex('02' + pubkey_hex)

    # convert pubkey to ec EllipticCurvePublicKey instance 
    ec_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pubkey_bytes)

    # convert secret to ec EllipticCurvePrivateKey instance
    sk = ec.derive_private_key(int(secret_key, 16), ec.SECP256K1())

    #perform elliptic curve Diffie-Helman key exchange
    shared_key = sk.exchange(ec.ECDH(), ec_key)

    return shared_key

def process_aes(data: bytes, key: bytes, iv: bytes, mode: str) -> bytes:
    """
    Process data using AES-256-CBC encryption or decryption.

    Parameters:
    data (bytes): The data to be encrypted or decrypted.
    key (bytes): The AES key for encryption or decryption.
    iv (bytes): The initialization vector for AES.
    mode (str): The mode of operation - 'encrypt' or 'decrypt'.

    Returns:
    bytes: The result of the AES encryption or decryption process.
    """

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    if mode == 'encrypt':
        processor = cipher.encryptor()
    elif mode == 'decrypt':
        processor = cipher.decryptor()

    result = processor.update(data) + processor.finalize()
    if mode == 'decrypt':
        unpadder = padding.PKCS7(128).unpadder()
        result = unpadder.update(result) + unpadder.finalize()
    
    return result

def encrypt(secret_key: str, pubkey_hex: str, data: str) -> str:
    """
    Encrypt data according to the NIP04 specification.

    Parameters:
    secret_key (str): The private key in hexadecimal format.
    pubkey_hex (str): The public key in hexadecimal format.
    data (str): The plaintext data to be encrypted.

    Returns:
    str: The encrypted data in base64 format with appended IV.
    """

    shared_key = get_ecdh_key(secret_key, pubkey_hex)

    # random 16 bytes
    iv = os.urandom(16)

    # add padding
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data.encode()) + padder.finalize()

    # encrypt using AES-256-CBC
    encrypted_data = process_aes(padded_data, shared_key, iv, 'encrypt')

    # return as base 65 string
    return base64.b64encode(encrypted_data).decode() + '?iv=' + base64.b64encode(iv).decode()

def decrypt(secret_key: str, pubkey_hex: str, data: str) -> str:
    """
    Decrypt data according to the NIP04 specification.

    Parameters:
    secret_key (str): The private key in hexadecimal format.
    pubkey_hex (str): The public key in hexadecimal format.
    data (str): The encrypted data in base64 format with appended IV.

    Returns:
    str: The decrypted plaintext data.
    """
   
    shared_key = get_ecdh_key(secret_key, pubkey_hex)

    # split the data into encrypted data and IV then decode
    encrypted_message_b64, iv_b64 = data.split('?iv=')
    encrypted_message = base64.b64decode(encrypted_message_b64)
    iv = base64.b64decode(iv_b64)

    # decrypt using AES-256-CBC
    decrypted_data = process_aes(encrypted_message, shared_key, iv, 'decrypt')

    # return as  string
    return decrypted_data.decode('utf-8')

# # TEST

# from coincurve import PrivateKey, PublicKey

# priv = PrivateKey().secret.hex()
# pub = PublicKey.from_secret(bytes.fromhex('B901EF')).format().hex()[2:]

# text = "This should get encrypted"

# encrypted = encrypt(secret_key=priv, pubkey_hex=pub, data=text)
# print("ENCRYPTED", encrypted)
 
# decrypted = decrypt(secret_key=priv, pubkey_hex=pub, data=encrypted)
# print("DECRYPTED", decrypted)

# assert text == decrypted