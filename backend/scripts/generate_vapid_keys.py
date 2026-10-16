"""Print environment-ready VAPID key values for self-hosted Web Push."""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


key = ec.generate_private_key(ec.SECP256R1())
private_pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode("ascii")
public = key.public_key().public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
print("HOMEDOCTOR_PUSH_VAPID_PRIVATE_KEY=" + private_pem.replace("\n", "\\n"))
print("HOMEDOCTOR_PUSH_VAPID_PUBLIC_KEY=" + b64url(public))
print("HOMEDOCTOR_PUSH_VAPID_SUBJECT=mailto:admin@example.invalid")
