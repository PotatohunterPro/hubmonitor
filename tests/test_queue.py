"""Testes da fila local do agente - plano secao 8."""

from __future__ import annotations

from agent.queue.local_queue import LocalQueue


def test_enfileirar_e_ler(tmp_path):
    queue = LocalQueue(tmp_path / "q.db")
    assert queue.enqueue("measurement", {"machine_name": "CAIXA02", "n": 1}) > 0
    queue.enqueue("event", {"machine_name": "CAIXA02", "kind": "state_change"})

    counts = queue.counts()
    assert counts == {"measurement": 1, "event": 1}

    pending = queue.pending("measurement", limit=10)
    assert len(pending) == 1
    assert pending[0]["payload"].startswith('{"machine_name"')
    queue.close()


def test_falha_incrementa_tentativas_e_mantem_o_item(tmp_path):
    queue = LocalQueue(tmp_path / "q.db")
    queue.enqueue("measurement", {"n": 1})
    ids = [row["id"] for row in queue.pending("measurement", 10)]

    queue.mark_failed(ids, "servidor fora do ar")
    rows = queue.pending("measurement", 10)
    assert len(rows) == 1
    assert rows[0]["attempts"] == 1
    queue.close()


def test_item_so_sai_da_fila_apos_confirmacao(tmp_path):
    queue = LocalQueue(tmp_path / "q.db")
    queue.enqueue("measurement", {"n": 1})
    ids = [row["id"] for row in queue.pending("measurement", 10)]
    queue.delete(ids)
    assert queue.pending("measurement", 10) == []
    queue.close()


def test_fila_sobrevive_a_reabertura(tmp_path):
    path = tmp_path / "q.db"
    queue = LocalQueue(path)
    queue.enqueue("measurement", {"n": 1})
    queue.close()

    reopened = LocalQueue(path)
    assert len(reopened.pending("measurement", 10)) == 1
    assert reopened.stats().measurements == 1
    reopened.close()


def test_trim_limita_o_tamanho_da_fila(tmp_path):
    queue = LocalQueue(tmp_path / "q.db", max_rows=5)
    for index in range(12):
        queue.enqueue("measurement", {"n": index})
    assert queue.trim() > 0
    assert queue.stats().total <= 5
    queue.close()


def test_contadores_persistem(tmp_path):
    queue = LocalQueue(tmp_path / "q.db")
    queue.bump_counter("sent_total", 7)
    assert queue.stats().sent_total == 7
    queue.close()
