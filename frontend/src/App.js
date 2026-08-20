import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect, createContext, useContext } from "react";
import { supabase } from "./lib/supabaseClient";
import api from "./lib/api";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Dashboard from "./pages/Dashboard";
import GameSelect from "./pages/GameSelect";
import AdminPage from "./pages/AdminPage";
import { Toaster } from "./components/ui/sonner";
import "./App.css";

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

function App() {
  const [session, setSession] = useState(undefined); // undefined = carregando ainda
  const [selectedGame, setSelectedGame] = useState(
    () => localStorage.getItem("alphasignal_game") || null
  );

  useEffect(() => {
    // Pega a sessão atual (se já estava logado antes, ex: recarregou a página)
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
    });

    // Escuta mudanças de login/logout/refresh de token em tempo real
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  const isAuthenticated = !!session;

  const login = async () => {
    // Chamado toda vez que o login acontece de verdade (nunca em F5, já que
    // aí a sessão continua valenda e login() não é chamado de novo).
    // Sempre força cair na tela de seleção de jogo — mesmo que já tivesse
    // escolhido um antes — assim o cliente sempre vê o aviso da extensão.
    localStorage.removeItem("alphasignal_game");
    setSelectedGame(null);

    // Avisa o backend pra começar uma sessão limpa (zera histórico/placar desse usuário)
    try {
      await api.post(`${process.env.REACT_APP_BACKEND_URL}/api/session/start`);
    } catch (e) {}
  };

  const logout = async () => {
    await supabase.auth.signOut();
    localStorage.removeItem("alphasignal_game");
    setSelectedGame(null);
  };

  const selectGame = (game) => {
    localStorage.setItem("alphasignal_game", game);
    setSelectedGame(game);
  };

  // Enquanto não sabemos se tem sessão ou não, não decide rota nenhuma
  if (session === undefined) {
    return (
      <div className="dark min-h-screen bg-[#14171c] flex items-center justify-center">
        <p className="text-muted-foreground text-sm">Carregando...</p>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout, selectedGame, selectGame }}>
      <div className="dark min-h-screen bg-[#14171c]">
        <BrowserRouter>
          <Routes>
            <Route
              path="/login"
              element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
            />
            <Route
              path="/signup"
              element={isAuthenticated ? <Navigate to="/" replace /> : <Signup />}
            />
            <Route
              path="/select-game"
              element={
                !isAuthenticated
                  ? <Navigate to="/login" replace />
                  : <GameSelect />
              }
            />
            <Route
              path="/"
              element={
                !isAuthenticated
                  ? <Navigate to="/login" replace />
                  : !selectedGame
                  ? <Navigate to="/select-game" replace />
                  : <Dashboard />
              }
            />
            <Route
              path="/admin"
              element={
                !isAuthenticated
                  ? <Navigate to="/login" replace />
                  : <AdminPage />
              }
            />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </div>
    </AuthContext.Provider>
  );
}

export default App;
