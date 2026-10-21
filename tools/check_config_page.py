"""Executa o JavaScript da tela de configuracao com DOM e fetch falsos.

Cobre o caminho que o operador percorre logo apos instalar: descobrir o
estado da sessao e carregar as configuracoes no formulario.
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
TELA = ROOT / "server" / "dashboard" / "templates" / "configuration.html"

NODE_CANDIDATOS = [
    os.environ.get("NODE_BIN", ""),
    shutil.which("node") or "",
    "/Users/wellington/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node",
]

BLOCO = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
IDS = re.compile(r"""(?:getElementById\(\s*["']([\w-]+)["']|\$\(\s*["']([\w-]+)["']\s*\))""")

STUB = """
const __handlers = {};
const __els = new Map();
function __make(id) {
  const classes = new Set(id === 'settingsPanel' || id === 'setupPanel' || id === 'loginPanel' ? [] : []);
  const el = {
    id: id, value: '', textContent: '', innerHTML: '', placeholder: '', type: 'text',
    checked: false, disabled: false, options: [], dataset: {},
    style: {},
    classList: {
      add: (c) => classes.add(c), remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c), toggle: (c, on) => { if (on) classes.add(c); else classes.delete(c); },
    },
    addEventListener: (evento, fn) => { __handlers[id + ':' + evento] = fn; },
    appendChild: () => {}, append: () => {}, remove: () => {},
    setAttribute: () => {}, getAttribute: () => null, focus: () => {},
    insertAdjacentHTML: () => {}, scrollIntoView: () => {},
    _classes: classes,
  };
  return el;
}
global.document = {
  getElementById: (id) => { if (!__els.has(id)) __els.set(id, __make(id)); return __els.get(id); },
  querySelectorAll: () => [],
  querySelector: () => null,
  addEventListener: () => {},
  createElement: (tag) => __make('novo-' + tag),
  body: { appendChild: () => {} },
};
global.window = { addEventListener: () => {}, confirm: () => true, location: { reload: () => {} } };
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
global.confirm = () => true;
const ROTAS = {
  '/api/v1/admin/status': { authenticated: true, configured: true, can_setup: false },
  '/api/v1/admin/settings': {
    store_name: 'Mercado Bertolo', local_subnet: '192.168.0.0/24',
    telegram_enabled: true, telegram_chat_id: '-100123', telegram_bot_configured: true,
    mikrotik_enabled: false, mikrotik_host: '', mikrotik_port: 8728, mikrotik_user: '',
    mikrotik_password_configured: false, mikrotik_use_ssl: false,
    fiscal_uf: 'SP', fiscal_document: 'nfce', sefaz_host: 'nfce.fazenda.sp.gov.br',
    sefaz_port: 443, fiscal_confirmed: true,
  },
  '/api/v1/admin/fiscal/options': { ufs: ['SP', 'MG'], documents: ['nfe', 'nfce'] },
  '/api/v1/admin/agent-token': { agent_ingest_token: 'token-de-teste' },
};
global.__requests = [];
global.fetch = async (caminho, opcoes) => {
  let corpo = null;
  if (opcoes && opcoes.body) {
    try { corpo = JSON.parse(opcoes.body); } catch (erro) { corpo = null; }
  }
  global.__requests.push({ path: caminho, method: (opcoes && opcoes.method) || 'GET', body: corpo });
  return {
    ok: true, status: 200,
    json: async () => (ROTAS[caminho] !== undefined ? ROTAS[caminho] : { message: 'ok' }),
    text: async () => '',
  };
};
"""

ASSERTS = """
(async () => {
  let falhas = 0;
  const ok = (m) => console.log('  [PASS] ' + m);
  const fail = (m, extra) => { falhas += 1; console.log('  [FALHA] ' + m + (extra !== undefined ? ' -> ' + extra : '')); };

  try {
    await refreshAccess();
  } catch (erro) {
    fail('refreshAccess lancou', erro && erro.message);
    process.exit(1);
  }

  const el = (id) => document.getElementById(id);
  if (el('storeName').value === 'Mercado Bertolo') ok('nome da loja carregado');
  else fail('nome da loja nao carregado', el('storeName').value);

  if (el('telegramChatId').value === '-100123') ok('grupo do Telegram carregado');
  else fail('grupo do Telegram nao carregado', el('telegramChatId').value);

  if (el('telegramEnabled').checked === true) ok('Telegram marcado como ativo');
  else fail('Telegram nao marcado');

  if (String(el('mikrotikPort').value) === '8728') ok('porta padrao do MikroTik');
  else fail('porta do MikroTik', el('mikrotikPort').value);

  if (el('fiscalUf').value === 'SP') ok('UF fiscal carregada');
  else fail('UF fiscal nao carregada', el('fiscalUf').value);

  if (el('fiscalConfirmed').checked === true) ok('destino fiscal confirmado');
  else fail('destino fiscal nao confirmado');

  if (el('pageStatus').textContent === '') ok('sem mensagem de erro na tela');
  else fail('mensagem inesperada', el('pageStatus').textContent);

  el('telegramToken').value = '123:ABC';
  el('telegramChatId').value = '-100999';
  try {
    await __handlers['saveButton:click']();
    ok('acao de salvar executou');
  } catch (erro) { fail('salvar lancou', erro && erro.message); }

  try {
    await __handlers['testTelegramButton:click']();
    ok('acao de testar Telegram executou');
  } catch (erro) { fail('testar Telegram lancou', erro && erro.message); }

  const salvar = global.__requests.find((r) => r.path === '/api/v1/admin/settings' && r.method === 'PUT');
  const telegram = global.__requests.find((r) => r.path === '/api/v1/admin/telegram/test');
  if (!salvar) fail('PUT de configuracoes nao foi enviado');
  if (!telegram) fail('POST de teste do Telegram nao foi enviado');
  require('fs').writeFileSync(process.argv[2], JSON.stringify({ save: salvar, telegram: telegram }, null, 2));

  ROTAS['/api/v1/admin/status'] = { authenticated: false, configured: false, can_setup: true };
  try {
    await refreshAccess();
    ok('segundo cenario executou');
  } catch (erro) {
    fail('refreshAccess (setup) lancou', erro && erro.message);
  }
  if (el('setupPanel')._classes.has('hidden')) fail('painel de criacao deveria aparecer');
  else ok('painel de criacao exibido');

  process.exit(falhas ? 1 : 0);
})();
"""


def node() -> str | None:
    for candidato in NODE_CANDIDATOS:
        if candidato and Path(candidato).is_file():
            return candidato
    return None


def main() -> int:
    sys.path.insert(0, str(ROOT))
    executor = node()
    if executor is None:
        print("node nao encontrado")
        return 1

    texto = TELA.read_text(encoding="utf-8")
    blocos = BLOCO.findall(texto)
    if not blocos:
        print("nenhum bloco de script")
        return 1

    programa = STUB + "\n" + blocos[0] + "\n" + ASSERTS
    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / "config.js"
        capturado = Path(tmp) / "payloads.json"
        alvo.write_text(programa, encoding="utf-8")
        resultado = subprocess.run(
            [executor, str(alvo), str(capturado)], capture_output=True, text=True, timeout=60
        )
        dados = {}
        if capturado.is_file():
            dados = json.loads(capturado.read_text(encoding="utf-8"))

    print((resultado.stdout or "").rstrip())
    if resultado.returncode != 0:
        if resultado.stderr:
            print((resultado.stderr or "").strip()[:1500])
        print("\nRESULTADO: a tela de configuracao falhou")
        return 1

    # Contrato entre o formulario e a API: os nomes de campo precisam casar.
    from server.api.routes import AdminSettingsPayload, TelegramTestPayload

    enviado = set((dados.get("save") or {}).get("body") or {})
    esperado = set(AdminSettingsPayload.model_fields)
    if enviado != esperado:
        print(f"  [FALHA] campos divergentes: faltando={sorted(esperado - enviado)} sobrando={sorted(enviado - esperado)}")
        return 1
    print(f"  [PASS] formulario envia os {len(esperado)} campos do modelo")

    teste = set((dados.get("telegram") or {}).get("body") or {})
    if teste != set(TelegramTestPayload.model_fields):
        print(f"  [FALHA] teste do Telegram divergente: {sorted(teste)}")
        return 1
    print("  [PASS] teste do Telegram envia os campos do modelo")

    print("\nRESULTADO: a tela de configuracao carregou, salvou e testou")
    return 0


if __name__ == "__main__":
    sys.exit(main())
