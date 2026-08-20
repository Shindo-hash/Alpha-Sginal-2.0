import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, Download, ChevronDown } from "lucide-react";
import { useAuth } from "../App";

export default function GameSelect() {
  const navigate = useNavigate();
  const { selectGame } = useAuth();
  const [showInstructions, setShowInstructions] = useState(false);

  const handleSelect = (game) => {
    selectGame(game);
    navigate("/");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#14171c] p-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-10 animate-fadeIn">
          <div className="flex items-center justify-center gap-2 mb-3">
            <Zap className="w-8 h-8 text-player" />
            <h1 className="text-3xl font-heading font-bold text-white">
              Alpha<span className="text-player">Signal</span>
            </h1>
          </div>
          <p className="text-muted-foreground text-sm">
            Selecione o jogo que você vai jogar hoje
          </p>
        </div>

        {/* Extensão de captura */}
        <div className="glass rounded-xl p-4 mb-6 animate-fadeIn" data-testid="extension-download-card">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-white">Extensão de Captura</p>
              <p className="text-xs text-muted-foreground">Necessária pra capturar os resultados do cassino</p>
            </div>
            <a
              href="/AlphaSignal-Capture.zip"
              download
              className="shrink-0 inline-flex items-center gap-2 bg-player text-black text-xs font-semibold px-3 py-2 rounded-lg hover:bg-player/90 transition-colors"
              data-testid="download-extension-btn"
            >
              <Download className="w-4 h-4" />
              Baixar
            </a>
          </div>

          <button
            onClick={() => setShowInstructions(!showInstructions)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-white mt-3 transition-colors"
          >
            <ChevronDown className={`w-3 h-3 transition-transform ${showInstructions ? "rotate-180" : ""}`} />
            {showInstructions ? "Ocultar instruções" : "Como instalar?"}
          </button>

          {showInstructions && (
            <ol className="text-xs text-muted-foreground mt-3 space-y-1.5 list-decimal list-inside animate-fadeIn">
              <li>Extraia o arquivo .zip baixado (vira uma pasta)</li>
              <li>Abra <span className="text-white font-mono">chrome://extensions</span> no Chrome</li>
              <li>Ative o <span className="text-white">"Modo do desenvolvedor"</span> (canto superior direito)</li>
              <li>Clique em <span className="text-white">"Carregar sem compactação"</span> e selecione a pasta extraída</li>
              <li>Deixe essa aba do AlphaSignal aberta e logada — é ela que autentica a extensão</li>
            </ol>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-fadeIn" style={{ animationDelay: "0.1s" }}>
          <button
            onClick={() => handleSelect("bacbo")}
            className="glass rounded-xl p-6 border border-white/10 hover:border-player/60 transition-all duration-200 text-left group"
          >
            <div className="text-4xl mb-3">🎲</div>
            <h2 className="text-xl font-heading font-bold text-white group-hover:text-player transition-colors">
              Bac Bo
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Player · Banker · Tie</p>
            <p className="text-xs text-player mt-4 font-medium">Estratégias: Adaptativo 🧠 · Número 🎲 · Número PRO 🎲 · Consenso ⚡</p>
          </button>

          <button
            onClick={() => handleSelect("football_studio")}
            className="glass rounded-xl p-6 border border-white/10 hover:border-player/60 transition-all duration-200 text-left group"
          >
            <div className="text-4xl mb-3">⚽</div>
            <h2 className="text-xl font-heading font-bold text-white group-hover:text-player transition-colors">
              Football Studio
            </h2>
            <p className="text-sm text-muted-foreground mt-1">Casa · Visitante · Empate</p>
            <p className="text-xs text-player mt-4 font-medium">Estratégias: Adaptativo 🧠 · Fluxo 🌊 · Alternância 🔁</p>
          </button>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-8">
          Você pode trocar de jogo a qualquer momento pelo dashboard
        </p>
      </div>
    </div>
  );
}
