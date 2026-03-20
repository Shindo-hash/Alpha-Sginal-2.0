console.log('📡 AlphaSignal Capture - Content Script ativo');

window.addEventListener('message', (event) => {
  if (event.source !== window) return;

  // ============================================================
  // BAC BO
  // ============================================================
  if (event.data.type === 'BACBO_HISTORICO') {
    chrome.runtime.sendMessage({
      type: 'HISTORICO_INICIAL',
      jogo: 'bacbo',
      data: event.data.data,
      timestamp: Date.now()
    }).catch(() => {});
  }

  if (event.data.type === 'BACBO_RESULT') {
    chrome.runtime.sendMessage({
      type: 'NEW_RESULT',
      jogo: 'bacbo',
      data: event.data.data,
      timestamp: Date.now()
    }).catch(() => {});
  }

  // ============================================================
  // FOOTBALL STUDIO
  // ============================================================
  if (event.data.type === 'FS_HISTORICO') {
    chrome.runtime.sendMessage({
      type: 'HISTORICO_INICIAL',
      jogo: 'football_studio',
      data: event.data.data,
      timestamp: Date.now()
    }).catch(() => {});
  }

  if (event.data.type === 'FS_RESULTADO') {
    chrome.runtime.sendMessage({
      type: 'NEW_RESULT',
      jogo: 'football_studio',
      data: event.data.data,
      timestamp: Date.now()
    }).catch(() => {});
  }
});
