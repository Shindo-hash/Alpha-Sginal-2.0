import { createClient } from "@supabase/supabase-js";

// Mesmo projeto Supabase usado no MetaEdge — login único pros dois apps.
// URL e a chave "anon" são públicas por design, seguras de ficar no frontend.
// Dá pra sobrescrever via .env (REACT_APP_SUPABASE_URL / REACT_APP_SUPABASE_ANON_KEY)
// se um dia trocar de projeto, mas já vem funcionando com os valores atuais.
const SUPABASE_URL = process.env.REACT_APP_SUPABASE_URL || "https://mcdxxombghjfyfofncik.supabase.co";
const SUPABASE_ANON_KEY = process.env.REACT_APP_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1jZHh4b21iZ2hqZnlmb2ZuY2lrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAzNzgwNTYsImV4cCI6MjA5NTk1NDA1Nn0.IIDNLuWKh_gTeEvsh7LpJvC9krzvBLrE4ADvgprbOXo";

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // eslint-disable-next-line no-console
  console.error(
    "REACT_APP_SUPABASE_URL / REACT_APP_SUPABASE_ANON_KEY não configurados no .env do frontend."
  );
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    // sessionStorage em vez de localStorage: sobrevive a F5 (mesma aba), mas
    // some quando a aba é fechada de verdade — obriga login de novo nesse caso.
    storage: window.sessionStorage,
  },
});
