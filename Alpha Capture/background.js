console.log('🚀 AlphaSignal Capture - Background ativo');

const BACKEND_URL = 'http://localhost:8001';

let resultadosBacBo = [];
let resultadosFS = [];
let ultimoBacBo = null;
let ultimoFS = null;

// ============================================================
// LISTENER
// ============================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

  if (message.type === 'HISTORICO_INICIAL') {
    handleHistorico(message.jogo, message.data, message.timestamp);
    sendResponse({ success: true });
  }

  if (message.type === 'NEW_RESULT') {
    handleNovoResultado(message.jogo, message.data, message.timestamp);
    sendResponse({ success: true });
  }

  if (message.type === 'GET_RESULTS') {
    sendResponse({
      bacbo: { resultados: resultadosBacBo, ultimo: ultimoBacBo, total: resultadosBacBo.length },
      fs:    { resultados: resultadosFS,    ultimo: ultimoFS,    total: resultadosFS.length }
    });
  }

  return true;
});

// ============================================================
// HISTÓRICO INICIAL
// ============================================================
async function handleHistorico(jogo, historico, timestamp) {
  console.log(`📊 [${jogo}] Histórico: ${historico.length} resultados`);

  const endpoint = jogo === 'bacbo' ? '/api/historico' : '/api/fs/historico';

  // Salva local
  const lista = historico.map(r => ({
    data: r, timestamp,
    processado: new Date(timestamp).toLocaleString('pt-BR')
  }));

  if (jogo === 'bacbo') {
    resultadosBacBo = lista;
    ultimoBacBo = lista[lista.length - 1];
  } else {
    resultadosFS = lista;
    ultimoFS = lista[lista.length - 1];
  }

  salvarStorage();

  // Envia pro backend
  try {
    const response = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resultados: historico })
    });
    if (response.ok) console.log(`✅ [${jogo}] Histórico enviado!`);
    else console.error(`❌ [${jogo}] Backend erro:`, response.status);
  } catch (e) {
    console.warn(`⚠️ [${jogo}] Backend offline, dados salvos localmente.`);
  }
}

// ============================================================
// NOVO RESULTADO
// ============================================================
async function handleNovoResultado(jogo, data, timestamp) {
  const resultado = {
    data, timestamp,
    processado: new Date(timestamp).toLocaleString('pt-BR')
  };

  if (jogo === 'bacbo') {
    resultadosBacBo.push(resultado);
    if (resultadosBacBo.length > 100) resultadosBacBo = resultadosBacBo.slice(-100);
    ultimoBacBo = resultado;
  } else {
    resultadosFS.push(resultado);
    if (resultadosFS.length > 100) resultadosFS = resultadosFS.slice(-100);
    ultimoFS = resultado;
  }

  salvarStorage();
  console.log(`🎯 [${jogo}] Novo resultado:`, data);

  // Envia pro backend
  const endpoint = jogo === 'bacbo' ? '/api/resultado' : '/api/fs/resultado';

  try {
    const response = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (response.ok) console.log(`✅ [${jogo}] Resultado enviado!`);
  } catch (e) {
    console.warn(`⚠️ [${jogo}] Backend offline.`);
  }
}

// ============================================================
// STORAGE
// ============================================================
function salvarStorage() {
  chrome.storage.local.set({
    bacbo_resultados: resultadosBacBo,
    bacbo_ultimo: ultimoBacBo,
    fs_resultados: resultadosFS,
    fs_ultimo: ultimoFS
  });
}

// Carrega ao iniciar
chrome.storage.local.get(['bacbo_resultados', 'bacbo_ultimo', 'fs_resultados', 'fs_ultimo'], (data) => {
  if (data.bacbo_resultados) resultadosBacBo = data.bacbo_resultados;
  if (data.bacbo_ultimo) ultimoBacBo = data.bacbo_ultimo;
  if (data.fs_resultados) resultadosFS = data.fs_resultados;
  if (data.fs_ultimo) ultimoFS = data.fs_ultimo;
  console.log(`📂 Carregado: BacBo(${resultadosBacBo.length}) | FS(${resultadosFS.length})`);
});
