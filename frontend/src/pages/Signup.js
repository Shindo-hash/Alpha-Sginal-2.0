import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Zap, ArrowLeft, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

export default function Signup() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      // Rota pública, sem token — não usa a instância "api" com interceptor de auth
      await axios.post(`${API}/api/signup-request`, { username, password });
      setSent(true);
    } catch (error) {
      const msg = error?.response?.data?.detail || "Erro ao enviar pedido. Tenta de novo.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#14171c] p-4">
        <div className="glass rounded-lg p-8 max-w-md text-center animate-fadeIn">
          <CheckCircle2 className="w-12 h-12 text-green-400 mx-auto mb-4" />
          <h2 className="font-heading font-bold text-lg text-white mb-2">Pedido enviado!</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Seu usuário <span className="text-white font-semibold">{username}</span> foi enviado
            pra aprovação. Avisa no WhatsApp que você já pediu — assim que for liberado, é só logar
            normalmente com o usuário e senha que você escolheu.
          </p>
          <div className="space-y-3">
            <a
              href="https://wa.me/5563981228800"
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full bg-green-500 text-black font-semibold py-2 rounded-lg hover:bg-green-400 transition-colors"
            >
              Avisar no WhatsApp
            </a>
            <Button variant="outline" className="w-full" onClick={() => navigate("/login")}>
              Voltar pro login
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#14171c] p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8 animate-fadeIn">
          <div className="flex items-center justify-center gap-2 mb-4">
            <Zap className="w-10 h-10 text-player" />
            <h1 className="text-4xl md:text-5xl font-heading font-bold tracking-tight text-white">
              Alpha<span className="text-player">Signal</span>
            </h1>
          </div>
          <p className="text-muted-foreground text-sm">Pedir acesso</p>
        </div>

        <div className="glass rounded-lg p-8 animate-fadeIn" data-testid="signup-form">
          <button
            onClick={() => navigate("/login")}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-white mb-4 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            Voltar
          </button>

          <p className="text-sm text-muted-foreground mb-6">
            Escolhe o usuário e senha que você quer usar. Seu pedido fica esperando aprovação —
            você só consegue logar depois que for liberado.
          </p>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="signup-username" className="text-white">Usuário que você quer</Label>
              <Input
                id="signup-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ex: joao123"
                className="bg-surface border-white/10 text-white placeholder:text-muted-foreground focus:border-player focus:ring-player"
                required
                minLength={3}
                data-testid="signup-username-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="signup-password" className="text-white">Senha</Label>
              <Input
                id="signup-password"
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 6 caracteres"
                className="bg-surface border-white/10 text-white placeholder:text-muted-foreground focus:border-player focus:ring-player"
                required
                minLength={6}
                data-testid="signup-password-input"
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full bg-player text-black hover:bg-player/90 font-semibold"
              data-testid="signup-submit"
            >
              {loading ? "Enviando..." : "Pedir cadastro"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
