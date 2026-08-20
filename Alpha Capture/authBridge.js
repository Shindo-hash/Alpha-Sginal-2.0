// authBridge.js — roda SÓ na aba do próprio site AlphaSignal (não no cassino).
// O Supabase guarda a sessão de login no sessionStorage da página (assim o
// login sobrevive a um F5, mas exige login de novo se a aba for fechada de
// verdade — regra pedida pelo Fernando). Esse script lê esse token e manda
// pro background.js da extensão, que passa a usar ele em toda chamada pro
// backend — assim o backend sabe de quem são os dados.

function extractSupabaseToken() {
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i);
    if (key && key.startsWith('sb-') && key.endsWith('-auth-token')) {
      try {
        const parsed = JSON.parse(sessionStorage.getItem(key));
        const token = parsed?.access_token || parsed?.currentSession?.access_token;
        if (token) return token;
      } catch (e) {
        // valor não é JSON válido, ignora e tenta a próxima chave
      }
    }
  }
  return null;
}

function sendTokenToExtension() {
  const token = extractSupabaseToken();
  if (token) {
    // Manda junto de onde veio (localhost = dev, vercel = produção) — o
    // background.js usa isso pra saber automaticamente qual backend chamar,
    // sem precisar trocar URL na mão toda vez que for testar local.
    chrome.runtime.sendMessage({ type: 'AUTH_TOKEN', token, origin: window.location.origin }, () => {
      // void chrome.runtime.lastError — evita warning no console se o
      // background ainda não tiver terminado de subir
      void chrome.runtime.lastError;
    });
  }
}

// Manda assim que a página carrega...
sendTokenToExtension();

// ...e continua reenviando periodicamente (o Supabase renova o token sozinho
// de tempos em tempos, e o background.js precisa sempre ter a versão mais
// recente). 10s em vez de 60s — reduz bem a janela onde a extensão fica
// com token desatualizado achando que expirou.
setInterval(sendTokenToExtension, 10 * 1000);
