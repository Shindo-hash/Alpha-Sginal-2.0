const ATIVO_TIMEOUT = 30000; // 30s sem sinal = inativo

function atualizar() {
  chrome.runtime.sendMessage({ type: 'GET_RESULTS' }, (response) => {
    if (!response) return;

    const agora = Date.now();
    const bacbo = response.bacbo;
    const fs = response.fs;

    const bacboAtivo = bacbo.ultimo && (agora - bacbo.ultimo.timestamp) < ATIVO_TIMEOUT;
    const fsAtivo    = fs.ultimo    && (agora - fs.ultimo.timestamp)    < ATIVO_TIMEOUT;

    // ---- BacBo ----
    const bacboCard = document.getElementById('bacbo-card');
    if (bacboAtivo) {
      bacboCard.classList.remove('inativo');
      document.getElementById('bacbo-badge').innerHTML = '🟢 Ativo';
      document.getElementById('bacbo-total').textContent = bacbo.resultados?.length || 0;
      const d = bacbo.ultimo.data;
      const cls = d.winner === 'Player' ? 'visitante' : d.winner === 'Banker' ? 'casa' : 'empate';
      document.getElementById('bacbo-ultimo').innerHTML =
        `<span class="${cls}">${d.winner}</span> — P:${d.player} B:${d.banker}`;
      document.getElementById('bacbo-tempo').textContent = bacbo.ultimo.processado;
      document.getElementById('bacbo-msg').textContent = '';
    } else {
      bacboCard.classList.add('inativo');
      document.getElementById('bacbo-badge').innerHTML = '⚫ Inativo';
      document.getElementById('bacbo-ultimo').textContent = '—';
      document.getElementById('bacbo-tempo').textContent = '—';
      document.getElementById('bacbo-total').textContent = bacbo.resultados?.length || 0;
      document.getElementById('bacbo-msg').textContent = fsAtivo
        ? '⚽ Sinal ativo no Football Studio'
        : 'Abra o jogo para capturar';
    }

    // ---- Football Studio ----
    const fsCard = document.getElementById('fs-card');
    if (fsAtivo) {
      fsCard.classList.remove('inativo');
      document.getElementById('fs-badge').innerHTML = '🟢 Ativo';
      document.getElementById('fs-total').textContent = fs.resultados?.length || 0;
      const d = fs.ultimo.data;
      const cls = d.winner === 'Casa' ? 'casa' : d.winner === 'Visitante' ? 'visitante' : 'empate';
      document.getElementById('fs-ultimo').innerHTML =
        `<span class="${cls}">${d.winner}</span> — C:${d.casa} V:${d.visitante}`;
      document.getElementById('fs-tempo').textContent = fs.ultimo.processado;
      document.getElementById('fs-msg').textContent = '';
    } else {
      fsCard.classList.add('inativo');
      document.getElementById('fs-badge').innerHTML = '⚫ Inativo';
      document.getElementById('fs-ultimo').textContent = '—';
      document.getElementById('fs-tempo').textContent = '—';
      document.getElementById('fs-total').textContent = fs.resultados?.length || 0;
      document.getElementById('fs-msg').textContent = bacboAtivo
        ? '🎲 Sinal ativo no Bac Bo'
        : 'Abra o jogo para capturar';
    }
  });
}

atualizar();
setInterval(atualizar, 2000);
