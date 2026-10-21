from __future__ import annotations

import json

from agent.queue.local_queue import LocalQueue
from agent.sefaz_authorization_log import SefazAuthorizationLogReader, parse_authorization_record


def sample_record(event_id: str = "auth-1") -> dict:
    return {
        "event_id": event_id,
        "started_at": "2026-10-12T12:00:00Z",
        "completed_at": "2026-10-12T12:00:06Z",
        "duration_ms": 6000,
        "outcome": "autorizada",
        "xml": "NAO-ARMAZENAR",
        "access_key": "CHAVE-NAO-ARMAZENAR",
        "consumer": {"name": "NAO-ARMAZENAR"},
    }


def test_parser_extrai_apenas_os_campos_permitidos():
    parsed = parse_authorization_record(json.dumps(sample_record()), "caixa02")
    assert parsed is not None
    assert parsed.machine_name == "CAIXA02"
    assert parsed.outcome == "authorized"
    assert parsed.model_dump().keys() == {
        "event_id", "machine_name", "started_at", "completed_at", "duration_ms", "outcome"
    }
    assert "NAO-ARMAZENAR" not in parsed.model_dump_json()


def test_parser_rejeita_linha_incompleta_ou_duracao_nao_inteira():
    incomplete = sample_record()
    del incomplete["event_id"]
    assert parse_authorization_record(json.dumps(incomplete), "CAIXA02") is None

    fractional = sample_record()
    fractional["duration_ms"] = 6.5
    assert parse_authorization_record(json.dumps(fractional), "CAIXA02") is None

    access_key_as_id = sample_record("12345678901234567890123456789012345678901234")
    assert parse_authorization_record(json.dumps(access_key_as_id), "CAIXA02") is None


def test_leitor_retorna_somente_registros_novos_e_reutiliza_checkpoint(tmp_path):
    log_path = tmp_path / "issuer.jsonl"
    log_path.write_text("old history with fiscal data\n", encoding="utf-8")
    queue_path = tmp_path / "queue.db"
    queue = LocalQueue(queue_path)
    reader = SefazAuthorizationLogReader(log_path, "CAIXA02", queue)
    assert reader.poll() == 0  # comeca no fim e nao varre o historico anterior

    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample_record()) + "\n")
    assert reader.poll() == 1
    pending = queue.pending("sefaz_authorization", 10)
    assert len(pending) == 1
    assert "NAO-ARMAZENAR" not in pending[0]["payload"]
    queue.close()

    reopened = LocalQueue(queue_path)
    resumed = SefazAuthorizationLogReader(log_path, "CAIXA02", reopened)
    assert resumed.poll() == 0
    assert reopened.stats().authorizations == 1
    reopened.close()


def test_leitor_aguarda_linha_jsonl_completa(tmp_path):
    log_path = tmp_path / "issuer.jsonl"
    log_path.write_bytes(b"")
    queue = LocalQueue(tmp_path / "queue.db")
    reader = SefazAuthorizationLogReader(log_path, "CAIXA02", queue)
    assert reader.poll() == 0
    with log_path.open("ab") as stream:
        stream.write(json.dumps(sample_record()).encode("utf-8"))
    assert reader.poll() == 0
    with log_path.open("ab") as stream:
        stream.write(b"\n")
    assert reader.poll() == 1
    queue.close()


def test_leitor_apos_truncamento_nao_rele_historico_antigo(tmp_path):
    log_path = tmp_path / "issuer.jsonl"
    log_path.write_text("", encoding="utf-8")
    queue = LocalQueue(tmp_path / "queue.db")
    reader = SefazAuthorizationLogReader(log_path, "CAIXA02", queue)
    assert reader.poll() == 0

    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample_record("first")) + "\n")
    assert reader.poll() == 1

    # Uma rotacao por truncamento nao deve importar linhas que ja estavam no arquivo.
    log_path.write_text(json.dumps(sample_record("old-after-truncate")) + "\n", encoding="utf-8")
    assert reader.poll() == 0
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample_record("new-after-truncate")) + "\n")
    assert reader.poll() == 1
    pending = queue.pending("sefaz_authorization", 10)
    assert [json.loads(row["payload"])["event_id"] for row in pending] == [
        "first", "new-after-truncate"
    ]
    queue.close()
