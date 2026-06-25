"""Erzeugt einen MASTER_ENCRYPTION_KEY für die Produktion (32 Bytes, Base64)."""
import base64
import os

print(base64.b64encode(os.urandom(32)).decode("ascii"))
