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

// ID de dispositivo — gerado uma vez e guardado no localStorage (sobrevive
// a F5 E a fechar/abrir o navegador, diferente do token de sessão). Usado
// pelo backend pra saber se esse é um aparelho já conhecido desse login ou
// um novo, aplicando o limite de dispositivos configurado por cliente.
function getDeviceId() {
  let id = localStorage.getItem("alphasignal_device_id");
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
    localStorage.setItem("alphasignal_device_id", id);
  }
  return id;
}

api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
    config.headers["X-Device-Id"] = getDeviceId();
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

// Se o backend recusar por limite de dispositivos (403 específico), desloga
// e manda pra tela de login com uma explicação clara — evita o app ficar
// "travado" silenciosamente tentando chamadas que sempre vão falhar.
let _handlingDeviceLimit = false;
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const detail = error?.response?.data?.detail || "";
    if (error?.response?.status === 403 && detail.includes("dispositivos") && !_handlingDeviceLimit) {
      _handlingDeviceLimit = true;
      console.error("🚫 Limite de dispositivos atingido:", detail);
      await supabase.auth.signOut();
      window.location.href = "/login?device_limit=1";
    }
    return Promise.reject(error);
  }
);

export default api;
