console.log('🚀 AlphaSignal Capture - Background ativo');

// Mapeia de onde veio o login pro backend certo — assim a extensão sabe
// sozinha se deve falar com o backend local (testando) ou o de produção
// (Render), sem precisar trocar URL na mão.
const BACKEND_BY_ORIGIN = {
  'http://localhost:3000': 'http://localhost:8001',
  'https://alpha-sginal-2-0.vercel.app': 'https://alpha-sginal-2-0.onrender.com',
};
let BACKEND_URL = BACKEND_BY_ORIGIN['https://alpha-sginal-2-0.vercel.app']; // padrão: produção

let resultadosBacBo = [];
let resultadosFS = [];
let ultimoBacBo = null;
let ultimoFS = null;
let authToken = null; // token do usuário logado, recebido via authBridge.js
let tokenExpired = false; // true quando o backend recusou o token por expirado (401)
let pendingQueue = []; // resultados que falharam ao enviar — reenviados assim que possível

function decodeJwtPayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch (e) {
    return null;
  }
}

// ============================================================
// LISTENER
// ============================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

  if (message.type === 'AUTH_TOKEN') {
    const isNewToken = message.token !== authToken;
    authToken = message.token;
    tokenExpired = false; // token novo chegou, reseta o alerta de expirado
    if (message.origin && BACKEND_BY_ORIGIN[message.origin]) {
      const novoBackend = BACKEND_BY_ORIGIN[message.origin];
      if (novoBackend !== BACKEND_URL) {
        BACKEND_URL = novoBackend;
        console.log(`🔀 Backend alvo trocado pra: ${BACKEND_URL} (login veio de ${message.origin})`);
      }
    }
    if (isNewToken) {
      const payload = decodeJwtPayload(authToken);
      console.log('🔑 [background.js] Extensão autenticada como:', payload?.email, '| sub:', payload?.sub);
      flushQueue(); // token novo chegou — tenta reenviar o que ficou pendente
    }
    sendResponse({ success: true });
    return;
  }

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
      fs:    { resultados: resultadosFS,    ultimo: ultimoFS,    total: resultadosFS.length },
      logado: !!authToken && !tokenExpired,
      expirado: tokenExpired,
      pendentes: pendingQueue.length
    });
  }

  return true;
});

// Monta os headers da chamada, incluindo o token se já tiver um
function authHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  return headers;
}

// Chama depois de toda requisição pro backend — se vier 401, o token expirou
// (provavelmente porque a aba do AlphaSignal foi fechada e parou de renovar).
// Marca isso pra avisar no popup, em vez de ficar tentando enviar silenciosamente.
function checkAuthExpired(response) {
  if (response.status === 401) {
    tokenExpired = true;
    console.warn('⚠️ Token expirado — reabra e faça login numa aba do AlphaSignal.');
  }
}

// Faz o POST de verdade. Devolve true se deu certo, false se falhou (rede
// caiu, 401, ou qualquer erro) — quem chama decide o que fazer com isso.
async function postToBackend(endpoint, body) {
  if (!authToken) return false;
  try {
    const response = await fetch(`${BACKEND_URL}${endpoint}`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    checkAuthExpired(response);
    return response.ok;
  } catch (e) {
    return false;
  }
}

// Tudo que falhou ao enviar (token vencido, offline, etc) fica guardado aqui
// e é reenviado NA ORDEM assim que um token novo chega ou o backend volta —
// evita perder resultado de verdade por causa de uma janela de login instável.
async function flushQueue() {
  while (pendingQueue.length > 0) {
    const item = pendingQueue[0];
    const ok = await postToBackend(item.endpoint, item.body);
    if (!ok) break; // ainda sem condição de enviar — para aqui, tenta de novo depois
    pendingQueue.shift();
    console.log(`✅ [fila] Reenviado com sucesso: ${item.endpoint}`);
  }
}

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

  // Envia pro backend — se falhar (sem login, offline, token vencido),
  // guarda na fila pra reenviar assim que possível, em vez de descartar.
  const ok = await postToBackend(endpoint, { resultados: historico });
  if (ok) {
    console.log(`✅ [${jogo}] Histórico enviado!`);
  } else {
    pendingQueue.push({ endpoint, body: { resultados: historico }, jogo });
    console.warn(`⚠️ [${jogo}] Não deu pra enviar agora — guardado na fila (${pendingQueue.length} pendente(s)).`);
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

  // Se tiver algo pendente da fila, tenta esvaziar ela ANTES de mandar esse
  // novo, pra manter a ordem cronológica certa.
  if (pendingQueue.length > 0) await flushQueue();

  const endpoint = jogo === 'bacbo' ? '/api/resultado' : '/api/fs/resultado';
  const ok = await postToBackend(endpoint, data);
  if (ok) {
    console.log(`✅ [${jogo}] Resultado enviado!`);
  } else {
    pendingQueue.push({ endpoint, body: data, jogo });
    console.warn(`⚠️ [${jogo}] Não deu pra enviar agora — guardado na fila (${pendingQueue.length} pendente(s)).`);
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
