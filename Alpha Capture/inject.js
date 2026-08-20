if (!window.__ALPHA_CAPTURE__) {
  window.__ALPHA_CAPTURE__ = true;

  console.log('🚀 AlphaSignal Capture v1.1 - BacBo + Football Studio');

  const OriginalWebSocket = WebSocket;

  // ============================================================
  // FLAGS DE CONTROLE
  // ============================================================
  let bacboHistoricoEnviado = false;
  let bacboLastTail = []; // assinaturas das últimas rodadas já mandadas — usa uma sequência (não só 1) pra achar onde paramos sem se confundir com placar repetido

  let fsHistoricoEnviado = false;

  function bacboSig(r) {
    return `${r.winner}|${r.playerScore}|${r.bankerScore}`;
  }

  // A mensagem "bacbo.road" traz o histórico inteiro (tipo um placar de mesa),
  // sempre no formato {winner, playerScore, bankerScore} — muito mais
  // confiável que tentar achar isso solto no texto cru com regex.
  function processarBacboRoad(historyArr) {
    if (!Array.isArray(historyArr) || historyArr.length === 0) return;

    if (!bacboHistoricoEnviado) {
      const historico = historyArr.map(r => ({ winner: r.winner, player: r.playerScore, banker: r.bankerScore }));
      console.log(`🎲 BacBo - Histórico: ${historico.length} resultados`);
      window.postMessage({ type: 'BACBO_HISTORICO', data: historico }, '*');
      bacboHistoricoEnviado = true;
      bacboLastTail = historyArr.slice(-3).map(bacboSig);
      return;
    }

    // Acha onde está a ÚLTIMA SEQUÊNCIA de rodadas que já mandamos (não só 1
    // resultado — usar uma sequência de 3 evita confundir com um placar
    // repetido isolado, que é bem comum de acontecer por coincidência).
    const tailLen = bacboLastTail.length;
    let idx = -1;
    if (tailLen > 0) {
      for (let i = historyArr.length - 1; i >= tailLen - 1; i--) {
        let bateu = true;
        for (let k = 0; k < tailLen; k++) {
          if (bacboSig(historyArr[i - tailLen + 1 + k]) !== bacboLastTail[k]) { bateu = false; break; }
        }
        if (bateu) { idx = i; break; }
      }
    }

    let novos;
    if (idx === -1) {
      // Não achou a sequência (rolou pra fora da janela, ou algo bem raro
      // aconteceu) — pra não repetir nem perder nada, manda só o último
      // resultado com segurança.
      novos = [historyArr[historyArr.length - 1]];
    } else {
      novos = historyArr.slice(idx + 1);
    }

    if (novos.length === 0) return; // mensagem repetida, nada novo de verdade

    novos.forEach((r) => {
      const resultado = { winner: r.winner, player: r.playerScore, banker: r.bankerScore };
      console.log('🎲 BacBo - Novo resultado:', resultado);
      window.postMessage({ type: 'BACBO_RESULT', data: resultado }, '*');
    });
    bacboLastTail = historyArr.slice(-3).map(bacboSig);
  }

  window.WebSocket = new Proxy(OriginalWebSocket, {
    construct(target, args) {
      const instance = new target(...args);

      const originalAddEventListener = instance.addEventListener;
      instance.addEventListener = function(type, listener, options) {
        if (type === 'message') {
          const wrappedListener = function(event) {
            const data = event.data;

            if (data instanceof ArrayBuffer) {
              return listener.call(this, event);
            }

            if (typeof data === 'string') {
              try {
                const msg = JSON.parse(data);

                // ============================================================
                // BAC BO — "bacbo.road" traz o histórico completo e atualizado
                // ============================================================
                if (msg.type === 'bacbo.road' && msg.args?.history) {
                  processarBacboRoad(msg.args.history);
                }

                // ============================================================
                // FOOTBALL STUDIO — detecta por JSON com dragontiger
                // ============================================================
                if (
                  !fsHistoricoEnviado &&
                  msg.type === 'dragontiger.encodedShoeState' &&
                  msg.args?.history_v2?.length > 1
                ) {
                  const historico = msg.args.history_v2.map(r => ({
                    winner: r.winner === 'Dragon' ? 'Casa' : r.winner === 'Tiger' ? 'Visitante' : 'Empate',
                    casa: r.dragonScore,
                    visitante: r.tigerScore
                  }));

                  console.log(`⚽ FootballStudio - Histórico: ${historico.length} resultados`);
                  window.postMessage({ type: 'FS_HISTORICO', data: historico }, '*');
                  fsHistoricoEnviado = true;
                }

                if (msg.type === 'dragontiger.resolved' && msg.args?.result) {
                  const resultado = {
                    winner: msg.args.result.winner === 'Dragon' ? 'Casa' : msg.args.result.winner === 'Tiger' ? 'Visitante' : 'Empate',
                    casa: msg.args.result.dragonScore,
                    visitante: msg.args.result.tigerScore
                  };

                  console.log('⚽ FootballStudio - Novo resultado:', resultado);
                  window.postMessage({ type: 'FS_RESULTADO', data: resultado }, '*');
                }

              } catch (e) {
                // não é JSON válido, ignora (mensagens de vídeo/binário etc)
              }
            }

            return listener.call(this, event);
          };
          return originalAddEventListener.call(this, type, wrappedListener, options);
        }
        return originalAddEventListener.call(this, type, listener, options);
      };

      return instance;
    }
  });

  // Anti-inatividade
  setTimeout(() => {
    setInterval(() => {
      document.dispatchEvent(new MouseEvent('mousemove', {
        bubbles: true,
        clientX: Math.random() * window.innerWidth,
        clientY: Math.random() * window.innerHeight
      }));
    }, 45000);
  }, 3000);

  console.log('✅ AlphaSignal Capture - Proxy instalado!');
}
