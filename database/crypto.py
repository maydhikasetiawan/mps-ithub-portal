import os
from cryptography.fernet import Fernet


def get_cipher():
    """Return a Fernet instance from SETTINGS_ENCRYPTION_KEY or None."""
    key = os.environ.get('SETTINGS_ENCRYPTION_KEY')
    if not key:
        return None
    try:
        return Fernet(key.strip().encode('utf-8') if isinstance(key, str) else key)
    except Exception:
        return None



def encrypt_value(plaintext):
    """Encrypt a plaintext string. Returns ciphertext string or None."""
    cipher = get_cipher()
    if cipher is None:
        return None
    if plaintext is None:
        return None
    try:
        data = plaintext.encode('utf-8') if isinstance(plaintext, str) else str(plaintext).encode('utf-8')
        return cipher.encrypt(data).decode('utf-8')
    except Exception:
        return None


def decrypt_value(ciphertext):
    """Decrypt a ciphertext string. Returns plaintext string or None on any failure."""
    cipher = get_cipher()
    if cipher is None:
        return None
    if ciphertext is None:
        return None
    try:
        data = ciphertext.strip().encode('utf-8') if isinstance(ciphertext, str) else ciphertext
        return cipher.decrypt(data).decode('utf-8')
    except Exception:
        return None
