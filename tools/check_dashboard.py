"""Executa as funcoes de renderizacao do painel num DOM falso.

O painel monta a matriz, as WANs, as ocorrencias, os eventos, a
disponibilidade e o grafico. Nada disso tinha rodado.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TELA = ROOT / "server" / "dashboard" / "templates" / "dashboard.html"

NODE_CANDIDATOS = [
    os.environ.get("NODE_BIN", ""),
    shutil.which("node") or "",
    "/Users/wellington/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node",
]

BLOCO = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
JINJA_EXPR = re.compile(r"{{.*?}}", re.S)
JINJA_TAG = re.compile(r"{%.*?%}", re.S)

STUB = """
const __els = new Map();
function __make(id) {
  return {
    id: id, value: '6', textContent: '', innerHTML: '', placeholder: '', type: 'text',
    checked: false, disabled: false, style: {}, dataset: {},
    options: [], selectedIndex: 0,
    classList: { add: () => {}, remove: () => {}, contains: () => false, toggle: () => {} },
    addEventListener: () => {}, appendChild: () => {}, append: () => {}, remove: () => {},
    setAttribute: () => {}, getAttribute: () => null, focus: () => {},
    getContext: () => ({}), scrollIntoView: () => {},
  };
}
global.document = {
  getElementById: (id) => { if (!__els.has(id)) __els.set(id, __make(id)); return __els.get(id); },
  querySelectorAll: () => [],
  querySelector: (sel) => { if (!__els.has(sel)) __els.set(sel, __make(sel)); return __els.get(sel); },
  addEventListener: () => {},
  createElement: (tag) => __make('novo-' + tag),
  body: { appendChild: () => {} },
};
global.window = { addEventListener: () => {}, location: { href: '' } };
global.localStorage = { getItem: () => null, setItem: () => {} };
global.setInterval = () => 0;
global.clearInterval = () => {};
global.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
global.Chart = function (alvo, config) { global.__chart = config; };
"""

ASSERTS = """
let falhas = 0;
const ok = (m) => console.log('  [PASS] ' + m);
const fail = (m, extra) => { falhas += 1; console.log('  [FALHA] ' + m + (extra !== undefined ? ' -> ' + String(extra) : '')); };
const conteudo = (id) => document.getElementById(id).innerHTML || '';

function exercitar(rotulo, alvo, funcao, dados, minimo) {
  try {
    funcao(dados);
  } catch (erro) {
    fail(rotulo + ' lancou', erro && erro.message);
    return;
  }
  const html = conteudo(alvo);
  if (html.length >= (minimo || 10)) ok(rotulo);
  else fail(rotulo + ' nao escreveu no DOM', html.length);
}

const maquinas = [{
  machine_name: 'CAIXA02', online: true, gateway_ok: true, internet_ok: true,
  sefaz_tcp_ok: true, sefaz_tls_ok: true, server_ok: true, tef_ok: true,
  diagnosis: 'Tudo normal', last_seen: new Date().toISOString(),
}];
const wans = [{ wan_name: 'WAN1', provider: 'Vivo', status: 'online', latency_ms: 12,
  active_route: true, timestamp: new Date().toISOString() }];
const ocorrencias = [{ id: 1, type: 'internet', title: 'Internet caiu', open: true,
  started_at: new Date().toISOString(), recovered_at: new Date().toISOString(),
  duration_seconds: 600, unobserved_seconds: 120, affected_machines: ['CAIXA02'],
  diagnosis: 'Falha externa' }];
const eventos = [{ timestamp: new Date().toISOString(), machine_name: 'CAIXA02',
  component: 'internet', ok: false, detail: 'timeout' }];
const medicoes = [
  { timestamp: new Date(Date.now() - 60000).toISOString(), internet_latency_ms: 20, sefaz_latency_ms: 300 },
  { timestamp: new Date().toISOString(), internet_latency_ms: 25, sefaz_latency_ms: 280 },
];

exercitar('matriz de maquinas', '#matrix tbody', renderMatrix, maquinas);
exercitar('lista de WANs', 'wans', renderWans, wans, 5);
exercitar('lista de ocorrencias', 'incidents', renderIncidents, ocorrencias);
if (conteudo('incidents').indexOf('sem observacao') < 0) fail('ocorrencia sem o tempo nao observado');
else ok('ocorrencia mostra tempo sem observacao');
exercitar('lista de eventos', 'events', renderEvents, eventos);
try {
  renderChart(medicoes);
  if (global.__chart && global.__chart.data && global.__chart.data.datasets.length) ok('grafico de latencia com series');
  else fail('grafico sem series');
} catch (erro) { fail('renderChart lancou', erro && erro.message); }

try {
  fillMachineSelect(maquinas);
  ok('seletor de maquinas preenchido');
} catch (erro) { fail('fillMachineSelect lancou', erro && erro.message); }

if (typeof esc === 'function' && esc('<b>') === '&lt;b&gt;') ok('escape de HTML');
else fail('escape de HTML ausente');

process.exit(falhas ? 1 : 0);
"""


def node() -> str | None:
    for candidato in NODE_CANDIDATOS:
        if candidato and Path(candidato).is_file():
            return candidato
    return None


def main() -> int:
    executor = node()
    if executor is None:
        print("node nao encontrado")
        return 1

    texto = TELA.read_text(encoding="utf-8")
    blocos = BLOCO.findall(texto)
    if not blocos:
        print("nenhum bloco de script")
        return 1

    codigo = JINJA_EXPR.sub("null", blocos[0])
    codigo = JINJA_TAG.sub("", codigo)
    programa = STUB + "\n" + codigo + "\n" + ASSERTS
    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / "dashboard.js"
        alvo.write_text(programa, encoding="utf-8")
        resultado = subprocess.run([executor, str(alvo)], capture_output=True, text=True, timeout=60)

    print((resultado.stdout or "").rstrip())
    if resultado.returncode != 0:
        if resultado.stderr:
            print((resultado.stderr or "").strip()[:1800])
        print("\nRESULTADO: o painel falhou ao renderizar")
        return 1
    print("\nRESULTADO: o painel renderizou todas as secoes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
