"""Constantes compartilhadas entre agente e servidor.

Todos os valores aqui podem ser sobrescritos por variaveis de ambiente,
carregadas em agent.config / server.config.
"""

from __future__ import annotations

APP_NAME = "HUB Monitoramento"
SCHEMA_VERSION = 1

#: Versao do produto. Precisa coincidir com VERSION, pyproject.toml e o
#: -Version usado no build (ha teste garantindo isso).
AGENT_VERSION = "1.0.0"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------
# Componentes monitorados
# ---------------------------------------------------------------------
COMPONENT_GATEWAY = "gateway"
COMPONENT_SERVER = "server"
COMPONENT_INTERNET = "internet"
COMPONENT_DNS = "dns"
COMPONENT_SEFAZ_TCP = "sefaz_tcp"
COMPONENT_SEFAZ_TLS = "sefaz_tls"
COMPONENT_TEF = "tef"
COMPONENT_WAN = "wan"

COMPONENTS: tuple[str, ...] = (
    COMPONENT_GATEWAY,
    COMPONENT_SERVER,
    COMPONENT_INTERNET,
    COMPONENT_DNS,
    COMPONENT_SEFAZ_TCP,
    COMPONENT_SEFAZ_TLS,
)

COMPONENT_LABELS: dict[str, str] = {
    COMPONENT_GATEWAY: "Rede local",
    COMPONENT_SERVER: "Servidor da loja",
    COMPONENT_INTERNET: "Conexão à internet",
    COMPONENT_DNS: "Consulta de endereço da SEFAZ",
    COMPONENT_SEFAZ_TCP: "Acesso à SEFAZ",
    COMPONENT_SEFAZ_TLS: "Conexão segura com a SEFAZ",
    COMPONENT_TEF: "TEF / adquirente",
    COMPONENT_WAN: "Link de internet",
}

# ---------------------------------------------------------------------
# Intervalos padrao de coleta (segundos) - plano secao 7
# ---------------------------------------------------------------------
DEFAULT_INTERVALS: dict[str, float] = {
    COMPONENT_GATEWAY: 2.0,
    COMPONENT_SERVER: 2.0,
    COMPONENT_INTERNET: 3.0,
    COMPONENT_DNS: 10.0,
    COMPONENT_SEFAZ_TCP: 5.0,
    COMPONENT_SEFAZ_TLS: 15.0,
    COMPONENT_TEF: 3.0,
}

SNAPSHOT_INTERVAL_SECONDS = 5.0
SENDER_INTERVAL_SECONDS = 5.0
QUEUE_MAX_ROWS = 200_000

# ---------------------------------------------------------------------
# Rede
# ---------------------------------------------------------------------
DEFAULT_GATEWAY_IP = "192.168.0.1"
DEFAULT_SERVER_IP = "192.168.0.110"
DEFAULT_SERVER_URL = "https://192.168.0.110:8000"
DEFAULT_SERVER_PORT = 8000
DEFAULT_HEALTH_HOST = "127.0.0.1"
DEFAULT_HEALTH_PORT = 8010

SEFAZ_HOST = "nfce.fazenda.sp.gov.br"
SEFAZ_PORT = 443

INTERNET_TARGETS: tuple[str, ...] = ("1.1.1.1", "8.8.8.8")
EXTERNAL_DNS_SERVERS: tuple[str, ...] = ("1.1.1.1", "8.8.8.8")

TCP_TIMEOUT_SECONDS = 3.0
PING_TIMEOUT_MS = 1500

# ---------------------------------------------------------------------
# TEF - plano secao 7.7
# Nunca fixar IP: a porta e apenas um sinal inicial.
# ---------------------------------------------------------------------
TEF_CANDIDATE_PORTS: tuple[int, ...] = (55845,)
TEF_LEARNING_MODE = False
TEF_MAX_TRACKED_CONNECTIONS = 50

# ---------------------------------------------------------------------
# Incidentes - plano secao 15
# ---------------------------------------------------------------------
INCIDENT_FAILURE_THRESHOLD = 3
INCIDENT_RECOVERY_THRESHOLD = 3
INCIDENT_AGGREGATION_WINDOW_SECONDS = 30

# ---------------------------------------------------------------------
# Diagnosticos - plano secao 14
# ---------------------------------------------------------------------
DIAG_OK = "OPERACIONAL"
DIAG_LOCAL_NETWORK = "REDE LOCAL"
DIAG_SERVER_COMM = "COMUNICACAO COM SERVIDOR"
DIAG_INTERNET = "INTERNET / OPERADORA"
DIAG_DNS = "DNS"
DIAG_SEFAZ_PATH = "CAMINHO / SEFAZ"
DIAG_TLS = "TLS / CERTIFICADO REMOTO / SEFAZ"
DIAG_TEF = "TEF / ADQUIRENTE / ROTA TEF"
DIAG_AGENT = "AGENTE / PDV"
DIAG_UNKNOWN = "INDETERMINADO"
DIAG_AUTH_AFTER_CONNECTION = "demora após a conexão ou no emissor/SEFAZ"

# ---------------------------------------------------------------------
# WANs da MikroTik - plano secao 12
# ---------------------------------------------------------------------
WAN_MAP: dict[str, str] = {
    "WAN1": "STARLINK",
    "WAN2": "DESKTOP",
    "WAN3": "OQUEI",
}
WAN_SLOTS: tuple[str, ...] = ("WAN1", "WAN2", "WAN3")

# ---------------------------------------------------------------------
# Diversos
# ---------------------------------------------------------------------
TIMEZONE = "America/Sao_Paulo"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
