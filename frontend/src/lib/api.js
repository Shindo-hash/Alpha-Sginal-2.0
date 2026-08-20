import axios from "axios";
import { supabase } from "./supabaseClient";

// Instância única de axios usada em todo o app. Antes de CADA requisição,
// pega a sessão atual do Supabase e anexa o token — assim o backend sabe
// exatamente qual usuário tá fazendo a chamada, sem precisar de login
// caseiro (admin/admin) nem repetir esse código em cada arquivo.
const api = axios.create();

let _lastLoggedToken = null; // evita logar a cada 500ms, só quando o token muda

function decodeJwtPayload(token) {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch (e) {
    return null;
  }
}

api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
    if (token !== _lastLoggedToken) {
      _lastLoggedToken = token;
      const payload = decodeJwtPayload(token);
      console.log("🔑 [api.js] Dashboard autenticado como:", payload?.email, "| sub:", payload?.sub);
    }
  } else {
    console.warn("⚠️ [api.js] Nenhum token de sessão encontrado — chamada vai sem Authorization");
  }
  return config;
});

export default api;
