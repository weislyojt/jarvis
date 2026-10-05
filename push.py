"""Phone notifications (Web Push) so reminders arrive even when the Jarvis app is closed.

Implements VAPID (RFC 8292) and aes128gcm message encryption (RFC 8291) directly,
so the only dependency is the `cryptography` package.
"""
import base64
import json
import os
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

import config
import db

KEY_PATH = config.DATA_DIR / "vapid_private.pem"
_key_lock = threading.Lock()
_key = None


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw_public(key) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def server_key():
    """This server's VAPID key pair, created once and kept in the data folder."""
    global _key
    with _key_lock:
        if _key is None:
            if KEY_PATH.exists():
                _key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
            else:
                _key = ec.generate_private_key(ec.SECP256R1())
                KEY_PATH.write_bytes(_key.private_bytes(serialization.Encoding.PEM,
                                                        serialization.PrivateFormat.PKCS8,
                                                        serialization.NoEncryption()))
        return _key


def public_key() -> str:
    return b64u(_raw_public(server_key()))


def _extract(salt: bytes, ikm: bytes) -> bytes:
    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(ikm)
    return h.finalize()


def _expand(prk: bytes, info: bytes, length: int) -> bytes:
    return HKDFExpand(hashes.SHA256(), length, info).derive(prk)


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    """Encrypt a message for one browser subscription (RFC 8291, single aes128gcm record)."""
    ua_public = b64u_decode(p256dh)
    auth_secret = b64u_decode(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    eph = ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(eph)
    shared = eph.exchange(ec.ECDH(), ua_key)
    ikm = _expand(_extract(auth_secret, shared), b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = os.urandom(16)
    prk = _extract(salt, ikm)
    cek = _expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _expand(prk, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!I", 4096) + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_auth(endpoint: str) -> str:
    parts = urllib.parse.urlparse(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 3600,
              "sub": config.PUSH_CONTACT}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    der = server_key().sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    token = f"{head}.{body}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={public_key()}"


def send_one(sub: dict, message: dict) -> bool:
    body = encrypt(json.dumps(message).encode(), sub["p256dh"], sub["auth"])
    req = urllib.request.Request(sub["endpoint"], data=body, method="POST", headers={
        "Authorization": vapid_auth(sub["endpoint"]),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": "86400",
        "Urgency": "high",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):  # phone unsubscribed or app removed
            db.delete_push_sub(sub["endpoint"])
        else:
            print(f"Push failed ({e.code}): {e.read()[:200]!r}")
        return False
    except Exception as e:
        print("Push failed:", e)
        return False


def notify_all(title: str, text: str, tag: str = "jarvis"):
    """Send to every subscribed device in the background. Returns how many devices there are."""
    subs = db.push_subs()
    message = {"title": title, "body": text, "tag": tag}

    def _run():
        for sub in subs:
            send_one(sub, message)

    if subs:
        threading.Thread(target=_run, daemon=True).start()
    return len(subs)
