if (!window.__ALPHA_CAPTURE__) {
  window.__ALPHA_CAPTURE__ = true;

  console.log('🚀 AlphaSignal Capture v1.0 - BacBo + Football Studio');

  const OriginalWebSocket = WebSocket;

  // ============================================================
  // FLAGS DE CONTROLE
  // ============================================================
  let bacboHistoricoEnviado = false;
  let bacboLastSeen = null;

  let fsHistoricoEnviado = false;

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

              // ============================================================
              // BAC BO — detecta por "playerScore"
              // ============================================================
              if (data.includes('playerScore')) {
                const regex = /"winner":"(\w+)","playerScore":(\d+),"bankerScore":(\d+)/g;
                const results = [];
                let match;

                while ((match = regex.exec(data)) !== null) {
                  results.push({
                    winner: match[1],
                    player: parseInt(match[2]),
                    banker: parseInt(match[3])
                  });
                }

                if (results.length > 0) {
                  // Histórico inicial
                  if (!bacboHistoricoEnviado && results.length > 1) {
                    console.log(`🎲 BacBo - Histórico: ${results.length} resultados`);
                    window.postMessage({ type: 'BACBO_HISTORICO', data: results }, '*');
                    bacboHistoricoEnviado = true;
                    bacboLastSeen = `${results[results.length - 1].player}-${results[results.length - 1].banker}`;
                  } else {
                    // Resultado novo
                    const latest = results[results.length - 1];
                    const key = `${latest.player}-${latest.banker}`;
                    if (key !== bacboLastSeen) {
                      bacboLastSeen = key;
                      console.log('🎲 BacBo - Novo resultado:', latest);
                      window.postMessage({ type: 'BACBO_RESULT', data: latest }, '*');
                    }
                  }
                }
              }

              // ============================================================
              // FOOTBALL STUDIO — detecta por JSON com dragontiger
              // ============================================================
              else {
                try {
                  const msg = JSON.parse(data);

                  // Histórico inicial
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

                  // Resultado novo
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
                  // não é JSON válido, ignora
                }
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
