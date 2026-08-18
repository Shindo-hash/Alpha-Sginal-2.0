from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import secrets
import random
import time

from collections import Counter
import asyncio
# IA removida — análise 100% estatística

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configuration
APP_USER = os.environ.get('APP_USER', 'admin')
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'admin')


app = FastAPI(title="AlphaSignal API")
api_router = APIRouter(prefix="/api")
security = HTTPBasic()

# In-memory storage
game_history: List[Dict[str, Any]] = []
stats = {"wins": 0, "losses": 0, "total_signals": 0}
pattern_weights: Dict[str, float] = {}
logs: List[Dict[str, Any]] = []
resolved_signals: List[Dict[str, Any]] = []  # histórico detalhado de sinais resolvidos (clicável no front)
current_signal: Optional[Dict[str, Any]] = None
current_tie_watch: Optional[Dict[str, Any]] = None  # Empate Seco pendente (número/padrão puxando empate)
tie_watch_registry: Dict[str, Dict] = {}  # watch_id -> detalhes (evita contagem dupla)
active_strategy = "consensus"
min_probability = 60
auto_select = True  # auto-seleção de estratégia ativa

# Placar por estratégia para auto-seleção
strategy_stats: Dict[str, Dict] = {
    "adaptive":  {"wins": 0, "losses": 0, "total": 0},
    "number":    {"wins": 0, "losses": 0, "total": 0},
    "number_pro":{"wins": 0, "losses": 0, "total": 0},
    "consensus": {"wins": 0, "losses": 0, "total": 0},
}
last_signal_strategy: Optional[str] = None  # qual estratégia gerou o sinal atual
signal_strategy_map: Dict[str, str] = {}  # signal_id -> estratégia que o gerou (evita contagem dupla/errada)
user_triggers: List[Dict[str, Any]] = []  # gatilhos cadastrados pelo usuário
cooldown_results: int = 0  # resultados recebidos desde último win/loss (cooldown)
last_activity: float = time.time()  # timestamp da última atividade
session_token: str = str(int(time.time()))  # muda a cada reconexão (historico)
session_start_time: float = time.time()  # marca início da sessão, pra calcular tempo de mesa e sinais/min
AUTO_RESET_MINUTES: int = 30  # reseta após X minutos sem uso
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Models
















# Auth
def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, APP_USER)
    correct_password = secrets.compare_digest(credentials.password, APP_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return credentials.username

# Analysis Engine
class AnalysisEngine:
    @staticmethod
    def get_sequence_string(history: List[Dict], length: int = 5) -> str:
        if len(history) < length:
            return ""
        recent = history[-length:]
        return " ".join([r.get("winner", "")[0] if r.get("winner") else "" for r in recent])
    
    @staticmethod
    def calculate_percentages(history: List[Dict]) -> Dict[str, float]:
        if not history:
            return {"Player": 0, "Banker": 0, "Tie": 0}
        
        counter = Counter([r.get("winner", "") for r in history])
        total = len(history)
        return {
            "Player": round((counter.get("Player", 0) / total) * 100, 1),
            "Banker": round((counter.get("Banker", 0) / total) * 100, 1),
            "Tie": round((counter.get("Tie", 0) / total) * 100, 1)
        }
    
    @staticmethod
    def detect_patterns(history: List[Dict], pattern_length: int = 3) -> Dict[str, Dict]:
        if len(history) < pattern_length + 1:
            return {}
        patterns = {}
        for i in range(len(history) - pattern_length):
            pattern = " ".join([h.get("winner", "")[0] for h in history[i:i+pattern_length]])
            next_result = history[i + pattern_length].get("winner", "")[0]
            if pattern not in patterns:
                patterns[pattern] = {"P": 0, "B": 0, "T": 0, "total": 0}
            patterns[pattern][next_result] = patterns[pattern].get(next_result, 0) + 1
            patterns[pattern]["total"] += 1
        result = {}
        for pattern, counts in patterns.items():
            if counts["total"] >= 3:
                player_pct = round((counts["P"] / counts["total"]) * 100, 1)
                banker_pct = round((counts["B"] / counts["total"]) * 100, 1)
                tie_pct = round((counts["T"] / counts["total"]) * 100, 1)
                result[pattern] = {
                    "Player": player_pct,
                    "Banker": banker_pct,
                    "Tie": tie_pct,
                    "count": counts["total"]
                }
        
        return result
    
    @staticmethod
    def detect_streaks(history: List[Dict]) -> Dict[str, Any]:
        if len(history) < 3:
            return {"current_streak": None, "length": 0}
        
        current_winner = history[-1].get("winner", "")
        streak_length = 1
        
        for i in range(len(history) - 2, -1, -1):
            if history[i].get("winner", "") == current_winner:
                streak_length += 1
            else:
                break
        
        return {
            "current_streak": current_winner,
            "length": streak_length,
            "reversal_probability": min(95, 50 + (streak_length * 5))
        }
    
    @staticmethod
    def monte_carlo_simulation(history: List[Dict], simulations: int = 5000) -> Dict[str, float]:
        if len(history) < 10:
            return {"Player": 33.3, "Banker": 33.3, "Tie": 33.3}
        
        percentages = AnalysisEngine.calculate_percentages(history[-50:])
        results = {"Player": 0, "Banker": 0, "Tie": 0}
        
        for _ in range(simulations):
            rand = random.random() * 100
            if rand < percentages["Player"]:
                results["Player"] += 1
            elif rand < percentages["Player"] + percentages["Banker"]:
                results["Banker"] += 1
            else:
                results["Tie"] += 1
        
        return {
            "Player": round((results["Player"] / simulations) * 100, 1),
            "Banker": round((results["Banker"] / simulations) * 100, 1),
            "Tie": round((results["Tie"] / simulations) * 100, 1)
        }
    
    @staticmethod
    def detect_drift(history: List[Dict]) -> Dict[str, Any]:
        if len(history) < 50:
            return {"drift_detected": False, "message": "Dados insuficientes"}
        
        recent_30 = AnalysisEngine.calculate_percentages(history[-30:])
        full_150 = AnalysisEngine.calculate_percentages(history[-150:])
        
        player_diff = abs(recent_30["Player"] - full_150["Player"])
        banker_diff = abs(recent_30["Banker"] - full_150["Banker"])
        
        drift_detected = player_diff > 10 or banker_diff > 10
        
        return {
            "drift_detected": drift_detected,
            "recent_30": recent_30,
            "full_150": full_150,
            "player_diff": round(player_diff, 1),
            "banker_diff": round(banker_diff, 1),
            "message": "Drift da mesa detectado! Comportamento mudando." if drift_detected else "Mesa estável"
        }

# ── Estratégias ────────────────────────────────────────────────────────────────

def analyze_adaptive(history: List[Dict]) -> Dict[str, Any]:
    """
    Analisa o padrão dos últimos 3 resultados e verifica o que costuma vir depois.
    Só sinaliza se o padrão tiver ao menos 3 ocorrências no histórico.
    """
    patterns = AnalysisEngine.detect_patterns(history)
    current_pattern = AnalysisEngine.get_sequence_string(history, 3)

    if current_pattern not in patterns:
        return {
            "signal": None, "probability": 0,
            "reason": f"Padrão '{current_pattern}' ainda sem histórico suficiente",
            "strategy": "adaptive"
        }

    data = patterns[current_pattern]
    best = "Player" if data["Player"] > data["Banker"] else "Banker"
    probability = max(data["Player"], data["Banker"])

    return {
        "signal": best if probability >= min_probability else None,
        "probability": round(probability, 1),
        "reason": f"Padrão '{current_pattern}' → {best} {round(probability,1)}% ({data['count']} ocorrências)",
        "strategy": "adaptive",
        "pattern": current_pattern
    }


def analyze_pressure(history: List[Dict]) -> Dict[str, Any]:
    """
    Aguarda sequência de 4+ resultados iguais e aposta na reversão.
    Probabilidade de reversão sobe 5% por rodada extra na sequência.
    """
    streak = AnalysisEngine.detect_streaks(history)

    if streak["length"] < 4:
        return {
            "signal": None, "probability": 0,
            "reason": f"Sequência atual: {streak['current_streak']} x{streak['length']} (aguardando ≥ 4)",
            "strategy": "pressure"
        }

    opposite = "Banker" if streak["current_streak"] == "Player" else "Player"
    probability = streak["reversal_probability"]

    return {
        "signal": opposite if probability >= min_probability else None,
        "probability": probability,
        "reason": f"{streak['length']}x {streak['current_streak']} seguidos → reversão para {opposite} ({probability}%)",
        "strategy": "pressure",
        "streak_length": streak["length"]
    }


def _number_pull_raw(history: List[Dict]) -> Dict[str, Any]:
    """
    Cálculo puro (sem consenso): pega o número (2-12) do lado vencedor da
    última rodada e verifica, em todas as ocorrências desse mesmo número
    no histórico de 150, o que veio na rodada SEGUINTE.
    """
    clean = [r for r in history if r.get("winner") in ("Player", "Banker")]

    if len(clean) < 6:
        return {"signal": None, "probability": 0, "reason": "Aguardando mais resultados para análise por número"}

    def winning_number(r: Dict) -> Optional[int]:
        if r.get("winner") == "Player":
            return r.get("player")
        if r.get("winner") == "Banker":
            return r.get("banker")
        return None

    current_number = winning_number(clean[-1])
    if current_number is None:
        return {"signal": None, "probability": 0, "reason": "Número do último resultado indisponível"}

    # Varre o histórico (exceto o último) contando o que veio depois de cada número
    pulls = {"Player": 0, "Banker": 0}
    for i in range(len(clean) - 1):
        num = winning_number(clean[i])
        if num == current_number:
            next_winner = clean[i + 1].get("winner")
            if next_winner in pulls:
                pulls[next_winner] += 1

    total = pulls["Player"] + pulls["Banker"]

    if total < 3:
        return {
            "signal": None, "probability": 0,
            "reason": f"Número {current_number} apareceu só {total}x até agora — dados insuficientes",
            "number": current_number, "pulls": pulls
        }

    best = "Player" if pulls["Player"] > pulls["Banker"] else "Banker"
    probability = round((max(pulls["Player"], pulls["Banker"]) / total) * 100, 1)
    base_msg = f"Número {current_number} apareceu {total}x e puxou {best} {pulls[best]}x ({probability}%)"

    if probability < min_probability:
        reason = f"{base_msg} — abaixo do mínimo, sem entrada"
    else:
        reason = f"{base_msg} — ENTRADA"

    return {
        "signal": best if probability >= min_probability else None,
        "probability": probability,
        "reason": reason,
        "number": current_number, "pulls": pulls, "best": best, "total": total
    }


def analyze_number(history: List[Dict]) -> Dict[str, Any]:
    """
    Estratégia Número 🎲 (solo): usa só o critério do número puxando cor,
    sem exigir concordância de nenhuma outra estratégia.
    """
    raw = _number_pull_raw(history)
    raw["strategy"] = "number"
    return raw


def analyze_number_pro(history: List[Dict]) -> Dict[str, Any]:
    """
    Estratégia Número PRO 🎲: igual à Número, mas só confirma o sinal se a
    estratégia Adaptativo concordar com a mesma cor (consenso obrigatório).
    """
    raw = _number_pull_raw(history)
    number, pulls = raw.get("number"), raw.get("pulls")

    if not raw["signal"]:
        return {**raw, "strategy": "number_pro"}

    adaptive = analyze_adaptive(history)
    best, probability, total = raw["best"], raw["probability"], raw["total"]
    base_msg = f"Número {number} apareceu {total}x e puxou {best} {pulls[best]}x ({probability}%)"

    if adaptive["signal"] != best:
        return {
            "signal": None, "probability": probability,
            "reason": f"{base_msg}, mas o Adaptativo aponta outro lado — sem consenso, aguardando",
            "strategy": "number_pro", "number": number, "pulls": pulls
        }

    return {
        "signal": best,
        "probability": probability,
        "reason": f"{base_msg} + Adaptativo concorda — CONSENSO, entrada {best}",
        "strategy": "number_pro", "number": number, "pulls": pulls
    }


def analyze_consensus(history: List[Dict]) -> Dict[str, Any]:
    """
    Roda Adaptativo + Pressure + Tendência de curto prazo.
    - 2 de 3 concordam → sinal normal
    - 3 de 3 concordam → sinal FORTE (priority=True)
    Tie em alta (>10%) é avisado mas não bloqueia o sinal.
    """
    # Tendência curto prazo: últimos 20 resultados
    recent = history[-20:] if len(history) >= 20 else history
    pct = AnalysisEngine.calculate_percentages(recent)
    diff = abs(pct["Player"] - pct["Banker"])
    if diff >= 5:
        trend_signal = "Player" if pct["Player"] > pct["Banker"] else "Banker"
        trend_prob = max(pct["Player"], pct["Banker"])
    else:
        trend_signal = None
        trend_prob = 0

    trend = {
        "signal": trend_signal if trend_prob >= min_probability else None,
        "probability": round(trend_prob, 1),
        "strategy": "trend"
    }

    adaptive = analyze_adaptive(history)
    pressure = analyze_pressure(history)

    signals = [s["signal"] for s in [adaptive, pressure, trend] if s["signal"]]

    if len(signals) < 2:
        return {
            "signal": None, "probability": 0,
            "reason": "Consenso não atingido — estratégias divergem",
            "strategy": "consensus",
            "priority": False
        }

    counter = Counter(signals)
    best_signal, count = counter.most_common(1)[0]

    if count < 2:
        return {
            "signal": None, "probability": 0,
            "reason": "Consenso não atingido — estratégias divergem",
            "strategy": "consensus",
            "priority": False
        }

    agreeing = [s for s in [adaptive, pressure, trend] if s["signal"] == best_signal]
    avg_prob = round(sum(s["probability"] for s in agreeing) / len(agreeing), 1)
    priority = count == 3  # todas concordam

    tie_pct = AnalysisEngine.calculate_percentages(history[-30:]).get("Tie", 0)
    tie_warning = tie_pct >= 10

    reason = (
        f"{'⚡ SINAL FORTE — ' if priority else ''}Consenso {count}/3: {best_signal} "
        f"({avg_prob}%)"
        + (f" | ⚠️ Empate em alta ({tie_pct}%), cubra!" if tie_warning else "")
    )

    return {
        "signal": best_signal if avg_prob >= min_probability else None,
        "probability": avg_prob,
        "reason": reason,
        "strategy": "consensus",
        "agreeing_count": count,
        "priority": priority,
        "tie_warning": tie_warning
    }


def analyze_fluxo(history: List[Dict]) -> Dict[str, Any]:
    """
    Estratégia Fluxo (Football Studio):
    - Ignora Empates/Ties completamente
    - Detecta sequência de 3+ iguais
    - Quando alternar após 3+, aposta na cor principal voltar
    - Ex: C C C V → próximo é C (cor principal)
    """
    # Filtra Ties/Empates
    filtered = [r["winner"] for r in history if r["winner"] not in ("Tie",)]

    if len(filtered) < 4:
        return {
            "signal": None, "probability": 0,
            "reason": "Aguardando mais resultados para análise de fluxo",
            "strategy": "fluxo"
        }

    # Conta sequência atual sem Ties
    current = filtered[-1]
    streak = 1
    for i in range(len(filtered) - 2, -1, -1):
        if filtered[i] == current:
            streak += 1
        else:
            break

    # Sequência anterior (cor principal)
    prev_color = None
    prev_streak = 0
    if streak < len(filtered):
        prev = filtered[-(streak + 1)]
        for i in range(len(filtered) - streak - 1, -1, -1):
            if filtered[i] == prev:
                prev_streak += 1
            else:
                break
        prev_color = prev

    # Regra: se acabou de alternar (streak == 1) e a sequência anterior tinha 3+
    # → aposta que a cor principal volta
    if streak == 1 and prev_color and prev_streak >= 3:
        probability = min(90, 60 + (prev_streak - 3) * 5)
        return {
            "signal": prev_color,
            "probability": probability,
            "reason": f"Fluxo: {prev_streak}x {prev_color} → alternância → {prev_color} retorna ({probability}%)",
            "strategy": "fluxo"
        }

    # Regra: sequência de 3+ iguais → avisa que alternância vem
    if streak >= 3:
        opposite = "Banker" if current == "Player" else "Player"
        probability = min(85, 55 + (streak - 3) * 5)
        return {
            "signal": opposite,
            "probability": probability,
            "reason": f"Fluxo: {streak}x {current} seguidos → alternância para {opposite} ({probability}%)",
            "strategy": "fluxo"
        }

    return {
        "signal": None, "probability": 0,
        "reason": f"Fluxo: sequência atual {current} x{streak} — aguardando 3+ iguais",
        "strategy": "fluxo"
    }


def analyze_sequential(history: List[Dict], seq_min: int = 3) -> Dict[str, Any]:
    """
    Sequencial: ignora Empates, detecta sequência de 3+ iguais seguida de alternância
    e aposta na cor principal (que apareceu mais).
    """
    # Remove Ties do histórico para análise
    clean = [r for r in history if r.get("winner") not in ("Tie", "Empate")]

    if len(clean) < 5:
        return {
            "signal": None, "probability": 0,
            "reason": "Aguardando mais resultados (ignorando Empates)",
            "strategy": "sequential"
        }

    # Pega os últimos resultados sem Tie
    recent = clean[-10:]

    # Detecta a sequência atual
    current = recent[-1]["winner"]
    streak = 1
    for i in range(len(recent) - 2, -1, -1):
        if recent[i]["winner"] == current:
            streak += 1
        else:
            break

    # Detecta se houve alternância após 3+ iguais
    # Procura padrão: [3+ iguais] → [diferente] → apostamos na cor principal
    if len(recent) >= 4:
        # Verifica se o resultado anterior à sequência atual era diferente
        prev_idx = len(recent) - 1 - streak
        if prev_idx >= 0:
            prev_winner = recent[prev_idx]["winner"]
            # Se teve 1 alternância e agora voltou → sequência de alternância detectada
            if prev_winner != current and streak >= 1:
                # Conta quantas vezes cada um apareceu nos últimos 8
                last8 = recent[-8:]
                count = Counter([r["winner"] for r in last8])
                main_color = count.most_common(1)[0][0]
                main_count = count.most_common(1)[0][1]
                total = len(last8)
                prob = round((main_count / total) * 100, 1)

                # Só sinaliza se a cor principal tiver clara dominância
                if prob >= min_probability and main_count >= seq_min:
                    opposite = "Banker" if main_color == "Player" else "Player"
                    # Se estamos em sequência da cor principal (seq_min+), aguarda alternância
                    if streak >= seq_min:
                        return {
                            "signal": opposite,
                            "probability": min(90, 50 + streak * 8),
                            "reason": f"Sequência de {streak}x {main_color} — aguardando alternância para {opposite}",
                            "strategy": "sequential"
                        }
                    # Se acabou de alternar, volta para cor principal
                    elif streak == 1 and prev_winner == main_color:
                        return {
                            "signal": main_color,
                            "probability": prob,
                            "reason": f"Alternância detectada — cor principal {main_color} ({prob}%)",
                            "strategy": "sequential"
                        }

    # Fallback: sequência de seq_min+ → aposta na reversão
    if streak >= seq_min:
        opposite = "Banker" if current == "Player" else "Player"
        prob = min(90, 50 + streak * 8)
        return {
            "signal": opposite if prob >= min_probability else None,
            "probability": prob,
            "reason": f"Sequência de {streak}x {current} → reversão para {opposite} ({prob}%)",
            "strategy": "sequential"
        }

    return {
        "signal": None, "probability": 0,
        "reason": f"Sequência atual: {current} x{streak} — aguardando {seq_min}+ para sinalizar",
        "strategy": "sequential"
    }


def analyze_alternancia(history: List[Dict]) -> Dict[str, Any]:
    """
    Alternância: detecta dois padrões de ritmo da mesa (ignorando Ties):
    - Ping-Pong (1x1): P→B→P→B → entra contra o último
    - Duplas (2x2): PP→BB→PP→BB → entra na segunda repetição do bloco
    """
    clean = [r for r in history if r.get("winner") not in ("Tie", "Empate")]

    if len(clean) < 6:
        return {
            "signal": None, "probability": 0,
            "reason": "Aguardando mais resultados (ignorando Empates)",
            "strategy": "alternancia"
        }

    recent = [r["winner"] for r in clean[-8:]]

    # ── Ping-Pong (1x1) ─────────────────────────────────────────
    # Verifica se os últimos 4+ alternam perfeitamente
    ping_pong = True
    for i in range(len(recent) - 1, max(len(recent) - 5, 0), -1):
        if recent[i] == recent[i - 1]:
            ping_pong = False
            break

    if ping_pong and len(recent) >= 4:
        opposite = "Banker" if recent[-1] == "Player" else "Player"
        prob = min(85, 55 + (len(recent) - 4) * 5)
        return {
            "signal": opposite if prob >= min_probability else None,
            "probability": prob,
            "reason": f"Ping-Pong detectado — entra contra último ({opposite})",
            "strategy": "alternancia"
        }

    # ── Duplas Seguidas (2x2) ────────────────────────────────────
    # Verifica padrão PP→BB→PP ou BB→PP→BB nos últimos 6
    if len(recent) >= 6:
        r = recent[-6:]
        dupla_ok = (
            r[0] == r[1] and       # bloco 1
            r[2] == r[3] and       # bloco 2
            r[0] != r[2] and       # blocos alternados
            r[2] == r[4] and       # bloco 3 igual ao bloco 2? não
            r[4] == r[5]           # bloco 3 formado
        )
        # Padrão: AA BB AA (últimos 6 = AA BB AA → próximo é B)
        dupla_ok2 = (
            r[0] == r[1] and
            r[2] == r[3] and
            r[4] == r[5] and
            r[0] != r[2] and
            r[2] != r[4] and
            r[0] == r[4]  # voltou pro primeiro
        )

        if dupla_ok2:
            # Padrão AA BB AA confirmado → próximo é BB
            opposite = "Banker" if recent[-1] == "Player" else "Player"
            return {
                "signal": opposite if 72 >= min_probability else None,
                "probability": 72,
                "reason": f"Duplas seguidas (2x2) — bloco {recent[-1]} fechado → entra {opposite}",
                "strategy": "alternancia"
            }

        # Padrão parcial: AA BB → esperando fechar o segundo bloco
        if len(recent) >= 4:
            r4 = recent[-4:]
            if r4[0] == r4[1] and r4[2] == r4[3] and r4[0] != r4[2]:
                # Dois blocos formados → aposta que o próximo começa novo bloco igual ao primeiro
                signal = r4[0]  # volta pro primeiro bloco
                return {
                    "signal": signal if 65 >= min_probability else None,
                    "probability": 65,
                    "reason": f"Duplas (2x2) — padrão {r4[0]}{r4[0]}→{r4[2]}{r4[2]} → próximo bloco {signal}",
                    "strategy": "alternancia"
                }

    return {
        "signal": None, "probability": 0,
        "reason": f"Sem padrão de alternância identificado",
        "strategy": "alternancia"
    }


TIE_MIN_OCCURRENCES = 4
TIE_MIN_RATE = 25.0

# Tabela de multiplicador de Empate no Bac Bo, por número do dado vencedor (2-12)
TIE_MULTIPLIER_TABLE = {
    6: 4, 7: 4, 8: 4,
    5: 6, 9: 6,
    4: 10, 10: 10,
    3: 25, 11: 25,
    2: 88, 12: 88,
}
def get_tie_multiplier(number: Optional[int]) -> Optional[int]:
    return TIE_MULTIPLIER_TABLE.get(number)

def now_hm() -> str:
    """Horário local formatado HH:MM, usado nos itens do histórico de sinais resolvidos."""
    return time.strftime("%H:%M")

def _number_tie_watch(history: List[Dict]) -> Optional[Dict[str, Any]]:
    """Vê se o número da última rodada tem histórico forte de puxar Empate."""
    if len(history) < 6:
        return None

    def dice_number(r: Dict) -> Optional[int]:
        if r.get("winner") == "Player":
            return r.get("player")
        if r.get("winner") == "Banker":
            return r.get("banker")
        if r.get("winner") == "Tie":
            return r.get("player")  # empate: player == banker
        return None

    current_number = dice_number(history[-1])
    if current_number is None:
        return None

    tie_count, total = 0, 0
    for i in range(len(history) - 1):
        if dice_number(history[i]) == current_number:
            total += 1
            if history[i + 1].get("winner") == "Tie":
                tie_count += 1

    if total < TIE_MIN_OCCURRENCES:
        return None
    tie_rate = round((tie_count / total) * 100, 1)
    if tie_rate < TIE_MIN_RATE:
        return None

    return {
        "source": "number",
        "number": current_number,
        "tie_count": tie_count,
        "total": total,
        "tie_rate": tie_rate,
        "reason": f"Número {current_number} apareceu {total}x e puxou Empate {tie_count}x ({tie_rate}%)"
    }


def _pattern_tie_watch(history: List[Dict]) -> Optional[Dict[str, Any]]:
    """Vê se o padrão atual dos últimos 3 resultados tem histórico forte de puxar Empate."""
    patterns = AnalysisEngine.detect_patterns(history)
    current_pattern = AnalysisEngine.get_sequence_string(history, 3)

    if current_pattern not in patterns:
        return None

    data = patterns[current_pattern]
    if data["count"] < TIE_MIN_OCCURRENCES:
        return None
    if data["Tie"] < TIE_MIN_RATE:
        return None

    return {
        "source": "pattern",
        "pattern": current_pattern,
        "count": data["count"],
        "tie_rate": data["Tie"],
        "reason": f"Padrão '{current_pattern}' apareceu {data['count']}x e puxou Empate {data['Tie']}%"
    }


def analyze_tie_watch(history: List[Dict]) -> Dict[str, Any]:
    """
    Aviso independente de Empate Seco 🟡 — não é uma entrada de cor, é só um
    alerta separado. NUNCA entra no placar (o front nunca manda feedback
    pra isso pro backend, só mostra visualmente se acertou ou não).
    """
    alerts = []
    num_alert = _number_tie_watch(history)
    if num_alert:
        alerts.append(num_alert)
    pattern_alert = _pattern_tie_watch(history)
    if pattern_alert:
        alerts.append(pattern_alert)

    return {"active": len(alerts) > 0, "alerts": alerts}


STRATEGY_MAP = {
    "adaptive": analyze_adaptive,
    "number": analyze_number,
    "number_pro": analyze_number_pro,
    "consensus": analyze_consensus,
    "sequential": analyze_sequential,
    "alternancia": analyze_alternancia,
}

# API Endpoints
@api_router.get("/")
async def root():
    return {"message": "AlphaSignal API v1.0"}

@api_router.post("/login")
async def login(request: Request):
    data = await request.json()
    if data.get("username") == APP_USER and data.get("password") == APP_PASSWORD:
        # Zera histórico de ambos os jogos ao fazer login
        global game_history, logs, current_signal, cooldown_results, session_token, signal_strategy_map, resolved_signals, current_tie_watch, tie_watch_registry, session_start_time
        global fs_game_history, fs_logs, fs_current_signal, fs_cooldown_results, fs_session_token, fs_signal_strategy_map
        game_history.clear()
        logs.clear()
        current_signal = None
        cooldown_results = 0
        session_token = str(int(time.time()))
        session_start_time = time.time()
        signal_strategy_map = {}
        resolved_signals = []
        current_tie_watch = None
        tie_watch_registry = {}
        fs_game_history.clear()
        fs_logs.clear()
        fs_current_signal = None
        fs_cooldown_results = 0
        fs_session_token = str(int(time.time())) + "_fs"
        fs_signal_strategy_map = {}
        return {"success": True, "message": "Login bem sucedido"}
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

@api_router.post("/historico")
async def receive_historico(request: Request):
    data = await request.json()
    global game_history, logs, current_signal, cooldown_results, last_activity, session_token
    last_activity = time.time()
    session_token = str(int(time.time()))  # novo token = frontend detecta reconexão e limpa sinal pendente
    
    game_history = []
    for r in data.get("resultados", []):
        game_history.append({
            "winner": r.get("winner", ""),
            "player": r.get("player", 0),
            "banker": r.get("banker", 0)
        })
    
    if len(game_history) > 150:
        game_history = game_history[-150:]

    # Reconexão da extensão — reseta sinal e cooldown
    current_signal = None
    cooldown_results = 0
    
    logs.append({
        "type": "info",
        "message": f"Histórico inicial recebido: {len(game_history)} resultados",
        "timestamp": "now"
    })
    
    analysis = await run_analysis()
    
    return {
        "success": True,
        "received": len(game_history),
        "analysis": analysis
    }

@api_router.post("/resultado")
async def receive_resultado(request: Request):
    data = await request.json()
    global game_history, logs, current_signal, last_activity
    last_activity = time.time()
    
    new_result = {
        "winner": data.get("winner", ""),
        "player": data.get("player", 0),
        "banker": data.get("banker", 0)
    }
    
    game_history.append(new_result)
    
    if len(game_history) > 150:
        game_history = game_history[-150:]
    
    logs.append({
        "type": "result",
        "message": f"Novo resultado: {new_result['winner']} (P:{new_result['player']} B:{new_result['banker']})",
        "timestamp": "now"
    })
    
    analysis = await run_analysis()
    
    return {
        "success": True,
        "total": len(game_history),
        "analysis": analysis
    }

def evaluate_triggers(history: List[Dict], triggers: List[Dict]) -> List[Dict]:
    """Avalia cada gatilho ativo no histórico e retorna stats + se está ativo agora."""
    if len(history) < 4:
        return []

    results = []
    # Sequência atual (últimos 3 resultados non-tie para comparar com padrão)
    recent = [r["winner"][0] for r in history if r["winner"] != "Tie"][-3:]
    current_seq = " ".join(recent).upper()

    for t in triggers:
        if not t.get("active", True):
            results.append({**t, "hits": 0, "total": 0, "rate": 0, "active_now": False})
            continue

        pattern = t["pattern"].strip().upper()
        signal = t["signal"]  # "Player" ou "Banker"
        pat_parts = pattern.split()
        pat_len = len(pat_parts)

        if pat_len < 1:
            continue

        # Conta ocorrências do padrão no histórico e quantas vezes o signal veio depois
        seq = [r["winner"][0].upper() for r in history if r["winner"] != "Tie"]
        hits = 0
        total = 0
        for i in range(len(seq) - pat_len):
            window = seq[i:i + pat_len]
            # Compara cada parte (P=Player, B=Banker, T=Tie)
            match = all(
                (p == "P" and w == "P") or (p == "B" and w == "B") or (p == "T" and w == "T")
                for p, w in zip(pat_parts, window)
            )
            if match:
                total += 1
                next_r = seq[i + pat_len] if i + pat_len < len(seq) else None
                if next_r and next_r == signal[0].upper():
                    hits += 1

        rate = round((hits / total) * 100, 1) if total > 0 else 0
        active_now = current_seq.endswith(pattern) if len(current_seq) >= len(pattern) else False

        results.append({
            **t,
            "hits": hits,
            "total": total,
            "rate": rate,
            "active_now": active_now,
        })

    return results


async def run_analysis():
    global current_signal, logs, last_signal_strategy, current_tie_watch, tie_watch_registry

    if len(game_history) < 5:
        return {"signal": None, "reason": "Aguardando mais resultados"}

    # Empate Seco 🟡 — independente do sinal de cor, roda sempre que houver resultado novo
    tw = analyze_tie_watch(game_history)
    current_tie_watch = None
    if tw["active"]:
        watch_id = f"tiewatch_{int(time.time()*1000)}"
        last = game_history[-1]
        number = last.get("player") if last.get("winner") in ("Player", "Tie") else last.get("banker")
        current_tie_watch = {
            "id": watch_id,
            "number": number,
            "alerts": tw["alerts"],
        }
        tie_watch_registry[watch_id] = current_tie_watch
        logs.append({
            "type": "analysis",
            "message": "🟡 Empate Seco ativo: " + " | ".join(a["reason"] for a in tw["alerts"]),
            "timestamp": "now"
        })

    # LOCK: sinal ativo não resolvido → não gera novo
    if current_signal is not None:
        logs.append({
            "type": "analysis",
            "message": "⏳ Aguardando resolução do sinal anterior...",
            "timestamp": "now"
        })
        if len(logs) > 100:
            logs[:] = logs[-100:]
        return {"signal": current_signal, "reason": "Sinal pendente"}

    # COOLDOWN: após win/loss, espera 1 resultado antes de gerar novo sinal
    global cooldown_results
    if cooldown_results > 0:
        cooldown_results -= 1
        logs.append({
            "type": "analysis",
            "message": f"⏸️ Cooldown — aguardando próximo resultado para analisar...",
            "timestamp": "now"
        })
        if len(logs) > 100:
            logs[:] = logs[-100:]
        return {"signal": None, "reason": "Cooldown"}

    strategy_func = STRATEGY_MAP.get(active_strategy, analyze_consensus)
    analysis = strategy_func(game_history)

    patterns = AnalysisEngine.detect_patterns(game_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(game_history)
    drift = AnalysisEngine.detect_drift(game_history)
    percentages = AnalysisEngine.calculate_percentages(game_history)
    tie_warning = analysis.get("tie_warning", percentages.get("Tie", 0) >= 7)
    priority = analysis.get("priority", False)

    # Verifica gatilhos ativos com boa taxa — podem reforçar ou gerar sinal
    if not analysis.get("signal") and user_triggers:
        trigger_results = evaluate_triggers(game_history, user_triggers)
        for tr in trigger_results:
            if tr.get("active_now") and tr.get("rate", 0) >= min_probability and tr.get("total", 0) >= 5:
                analysis = {
                    "signal": tr["signal"],
                    "probability": tr["rate"],
                    "reason": f"Gatilho '{tr['pattern']}' → {tr['signal']} ({tr['rate']}% em {tr['total']} ocorrências)",
                    "strategy": "trigger",
                    "priority": tr["rate"] >= 75,
                }
                break

    if analysis.get("signal"):
        last_signal_strategy = analysis["strategy"]
        current_signal = {
            "id": f"signal_{int(time.time()*1000)}",
            "signal": analysis["signal"],
            "probability": analysis["probability"],
            "reason": analysis["reason"],
            "strategy": analysis["strategy"],
            "tie_warning": tie_warning,
            "priority": priority,
            "source": "Estatística"
        }
        signal_strategy_map[current_signal["id"]] = analysis["strategy"]
        logs.append({
            "type": "signal",
            "message": f"{'⚡ FORTE' if priority else 'SINAL'}: {analysis['signal']} ({analysis['probability']}%)",
            "timestamp": "now"
        })
    else:
        current_signal = None
        logs.append({
            "type": "analysis",
            "message": analysis["reason"],
            "timestamp": "now"
        })

    if len(logs) > 100:
        logs = logs[-100:]

    return {
        "analysis": analysis,
        "monte_carlo": monte_carlo,
        "drift": drift,
        "patterns": dict(list(patterns.items())[:10]),
        "percentages": percentages,
        "tie_warning": tie_warning,
        "priority": priority,
        "current_tie_watch": current_tie_watch
    }

@api_router.get("/state")
async def get_state():
    global game_history, stats, logs, current_signal, cooldown_results
    global strategy_stats, last_signal_strategy, last_activity, current_tie_watch, tie_watch_registry, resolved_signals, session_start_time
    # Auto-reset se passou mais de AUTO_RESET_MINUTES sem atividade
    elapsed = (time.time() - last_activity) / 60
    if elapsed > AUTO_RESET_MINUTES and len(game_history) > 0:
        game_history.clear()
        logs.clear()
        stats.update({"wins": 0, "losses": 0, "total_signals": 0})
        current_signal = None
        cooldown_results = 0
        last_signal_strategy = None
        current_tie_watch = None
        tie_watch_registry = {}
        resolved_signals = []
        session_start_time = time.time()
        for k in strategy_stats:
            strategy_stats[k] = {"wins": 0, "losses": 0, "total": 0}
        logs.append({"type": "system", "message": f"🔄 Reset automático após {int(elapsed)}min de inatividade", "timestamp": "now"})

    percentages = AnalysisEngine.calculate_percentages(game_history)
    patterns = AnalysisEngine.detect_patterns(game_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(game_history)
    drift = AnalysisEngine.detect_drift(game_history)
    
    trigger_results = evaluate_triggers(game_history, user_triggers)

    return {
        "history": game_history[-150:],
        "stats": stats,
        "logs": logs[-50:],
        "current_signal": current_signal,
        "active_strategy": active_strategy,
        "min_probability": min_probability,
        "auto_select": auto_select,
        "strategy_stats": strategy_stats,
        "percentages": percentages,
        "patterns": dict(list(patterns.items())[:10]),
        "monte_carlo": monte_carlo,
        "drift": drift,
        "tie_warning": percentages.get("Tie", 0) >= 7,
        "trigger_results": trigger_results,
        "session_token": session_token,
        "resolved_signals": resolved_signals[-100:],
        "current_tie_watch": current_tie_watch,
        "session_start_time": session_start_time,
    }

@api_router.post("/strategy")
async def change_strategy(request: Request):
    data = await request.json()
    global active_strategy
    
    if data.get("strategy") not in STRATEGY_MAP:
        raise HTTPException(status_code=400, detail=f"Estratégia inválida.")
    
    global current_signal
    active_strategy = data.get("strategy")
    current_signal = None  # limpa sinal ao trocar estratégia
    logs.append({
        "type": "config",
        "message": f"Estratégia alterada para: {active_strategy}",
        "timestamp": "now"
    })
    return {"success": True, "strategy": active_strategy}

@api_router.post("/probability")
async def change_probability(request: Request):
    data = await request.json()
    global min_probability
    prob = data.get("min_probability", 60)
    if prob < 40 or prob > 90:
        raise HTTPException(status_code=400, detail="Probabilidade deve estar entre 40 e 90")
    
    min_probability = prob
    logs.append({
        "type": "config",
        "message": f"Probabilidade mínima alterada para: {min_probability}%",
        "timestamp": "now"
    })
    
    return {"success": True, "min_probability": min_probability}

@api_router.post("/signal/feedback")
async def signal_feedback(request: Request):
    data = await request.json()
    global stats, pattern_weights, active_strategy, strategy_stats, last_signal_strategy, current_signal, signal_strategy_map, resolved_signals, current_tie_watch, tie_watch_registry
    current_signal = None  # libera o lock — sinal resolvido

    signal_id = data.get("signal_id")

    # Trava anti-duplicidade: se esse signal_id já foi contabilizado (ou nunca existiu), ignora
    if signal_id is not None and signal_id not in signal_strategy_map:
        return {"success": True, "stats": stats, "strategy_stats": strategy_stats, "duplicate": True}

    # Estratégia exata que gerou ESSE sinal (não depende de variável global que pode ter mudado)
    strat = signal_strategy_map.pop(signal_id, None) if signal_id else (last_signal_strategy or active_strategy)
    if not strat:
        strat = last_signal_strategy or active_strategy

    if data.get("result") == "win":
        stats["wins"] += 1
    else:
        stats["losses"] += 1
    stats["total_signals"] += 1

    # Atualiza placar da estratégia que gerou o sinal
    if strat in strategy_stats:
        strategy_stats[strat]["total"] += 1
        if data.get("result") == "win":
            strategy_stats[strat]["wins"] += 1
        else:
            strategy_stats[strat]["losses"] += 1

    # Se esse sinal venceu por causa de um Empate, e tinha um Empate Seco pendente
    # NO MESMO ROUND, resolve ele aqui também — mas SEM contar de novo no
    # placar (o placar já subiu acima). Usa o ID exato que o FRONT mandou
    # (não o ponteiro global current_tie_watch, que já pode ter avançado pro
    # próximo round antes desse feedback chegar — era a causa da contagem dupla).
    tie_watch_id = data.get("tie_watch_id")
    if data.get("actual_winner") == "Tie" and tie_watch_id and tie_watch_id in tie_watch_registry:
        auto_watch = tie_watch_registry.pop(tie_watch_id)
        if current_tie_watch and current_tie_watch.get("id") == tie_watch_id:
            current_tie_watch = None
        auto_number = auto_watch.get("number")
        auto_source = " + ".join(sorted(set(a["source"] for a in auto_watch.get("alerts", []))))
        auto_detail = " | ".join(a["reason"] for a in auto_watch.get("alerts", []))
        resolved_signals.append({
            "id": tie_watch_id,
            "kind": "tie_watch",
            "strategy": f"Empate Seco ({auto_source})" if auto_source else "Empate Seco",
            "result": "win",
            "gale": 0,
            "actual_winner": "Tie",
            "number": auto_number,
            "multiplier": get_tie_multiplier(auto_number),
            "detail": auto_detail,
            "counted_in_stats": False,
            "timestamp": now_hm()
        })

    # Detalhe clicável: como o sinal foi resolvido (direto/G1, e se veio de Empate)
    resolved_signals.append({
        "id": signal_id or f"resolved_{int(time.time()*1000)}",
        "strategy": strat,
        "entry_signal": data.get("entry_signal"),      # Player/Banker que a entrada pedia
        "result": data.get("result"),                  # win/loss
        "gale": data.get("gale", 0),                    # 0 = direto, 1 = venceu/perdeu no G1
        "actual_winner": data.get("actual_winner"),      # Player/Banker/Tie do resultado real
        "player": data.get("player"),
        "banker": data.get("banker"),
        "timestamp": now_hm()
    })
    if len(resolved_signals) > 50:
        resolved_signals = resolved_signals[-200:]

    logs.append({
        "type": "feedback",
        "message": f"{'✅ VITÓRIA' if data.get('result') == 'win' else '❌ DERROTA'} ({strat})",
        "timestamp": "now"
    })

    # Auto-seleção: avalia a cada 8 sinais resolvidos
    if auto_select and stats["total_signals"] % 8 == 0:
        best = _pick_best_strategy()
        if best and best != active_strategy:
            old = active_strategy
            active_strategy = best
            logs.append({
                "type": "auto_select",
                "message": f"🔄 Auto-seleção: {old} → {best} ({_strategy_rate(best)}% de acerto recente)",
                "timestamp": "now"
            })
            logger.info(f"Auto-seleção: {old} → {best}")

    # Ativa cooldown: 2 resultados de pausa antes do próximo sinal
    cooldown_results = 2

    return {"success": True, "stats": stats, "strategy_stats": strategy_stats}


@api_router.post("/tiewatch/feedback")
async def tiewatch_feedback(request: Request):
    """
    Resolve o Empate Seco 🟡. Só entra no placar geral quando BATE (win).
    Se não bater, fica registrado no histórico mas NÃO mexe no placar.
    Nunca entra no placar por estratégia (strategy_stats) — pra não
    bagunçar a auto-seleção de estratégia de cor.
    """
    data = await request.json()
    global stats, resolved_signals, current_tie_watch, tie_watch_registry

    watch_id = data.get("watch_id")
    if not watch_id or watch_id not in tie_watch_registry:
        return {"success": True, "stats": stats, "duplicate": True}

    watch = tie_watch_registry.pop(watch_id)
    if current_tie_watch and current_tie_watch.get("id") == watch_id:
        current_tie_watch = None

    result = data.get("result")  # win/loss
    number = watch.get("number")
    multiplier = data.get("multiplier") or get_tie_multiplier(number)
    source = " + ".join(sorted(set(a["source"] for a in watch.get("alerts", []))))
    detail = " | ".join(a["reason"] for a in watch.get("alerts", []))

    # Empate Seco só entra no placar E no histórico quando BATE (win).
    # Se não bater, não mexe no placar e nem aparece no histórico de sinais.
    counted = False
    if result == "win":
        stats["wins"] += 1
        stats["total_signals"] += 1
        counted = True

        resolved_signals.append({
            "id": watch_id,
            "kind": "tie_watch",
            "strategy": f"Empate Seco ({source})" if source else "Empate Seco",
            "result": result,
            "gale": 0,
            "actual_winner": "Tie",
            "number": number,
            "multiplier": multiplier,
            "detail": detail,
            "counted_in_stats": counted,
            "timestamp": now_hm()
        })
        if len(resolved_signals) > 200:
            resolved_signals = resolved_signals[-200:]

    logs.append({
        "type": "feedback",
        "message": f"{'✅ EMPATE SECO BATEU' if result == 'win' else '❌ Empate Seco não bateu'} (número {number}{f', {multiplier}x' if multiplier else ''})",
        "timestamp": "now"
    })

    return {"success": True, "stats": stats}


def _strategy_rate(strat: str) -> float:
    s = strategy_stats.get(strat, {})
    total = s.get("total", 0)
    if total == 0:
        return 0.0
    return round((s["wins"] / total) * 100, 1)


def _pick_best_strategy() -> Optional[str]:
    """Retorna a estratégia com maior taxa de acerto (mínimo 3 sinais pra contar)."""
    candidates = {
        k: _strategy_rate(k)
        for k, v in strategy_stats.items()
        if v["total"] >= 3
    }
    if not candidates:
        return None
    return max(candidates, key=candidates.get)

@api_router.post("/triggers")
async def save_triggers(request: Request):
    data = await request.json()
    """Recebe lista completa de gatilhos do frontend e salva."""
    global user_triggers
    user_triggers = data.get("triggers", [])
    return {"success": True, "count": len(user_triggers)}

@api_router.get("/triggers")
async def get_triggers():
    """Retorna gatilhos com stats calculadas."""
    results = evaluate_triggers(game_history, user_triggers)
    return {"triggers": results}

@api_router.post("/auto_select")
async def toggle_auto_select(request: Request):
    data = await request.json()
    global auto_select
    auto_select = data.get("enabled", True)
    logs.append({
        "type": "config",
        "message": f"Auto-seleção: {'ativada' if auto_select else 'desativada'}",
        "timestamp": "now"
    })
    return {"success": True, "auto_select": auto_select}

@api_router.post("/reset")
async def reset_stats():
    global stats, logs, strategy_stats, current_signal, cooldown_results, signal_strategy_map, resolved_signals, current_tie_watch, tie_watch_registry, session_start_time

    stats = {"wins": 0, "losses": 0, "total_signals": 0}
    strategy_stats = {
        "adaptive":  {"wins": 0, "losses": 0, "total": 0},
        "number":    {"wins": 0, "losses": 0, "total": 0},
        "number_pro":{"wins": 0, "losses": 0, "total": 0},
        "consensus": {"wins": 0, "losses": 0, "total": 0},
    }
    current_signal = None
    signal_strategy_map = {}
    resolved_signals = []
    current_tie_watch = None
    tie_watch_registry = {}
    cooldown_results = 0
    session_start_time = time.time()
    logs.append({
        "type": "reset",
        "message": "Estatísticas resetadas",
        "timestamp": "now"
    })
    return {"success": True, "stats": stats}

@api_router.post("/analyze")
async def force_analyze():
    analysis = await run_analysis()
    return analysis

# ============================================================
# FOOTBALL STUDIO — estado separado + rotas /api/fs/...
# ============================================================
fs_router = APIRouter(prefix="/api/fs")

fs_game_history: List[Dict[str, Any]] = []
fs_stats = {"wins": 0, "losses": 0, "total_signals": 0}
fs_logs: List[Dict[str, Any]] = []
fs_current_signal: Optional[Dict[str, Any]] = None
fs_active_strategy = "adaptive"
fs_min_probability = 60
fs_auto_select = True
fs_strategy_stats: Dict[str, Dict] = {
    "adaptive":  {"wins": 0, "losses": 0, "total": 0},
    "pressure":  {"wins": 0, "losses": 0, "total": 0},
    "consensus": {"wins": 0, "losses": 0, "total": 0},
    "fluxo":     {"wins": 0, "losses": 0, "total": 0},
}
fs_last_signal_strategy: Optional[str] = None
fs_signal_strategy_map: Dict[str, str] = {}
fs_cooldown_results: int = 0
fs_last_activity: float = time.time()
fs_session_token: str = str(int(time.time())) + "_fs"
fs_user_triggers: List[Dict[str, Any]] = []
fs_seq_min: int = 3  # mínimo de rodadas na sequência para sinalizar

# Normaliza Casa/Visitante/Empate → Player/Banker/Tie internamente
def _fs_translate_signal(signal: str) -> str:
    return {"Player": "Visitante", "Banker": "Casa", "Tie": "Empate"}.get(signal, signal)

def _fs_translate_reason(reason: str) -> str:
    import re
    reason = reason.replace("Player", "Visitante").replace("Banker", "Casa").replace("Tie", "Empate")
    reason = re.sub(r"(?<=')[PBT](?=[' ])|(?<= )[PBT](?=[ '])",
                    lambda m: {"P": "V", "B": "C", "T": "E"}.get(m.group(0), m.group(0)), reason)
    return reason

def _fs_normalize(winner: str) -> str:
    return {"Casa": "Banker", "Visitante": "Player", "Empate": "Tie"}.get(winner, winner)
    return {"Casa": "Banker", "Visitante": "Player", "Empate": "Tie"}.get(winner, winner)

async def fs_run_analysis():
    global fs_current_signal, fs_logs, fs_last_signal_strategy, fs_min_probability
    global fs_active_strategy, fs_cooldown_results

    if len(fs_game_history) < 5:
        return {"signal": None, "reason": "Aguardando mais resultados"}

    if fs_current_signal is not None:
        return {"signal": fs_current_signal, "reason": "Sinal pendente"}

    if fs_cooldown_results > 0:
        fs_cooldown_results -= 1
        return {"signal": None, "reason": "Cooldown"}

    # Usa o mesmo engine mas com histórico normalizado
    norm_history = [{"winner": _fs_normalize(r["winner"]), "player": r.get("player", 0), "banker": r.get("banker", 0)} for r in fs_game_history]

    global min_probability
    old_min = min_probability
    strategy_func = STRATEGY_MAP.get(fs_active_strategy, analyze_adaptive)
    min_probability = fs_min_probability

    # Para Sequencial, injeta seq_min no histórico como metadado
    if fs_active_strategy == "sequential":
        analysis = analyze_sequential(norm_history, seq_min=fs_seq_min)
    else:
        analysis = strategy_func(norm_history)
    min_probability = old_min

    patterns = AnalysisEngine.detect_patterns(norm_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(norm_history)
    drift = AnalysisEngine.detect_drift(norm_history)
    percentages = AnalysisEngine.calculate_percentages(norm_history)
    tie_warning = analysis.get("tie_warning", percentages.get("Tie", 0) >= 7)
    priority = analysis.get("priority", False)

    if analysis.get("signal"):
        fs_last_signal_strategy = analysis["strategy"]
        fs_current_signal = {
            "id": f"fs_signal_{int(time.time()*1000)}",
            "signal": analysis["signal"],
            "probability": analysis["probability"],
            "reason": _fs_translate_reason(analysis["reason"]),
            "strategy": analysis["strategy"],
            "tie_warning": tie_warning,
            "priority": priority,
            "source": "Estatística",
        }
        fs_signal_strategy_map[fs_current_signal["id"]] = analysis["strategy"]
        label = _fs_translate_signal(analysis["signal"])
        fs_logs.append({"type": "signal", "message": f"{'⚡ FORTE' if priority else 'SINAL'}: {label} ({analysis['probability']}%)", "timestamp": "now"})
    else:
        fs_current_signal = None
        fs_logs.append({"type": "analysis", "message": _fs_translate_reason(analysis["reason"]), "timestamp": "now"})

    if len(fs_logs) > 100:
        fs_logs[:] = fs_logs[-100:]

    return {
        "analysis": analysis,
        "monte_carlo": monte_carlo,
        "drift": drift,
        "patterns": dict(list(patterns.items())[:10]),
        "percentages": percentages,
        "tie_warning": tie_warning,
        "priority": priority,
    }

@fs_router.post("/historico")
async def fs_receive_historico(request: Request):
    data = await request.json()
    global fs_game_history, fs_logs, fs_current_signal, fs_cooldown_results, fs_last_activity, fs_session_token
    fs_last_activity = time.time()
    fs_session_token = str(int(time.time())) + "_fs"
    fs_game_history = []
    for r in data.get("resultados", []):
        w = r.get("winner", "")
        fs_game_history.append({
            "winner": _fs_normalize(w),
            "player": r.get("visitante", r.get("player", 0)),
            "banker": r.get("casa", r.get("banker", 0)),
        })
    if len(fs_game_history) > 150:
        fs_game_history = fs_game_history[-150:]
    fs_current_signal = None
    fs_cooldown_results = 0
    fs_logs.append({"type": "info", "message": f"FS Histórico recebido: {len(fs_game_history)} resultados", "timestamp": "now"})
    analysis = await fs_run_analysis()
    return {"success": True, "received": len(fs_game_history), "analysis": analysis}

@fs_router.post("/resultado")
async def fs_receive_resultado(request: Request):
    data = await request.json()
    global fs_game_history, fs_logs, fs_current_signal, fs_last_activity
    fs_last_activity = time.time()
    w = data.get("winner", "")
    new_result = {
        "winner": _fs_normalize(w),
        "player": data.get("visitante", data.get("player", 0)),
        "banker": data.get("casa", data.get("banker", 0)),
    }
    fs_game_history.append(new_result)
    if len(fs_game_history) > 150:
        fs_game_history[:] = fs_game_history[-150:]
    fs_logs.append({"type": "result", "message": f"FS Resultado: {w}", "timestamp": "now"})
    analysis = await fs_run_analysis()
    return {"success": True, "total": len(fs_game_history), "analysis": analysis}

@fs_router.get("/state")
async def fs_get_state():
    global fs_game_history, fs_stats, fs_logs, fs_current_signal, fs_last_activity, fs_session_token
    elapsed = (time.time() - fs_last_activity) / 60
    if elapsed > AUTO_RESET_MINUTES and len(fs_game_history) > 0:
        fs_game_history.clear()
        fs_logs.clear()
        fs_stats.update({"wins": 0, "losses": 0, "total_signals": 0})
        fs_current_signal = None

    norm_history = [{"winner": r["winner"], "player": r.get("player", 0), "banker": r.get("banker", 0)} for r in fs_game_history]
    percentages = AnalysisEngine.calculate_percentages(norm_history)
    patterns = AnalysisEngine.detect_patterns(norm_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(norm_history)
    drift = AnalysisEngine.detect_drift(norm_history)
    trigger_results = evaluate_triggers(norm_history, fs_user_triggers)

    return {
        "history": fs_game_history[-150:],
        "stats": fs_stats,
        "logs": fs_logs[-50:],
        "current_signal": fs_current_signal,
        "active_strategy": fs_active_strategy,
        "min_probability": fs_min_probability,
        "auto_select": fs_auto_select,
        "strategy_stats": fs_strategy_stats,
        "percentages": percentages,
        "patterns": dict(list(patterns.items())[:10]),
        "monte_carlo": monte_carlo,
        "drift": drift,
        "tie_warning": percentages.get("Tie", 0) >= 7,
        "trigger_results": trigger_results,
        "session_token": fs_session_token,
        "seq_min": fs_seq_min,
    }

@fs_router.post("/strategy")
async def fs_change_strategy(request: Request):
    data = await request.json()
    global fs_active_strategy, fs_current_signal
    if data.get("strategy") not in STRATEGY_MAP:
        raise HTTPException(status_code=400, detail="Estratégia inválida")
    fs_active_strategy = data.get("strategy")
    fs_current_signal = None
    return {"success": True, "strategy": fs_active_strategy}

@fs_router.post("/probability")
async def fs_change_probability(request: Request):
    data = await request.json()
    global fs_min_probability
    prob = data.get("min_probability", 60)
    if prob < 40 or prob > 90:
        raise HTTPException(status_code=400, detail="Probabilidade deve estar entre 40 e 90")
    fs_min_probability = prob
    return {"success": True, "min_probability": fs_min_probability}

@fs_router.post("/signal/feedback")
async def fs_signal_feedback(request: Request):
    data = await request.json()
    global fs_stats, fs_strategy_stats, fs_last_signal_strategy, fs_current_signal, fs_active_strategy, fs_auto_select, fs_cooldown_results, fs_signal_strategy_map
    fs_current_signal = None

    signal_id = data.get("signal_id")
    if signal_id is not None and signal_id not in fs_signal_strategy_map:
        return {"success": True, "stats": fs_stats, "duplicate": True}

    strat = fs_signal_strategy_map.pop(signal_id, None) if signal_id else None
    if not strat:
        strat = fs_last_signal_strategy or fs_active_strategy

    if data.get("result") == "win":
        fs_stats["wins"] += 1
    else:
        fs_stats["losses"] += 1
    fs_stats["total_signals"] += 1
    if strat in fs_strategy_stats:
        fs_strategy_stats[strat]["total"] += 1
        if data.get("result") == "win":
            fs_strategy_stats[strat]["wins"] += 1
        else:
            fs_strategy_stats[strat]["losses"] += 1
    fs_cooldown_results = 2
    return {"success": True, "stats": fs_stats}

@fs_router.post("/triggers")
async def fs_save_triggers(request: Request):
    data = await request.json()
    global fs_user_triggers
    fs_user_triggers = data.get("triggers", [])
    return {"success": True, "count": len(fs_user_triggers)}

@fs_router.get("/triggers")
async def fs_get_triggers():
    norm_history = [{"winner": r["winner"], "player": r.get("player", 0), "banker": r.get("banker", 0)} for r in fs_game_history]
    results = evaluate_triggers(norm_history, fs_user_triggers)
    return {"triggers": results}

@fs_router.post("/auto_select")
async def fs_toggle_auto_select(request: Request):
    data = await request.json()
    global fs_auto_select
    fs_auto_select = data.get("enabled", True)
    return {"success": True, "auto_select": fs_auto_select}

@fs_router.post("/seq_min")
async def fs_set_seq_min(request: Request):
    data = await request.json()
    global fs_seq_min
    val = data.get("seq_min", 3)
    if val < 2 or val > 5:
        raise HTTPException(status_code=400, detail="seq_min deve estar entre 2 e 5")
    fs_seq_min = val
    return {"success": True, "seq_min": fs_seq_min}

@fs_router.post("/reset")
async def fs_reset_stats():
    global fs_stats, fs_logs, fs_strategy_stats, fs_current_signal, fs_cooldown_results, fs_signal_strategy_map
    fs_stats = {"wins": 0, "losses": 0, "total_signals": 0}
    fs_strategy_stats = {
        "adaptive":  {"wins": 0, "losses": 0, "total": 0},
        "pressure":  {"wins": 0, "losses": 0, "total": 0},
        "consensus": {"wins": 0, "losses": 0, "total": 0},
    }
    fs_current_signal = None
    fs_signal_strategy_map = {}
    fs_cooldown_results = 0
    fs_logs.append({"type": "reset", "message": "FS Estatísticas resetadas", "timestamp": "now"})
    return {"success": True}

# Include router
app.include_router(api_router)
app.include_router(fs_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("AlphaSignal API iniciada")
    logger.info(f"Estratégia padrão: {active_strategy}")
    logger.info("Modo: análise estatística pura (sem IA externa)")
