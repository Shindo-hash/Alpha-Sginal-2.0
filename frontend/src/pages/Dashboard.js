import { useState, useEffect, useCallback, useRef, useMemo, memo } from "react";
import { useAuth } from "../App";
import { useNavigate } from "react-router-dom";
import api from "../lib/api"; // axios com token do Supabase anexado automaticamente
import { toast } from "sonner";
import {
  Zap, LogOut, RotateCcw, ExternalLink, Volume2, VolumeX,
  Activity, TrendingUp, AlertTriangle, Settings, ChevronRight, RefreshCw, CheckCircle2, Download,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Slider } from "../components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ScrollArea } from "../components/ui/scroll-area";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { Input } from "../components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ============================================================
// GAME CONFIG — tudo que muda entre BacBo e Football Studio
// ============================================================
const GAME_CONFIGS = {
  bacbo: {
    name: "Bac Bo",
    emoji: "🎲",
    link: "https://cassino.bet.br/games/evolution/bac-bo",
    linkLabel: "Ir para Bac Bo",
    apiPrefix: "",           // /api/state, /api/historico...
    // Mapeamento winner → aparência
    getOutcome: (winner) => {
      if (winner === "Player") return "player";
      if (winner === "Banker") return "banker";
      return "tie";
    },
    labels: { player: "Player", banker: "Banker", tie: "Tie" },
    shortLabels: { player: "P", banker: "B", tie: "T" },
    // Opções nos gatilhos
    signalOptions: [
      { value: "Player", label: "Player" },
      { value: "Banker", label: "Banker" },
    ],
    // Cor de sinal
    getSignalColor: (signal) => signal === "Player" ? "player" : "banker",
  },
  football_studio: {
    name: "Football Studio",
    emoji: "⚽",
    link: "https://cassino.bet.br/games/evolution/football-studio",
    linkLabel: "Ir para Football Studio",
    apiPrefix: "/fs",        // /api/fs/state, /api/fs/historico...
    getOutcome: (winner) => {
      // Backend normaliza internamente como Player/Banker/Tie
      if (winner === "Player") return "visitante";
      if (winner === "Banker") return "casa";
      return "empate";
    },
    labels: { player: "Visitante", banker: "Casa", tie: "Empate" },
    shortLabels: { player: "V", banker: "C", tie: "E" },
    signalOptions: [
      { value: "Player", label: "Visitante" },
      { value: "Banker", label: "Casa" },
    ],
    getSignalColor: (signal) => signal === "Player" ? "player" : "banker",
  },
};

// Mapeamento outcome → cores visuais
const OUTCOME_STYLES = {
  player:    { bg: "#1a56db", border: "#76a9fa", glow: "#76a9fa", textClass: "neon-player",  borderClass: "border-player/50", glowClass: "glow-player"  },
  banker:    { bg: "#e02424", border: "#f98080", glow: "#f98080", textClass: "neon-banker",  borderClass: "border-banker/50", glowClass: "glow-banker"  },
  tie:       { bg: "#a16207", border: "#eab308", glow: "#eab308", textClass: "neon-tie",     borderClass: "border-tie/50",    glowClass: "glow-tie"     },
  visitante: { bg: "#1a56db", border: "#76a9fa", glow: "#76a9fa", textClass: "neon-player",  borderClass: "border-player/50", glowClass: "glow-player"  },
  casa:      { bg: "#e02424", border: "#f98080", glow: "#f98080", textClass: "neon-banker",  borderClass: "border-banker/50", glowClass: "glow-banker"  },
  empate:    { bg: "#a16207", border: "#eab308", glow: "#eab308", textClass: "neon-tie",     borderClass: "border-tie/50",    glowClass: "glow-tie"     },
};

// Tabela de multiplicador de Empate no Bac Bo, por número do dado vencedor (2-12)
const TIE_MULTIPLIER_TABLE = {
  6: 4, 7: 4, 8: 4,
  5: 6, 9: 6,
  4: 10, 10: 10,
  3: 25, 11: 25,
  2: 88, 12: 88,
};
const getTieMultiplier = (number) => TIE_MULTIPLIER_TABLE[number] ?? null;

// ============================================================
// Estabilização de referência — o backend manda um array/objeto NOVO a
// cada poll (500ms) mesmo quando o conteúdo é idêntico. Sem isso, useMemo
// e React.memo não conseguem economizar nada (comparam por referência).
// Aqui a gente reaproveita a referência antiga quando o conteúdo é igual,
// pra que os componentes memoizados realmente pulem o redesenho.
// ============================================================
function stabilizeArray(ref, newArr, keyFn) {
  const prev = ref.current;
  const arr = newArr || [];
  if (prev && prev.length === arr.length) {
    let same = true;
    for (let i = 0; i < arr.length; i++) {
      if (keyFn(prev[i], i) !== keyFn(arr[i], i)) { same = false; break; }
    }
    if (same) return prev;
  }
  ref.current = arr;
  return arr;
}

function stabilizeObject(ref, newObj) {
  const prev = ref.current;
  const str = JSON.stringify(newObj);
  if (prev && prev.str === str) return prev.value;
  const stable = { str, value: newObj };
  ref.current = stable;
  return newObj;
}

// Sound utilities
const playSound = (type) => {
  const audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const oscillator = audioContext.createOscillator();
  const gainNode = audioContext.createGain();
  oscillator.connect(gainNode);
  gainNode.connect(audioContext.destination);
  switch (type) {
    case "signal":
      oscillator.frequency.setValueAtTime(880, audioContext.currentTime);
      oscillator.type = "sine";
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.3);
      break;
    case "win":
      oscillator.frequency.setValueAtTime(523.25, audioContext.currentTime);
      oscillator.frequency.setValueAtTime(659.25, audioContext.currentTime + 0.1);
      oscillator.frequency.setValueAtTime(783.99, audioContext.currentTime + 0.2);
      oscillator.type = "sine";
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.4);
      break;
    case "notification":
      oscillator.frequency.setValueAtTime(440, audioContext.currentTime);
      oscillator.type = "triangle";
      gainNode.gain.setValueAtTime(0.2, audioContext.currentTime);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.15);
      break;
    case "tie_watch":
      // Som próprio do Empate Seco: dois bipes curtos e agudos (diferente do win normal)
      oscillator.frequency.setValueAtTime(1046.5, audioContext.currentTime);
      oscillator.frequency.setValueAtTime(0, audioContext.currentTime + 0.08);
      oscillator.frequency.setValueAtTime(1046.5, audioContext.currentTime + 0.15);
      oscillator.type = "square";
      gainNode.gain.setValueAtTime(0.15, audioContext.currentTime);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.25);
      break;
    default: break;
  }
};

// ============================================================
// BigRoad
// ============================================================
const BigRoad = memo(({ history, gc }) => {
  const ROWS = 6;
  const isFS = !!gc.apiPrefix;
  const [hoveredValue, setHoveredValue] = useState(null);

  // Só recalcula as bolinhas quando o histórico realmente muda (não a cada poll de 500ms)
  const { cells, grid, lastCellIdx } = useMemo(() => {
    const cells = [];
    history.forEach((result) => {
      const outcome = gc.getOutcome(result.winner);
      const isTie = outcome === "tie" || outcome === "empate";

      if (isTie) {
        if (isFS) {
          cells.push({ winner: result.winner, outcome, value: "E", count: 1 });
        } else {
          const val = result.player ?? 0;
          cells.push({ winner: result.winner, outcome, value: val, count: 1 });
        }
      } else {
        let value;
        if (isFS) {
          value = (outcome === "visitante") ? "V" : "C";
        } else {
          value = (outcome === "player")
            ? (result.player ?? 0)
            : (result.banker ?? 0);
        }
        cells.push({ winner: result.winner, outcome, value, count: 1 });
      }
    });

    const totalCols = Math.ceil(cells.length / ROWS);
    const grid = Array.from({ length: totalCols }, (_, c) => cells.slice(c * ROWS, c * ROWS + ROWS));
    return { cells, grid, lastCellIdx: cells.length - 1 };
  }, [history, isFS, gc]);

  // Highlight de "puxada": passa o mouse num número e ilumina todas as outras
  // vezes que ele saiu (dourado) + o resultado que veio logo depois de cada uma.
  // Também memoizado — só recalcula quando muda o número passado no mouse ou o histórico.
  const { sourceIdx, pulledOutcome, pulledCounts, totalPulls } = useMemo(() => {
    const sourceIdx = new Set();
    const pulledOutcome = {};
    const pulledCounts = { player: 0, banker: 0, tie: 0, empate: 0 };
    if (hoveredValue !== null && !isFS) {
      cells.forEach((c, i) => {
        if (c.value === hoveredValue) {
          sourceIdx.add(i);
          const next = cells[i + 1];
          if (next) {
            pulledOutcome[i + 1] = next.outcome;
            pulledCounts[next.outcome] = (pulledCounts[next.outcome] || 0) + 1;
          }
        }
      });
    }
    const totalPulls = pulledCounts.player + pulledCounts.banker + (pulledCounts.tie || 0) + (pulledCounts.empate || 0);
    return { sourceIdx, pulledOutcome, pulledCounts, totalPulls };
  }, [cells, hoveredValue, isFS]);

  if (history.length === 0) {
    return <p className="text-muted-foreground text-sm py-4">Aguardando resultados da extensão...</p>;
  }

  return (
    <div data-testid="history-grid">
      {!isFS && (
        <p className="text-xs text-muted-foreground mb-2 h-4 truncate">
          {hoveredValue !== null && sourceIdx.size > 0 ? (
            <>
              Número <span className="font-bold text-white">{hoveredValue}</span> apareceu {sourceIdx.size}x
              {totalPulls > 0 && (
                <> → puxou <span className="text-player font-semibold">{pulledCounts.player || 0}x Player</span>,{" "}
                <span className="text-banker font-semibold">{pulledCounts.banker || 0}x Banker</span>
                {(pulledCounts.tie || pulledCounts.empate) ? <>, <span className="text-tie font-semibold">{(pulledCounts.tie || 0) + (pulledCounts.empate || 0)}x Empate</span></> : null}
                </>
              )}
            </>
          ) : (
            <>&nbsp;</>
          )}
        </p>
      )}
      <div className="overflow-x-auto">
      <div className="inline-flex gap-px" style={{ background: "rgba(255,255,255,0.03)", borderRadius: 6, padding: 3 }}>
        {grid.map((col, colIdx) => (
          <div key={colIdx} className="flex flex-col gap-px">
            {Array.from({ length: ROWS }).map((_, rowIdx) => {
              const cell = col[rowIdx];
              const globalIdx = colIdx * ROWS + rowIdx;
              const isLatest = globalIdx === lastCellIdx;
              if (!cell) return <div key={rowIdx} style={{ width: isFS ? 26 : 28, height: 28 }} />;
              const style = OUTCOME_STYLES[cell.outcome] || OUTCOME_STYLES.tie;

              if (isFS) {
                // Football Studio: retângulo igual ao jogo
                return (
                  <div key={rowIdx} style={{ width: 26, height: 28 }}>
                    <div
                      title={cell.winner}
                      style={{
                        width: 25, height: 27,
                        borderRadius: 4,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontWeight: "bold", fontSize: 11, color: "#fff",
                        background: style.bg,
                        border: `1.5px solid ${style.border}`,
                        boxShadow: isLatest ? `0 0 6px ${style.glow}` : "none",
                        letterSpacing: 0,
                      }}
                    >
                      {cell.value}
                    </div>
                  </div>
                );
              }

              // BacBo: círculo com placar
              return (
                <div key={rowIdx} style={{ width: 28, height: 28 }}>
                  <div
                    title={`${cell.winner}: ${cell.value}`}
                    onMouseEnter={() => !isFS && setHoveredValue(cell.value)}
                    onMouseLeave={() => !isFS && setHoveredValue(null)}
                    style={{
                      width: 27, height: 27,
                      borderRadius: "50%",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontWeight: "bold", fontSize: 10, color: "#fff",
                      background: style.bg,
                      border: `1.5px solid ${style.border}`,
                      boxShadow: isLatest ? `0 0 6px ${style.glow}` : "none",
                      cursor: "pointer",
                    }}
                  >
                    {cell.value}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      </div>
    </div>
  );
});

const StatCard = ({ label, value, color = "text-white" }) => (
  <div className="glass rounded p-3" data-testid={`stat-${label.toLowerCase()}`}>
    <p className="text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
    <p className={`text-2xl font-mono font-bold ${color}`}>{value}</p>
  </div>
);

// ============================================================
// SignalCard
// ============================================================
const SignalCard = ({ signal, onFeedback, soundEnabled, galeCount = 0, gc }) => {
  const prevSignalRef = useRef(null);

  useEffect(() => {
    if (signal && signal.id !== prevSignalRef.current && soundEnabled) {
      playSound("signal");
      prevSignalRef.current = signal.id;
    }
  }, [signal, soundEnabled]);

  if (!signal) {
    return (
      <div className="glass rounded-lg p-6 text-center" data-testid="no-signal">
        <Activity className="w-12 h-12 mx-auto text-muted-foreground mb-2" />
        <p className="text-muted-foreground">Aguardando sinal...</p>
      </div>
    );
  }

  const outcome = gc.getOutcome(signal.signal);
  const style = OUTCOME_STYLES[outcome] || OUTCOME_STYLES.banker;
  // Label do sinal
  const signalLabel = signal.signal === "Player" ? gc.labels.player : gc.labels.banker;

  return (
    <div
      className={`glass rounded-lg p-6 border-2 ${style.borderClass} ${style.glowClass} animate-signal-pulse`}
      data-testid="signal-active"
    >
      <div className="text-center mb-4">
        <p className="text-xs text-muted-foreground uppercase mb-2">ENTRADA RECOMENDADA</p>
        {signal.priority && (
          <div className="inline-block bg-player/20 border border-player/50 text-player text-xs font-bold px-2 py-1 rounded mb-2 animate-pulse">
            ⚡ SINAL FORTE — 3/3 concordam
          </div>
        )}
        {galeCount > 0 && (
          <div className="inline-block bg-yellow-500/20 border border-yellow-500/50 text-yellow-400 text-xs font-bold px-2 py-1 rounded mb-2">
            ⚠️ G{galeCount} — GALE
          </div>
        )}
        <h2 className={`text-4xl font-heading font-bold uppercase ${style.textClass}`}>
          {signalLabel}
        </h2>
        <p className="text-2xl font-mono mt-2">{signal.probability}%</p>
      </div>

      {signal.tie_warning && (
        <div className="bg-tie/10 border border-tie/30 rounded p-2 mb-4 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-tie" />
          <span className="text-tie text-sm">Cobrir {gc.labels.tie} recomendado</span>
        </div>
      )}

      <div className="text-xs text-muted-foreground mb-4">
        <p className="mb-1">Estratégia: {signal.strategy}</p>
        <p className="mb-1">Fonte: {signal.source}</p>
        <p>{signal.reason}</p>
      </div>
    </div>
  );
};

// ============================================================
// PatternHeatmap
// ============================================================
const PatternHeatmap = memo(({ patterns, triggerResults = [], gc }) => {
  const hasPatterns = patterns && Object.keys(patterns).length > 0;
  const hasTriggers = triggerResults.filter((t) => t.active && t.total > 0).length > 0;

  if (!hasPatterns && !hasTriggers) {
    return <div className="text-center text-muted-foreground py-8">Aguardando dados para análise de padrões...</div>;
  }

  const sortedPatterns = hasPatterns
    ? Object.entries(patterns)
        .sort((a, b) => {
          const diff = Math.max(b[1].Player, b[1].Banker) - Math.max(a[1].Player, a[1].Banker);
          if (diff !== 0) return diff;
          return a[0].localeCompare(b[0]); // desempate estável — mesma ordem sempre, sem "pular"
        })
        .slice(0, 8)
    : [];

  const activeTriggers = triggerResults.filter((t) => t.active);

  // Traduz o padrão ex: "P B B" → "V C C" no FS
  const translatePattern = (pattern) => {
    if (!gc.apiPrefix) return pattern; // BacBo: não mexe
    return pattern.split(" ").map(p => {
      if (p === "P") return gc.shortLabels.player;
      if (p === "B") return gc.shortLabels.banker;
      if (p === "T") return gc.shortLabels.tie;
      return p;
    }).join(" ");
  };

  // Traduz label do padrão: P/B → labels do jogo
  const translatePatternLabel = (label) => {
    if (label === "Player") return gc.labels.player;
    if (label === "Banker") return gc.labels.banker;
    return label;
  };

  return (
    <div className="space-y-2" data-testid="heatmap">
      {activeTriggers.length > 0 && (
        <div className="space-y-2 mb-3">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Seus Gatilhos</p>
          {activeTriggers.map((t) => {
            const isGood = t.rate >= 60;
            const isActiveNow = t.active_now;
            const signalLabel = t.signal === "Player" ? gc.labels.player : gc.labels.banker;
            const signalClass = t.signal === "Player" ? "text-player" : "text-banker";
            return (
              <div key={t.id} className={`glass rounded p-2 border ${isActiveNow ? "border-yellow-400/50" : "border-transparent"}`}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {isActiveNow && <span className="text-yellow-400 text-xs font-bold animate-pulse">⚡</span>}
                    <span className="font-mono text-sm">{t.pattern}</span>
                    <span className="text-muted-foreground text-xs">→</span>
                    <span className={`text-sm font-medium ${signalClass}`}>{signalLabel}</span>
                  </div>
                  <span className={`text-sm font-mono ${isGood ? "text-green-400" : "text-banker"}`}>{t.rate}%</span>
                </div>
                <div className="h-2 bg-surface-highlight rounded overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${t.signal === "Player" ? "bg-player" : "bg-banker"}`}
                    style={{ width: `${t.rate}%` }}
                  />
                </div>
                <span className="text-xs text-muted-foreground">{t.total} ocorrências</span>
              </div>
            );
          })}
        </div>
      )}

      {sortedPatterns.length > 0 && (
        <>
          {activeTriggers.length > 0 && <p className="text-xs text-muted-foreground uppercase tracking-wider">Padrões Detectados</p>}
          {sortedPatterns.map(([pattern, data]) => {
            const maxValue = Math.max(data.Player, data.Banker);
            const winner = data.Player > data.Banker ? "Player" : "Banker";
            const barColor = winner === "Player" ? "bg-player" : "bg-banker";
            const winnerLabel = translatePatternLabel(winner);
            return (
              <div key={pattern} className="glass rounded p-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-sm">{translatePattern(pattern)}</span>
                  <span className={`text-sm ${winner === "Player" ? "text-player" : "text-banker"}`}>
                    {winnerLabel} {maxValue}%
                  </span>
                </div>
                <div className="h-2 bg-surface-highlight rounded overflow-hidden">
                  <div className={`h-full ${barColor} transition-all duration-500`} style={{ width: `${maxValue}%` }} />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>Ocorrências: {data.count}</span>
                  <span>{gc.labels.tie}: {data.Tie}%</span>
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
});

// ============================================================
// StrategySelector
// ============================================================
const StrategySelector = memo(({ active, onChange, strategyStats = {}, autoSelect = false, isFS = false, seqMin, onSeqMinChange }) => {
  const allStrategies = [
    { id: "adaptive",       name: "Adaptativo 🧠",   desc: "Mais sinais",          tooltip: "Analisa o padrão dos últimos 3 resultados." },
    { id: "number",         name: "Número 🎲",       desc: "Sozinho",              tooltip: "Vê o que o número do dado vencedor (2-12) costuma puxar em seguida, no histórico inteiro." },
    { id: "number_pro",     name: "Número PRO 🎲",   desc: "Consenso numérico",    tooltip: "Igual à Número, mas só sinaliza se o Adaptativo concordar com a mesma cor." },
    { id: "number_20",      name: "Número 20 🎯",    desc: "Últimas 20 rodadas",   tooltip: "Igual à Número, mas olha só as últimas 20 rodadas — reage mais rápido a mudança de padrão da mesa." },
    { id: "number_20_pro",  name: "Número 20 PRO 🎯", desc: "20 rodadas + consenso", tooltip: "Igual à Número 20, mas só sinaliza se o Adaptativo concordar com a mesma cor." },
    { id: "consensus",      name: "Consenso ⚡",     desc: "Equilíbrio ideal",     tooltip: "Combina 3 estratégias, sinaliza só quando 2/3 concordam." },
    { id: "sequential",     name: "Fluxo 🌊",        desc: "Sequência + retorno",  tooltip: "Ignora Empates, detecta sequência de N+ iguais e aposta na cor principal voltar após alternância." },
    { id: "alternancia",    name: "Alternância 🔁",  desc: "Ping-pong + Duplas",   tooltip: "Detecta ritmo da mesa: alternância 1x1 (P→B→P) ou duplas 2x2 (PP→BB→PP)." },
  ];

  // BacBo: Adaptativo, Número, Número PRO, Número 20, Número 20 PRO, Consenso
  // FS: Adaptativo, Fluxo, Alternância
  const strategies = isFS
    ? allStrategies.filter(s => ["adaptive", "sequential", "alternancia"].includes(s.id))
    : allStrategies.filter(s => ["adaptive", "number", "number_pro", "number_20", "number_20_pro", "consensus"].includes(s.id));

  const getRate = (id) => {
    const s = strategyStats[id];
    if (!s || s.total === 0) return null;
    return Math.round((s.wins / s.total) * 100);
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2" data-testid="strategy-select">
        {strategies.map((strategy) => {
          const rate = getRate(strategy.id);
          const isActive = active === strategy.id;
          return (
            <button
              key={strategy.id}
              onClick={() => onChange(strategy.id)}
              title={strategy.tooltip}
              className={`glass rounded p-3 text-left transition-all ${isActive ? "border-player glow-player border" : "border border-transparent hover:border-white/20"}`}
              data-testid={`strategy-${strategy.id}`}
            >
              <div className="flex items-center justify-between">
                <p className="font-medium text-sm">{strategy.name}</p>
                {autoSelect && isActive && <span className="text-xs text-player">● auto</span>}
              </div>
              <p className="text-xs text-muted-foreground">{strategy.desc}</p>
              {rate !== null && (
                <p className={`text-xs font-mono mt-1 ${rate >= 60 ? "text-green-400" : rate >= 45 ? "text-yellow-400" : "text-banker"}`}>
                  {rate}% acerto ({strategyStats[strategy.id].total} sinais)
                </p>
              )}
            </button>
          );
        })}
      </div>

      {/* Controle específico por estratégia */}
      {active === "sequential" ? (
        <div className="space-y-2">
          <Label className="text-sm">Mínimo de rodadas na sequência: {seqMin}</Label>
          <Slider
            value={[seqMin]}
            onValueChange={(v) => onSeqMinChange(v[0])}
            min={2} max={5} step={1}
            className="cursor-pointer"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Mais sinais (2)</span>
            <span>Menos sinais (5)</span>
          </div>
        </div>
      ) : (
        <div id="prob-slider-placeholder" />
      )}
    </div>
  );
});

const LogItem = memo(({ log }) => {
  const typeColors = {
    signal: "text-player", result: "text-white", info: "text-muted-foreground",
    config: "text-tie", feedback: "text-green-400", analysis: "text-muted-foreground",
    reset: "text-banker",
  };
  return (
    <div className="flex items-start gap-2 py-1 border-b border-white/5 last:border-0">
      <ChevronRight className={`w-3 h-3 mt-1 ${typeColors[log.type] || "text-white"}`} />
      <p className={`text-xs ${typeColors[log.type] || "text-white"}`}>{log.message}</p>
    </div>
  );
});

// ============================================================
// ResolvedSignalsPanel — cards clicáveis: Direto/G1, e Empate mostra número + multiplicador
// + botão "Ver Histórico Completo" com placar geral e por estratégia
// ============================================================
const ResolvedItemDetail = ({ s }) => {
  const isWin = s.result === "win";
  const isTieKind = s.kind === "tie_watch";
  const isColorTieWin = !isTieKind && isWin && s.actual_winner === "Tie";
  const number = isTieKind ? s.number : (s.player ?? s.banker);
  const multiplier = isTieKind ? s.multiplier : (isColorTieWin ? getTieMultiplier(number) : null);

  return (
    <div className="pb-2 px-1 text-xs text-muted-foreground space-y-1 animate-fadeIn">
      {!isTieKind && <p>{s.gale === 0 ? "Direto (sem Gale)" : "No G1 (entrada repetida)"}</p>}
      {isTieKind && <p>{s.detail}</p>}
      {(isColorTieWin || (isTieKind && isWin)) && (
        <p className="text-tie font-semibold">
          🟡 Empate no número {number} — multiplicador {multiplier ? `${multiplier}x` : "desconhecido"}
        </p>
      )}
      {isTieKind && s.counted_in_stats === false && (
        <p className="text-muted-foreground italic">Não contou no placar (o sinal de cor já contou esse Empate)</p>
      )}
    </div>
  );
};

const ResolvedSignalRow = ({ s, isOpen, onToggle }) => {
  const isWin = s.result === "win";
  const isTieKind = s.kind === "tie_watch";
  const isColorTieWin = !isTieKind && isWin && s.actual_winner === "Tie";
  return (
    <div className="border-b border-white/5 last:border-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between py-2 text-left hover:bg-white/5 rounded px-1 transition-colors"
        data-testid={`resolved-signal-${s.id}`}
      >
        <span className={`text-xs font-semibold flex items-center gap-1.5 flex-wrap ${isWin ? "text-green-400" : "text-banker"}`}>
          {isWin ? "✅ WIN" : "❌ LOSS"} <span className="text-muted-foreground font-normal">({s.strategy})</span>
          {isTieKind && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-tie/20 text-tie">EMPATE SECO</span>
          )}
          {isColorTieWin && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-tie/20 text-tie">EMPATE NO SINAL</span>
          )}
        </span>
        <span className="flex items-center gap-2 shrink-0">
          {s.timestamp && s.timestamp !== "now" && (
            <span className="text-[10px] text-muted-foreground font-mono">{s.timestamp}</span>
          )}
          <ChevronRight className={`w-3 h-3 text-muted-foreground transition-transform ${isOpen ? "rotate-90" : ""}`} />
        </span>
      </button>
      {isOpen && <ResolvedItemDetail s={s} />}
    </div>
  );
};

const FullHistoryModal = ({ signals, stats, strategyStats, sessionStartTime, onClose }) => {
  const [openId, setOpenId] = useState(null);
  const [tab, setTab] = useState("all");
  const winRate = stats.total_signals > 0 ? Math.round((stats.wins / stats.total_signals) * 100) : 0;
  const strategyLabels = { adaptive: "Adaptativo", number: "Número", number_pro: "Número PRO", number_20: "Número 20", number_20_pro: "Número 20 PRO", consensus: "Consenso" };

  const colorSignals = signals.filter(s => s.kind !== "tie_watch");
  const tieSignals = signals.filter(s => s.kind === "tie_watch"); // só wins (backend não loga loss aqui)
  const filtered = tab === "color" ? colorSignals : tab === "tie" ? tieSignals : signals;

  // Como os wins de cor costumam vencer — ajuda a saber se dá pra ir direto ou se costuma precisar de G1
  const colorWins = colorSignals.filter(s => s.result === "win");
  const winsEmpate = colorWins.filter(s => s.actual_winner === "Tie").length;
  const winsDireto = colorWins.filter(s => s.actual_winner !== "Tie" && s.gale === 0).length;
  const winsG1 = colorWins.filter(s => s.actual_winner !== "Tie" && s.gale > 0).length;

  // Tempo de mesa e ritmo de sinais — ajuda a decidir quanto tempo ficar jogando
  const elapsedMin = sessionStartTime ? Math.max(1, Math.round((Date.now() / 1000 - sessionStartTime) / 60)) : null;
  const elapsedLabel = elapsedMin ? (elapsedMin >= 60 ? `${Math.floor(elapsedMin / 60)}h${elapsedMin % 60}min` : `${elapsedMin}min`) : "—";
  const signalsPerMin = elapsedMin ? (signals.length / elapsedMin).toFixed(2) : "—";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 overflow-hidden" style={{ background: "rgba(0,0,0,0.75)" }} onClick={onClose} data-testid="full-history-page">
      {/* Tamanho fixo em telas grandes, responsivo em telas pequenas — nunca estoura a viewport */}
      <div
        className="glass rounded-lg flex flex-col w-full sm:w-[600px] max-w-[600px]"
        style={{ height: "82vh", maxHeight: 820 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabeçalho fixo */}
        <div className="flex items-center justify-between p-4 border-b border-white/10 shrink-0">
          <div>
            <h2 className="font-heading font-bold text-lg flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0" />
              Histórico Completo
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              ⏱ Mesa há {elapsedLabel} · {signalsPerMin} sinais/min
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={onClose} data-testid="close-full-history-btn" className="shrink-0">
            ✕ Fechar
          </Button>
        </div>

        {/* Corpo com scroll único */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden p-4">
          {/* Placar geral */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
            <div className="glass rounded p-2 text-center min-w-0">
              <p className="text-[10px] text-muted-foreground uppercase truncate">Wins</p>
              <p className="text-xl font-mono font-bold text-green-400">{stats.wins}</p>
            </div>
            <div className="glass rounded p-2 text-center min-w-0">
              <p className="text-[10px] text-muted-foreground uppercase truncate">Losses</p>
              <p className="text-xl font-mono font-bold text-banker">{stats.losses}</p>
            </div>
            <div className="glass rounded p-2 text-center min-w-0">
              <p className="text-[10px] text-muted-foreground uppercase truncate">Total</p>
              <p className="text-xl font-mono font-bold text-white">{stats.total_signals}</p>
            </div>
            <div className="glass rounded p-2 text-center min-w-0">
              <p className="text-[10px] text-muted-foreground uppercase truncate">Taxa</p>
              <p className="text-xl font-mono font-bold text-player">{winRate}%</p>
            </div>
          </div>

          {/* Placar por estratégia de cor */}
          <div className="mb-3">
            <p className="text-xs text-muted-foreground mb-1">Por estratégia:</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {Object.entries(strategyStats || {}).map(([key, s]) => {
                const rate = s.total > 0 ? Math.round((s.wins / s.total) * 100) : 0;
                return (
                  <div key={key} className="glass rounded p-1.5 flex items-center justify-between gap-2 min-w-0">
                    <span className="text-xs text-white truncate">{strategyLabels[key] || key}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{s.wins}W/{s.losses}L ({rate}%)</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Como os wins costumam bater — ajuda a saber se dá pra ir direto ou se precisa esperar o G1 */}
          {colorWins.length > 0 && (
            <div className="mb-3">
              <p className="text-xs text-muted-foreground mb-1">Como os wins bateram ({colorWins.length} no total):</p>
              <div className="grid grid-cols-3 gap-1.5">
                <div className="glass rounded p-2 text-center border border-green-500/20 min-w-0">
                  <p className="text-[10px] text-muted-foreground uppercase truncate">Direto</p>
                  <p className="text-lg font-mono font-bold text-green-400">{winsDireto}</p>
                  <p className="text-[10px] text-muted-foreground">{Math.round((winsDireto / colorWins.length) * 100)}%</p>
                </div>
                <div className="glass rounded p-2 text-center border border-yellow-500/20 min-w-0">
                  <p className="text-[10px] text-muted-foreground uppercase truncate">No G1</p>
                  <p className="text-lg font-mono font-bold text-yellow-400">{winsG1}</p>
                  <p className="text-[10px] text-muted-foreground">{Math.round((winsG1 / colorWins.length) * 100)}%</p>
                </div>
                <div className="glass rounded p-2 text-center border border-tie/30 min-w-0">
                  <p className="text-[10px] text-muted-foreground uppercase truncate flex items-center justify-center gap-1">🟡 Empate</p>
                  <p className="text-lg font-mono font-bold text-tie">{winsEmpate}</p>
                  <p className="text-[10px] text-muted-foreground">{Math.round((winsEmpate / colorWins.length) * 100)}%</p>
                </div>
              </div>
            </div>
          )}

          {/* Abas + lista */}
          <Tabs value={tab} onValueChange={setTab} className="w-full">
            <TabsList className="mb-2 flex-wrap h-auto">
              <TabsTrigger value="all">Tudo ({signals.length})</TabsTrigger>
              <TabsTrigger value="color">Cor ({colorSignals.length})</TabsTrigger>
              <TabsTrigger value="tie">Empate Seco ({tieSignals.length})</TabsTrigger>
            </TabsList>
            <TabsContent value={tab}>
              {filtered.length === 0 ? (
                <p className="text-muted-foreground text-sm text-center py-8">Nenhuma entrada aqui ainda...</p>
              ) : (
                [...filtered].reverse().map((s) => (
                  <ResolvedSignalRow key={s.id} s={s} isOpen={openId === s.id} onToggle={() => setOpenId(openId === s.id ? null : s.id)} />
                ))
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
};

const ResolvedSignalsPanel = memo(({ signals = [], onViewMore }) => {
  const [openId, setOpenId] = useState(null);
  if (signals.length === 0) return null;

  const list = [...signals].reverse().slice(0, 3);

  return (
    <div className="glass rounded-lg p-4" data-testid="resolved-signals-panel">
      <h3 className="font-heading font-semibold text-sm mb-3 flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-green-400" />
        Sinais Resolvidos
      </h3>
      <div className="space-y-1">
        {list.map((s) => (
          <ResolvedSignalRow key={s.id} s={s} isOpen={openId === s.id} onToggle={() => setOpenId(openId === s.id ? null : s.id)} />
        ))}
      </div>
      {signals.length > 3 && (
        <button
          onClick={onViewMore}
          className="w-full text-center text-xs text-player hover:underline mt-2 pt-2 border-t border-white/5"
          data-testid="ver-mais-resolvidos"
        >
          Veja mais ({signals.length - 3} restantes) →
        </button>
      )}
    </div>
  );
});

// ============================================================
// UserTriggers
// ============================================================
const UserTriggers = ({ triggerResults = [], onSave, gc }) => {
  const storageKey = `alphasignal_triggers_${gc.apiPrefix || "bacbo"}`;
  const [triggers, setTriggers] = useState(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? JSON.parse(saved) : [];
  });
  const [newPattern, setNewPattern] = useState("");
  const [newSignal, setNewSignal] = useState("Player");

  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.length > 0) onSave && onSave(parsed);
      } catch (e) {}
    }
  }, []); // eslint-disable-line

  const enriched = triggers.map((t) => {
    const result = triggerResults.find((r) => String(r.id) === String(t.id));
    return result ? { ...t, ...result } : t;
  });

  const syncBackend = (list) => {
    localStorage.setItem(storageKey, JSON.stringify(list));
    onSave && onSave(list);
  };

  const addTrigger = () => {
    if (!newPattern.trim()) return;
    const trigger = { id: Date.now(), pattern: newPattern.toUpperCase().trim(), signal: newSignal, active: true };
    const next = [...triggers, trigger];
    setTriggers(next);
    syncBackend(next);
    setNewPattern("");
    toast.success("Gatilho adicionado!");
  };

  const toggleTrigger = (id) => {
    const next = triggers.map((t) => (t.id === id ? { ...t, active: !t.active } : t));
    setTriggers(next);
    syncBackend(next);
  };

  const deleteTrigger = (id) => {
    const next = triggers.filter((t) => t.id !== id);
    setTriggers(next);
    syncBackend(next);
    toast.info("Gatilho removido");
  };

  const shortP = gc.shortLabels.player;
  const shortB = gc.shortLabels.banker;

  return (
    <div className="space-y-4" data-testid="user-triggers">
      <p className="text-xs text-muted-foreground">
        Padrão: use <span className="font-mono text-white">{shortP}</span> = {gc.labels.player},{" "}
        <span className="font-mono text-white">{shortB}</span> = {gc.labels.banker}, ex:{" "}
        <span className="font-mono text-white">{shortB} {shortB} {shortB}</span>
      </p>
      <div className="flex gap-2">
        <Input
          placeholder={`Ex: ${shortB} ${shortB} ${shortB}`}
          value={newPattern}
          onChange={(e) => setNewPattern(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addTrigger()}
          className="bg-surface border-white/10 text-white font-mono"
          data-testid="trigger-pattern-input"
        />
        <Select value={newSignal} onValueChange={setNewSignal}>
          <SelectTrigger className="w-36 bg-surface border-white/10">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {gc.signalOptions.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={addTrigger} className="bg-player text-black font-bold px-4" data-testid="add-trigger-btn">+</Button>
      </div>

      <div className="space-y-2">
        {enriched.length === 0 ? (
          <p className="text-muted-foreground text-sm text-center py-4">Nenhum gatilho configurado</p>
        ) : (
          enriched.map((trigger) => {
            const hasStats = trigger.total > 0;
            const isGood = trigger.rate >= 60;
            const isActive = trigger.active_now && trigger.active;
            const signalLabel = trigger.signal === "Player" ? gc.labels.player : gc.labels.banker;
            const signalClass = trigger.signal === "Player" ? "text-player" : "text-banker";
            return (
              <div
                key={trigger.id}
                className={`glass rounded p-3 border transition-all ${
                  isActive ? "border-yellow-400/60 bg-yellow-400/5" : trigger.active ? "border-transparent" : "border-transparent opacity-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 flex-wrap">
                    {isActive && <span className="text-yellow-400 text-xs font-bold animate-pulse">⚡ ATIVO</span>}
                    <span className="font-mono text-sm">{trigger.pattern}</span>
                    <span className="text-muted-foreground">→</span>
                    <span className={`${signalClass} font-medium`}>{signalLabel}</span>
                    {hasStats ? (
                      <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${isGood ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-banker"}`}>
                        {trigger.rate}% ({trigger.total} ocorr.)
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">sem dados ainda</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Switch checked={trigger.active} onCheckedChange={() => toggleTrigger(trigger.id)} />
                    <Button variant="ghost" size="sm" onClick={() => deleteTrigger(trigger.id)} className="text-banker hover:text-banker/80">×</Button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

// ============================================================
// Dashboard Principal
// ============================================================
export default function Dashboard() {
  const { logout, selectedGame, selectGame } = useAuth();
  const navigate = useNavigate();

  const gc = GAME_CONFIGS[selectedGame] || GAME_CONFIGS.bacbo;
  const API_GAME = `${API}${gc.apiPrefix}`;
  const isFS = !!gc.apiPrefix;

  const [state, setState] = useState({
    history: [],
    stats: { wins: 0, losses: 0, total_signals: 0 },
    logs: [],
    current_signal: null,
    active_strategy: "consensus",
    min_probability: 60,
    auto_select: true,
    strategy_stats: {
      adaptive:      { wins: 0, losses: 0, total: 0 },
      number:        { wins: 0, losses: 0, total: 0 },
      number_pro:    { wins: 0, losses: 0, total: 0 },
      number_20:     { wins: 0, losses: 0, total: 0 },
      number_20_pro: { wins: 0, losses: 0, total: 0 },
      consensus:     { wins: 0, losses: 0, total: 0 },
    },
    percentages: { Player: 0, Banker: 0, Tie: 0 },
    patterns: {},
    monte_carlo: { Player: 33.3, Banker: 33.3, Tie: 33.3 },
    drift: { drift_detected: false, message: "" },
    tie_warning: false,
    trigger_results: [],
    resolved_signals: [],
    current_tie_watch: null,
    session_start_time: null,
  });

  const [soundEnabled, setSoundEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [localProbability, setLocalProbability] = useState(60);
  const [localCooldown, setLocalCooldown] = useState(2);
  const [localNumberWindow, setLocalNumberWindow] = useState(20);
  const [seqMin, setSeqMin] = useState(3);
  const [galeDisplay, setGaleDisplay] = useState(0);
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [tieWatchEnabled, setTieWatchEnabled] = useState(
    () => localStorage.getItem("alphasignal_tie_watch_enabled") !== "false"
  );
  const tieWatchEnabledRef = useRef(tieWatchEnabled);
  useEffect(() => {
    tieWatchEnabledRef.current = tieWatchEnabled;
    localStorage.setItem("alphasignal_tie_watch_enabled", String(tieWatchEnabled));
    if (!tieWatchEnabled) {
      pendingTieWatchRef.current = null; // descarta qualquer pendência ao desativar
    }
  }, [tieWatchEnabled]);
  const stableHistoryRef = useRef([]);
  const stableResolvedRef = useRef([]);
  const stableLogsRef = useRef([]);
  const stableStrategyStatsRef = useRef(null);
  const stablePercentagesRef = useRef(null);
  const stableMonteCarloRef = useRef(null);
  const stablePatternsRef = useRef(null);
  const stableTriggerResultsRef = useRef([]);
  const galeRef = useRef(0);
  const pendingSignalRef = useRef(null);
  const resolvingRef = useRef(false);
  const sessionTokenRef = useRef(null);
  const lastHistoryLenRef = useRef(0);
  const lastResultKeyRef = useRef(null);
  const soundEnabledRef = useRef(soundEnabled);
  useEffect(() => { soundEnabledRef.current = soundEnabled; }, [soundEnabled]);
  const pendingTieWatchRef = useRef(null); // resolve localmente, nunca conta no placar

  const sendFeedback = useCallback(async (signalId, result, extra = {}) => {
    try {
      await api.post(`${API_GAME}/signal/feedback`, { signal_id: signalId, result, ...extra });
    } catch (e) {}
  }, [API_GAME]);

  const fetchState = useCallback(async () => {
    try {
      const response = await api.get(`${API_GAME}/state`);
      localStorage.setItem("alphasignal_auth_ts", Date.now().toString());
      const newState = response.data;

      if (newState.session_token && sessionTokenRef.current && newState.session_token !== sessionTokenRef.current) {
        pendingSignalRef.current = null;
        resolvingRef.current = false;
        galeRef.current = 0;
        setGaleDisplay(0);
        pendingTieWatchRef.current = null;
      }
      if (newState.session_token) sessionTokenRef.current = newState.session_token;

      const newLen = newState.history.length;
      const prevLen = lastHistoryLenRef.current;
      const MAX_HISTORY = 150;

      // Detecta resultado novo:
      // - Normal: tamanho cresceu
      // - No limite (150/150): compara o último resultado com o que já vimos
      const lastResult = newState.history[newState.history.length - 1];
      const lastResultKey = lastResult ? `${lastResult.winner}_${lastResult.player ?? lastResult.casa ?? 0}_${lastResult.banker ?? lastResult.visitante ?? 0}` : null;
      const atLimit = newLen === MAX_HISTORY && prevLen === MAX_HISTORY;
      const hasNewResult = atLimit
        ? (lastResultKey !== lastResultKeyRef.current)
        : (newLen > prevLen);

      if (hasNewResult && pendingSignalRef.current) {
        // Quando no limite, o resultado novo é sempre o último
        const newResults = atLimit
          ? [lastResult]
          : newState.history.slice(prevLen);

        for (const result of newResults) {
          if (!pendingSignalRef.current) break;
          const pending = pendingSignalRef.current;
          const galeUsed = galeRef.current;
          const acertou = result.winner === pending.signal || result.winner === "Tie";
          if (acertou) {
            const label = result.winner === "Tie"
              ? `🟡 ${gc.labels.tie} — contado como WIN`
              : galeRef.current === 0 ? "✅ WIN" : "✅ WIN no Gale";
            toast.success(label);
            if (soundEnabledRef.current) playSound("win");
            resolvingRef.current = true;
            pendingSignalRef.current = null;
            galeRef.current = 0;
            setGaleDisplay(0);
            newState.current_signal = null;

            // Se ganhou por Empate E tinha um Empate Seco pendente no MESMO round,
            // manda o ID exato junto nessa ÚNICA chamada — evita a corrida que
            // causava contagem dupla quando as duas resoluções eram separadas.
            let tieWatchIdToResolve = null;
            let tieWatchMultiplier = null;
            if (result.winner === "Tie" && !isFS && tieWatchEnabledRef.current && pendingTieWatchRef.current) {
              tieWatchIdToResolve = pendingTieWatchRef.current.id;
              tieWatchMultiplier = getTieMultiplier(pendingTieWatchRef.current.number);
              toast.success(`🟡 Empate Seco também bateu (número ${pendingTieWatchRef.current.number}${tieWatchMultiplier ? `, ${tieWatchMultiplier}x` : ""}) — já contado pelo sinal de cor`);
              if (soundEnabledRef.current) playSound("tie_watch");
              pendingTieWatchRef.current = null; // já resolvido aqui, não deixa a outra rotina mandar de novo
            }

            await sendFeedback(pending.id, "win", {
              entry_signal: pending.signal,
              gale: galeUsed,
              actual_winner: result.winner,
              player: result.player,
              banker: result.banker,
              tie_watch_id: tieWatchIdToResolve,
              tie_watch_multiplier: tieWatchMultiplier,
            });
            resolvingRef.current = false;
            break;
          } else if (galeRef.current < 1) {
            galeRef.current = 1;
            setGaleDisplay(1);
            toast.warning("⚠️ G1 — entrada repetida");
          } else {
            toast.error("❌ LOSS (G1 usado)");
            if (soundEnabledRef.current) playSound("notification");
            resolvingRef.current = true;
            pendingSignalRef.current = null;
            galeRef.current = 0;
            setGaleDisplay(0);
            newState.current_signal = null;
            await sendFeedback(pending.id, "loss", {
              entry_signal: pending.signal,
              gale: galeUsed,
              actual_winner: result.winner,
              player: result.player,
              banker: result.banker,
            });
            resolvingRef.current = false;
            break;
          }
        }
      }

      lastHistoryLenRef.current = newLen;
      lastResultKeyRef.current = lastResultKey;

      // Empate Seco 🟡 — entra no placar geral quando ganha. O BACKEND decide
      // se já foi contado pelo sinal de cor (resposta "duplicate"), evitando
      // contar 2x sem depender de cálculo aqui no front.
      // Só roda se o cliente não desativou o Empate Seco no toggle.
      if (!isFS && tieWatchEnabledRef.current) {
        if (hasNewResult && pendingTieWatchRef.current) {
          const pendingTW = pendingTieWatchRef.current;
          const newResults = atLimit ? [lastResult] : newState.history.slice(prevLen);
          const deuTie = newResults.some(r => r.winner === "Tie");
          const multiplier = getTieMultiplier(pendingTW.number);
          pendingTieWatchRef.current = null;
          try {
            const res = await api.post(`${API_GAME}/tiewatch/feedback`, {
              watch_id: pendingTW.id,
              result: deuTie ? "win" : "loss",
              multiplier,
            });
            const jaContado = res.data?.duplicate === true;
            if (deuTie) {
              toast.success(
                jaContado
                  ? `🟡 Empate Seco também bateu (número ${pendingTW.number}${multiplier ? `, ${multiplier}x` : ""}) — já contado pelo sinal de cor`
                  : `🟡 Empate Seco bateu! (número ${pendingTW.number}${multiplier ? `, ${multiplier}x` : ""})`
              );
              if (soundEnabledRef.current) playSound("tie_watch");
            } else if (!jaContado) {
              toast.info("Empate Seco não bateu dessa vez");
            }
          } catch (e) {}
        }
        if (newState.current_tie_watch && !pendingTieWatchRef.current) {
          pendingTieWatchRef.current = newState.current_tie_watch;
          toast.info("🟡 Empate Seco ativo — de olho!");
          if (soundEnabledRef.current) playSound("tie_watch");
        }
      }

      if (newState.current_signal && !pendingSignalRef.current && !resolvingRef.current) {
        pendingSignalRef.current = newState.current_signal;
        galeRef.current = 0;
        setGaleDisplay(0);
      }

      // Reaproveita referências antigas quando o conteúdo não mudou de verdade —
      // deixa o React.memo dos painéis pesados (histórico, logs, sinais) funcionar
      newState.history = stabilizeArray(
        stableHistoryRef, newState.history,
        (r) => r ? `${r.winner}_${r.player ?? r.casa ?? 0}_${r.banker ?? r.visitante ?? 0}` : ""
      );
      newState.resolved_signals = stabilizeArray(
        stableResolvedRef, newState.resolved_signals,
        (s) => s ? s.id : ""
      );
      newState.logs = stabilizeArray(
        stableLogsRef, newState.logs,
        (l, i) => l ? `${i}_${l.message}` : ""
      );
      newState.strategy_stats = stabilizeObject(stableStrategyStatsRef, newState.strategy_stats);
      newState.percentages = stabilizeObject(stablePercentagesRef, newState.percentages);
      newState.monte_carlo = stabilizeObject(stableMonteCarloRef, newState.monte_carlo);
      newState.patterns = stabilizeObject(stablePatternsRef, newState.patterns);
      newState.trigger_results = stabilizeArray(
        stableTriggerResultsRef, newState.trigger_results,
        (t) => t ? `${t.id}_${t.active}_${t.active_now}_${t.rate}_${t.total}` : ""
      );

      lastHistoryLenRef.current = newLen;
      setState(newState);
      if (loading) setLocalProbability(newState.min_probability);
      if (loading) setLocalCooldown(newState.cooldown_rounds ?? 2);
      if (loading) setLocalNumberWindow(newState.number_window ?? 20);
    } catch (error) {
      console.error("Error fetching state:", error?.response?.status, error?.response?.data || error.message);
    } finally {
      setLoading(false);
    }
  }, [sendFeedback, loading, API_GAME, gc.labels.tie, isFS]);

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 500);
    return () => clearInterval(interval);
  }, [fetchState]);

  const handleStrategyChange = useCallback(async (strategy) => {
    try {
      await api.post(`${API_GAME}/strategy`, { strategy });
      pendingSignalRef.current = null;
      resolvingRef.current = false;
      galeRef.current = 0;
      setGaleDisplay(0);
      if (soundEnabled) playSound("notification");
      toast.success(`Estratégia alterada para ${strategy}`);
      fetchState();
    } catch (error) {
      toast.error("Erro ao alterar estratégia");
    }
  }, [API_GAME, soundEnabled, fetchState]);

  const handleSaveTriggers = async (list) => {
    try {
      await api.post(`${API_GAME}/triggers`, { triggers: list });
    } catch (e) {}
  };

  const handleAutoSelect = useCallback(async (enabled) => {
    try {
      await api.post(`${API_GAME}/auto_select`, { enabled });
      toast.info(enabled ? "Auto-seleção ativada" : "Auto-seleção desativada");
      fetchState();
    } catch (error) {}
  }, [API_GAME, fetchState]);

  const handleProbabilityChange = async (value) => {
    try {
      await api.post(`${API_GAME}/probability`, { min_probability: value[0] });
      fetchState();
    } catch (error) {}
  };

  const handleCooldownChange = async (value) => {
    try {
      await api.post(`${API_GAME}/cooldown`, { cooldown_rounds: value[0] });
      fetchState();
    } catch (error) {}
  };

  const handleNumberWindowChange = async (value) => {
    try {
      await api.post(`${API_GAME}/number_window`, { number_window: value[0] });
      fetchState();
    } catch (error) {}
  };

  const handleSeqMinChange = useCallback(async (val) => {
    setSeqMin(val);
    try {
      await api.post(`${API_GAME}/seq_min`, { seq_min: val });
    } catch (e) {}
  }, [API_GAME]);

  const handleViewMore = useCallback(() => setShowFullHistory(true), []);

  const handleReset = async () => {
    try {
      await api.post(`${API_GAME}/reset`);
      if (soundEnabled) playSound("notification");
      toast.info("Estatísticas resetadas");
      fetchState();
    } catch (error) {}
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const handleChangeGame = () => {
    selectGame(null);
    navigate("/select-game");
  };

  const assertividade =
    state.stats.total_signals > 0
      ? Math.round((state.stats.wins / state.stats.total_signals) * 100)
      : 0;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#14171c]">
        <div className="text-center">
          <Zap className="w-12 h-12 text-player animate-pulse mx-auto" />
          <p className="text-muted-foreground mt-4">Carregando...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#14171c]" data-testid="dashboard">
      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-white/10 px-4 py-3">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <Zap className="w-6 h-6 text-player" />
            <h1 className="font-heading font-bold text-xl text-white">
              Alpha<span className="text-player">Signal</span>
            </h1>
            {/* Badge do jogo ativo */}
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full glass border border-white/10 text-sm">
              <span>{gc.emoji}</span>
              <span className="font-semibold text-white">{gc.name}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground hidden md:inline">
              Modo: <span className="text-player capitalize">{state.active_strategy}</span>
            </span>

            {/* Trocar jogo */}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleChangeGame}
              className="text-xs text-muted-foreground hover:text-player flex items-center gap-1"
              title="Trocar jogo"
            >
              <RefreshCw className="w-3 h-3" />
              <span className="hidden md:inline">Trocar jogo</span>
            </Button>

            <a
              href="/AlphaSignal-Capture.zip"
              download
              title="Baixar extensão de captura"
              className="text-muted-foreground hover:text-player flex items-center justify-center"
              data-testid="download-extension-link"
            >
              <Download className="w-5 h-5" />
            </a>

            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSoundEnabled(!soundEnabled)}
              className="text-muted-foreground hover:text-white"
              data-testid="sound-toggle"
            >
              {soundEnabled ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={handleLogout}
              className="text-muted-foreground hover:text-banker"
              data-testid="logout-btn"
            >
              <LogOut className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-7xl mx-auto p-4 space-y-4">
        {state.drift?.drift_detected && (
          <div className="glass border border-tie/50 rounded-lg p-3 flex items-center gap-2 animate-fadeIn">
            <AlertTriangle className="w-5 h-5 text-tie" />
            <span className="text-tie text-sm">{state.drift.message}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left */}
          <div className="lg:col-span-8 space-y-4">
            {/* History */}
            <div className="glass rounded-lg p-4" data-testid="history-panel">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-heading font-semibold text-lg flex items-center gap-2">
                  <Activity className="w-5 h-5 text-player" />
                  Histórico ({state.history.length}/150)
                </h2>
              </div>
              <div className="overflow-x-auto py-1">
                <BigRoad history={state.history} gc={gc} />
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
              <StatCard label="Wins" value={state.stats.wins} color="text-green-400" />
              <StatCard label="Loss" value={state.stats.losses} color="text-banker" />
              <StatCard label="Assertividade" value={`${assertividade}%`} color="text-player" />
              <StatCard label={gc.labels.player} value={`${state.percentages.Player}%`} color="text-player" />
              <StatCard label={gc.labels.banker} value={`${state.percentages.Banker}%`} color="text-banker" />
              <StatCard label={gc.labels.tie} value={`${state.percentages.Tie}%`} color="text-tie" />
            </div>

            {/* Monte Carlo */}
            <div className="glass rounded-lg px-4 py-2 flex items-center gap-3">
              <TrendingUp className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="text-xs text-muted-foreground">Monte Carlo:</span>
              <span className="text-xs font-mono text-player">{gc.shortLabels.player} {state.monte_carlo.Player}%</span>
              <span className="text-xs font-mono text-banker">{gc.shortLabels.banker} {state.monte_carlo.Banker}%</span>
              <span className="text-xs font-mono text-tie">{gc.shortLabels.tie} {state.monte_carlo.Tie}%</span>
            </div>

            {/* Tabs */}
            <Tabs defaultValue="patterns" className="glass rounded-lg p-4">
              <TabsList className="grid grid-cols-3 mb-4 bg-surface">
                <TabsTrigger value="patterns" data-testid="tab-patterns">Padrões</TabsTrigger>
                <TabsTrigger value="strategies" data-testid="tab-strategies">Estratégias</TabsTrigger>
                <TabsTrigger value="triggers" data-testid="tab-triggers">Gatilhos</TabsTrigger>
              </TabsList>

              <TabsContent value="patterns">
                <PatternHeatmap patterns={state.patterns} triggerResults={state.trigger_results} gc={gc} />
              </TabsContent>

              <TabsContent value="strategies">
                <div className="flex items-center justify-between glass rounded p-3 mb-3">
                  <div>
                    <p className="text-sm font-medium">Auto-seleção inteligente</p>
                    <p className="text-xs text-muted-foreground">Troca automaticamente para a estratégia com mais acertos</p>
                  </div>
                  <Switch checked={state.auto_select} onCheckedChange={handleAutoSelect} />
                </div>
                <StrategySelector
                  active={state.active_strategy}
                  onChange={handleStrategyChange}
                  strategyStats={state.strategy_stats}
                  autoSelect={state.auto_select}
                  isFS={!!gc.apiPrefix}
                  seqMin={seqMin}
                  onSeqMinChange={handleSeqMinChange}
                />
                {state.active_strategy !== "sequential" && (
                  <div className="mt-4 space-y-2">
                    <Label className="text-sm">Probabilidade mínima: {localProbability}%</Label>
                    <Slider
                      value={[localProbability]}
                      onValueChange={(v) => setLocalProbability(v[0])}
                      onValueCommit={handleProbabilityChange}
                      min={40} max={90} step={5}
                      className="cursor-pointer"
                      data-testid="probability-slider"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Mais sinais (40%)</span>
                      <span>Menos sinais (90%)</span>
                    </div>
                  </div>
                )}

                {!isFS && (state.active_strategy === "number_20" || state.active_strategy === "number_20_pro") && (
                  <div className="mt-4 space-y-2">
                    <Label className="text-sm">Janela da estratégia: últimas {localNumberWindow} rodadas</Label>
                    <Slider
                      value={[localNumberWindow]}
                      onValueChange={(v) => setLocalNumberWindow(v[0])}
                      onValueCommit={handleNumberWindowChange}
                      min={5} max={100} step={5}
                      className="cursor-pointer"
                      data-testid="number-window-slider"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Reage rápido (5)</span>
                      <span>Mais histórico (100)</span>
                    </div>
                  </div>
                )}

                {!isFS && (
                  <div className="mt-4 space-y-2">
                    <Label className="text-sm">Cooldown: {localCooldown} rodada{localCooldown !== 1 ? "s" : ""} de descanso após cada sinal</Label>
                    <Slider
                      value={[localCooldown]}
                      onValueChange={(v) => setLocalCooldown(v[0])}
                      onValueCommit={handleCooldownChange}
                      min={0} max={10} step={1}
                      className="cursor-pointer"
                      data-testid="cooldown-slider"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Sem espera (0)</span>
                      <span>Mais cauteloso (10)</span>
                    </div>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="triggers">
                <UserTriggers triggerResults={state.trigger_results} onSave={handleSaveTriggers} gc={gc} />
              </TabsContent>
            </Tabs>
          </div>

          {/* Right */}
          <div className="lg:col-span-4 space-y-4">
            <SignalCard
              signal={state.current_signal}
              soundEnabled={soundEnabled}
              galeCount={galeDisplay}
              gc={gc}
            />

            {!isFS && (
              <div className="glass rounded-lg p-3 flex items-center justify-between" data-testid="tie-watch-toggle">
                <div>
                  <p className="text-sm font-medium text-white flex items-center gap-1.5">🟡 Empate Seco</p>
                  <p className="text-xs text-muted-foreground">
                    {tieWatchEnabled ? "Ativo — conta no placar quando bate" : "Desativado — só o sinal principal"}
                  </p>
                </div>
                <Switch
                  checked={tieWatchEnabled}
                  onCheckedChange={setTieWatchEnabled}
                  data-testid="tie-watch-switch"
                />
              </div>
            )}

            {!isFS && tieWatchEnabled && state.current_tie_watch && (
              <div className="glass border border-tie/50 rounded-lg p-3 flex items-start gap-2 animate-fadeIn" data-testid="tie-watch-alert">
                <span className="text-lg leading-none">🟡</span>
                <div className="flex-1">
                  <p className="text-tie text-sm font-semibold">Empate Seco ativo — conta no placar geral</p>
                  {state.current_tie_watch.alerts.map((a, i) => (
                    <p key={i} className="text-xs text-muted-foreground">{a.reason}</p>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <Button
                variant="outline"
                onClick={handleReset}
                className="border-white/20 hover:bg-white/10"
                data-testid="reset-btn"
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Reset Placar
              </Button>
              {!isFS && (
                <Button
                  variant="outline"
                  onClick={() => setShowFullHistory(true)}
                  className="border-white/20 hover:bg-white/10"
                  data-testid="ver-historico-completo-btn"
                >
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Histórico
                </Button>
              )}
              <Button
                onClick={() => window.open(gc.link, "_blank")}
                className={`bg-player text-black hover:bg-player/90 ${isFS ? "col-span-2" : ""}`}
                data-testid="goto-game-btn"
              >
                <ExternalLink className="w-4 h-4 mr-2" />
                {gc.linkLabel}
              </Button>
            </div>

            {!isFS && <ResolvedSignalsPanel signals={state.resolved_signals} onViewMore={handleViewMore} />}

            {!isFS && showFullHistory && (
              <FullHistoryModal
                signals={state.resolved_signals}
                stats={state.stats}
                strategyStats={state.strategy_stats}
                sessionStartTime={state.session_start_time}
                onClose={() => setShowFullHistory(false)}
              />
            )}

            <div className="glass rounded-lg p-4" data-testid="logs-panel">
              <h3 className="font-heading font-semibold mb-3 flex items-center gap-2">
                <Settings className="w-5 h-5 text-player" />
                Logs de Análise
              </h3>
              <ScrollArea className="h-64">
                {state.logs.length === 0 ? (
                  <p className="text-muted-foreground text-sm text-center py-4">Nenhum log ainda...</p>
                ) : (
                  [...state.logs].reverse().map((log, index) => <LogItem key={index} log={log} />)
                )}
              </ScrollArea>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
