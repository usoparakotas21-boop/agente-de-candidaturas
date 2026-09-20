"""Encrypt Supabase dump files for off-site storage without publishing raw data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


MAGIC = b"ACBKP001"
WRAP_LABEL = b"agente-candidaturas-backup-v1"
NONCE_SIZE = 12
AES_KEY_SIZE = 32


def generate_keypair(private_path: Path, public_path: Path) -> None:
    private_path = private_path.expanduser().resolve()
    public_path = public_path.expanduser().resolve()
    if private_path == public_path:
        raise ValueError("Os caminhos da chave privada e pública precisam ser diferentes.")
    if private_path.exists() or public_path.exists():
        raise FileExistsError("Uma das chaves já existe; nenhuma foi sobrescrita.")

    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def encrypt_dump(
    source: Path,
    public_key_path: Path,
    *,
    private_key_path: Path | None = None,
    delete_plaintext: bool = True,
) -> Path:
    source = source.expanduser().resolve()
    public_key_path = public_key_path.expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("O dump de origem não existe ou está vazio.")
    if source.suffix == ".enc":
        raise ValueError("O arquivo de origem já parece estar criptografado.")

    public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("A chave pública precisa ser RSA.")

    plaintext = source.read_bytes()
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = secrets.token_bytes(NONCE_SIZE)
    wrapped_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=WRAP_LABEL,
        ),
    )
    if len(wrapped_key) > 0xFFFF:
        raise ValueError("A chave envelopada excede o tamanho permitido.")
    header = MAGIC + struct.pack(">H", len(wrapped_key)) + wrapped_key + nonce
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, header)

    encrypted_path = source.with_name(source.name + ".enc")
    temporary_path = encrypted_path.with_name(encrypted_path.name + ".partial")
    manifest_path = encrypted_path.with_name(encrypted_path.name + ".json")
    temporary_manifest = manifest_path.with_name(manifest_path.name + ".partial")
    if any(path.exists() for path in (encrypted_path, manifest_path, temporary_path, temporary_manifest)):
        raise FileExistsError("O arquivo de backup ou um temporário já existe; nada foi sobrescrito.")
    created_temporary = False
    created_manifest_temporary = False
    try:
        with temporary_path.open("xb") as stream:
            created_temporary = True
            stream.write(header)
            stream.write(ciphertext)
            stream.flush()
            os.fsync(stream.fileno())
        encrypted_bytes = temporary_path.read_bytes()
        if private_key_path:
            recovered = decrypt_bytes(encrypted_bytes, private_key_path)
            if recovered != plaintext:
                raise ValueError("A validação local da criptografia falhou.")

        checksum = hashlib.sha256(encrypted_bytes).hexdigest()
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filename": encrypted_path.name,
            "format": "AES-256-GCM + RSA-OAEP-SHA256",
            "sha256": checksum,
        }
        with temporary_manifest.open("x", encoding="utf-8") as stream:
            created_manifest_temporary = True
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary_path, encrypted_path)
        created_temporary = False
        os.replace(temporary_manifest, manifest_path)
        created_manifest_temporary = False

        if delete_plaintext:
            source.unlink()
            source.with_suffix(source.suffix + ".sha256").unlink(missing_ok=True)
            source.with_suffix(source.suffix + ".json").unlink(missing_ok=True)
        return encrypted_path
    finally:
        if created_temporary:
            temporary_path.unlink(missing_ok=True)
        if created_manifest_temporary:
            temporary_manifest.unlink(missing_ok=True)


def decrypt_bytes(encrypted: bytes, private_key_path: Path) -> bytes:
    minimum_size = len(MAGIC) + 2 + NONCE_SIZE + 16
    if len(encrypted) < minimum_size or not encrypted.startswith(MAGIC):
        raise ValueError("O arquivo não é um backup criptografado reconhecido.")

    offset = len(MAGIC)
    wrapped_size = struct.unpack(">H", encrypted[offset : offset + 2])[0]
    offset += 2
    wrapped_end = offset + wrapped_size
    nonce_end = wrapped_end + NONCE_SIZE
    if wrapped_size == 0 or nonce_end >= len(encrypted):
        raise ValueError("O arquivo criptografado está incompleto.")

    header = encrypted[:nonce_end]
    wrapped_key = encrypted[offset:wrapped_end]
    nonce = encrypted[wrapped_end:nonce_end]
    ciphertext = encrypted[nonce_end:]
    private_key = serialization.load_pem_private_key(
        private_key_path.expanduser().resolve().read_bytes(), password=None
    )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("A chave privada precisa ser RSA.")
    aes_key = private_key.decrypt(
        wrapped_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=WRAP_LABEL,
        ),
    )
    if len(aes_key) != AES_KEY_SIZE:
        raise ValueError("A chave de conteúdo recuperada tem tamanho inválido.")
    return AESGCM(aes_key).decrypt(nonce, ciphertext, header)


def decrypt_dump(encrypted_path: Path, private_key_path: Path, output_path: Path) -> Path:
    encrypted_path = encrypted_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if encrypted_path == output_path or output_path.exists():
        raise FileExistsError("O destino precisa ser novo e diferente do arquivo criptografado.")
    plaintext = decrypt_bytes(encrypted_path.read_bytes(), private_key_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".partial")
    try:
        with temporary_path.open("xb") as stream:
            stream.write(plaintext)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("generate-keypair")
    keygen.add_argument("--private-key", type=Path, required=True)
    keygen.add_argument("--public-key", type=Path, required=True)

    encrypt = commands.add_parser("encrypt")
    encrypt.add_argument("dump", type=Path)
    encrypt.add_argument("--public-key", type=Path, required=True)
    encrypt.add_argument("--private-key", type=Path)
    encrypt.add_argument("--keep-plaintext", action="store_true")

    decrypt = commands.add_parser("decrypt")
    decrypt.add_argument("archive", type=Path)
    decrypt.add_argument("--private-key", type=Path, required=True)
    decrypt.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "generate-keypair":
            generate_keypair(args.private_key, args.public_key)
            print("Par de chaves criado; a chave privada não foi exibida.")
        elif args.command == "encrypt":
            path = encrypt_dump(
                args.dump,
                args.public_key,
                private_key_path=args.private_key,
                delete_plaintext=not args.keep_plaintext,
            )
            print(f"Backup criptografado e autenticado: {path.name}")
        else:
            path = decrypt_dump(args.archive, args.private_key, args.output)
            print(f"Backup descriptografado: {path}")
        return 0
    except (OSError, ValueError, TypeError, InvalidTag) as exc:
        print(f"Falha na operação de criptografia: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
