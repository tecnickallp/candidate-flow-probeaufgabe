import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import resolve_master_key


def encrypt(plaintext: str) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    aesgcm = AESGCM(resolve_master_key())
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce, ciphertext


def decrypt(nonce: bytes, ciphertext: bytes) -> str:
    aesgcm = AESGCM(resolve_master_key())
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
