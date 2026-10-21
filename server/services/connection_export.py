"""Exportacao do arquivo de conexao da loja (.hubconn).

Executa no servidor. Le a credencial do agente e o certificado publico
da CA local e produz o arquivo que sera importado nos computadores.

Uso:
    python -m server.services.connection_export --path loja.hubconn \
        --public-url https://192.168.0.110:8443
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from server.config import ServerSettings
from shared.connection_file import build_connection, read_connection, write_connection
from shared.timeutil import utc_now


def _default_ca_path(settings: ServerSettings) -> Path:
    if settings.tls_cert_file is not None:
        candidate = Path(settings.tls_cert_file).parent / "server-ca.pem"
        if candidate.is_file():
            return candidate
    return settings.data_dir / "certs" / "server-ca.pem"


def _detect_public_url(settings: ServerSettings, port: int | None = None) -> str:
    from agent.config import detect_local_ip

    ip = detect_local_ip("1.1.1.1") or "127.0.0.1"
    # A porta e exatamente a configurada em SERVER_PORT. Nada de heuristica:
    # o arquivo .hubconn precisa apontar para a porta em que a API escuta.
    return f"https://{ip}:{port or settings.port}"


def _fiscal_target(settings: ServerSettings):
    """Destino fiscal persistido.

    O .env e a fonte de verdade: a pagina de configuracao grava nele sem
    atualizar os.environ do processo. Ler os.environ aqui devolveria o
    destino anterior e o .hubconn sairia sem SEFAZ — exatamente o que o
    guia manda refazer depois de mudar o destino.
    """
    from server.services.config_store import fiscal_target_from_settings

    return fiscal_target_from_settings(settings)


def build_store_connection(settings: ServerSettings, public_url: str | None = None) -> dict:
    token = settings.agent_ingest_token
    if not token or len(token) < 16:
        raise ValueError(
            "A credencial do agente (AGENT_INGEST_TOKEN) nao esta configurada no servidor."
        )

    ca_path = _default_ca_path(settings)
    if not ca_path.is_file():
        raise FileNotFoundError(
            f"Certificado publico da CA nao encontrado em {ca_path}. "
            "Execute o servidor uma vez para provisionar o certificado."
        )

    url = (public_url or os.getenv("PUBLIC_URL") or _detect_public_url(settings)).rstrip("/")
    if not url.startswith("https://"):
        raise ValueError("O endereco publico do servidor precisa usar HTTPS.")

    return build_connection(
        store_name=settings.store_name,
        base_url=url,
        agent_token=token,
        ca_certificate_pem=ca_path.read_text(encoding="utf-8"),
        server_name=os.getenv("COMPUTERNAME") or "SERVIDOR",
        created_at=utc_now(),
        # Destino fiscal da loja: acompanha o arquivo para que todos os
        # caixas testem exatamente o mesmo endereco.
        fiscal=_fiscal_target(settings),
    )


def export_connection(
    settings: ServerSettings, path: Path, public_url: str | None = None
) -> Path:
    data = build_store_connection(settings, public_url)
    return write_connection(Path(path), data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hubmonitor-export-connection",
        description="Gera o arquivo de conexao da loja para os computadores monitorados.",
    )
    parser.add_argument("--path", required=True, help="arquivo .hubconn de saida")
    parser.add_argument(
        "--public-url",
        help="endereco HTTPS que os caixas usarao (ex.: https://192.168.0.110:8443)",
    )
    parser.add_argument("--print", action="store_true", help="mostra o fingerprint gerado")
    args = parser.parse_args(argv)

    settings = ServerSettings.from_env()
    destination = export_connection(settings, Path(args.path), args.public_url)
    data = read_connection(destination)
    print(str(destination))
    if args.print:
        print(json.dumps(
            {
                "store_name": data["store_name"],
                "base_url": data["base_url"],
                "fingerprint": data["fingerprint"],
                "created_at": data["created_at"],
            },
            ensure_ascii=False,
            indent=2,
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
