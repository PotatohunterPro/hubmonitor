"""Construcao do contexto TLS usado nas sondagens.

Confia em tres fontes, em ordem:
  1. repositorio de certificados do sistema operacional (store ROOT do
     Windows) - cobre proxies corporativos com CA propria;
  2. bundle do certifi - garante comportamento uniforme em qualquer SO;
  3. raizes oficiais da ICP-Brasil embarcadas em certs/.

O item 3 existe porque a cadeia do nfce.fazenda.sp.gov.br termina na
"Autoridade Certificadora Raiz Brasileira", que NAO esta presente no
certifi nem no bundle do macOS. Sem ela, toda verificacao TLS da SEFAZ
falharia por "unable to get local issuer certificate", gerando um falso
incidente permanente.

Observacao: sao certificados PUBLICOS de AC raiz. O projeto nao
armazena certificado digital do cliente em nenhum momento (plano 4.6).
"""

from __future__ import annotations

import logging
import ssl
import sys
from pathlib import Path

BUNDLE_DIR = "certs"
BUNDLE_NAME = "icp-brasil-roots.pem"

log = logging.getLogger("agent.tlsutil")
_bundle_cache: tuple[str, ...] = ()


def candidate_bundle_paths() -> list[Path]:
    from agent.config import app_base_dir

    paths: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / BUNDLE_DIR / BUNDLE_NAME)
    paths.append(app_base_dir() / BUNDLE_DIR / BUNDLE_NAME)
    paths.append(Path(__file__).resolve().parents[1] / BUNDLE_DIR / BUNDLE_NAME)
    paths.append(Path.cwd() / BUNDLE_DIR / BUNDLE_NAME)
    return paths


def find_bundle() -> Path | None:
    for path in candidate_bundle_paths():
        if path.is_file():
            return path
    return None


def _load_icp_brasil(context: ssl.SSLContext) -> dict:
    global _bundle_cache

    bundle = find_bundle()
    if bundle is None:
        if not _bundle_cache:
            log.warning(
                "Bundle de raizes ICP-Brasil nao encontrado. A verificacao TLS da SEFAZ "
                "pode falhar com 'unable to get local issuer certificate'."
            )
            _bundle_cache = ("ausente",)
        return {"icp_bundle": None}

    try:
        stats = context.load_verify_locations(cafile=str(bundle))
    except (ssl.SSLError, OSError) as exc:
        log.warning("Falha ao carregar %s: %s", bundle, exc)
        return {"icp_bundle": None, "icp_bundle_error": str(exc)}

    loaded = getattr(stats, "cert_store_stats", lambda: {})().get("x509_ca", 0)
    return {"icp_bundle": str(bundle), "icp_roots_loaded": loaded}


def build_ssl_context(verify: bool = True) -> ssl.SSLContext:
    if not verify:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - o store do SO ja cobre o caso normal
        pass
    _load_icp_brasil(context)
    return context


def build_ingest_ssl_context(ca_file: Path | None) -> ssl.SSLContext:
    """Contexto verificado para a API local; aceita CA local dedicada."""
    if ca_file is not None:
        if not ca_file.is_file():
            raise FileNotFoundError(f"Certificado confiavel da API nao encontrado: {ca_file}")
        return ssl.create_default_context(cafile=str(ca_file))
    return ssl.create_default_context()


def trust_info() -> dict:
    """Diagnostico das fontes de confianca (usado no health e no suporte)."""
    context = build_ssl_context(verify=True)
    bundle = find_bundle()
    stats = context.cert_store_stats()
    return {
        "system_store_cas": stats.get("x509_ca"),
        "icp_brasil_bundle": str(bundle) if bundle else None,
        "icp_brasil_present": bundle is not None,
    }
