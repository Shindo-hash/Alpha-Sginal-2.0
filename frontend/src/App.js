import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, createContext, useContext } from "react";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import GameSelect from "./pages/GameSelect";
import { Toaster } from "./components/ui/sonner";
import "./App.css";

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

function App() {
  const SESSION_TTL = 30 * 60 * 1000;

  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    const auth = localStorage.getItem("alphasignal_auth");
    const ts = parseInt(localStorage.getItem("alphasignal_auth_ts") || "0");
    if (auth === "true" && Date.now() - ts < SESSION_TTL) return true;
    localStorage.removeItem("alphasignal_auth");
    localStorage.removeItem("alphasignal_auth_ts");
    return false;
  });

  const [selectedGame, setSelectedGame] = useState(
    () => localStorage.getItem("alphasignal_game") || null
  );

  const login = () => {
    localStorage.setItem("alphasignal_auth", "true");
    localStorage.setItem("alphasignal_auth_ts", Date.now().toString());
    setIsAuthenticated(true);
  };

  const logout = () => {
    localStorage.removeItem("alphasignal_auth");
    localStorage.removeItem("alphasignal_auth_ts");
    localStorage.removeItem("alphasignal_game");
    setIsAuthenticated(false);
    setSelectedGame(null);
  };

  const selectGame = (game) => {
    localStorage.setItem("alphasignal_game", game);
    setSelectedGame(game);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout, selectedGame, selectGame }}>
      <div className="dark min-h-screen bg-[#050505]">
        <BrowserRouter>
          <Routes>
            <Route
              path="/login"
              element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
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
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </div>
    </AuthContext.Provider>
  );
}

export default App;
