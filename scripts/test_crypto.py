"""Exercise the native cryptography module, including rejection of tampering."""

import sys

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def rejects(exception, operation):
    try:
        operation()
    except exception:
        return
    raise AssertionError(f"Tampering must raise {exception.__name__}")


def main():
    # NIST SP 800-38D: zero 128-bit key, 96-bit IV and empty plaintext/AAD.
    aes = AESGCM(bytes(16))
    tag = bytes.fromhex("58e2fccefa7e3061367f1d57a4e7455a")
    assert aes.encrypt(bytes(12), b"", None) == tag
    assert aes.decrypt(bytes(12), tag, None) == b""
    rejects(InvalidTag, lambda: aes.decrypt(bytes(12), bytes(16), None))

    fernet = Fernet(Fernet.generate_key())
    token = fernet.encrypt(b"synthetic-wheel-test")
    assert fernet.decrypt(token) == b"synthetic-wheel-test"
    rejects(InvalidToken, lambda: fernet.decrypt(b"invalid"))

    for key, signer in (
        (ed25519.Ed25519PrivateKey.generate(), ()),
        (
            rsa.generate_private_key(public_exponent=65537, key_size=2048),
            (padding.PKCS1v15(), hashes.SHA256()),
        ),
    ):
        signature = key.sign(b"synthetic-wheel-test", *signer)
        public = serialization.load_pem_public_key(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        public.verify(signature, b"synthetic-wheel-test", *signer)
        rejects(
            InvalidSignature, lambda: public.verify(signature, b"tampered", *signer)
        )

    if sys.platform == "darwin":
        import subprocess

        from cryptography.hazmat.bindings import _rust

        result = subprocess.run(
            ["/usr/bin/otool", "-L", _rust.__file__],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        links = [
            line.strip().split(" ", 1)[0] for line in result.stdout.splitlines()[1:]
        ]
        # Mach-O dylibs can list their own LC_ID_DYLIB before dependencies.
        identity = "@rpath/cryptography.hazmat.bindings._rust.abi3.so"
        links = [link for link in links if link != identity]
        assert links and all(
            link.startswith(("/usr/lib/", "/System/Library/")) for link in links
        ), "Native wheel must not depend on Homebrew or other external dylibs"
    print("Native cryptography vector, round-trip, tamper and linkage checks passed.")


if __name__ == "__main__":
    main()
