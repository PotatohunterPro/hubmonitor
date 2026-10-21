"""Arquivo de conexão da loja (extensão .hubconn).

Gerado pelo servidor e importado nos computadores monitorados. Contém
somente o necessário para o caixa falar com a API:

  - endereço HTTPS da loja;
  - certificado público da CA local (para validar o servidor);
  - credencial do agente.

NÃO contém, em nenhuma hipótese: token do Telegram, senha
administrativa, chave privada do servidor ou qualquer outro segredo que
não seja a credencial do agente.

O arquivo é sensível: a gravação é atômica e restrita ao proprietário.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.fiscal import FiscalConfigError, FiscalTarget, validate_target
from shared.timeutil import parse_iso, to_iso, utc_now

CONNECTION_SUFFIX = ".hubconn"
CONNECTION_VERSION = 1
MIN_TOKEN_LENGTH = 16

#: Marcadores que nunca podem aparecer em um arquivo de conexão.
FORBIDDEN_MARKERS = (
    "PRIVATE KEY",
    "TELEGRAM_BOT_TOKEN",
    "ADMIN_PASSWORD",
    "TELEGRAM_CHAT_ID",
)


class ConnectionFileError(ValueError):
    """Arquivo de conexão inválido, adulterado ou com conteúdo proibido."""


def _looks_like_pem_certificate(value: str) -> bool:
    return "BEGIN CERTIFICATE" in value and "END CERTIFICATE" in value


def compute_fingerprint(payload: dict[str, Any]) -> str:
    """SHA-256 do conteúdo canônico, excluindo o próprio fingerprint."""
    body = {key: value for key, value in payload.items() if key != "fingerprint"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_connection(
    *,
    store_name: str,
    base_url: str,
    agent_token: str,
    ca_certificate_pem: str,
    server_name: str,
    created_at: datetime | None = None,
    fiscal: FiscalTarget | dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": CONNECTION_VERSION,
        "kind": "hubmonitor-store-connection",
        "store_name": (store_name or "").strip(),
        "server_name": (server_name or "").strip(),
        "base_url": (base_url or "").strip().rstrip("/"),
        "agent_token": (agent_token or "").strip(),
        "ca_certificate_pem": ca_certificate_pem,
        "created_at": to_iso(created_at or utc_now()),
    }
    if fiscal is not None:
        # O destino fiscal e da loja: todos os caixas testam o mesmo endereco.
        if isinstance(fiscal, FiscalTarget):
            payload["fiscal"] = fiscal.to_dict()
        else:
            payload["fiscal"] = validate_target(**fiscal).to_dict()
    payload["fingerprint"] = compute_fingerprint(payload)
    return validate_connection(payload)


def validate_connection(data: Any, *, allow_http: bool = False) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ConnectionFileError("O arquivo de conexão não é um objeto JSON.")

    raw = json.dumps(data, ensure_ascii=False)
    for marker in FORBIDDEN_MARKERS:
        if marker in raw:
            raise ConnectionFileError(
                "O arquivo contém informação que nunca deve ser compartilhada: " + marker
            )

    version = data.get("version")
    if version != CONNECTION_VERSION:
        raise ConnectionFileError(f"Versão de arquivo não suportada: {version!r}")

    base_url = str(data.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ConnectionFileError("Endereço do servidor ausente.")
    if not base_url.startswith("https://") and not (
        allow_http and base_url.startswith("http://")
    ):
        raise ConnectionFileError("O endereço do servidor precisa usar HTTPS.")

    token = str(data.get("agent_token") or "").strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise ConnectionFileError("Credencial do agente ausente ou curta demais.")

    certificate = str(data.get("ca_certificate_pem") or "")
    if not _looks_like_pem_certificate(certificate):
        raise ConnectionFileError("Certificado público do servidor ausente ou inválido.")

    expected = compute_fingerprint(data)
    informed = str(data.get("fingerprint") or "")
    if not informed:
        raise ConnectionFileError("Fingerprint ausente: arquivo possivelmente incompleto.")
    if informed != expected:
        raise ConnectionFileError("Fingerprint não confere: o arquivo foi alterado.")

    if parse_iso(str(data.get("created_at") or "")) is None:
        raise ConnectionFileError("Data de criação inválida.")

    normalized = dict(data)
    normalized["base_url"] = base_url
    normalized["agent_token"] = token
    normalized["ca_certificate_pem"] = certificate

    fiscal = data.get("fiscal")
    if fiscal is not None:
        if not isinstance(fiscal, dict):
            raise ConnectionFileError("Bloco fiscal do arquivo de conexao invalido.")
        try:
            normalized["fiscal"] = validate_target(
                uf=fiscal.get("uf"),
                document=fiscal.get("document"),
                host=fiscal.get("host"),
                port=fiscal.get("port", 443),
                confirmed=bool(fiscal.get("confirmed", False)),
            ).to_dict()
        except FiscalConfigError as exc:
            raise ConnectionFileError("Destino fiscal invalido: " + str(exc)) from exc

    return normalized


def read_connection(path: Path, *, allow_http: bool = False) -> dict[str, Any]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConnectionFileError(f"Não foi possível ler {path.name}: {exc}") from exc
    for marker in FORBIDDEN_MARKERS:
        if marker in text:
            raise ConnectionFileError(
                "O arquivo contém informação que nunca deve ser compartilhada: " + marker
            )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConnectionFileError("O arquivo de conexão não é um JSON válido.") from exc
    return validate_connection(data, allow_http=allow_http)


def write_connection(path: Path, data: dict[str, Any]) -> Path:
    """Grava de forma atômica e com permissão restrita ao proprietário."""
    path = Path(path)
    payload = validate_connection(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def fingerprint_short(data: dict[str, Any], length: int = 12) -> str:
    return str(data.get("fingerprint") or "")[:length]
