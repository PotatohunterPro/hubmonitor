"""Executa o render() da janela num DOM falso, via Node.

Checa sintaxe nao e suficiente: o render monta HTML a partir do payload.
Aqui ele roda de verdade com tres cenarios e verificamos o que aparece.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TELA = ROOT / "desktop" / "ui" / "index.html"

NODE_CANDIDATOS = [
    os.environ.get("NODE_BIN", ""),
    shutil.which("node") or "",
    "/Users/wellington/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node",
]

BLOCO = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)

STUB = """
const __els = {};
function __el(id) {
  if (!__els[id]) {
    const style = {};
    __els[id] = {
      id: id, innerHTML: '', textContent: '', style: style,
      addEventListener: function () {}, classList: { add: function () {}, remove: function () {} },
    };
  }
  return __els[id];
}
global.document = {
  getElementById: __el,
  addEventListener: function () {},
  querySelectorAll: function () { return []; },
  createElement: function () { return __el('criado-' + Math.random()); },
};
global.window = { pywebview: null, addEventListener: function () {} };
global.navigator = { clipboard: { writeText: function () { return Promise.resolve(); } } };
"""

ASSERTS = """
let falhas = 0;
function ok(msg) { console.log('  [PASS] ' + msg); }
function fail(msg, extra) { falhas += 1; console.log('  [FALHA] ' + msg + (extra ? ' -> ' + extra : '')); }

const base = {
  store: 'Mercado Bertolo',
  mode: 'server',
  generated_at: new Date().toISOString(),
  last_check: new Date().toISOString(),
  items: [{ label: 'Internet', state: 'ok', detail: '12 ms' }],
  occurrences: [],
  machines: [],
  error: null,
  needs_connection: false,
};

render(Object.assign({}, base, {
  machines: [{ name: 'CAIXA02', state: 'ok', last_seen: null, detail: 'Tudo normal' }],
  occurrences: [{ title: 'Internet caiu', started_at: new Date().toISOString(), recovered_at: null, duration: 90, machines: 'CAIXA02' }],
}));
if (__el('title').textContent !== 'Mercado Bertolo') fail('titulo', __el('title').textContent);
if (__el('subtitle').textContent.indexOf('ltima verifica') < 0) fail('subtitulo sem ultima verificacao', __el('subtitle').textContent);
if (__el('cards').innerHTML.indexOf('Internet') < 0) fail('cartao sem rotulo');
if (__el('cards').innerHTML.indexOf('Normal') < 0) fail('cartao sem estado');
if (__el('machinesPanel').style.display !== '') fail('painel de computadores deveria aparecer', __el('machinesPanel').style.display);
if (__el('machines').innerHTML.indexOf('CAIXA02') < 0) fail('computador nao renderizado');
if (__el('occurrences').innerHTML.indexOf('Internet caiu') < 0) fail('ocorrencia nao renderizada');
if (__el('banner').style.display !== 'none') fail('banner deveria estar oculto');
ok('cenario normal');

render(Object.assign({}, base, { machines: [], occurrences: [], error: 'conexao recusada' }));
if (__el('banner').style.display !== 'block') fail('banner de erro nao apareceu');
if (__el('banner').textContent.indexOf('conexao recusada') < 0) fail('banner sem a causa');
if (__el('machinesPanel').style.display !== 'none') fail('painel deveria esconder sem computadores');
ok('cenario de erro');

render(Object.assign({}, base, { needs_connection: true, items: [{ label: 'Comunicação com o servidor', state: 'unknown', detail: 'Nenhuma conexão importada.' }] }));
if (__el('banner').style.display !== 'block') fail('aviso de conexao ausente');
if (__el('banner').textContent.indexOf('Importar conex') < 0) fail('aviso sem instrucao');
if (__el('cards').innerHTML.indexOf('Sem dados') < 0) fail('estado sem dados nao exibido');
ok('cenario sem conexao');

process.exit(falhas ? 1 : 0);
"""


def node() -> str | None:
    for candidate in NODE_CANDIDATOS:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def main() -> int:
    executor = node()
    if executor is None:
        print("node nao encontrado")
        return 1

    texto = TELA.read_text(encoding="utf-8")
    blocos = BLOCO.findall(texto)
    if not blocos:
        print("nenhum bloco de script encontrado")
        return 1

    programa = STUB + "\n" + blocos[0] + "\n" + ASSERTS
    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / "ui.js"
        alvo.write_text(programa, encoding="utf-8")
        resultado = subprocess.run(
            [executor, str(alvo)], capture_output=True, text=True, timeout=60
        )

    print((resultado.stdout or "").rstrip())
    if resultado.returncode != 0:
        if resultado.stderr:
            print((resultado.stderr or "").strip()[:1200])
        print("\nRESULTADO: a janela falhou ao renderizar")
        return 1
    print("\nRESULTADO: os tres cenarios renderizaram como esperado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
