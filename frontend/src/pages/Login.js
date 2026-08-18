import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../App";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { MessageCircle, Zap } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await axios.post(`${API}/login`, {
        username,
        password,
      });

      if (response.data.success) {
        login();
        toast.success("Login realizado com sucesso!");
        navigate("/");
      }
    } catch (error) {
      toast.error("Credenciais inválidas");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#14171c] p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8 animate-fadeIn">
          <div className="flex items-center justify-center gap-2 mb-4">
            <Zap className="w-10 h-10 text-player" />
            <h1 className="text-4xl md:text-5xl font-heading font-bold tracking-tight text-white">
              Alpha<span className="text-player">Signal</span>
            </h1>
          </div>
          <p className="text-muted-foreground text-sm">
            Sistema de Análise para Cassino Ao Vivo
          </p>
        </div>

        {/* Login Card */}
        <div
          className="glass rounded-lg p-8 animate-fadeIn"
          style={{ animationDelay: "0.1s" }}
          data-testid="login-form"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-white">
                Usuário
              </Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Digite seu usuário"
                className="bg-surface border-white/10 text-white placeholder:text-muted-foreground focus:border-player focus:ring-player"
                data-testid="login-username"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-white">
                Senha
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Digite sua senha"
                className="bg-surface border-white/10 text-white placeholder:text-muted-foreground focus:border-player focus:ring-player"
                data-testid="login-password"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full bg-player text-black hover:bg-player/90 font-semibold transition-all hover:shadow-glow-player"
              data-testid="login-submit"
            >
              {loading ? "Entrando..." : "Entrar"}
            </Button>
          </form>
        </div>

        {/* Footer */}
        <div
          className="text-center mt-8 space-y-4 animate-fadeIn"
          style={{ animationDelay: "0.2s" }}
        >
          <div className="text-muted-foreground text-xs">
            <p>Desenvolvido por Fernando</p>
            <p>Criado em 2026</p>
          </div>

          <a
            href="https://wa.me/5563981228800"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-sm text-green-400 hover:text-green-300 transition-colors"
            data-testid="support-link"
          >
            <MessageCircle className="w-4 h-4" />
            Suporte via WhatsApp
          </a>
        </div>
      </div>
    </div>
  );
}
