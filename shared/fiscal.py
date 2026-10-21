"""Destino fiscal da loja: UF, tipo de documento e endereco.

Decisao de projeto: **nao inventamos** enderecos de SEFAZ. O operador
escolhe a UF e o documento (NF-e ou NFC-e) e informa o endereco que a
loja efetivamente usa; o sistema valida o formato e, quando solicitado,
testa a resolucao DNS e a conexao TCP antes de salvar.

Apenas Sao Paulo tem sugestao embutida, porque e o unico endereco que
podemos afirmar. Para as demais UFs o campo e obrigatorio: chutar um
endereco geraria alarme falso, exatamente o que o produto deve evitar.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any, Mapping

UF_LIST: tuple[str, ...] = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
)

DOCUMENTS: dict[str, str] = {
    "nfe": "NF-e (modelo 55)",
    "nfce": "NFC-e (modelo 65)",
}

DEFAULT_PORT = 443
MAX_HOST_LENGTH = 253

#: Sugestoes apenas onde o endereco e documentado e estavel.
SUGGESTIONS: dict[tuple[str, str], str] = {
    ("SP", "nfce"): "nfce.fazenda.sp.gov.br",
    ("SP", "nfe"): "nfe.fazenda.sp.gov.br",
}


class FiscalConfigError(ValueError):
    """Configuracao fiscal invalida."""


@dataclass(frozen=True, slots=True)
class FiscalTarget:
    uf: str
    document: str
    host: str
    port: int = DEFAULT_PORT
    confirmed: bool = False

    @property
    def label(self) -> str:
        return f"{self.uf} - {DOCUMENTS.get(self.document, self.document)}"

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uf": self.uf,
            "document": self.document,
            "host": self.host,
            "port": self.port,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FiscalTarget:
        return validate_target(
            uf=data.get("uf"),
            document=data.get("document"),
            host=data.get("host"),
            port=data.get("port", DEFAULT_PORT),
            confirmed=bool(data.get("confirmed", False)),
        )


def normalize_uf(value: Any) -> str:
    uf = str(value or "").strip().upper()
    if uf not in UF_LIST:
        raise FiscalConfigError("UF invalida. Use a sigla de duas letras, como SP.")
    return uf


def normalize_document(value: Any) -> str:
    document = str(value or "").strip().lower()
    if document not in DOCUMENTS:
        raise FiscalConfigError("Tipo de documento invalido: use nfe ou nfce.")
    return document


def normalize_host(value: Any) -> str:
    host = str(value or "").strip().lower().rstrip(".")
    if not host:
        raise FiscalConfigError("Informe o endereco da SEFAZ da loja.")
    if len(host) > MAX_HOST_LENGTH:
        raise FiscalConfigError("Endereco da SEFAZ longo demais.")
    if "://" in host or "/" in host or " " in host:
        raise FiscalConfigError("Informe apenas o nome do servidor, sem http:// nem caminho.")
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise FiscalConfigError("O endereco da SEFAZ nao pode ser um endereco local.")
    if not any(character.isalpha() for character in host):
        raise FiscalConfigError("O endereco da SEFAZ deve ser um nome, nao um IP.")
    return host


def normalize_port(value: Any) -> int:
    try:
        port = int(value if value not in (None, "") else DEFAULT_PORT)
    except (TypeError, ValueError) as exc:
        raise FiscalConfigError("Porta da SEFAZ invalida.") from exc
    if not 1 <= port <= 65535:
        raise FiscalConfigError("Porta da SEFAZ fora da faixa valida.")
    return port


def validate_target(
    *,
    uf: Any,
    document: Any,
    host: Any,
    port: Any = DEFAULT_PORT,
    confirmed: bool = False,
) -> FiscalTarget:
    return FiscalTarget(
        uf=normalize_uf(uf),
        document=normalize_document(document),
        host=normalize_host(host),
        port=normalize_port(port),
        confirmed=bool(confirmed),
    )


def suggest_host(uf: str, document: str) -> str | None:
    try:
        return SUGGESTIONS.get((normalize_uf(uf), normalize_document(document)))
    except FiscalConfigError:
        return None


def options() -> list[dict[str, Any]]:
    """Lista para a interface de configuracao."""
    return [
        {
            "uf": uf,
            "documents": [
                {
                    "value": key,
                    "label": label,
                    "suggested_host": SUGGESTIONS.get((uf, key)),
                }
                for key, label in DOCUMENTS.items()
            ],
        }
        for uf in UF_LIST
    ]


def probe(host: str, port: int = DEFAULT_PORT, timeout: float = 5.0) -> dict[str, Any]:
    """Testa resolucao DNS e conexao TCP. Nao envia nada a SEFAZ."""
    try:
        target = validate_target(uf="SP", document="nfce", host=host, port=port)
    except FiscalConfigError as exc:
        return {"ok": False, "stage": "validacao", "detail": str(exc), "ip": None}

    try:
        ip = socket.gethostbyname(target.host)
    except OSError as exc:
        return {
            "ok": False,
            "stage": "dns",
            "detail": f"Nao foi possivel resolver {target.host}: {exc}",
            "ip": None,
        }

    import time

    started = time.perf_counter()
    try:
        with socket.create_connection((ip, target.port), timeout=timeout):
            latency = round((time.perf_counter() - started) * 1000.0, 1)
    except OSError as exc:
        return {
            "ok": False,
            "stage": "tcp",
            "detail": f"Conexao TCP com {ip}:{target.port} falhou: {exc}",
            "ip": ip,
        }

    return {
        "ok": True,
        "stage": "tcp",
        "detail": f"{target.host} ({ip}) respondeu na porta {target.port} em {latency} ms",
        "ip": ip,
        "latency_ms": latency,
    }


def env_values(target: FiscalTarget) -> dict[str, str]:
    """Mapeia a configuracao para as chaves usadas pelo agente."""
    return {
        "FISCAL_UF": target.uf,
        "FISCAL_DOCUMENT": target.document,
        "FISCAL_ENDPOINT_CONFIRMED": "true" if target.confirmed else "false",
        "SEFAZ_HOST": target.host,
        "SEFAZ_PORT": str(target.port),
    }


def from_env(values: Mapping[str, str] | None) -> FiscalTarget | None:
    """Le a configuracao fiscal do .env. Ausente significa nao configurada."""
    if not values:
        return None
    uf = (values.get("FISCAL_UF") or "").strip()
    host = (values.get("SEFAZ_HOST") or "").strip()
    if not uf or not host:
        return None
    try:
        return validate_target(
            uf=uf,
            document=values.get("FISCAL_DOCUMENT") or "nfce",
            host=host,
            port=values.get("SEFAZ_PORT") or DEFAULT_PORT,
            confirmed=str(values.get("FISCAL_ENDPOINT_CONFIRMED", "")).lower()
            in {"1", "true", "yes", "sim"},
        )
    except FiscalConfigError:
        return None
