from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Header
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import random
import time
from datetime import datetime, timedelta, timezone
import jwt as pyjwt
from jwt import PyJWKClient
import httpx

from collections import Counter
import asyncio
# IA removida — análise 100% estatística

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ============================================================
# Autenticação — Supabase Auth (mesmo projeto usado no MetaEdge).
# Cada usuário loga direto no Supabase (frontend), recebe um JWT, e manda
# esse JWT em toda requisição (Authorization: Bearer <token>).
#
# Esse projeto usa chaves ASSIMÉTRICAS (ES256) — não uma senha compartilhada
# (HS256). Por isso, em vez de comparar com um "segredo", o backend busca a
# CHAVE PÚBLICA de verificação direto do Supabase (endpoint JWKS), que é
# segura de expor (só serve pra conferir assinatura, não pra criar uma nova).
# O PyJWKClient já cuida de buscar e cachear essa chave sozinho.
# ============================================================
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://mcdxxombghjfyfofncik.supabase.co')
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

# Só usado no painel de administração (criar login novo) — NUNCA exposto
# pro frontend, fica só aqui no backend. Sem essa chave, /api/admin/* não funciona.
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()

# Só esse e-mail consegue acessar as rotas /api/admin/* (criar/gerenciar logins)
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '').strip().lower()

app = FastAPI(title="AlphaSignal API")
api_router = APIRouter(prefix="/api")
admin_router = APIRouter(prefix="/api/admin")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Confere se a service_role key só tem caracteres ASCII normais (ela é sempre
# um JWT — só letras, números, -, _ e . — nunca acento nem símbolo estranho).
# Se tiver algo fora disso, é sinal de corrupção no copiar/colar (geralmente
# um app trocou uma aspa ou hífen "esperto" por uma versão especial). Melhor
# avisar isso no log de boot do que só quebrar depois com erro confuso.
if SUPABASE_SERVICE_ROLE_KEY:
    try:
        SUPABASE_SERVICE_ROLE_KEY.encode("ascii")
    except UnicodeEncodeError as e:
        bad_char = SUPABASE_SERVICE_ROLE_KEY[e.start:e.end]
        logger.error(
            f"⚠️⚠️⚠️ SUPABASE_SERVICE_ROLE_KEY tem um caractere inválido na posição {e.start} "
            f"({bad_char!r}) — provavelmente corrompeu no copiar/colar. Copia a chave de novo "
            f"direto do Supabase (Settings → API → service_role) e cola de novo no Render."
        )

try:
    _jwks_client = PyJWKClient(SUPABASE_JWKS_URL, cache_keys=True, lifespan=600)
    logger.info(f"JWKS carregado de: {SUPABASE_JWKS_URL}")
except Exception as e:
    _jwks_client = None
    logger.error(f"⚠️ Falha ao inicializar JWKS client: {e}")

if not SUPABASE_SERVICE_ROLE_KEY:
    logger.warning("⚠️ SUPABASE_SERVICE_ROLE_KEY não configurado — o painel de admin não vai funcionar")
if not ADMIN_EMAIL:
    logger.warning("⚠️ ADMIN_EMAIL não configurado — ninguém vai conseguir acessar o painel de admin")


async def _verify_token(authorization: Optional[str]) -> Dict[str, Any]:
    """Decodifica e valida o JWT do Supabase, devolvendo o payload completo."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente. Faça login novamente.")

    token = authorization.split(" ", 1)[1]

    if _jwks_client is None:
        raise HTTPException(status_code=500, detail="Servidor não conseguiu carregar as chaves de autenticação. Tenta de novo em instantes.")

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
    except pyjwt.InvalidTokenError as e:
        logger.warning(f"Token inválido: {e}")
        raise HTTPException(status_code=401, detail="Token inválido.")
    except Exception as e:
        logger.warning(f"Erro ao validar token: {e}")
        raise HTTPException(status_code=401, detail="Token inválido.")

    return payload


async def get_current_user(authorization: Optional[str] = Header(None), x_device_id: Optional[str] = Header(None)) -> str:
    """
    Extrai e valida o JWT do Supabase mandado no header Authorization.
    Retorna o ID (uuid) do usuário — usado como chave pra achar o estado dele.

    Também confere o limite de dispositivos (header X-Device-Id, mandado
    pelo frontend) — se o aparelho não é conhecido e o usuário já atingiu o
    limite dele, barra o acesso mesmo com login/senha corretos.
    O e-mail de admin (ADMIN_EMAIL) é isento desse limite automaticamente.
    """
    payload = await _verify_token(authorization)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido.")

    email = (payload.get("email") or "").strip().lower()
    is_admin = bool(ADMIN_EMAIL) and email == ADMIN_EMAIL

    if x_device_id and not is_admin:
        allowed = await _register_device_if_allowed(user_id, x_device_id)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="Limite de dispositivos atingido para esse login. Fale com o suporte."
            )

    return user_id


async def get_current_admin(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Igual ao get_current_user, mas só deixa passar se o e-mail do token
    bater com o ADMIN_EMAIL configurado. Usado nas rotas /api/admin/*.
    """
    payload = await _verify_token(authorization)
    email = (payload.get("email") or "").strip().lower()
    if not ADMIN_EMAIL or email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")
    return payload


def _supabase_admin_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


async def _supabase_request(method: str, url: str, **kwargs) -> httpx.Response:
    """
    Chamada HTTP pro Supabase com tratamento de erro consistente. Sem isso,
    uma falha de rede (timeout, DNS, etc) vira uma exceção não tratada que
    quebra a resposta ANTES do CORS ser aplicado — o navegador então mostra
    "bloqueado por CORS", mascarando o erro real. Com isso, sempre volta um
    erro de verdade (502), com CORS certo, e com a mensagem real no log.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, timeout=15, **kwargs)
        return resp
    except Exception as e:
        logger.error(f"Erro de conexão com o Supabase ({method} {url}): {e}")
        raise HTTPException(status_code=502, detail=f"Erro de conexão com o Supabase: {e}")


async def _record_hourly_history(user_id: str, game: str, strategy: Optional[str], result: str, local_hour: Optional[int] = None):
    """
    Grava 1 linha no histórico de desempenho por horário — usado pra
    comparação de estratégia por hora do dia. Roda em segundo plano
    (fire-and-forget); se falhar, só loga um aviso, nunca quebra a resposta
    principal do feedback.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        return
    hour = local_hour if local_hour is not None and 0 <= local_hour <= 23 else int(time.strftime("%H"))
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/resolved_signals_history",
                headers=_supabase_admin_headers(),
                json={"user_id": user_id, "game": game, "strategy": strategy or "desconhecida", "result": result, "hour": hour},
                timeout=10,
            )
    except Exception as e:
        logger.warning(f"Falha ao gravar histórico de horário: {e}")


# ============================================================
# Limite de dispositivos — cada usuário só pode logar em N aparelhos
# diferentes ao mesmo tempo (configurável por cliente, padrão 1). Guardado
# nas tabelas user_devices e user_device_limits no Supabase (Postgres).
#
# Pra não bater no banco a cada poll (a cada 500ms!), mantém um cache em
# memória de alguns minutos por usuário — só recarrega quando expira ou
# quando um dispositivo novo aparece.
# ============================================================
device_cache: Dict[str, Dict[str, Any]] = {}
DEVICE_CACHE_TTL = 300  # 5 minutos

async def _load_user_devices(user_id: str, force: bool = False) -> Dict[str, Any]:
    cached = device_cache.get(user_id)
    if not force and cached and (time.time() - cached["loaded_at"]) < DEVICE_CACHE_TTL:
        return cached

    devices = set()
    max_devices = 1

    if SUPABASE_SERVICE_ROLE_KEY:
        try:
            async with httpx.AsyncClient() as client:
                devices_resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/user_devices",
                    headers=_supabase_admin_headers(),
                    params={"user_id": f"eq.{user_id}", "select": "device_id"},
                    timeout=10,
                )
                limit_resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/user_device_limits",
                    headers=_supabase_admin_headers(),
                    params={"user_id": f"eq.{user_id}", "select": "max_devices"},
                    timeout=10,
                )
            if devices_resp.status_code < 400:
                devices = {d["device_id"] for d in devices_resp.json()}
            if limit_resp.status_code < 400 and limit_resp.json():
                max_devices = limit_resp.json()[0].get("max_devices", 1)
        except Exception as e:
            logger.warning(f"Falha ao carregar dispositivos de {user_id}: {e}")

    result = {"devices": devices, "max_devices": max_devices, "loaded_at": time.time()}
    device_cache[user_id] = result
    return result


async def _touch_device(user_id: str, device_id: str):
    """Atualiza o 'visto por último' em segundo plano — não trava a requisição."""
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/user_devices",
                headers=_supabase_admin_headers(),
                params={"user_id": f"eq.{user_id}", "device_id": f"eq.{device_id}"},
                json={"last_seen": datetime.now(timezone.utc).isoformat()},
                timeout=10,
            )
    except Exception:
        pass


async def _register_device_if_allowed(user_id: str, device_id: str) -> bool:
    """
    True se esse dispositivo já é conhecido, ou se ainda há espaço pra
    registrar um novo. False se o limite já foi atingido.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        return True  # sem chave configurada, não dá pra checar — deixa passar

    info = await _load_user_devices(user_id)

    if device_id in info["devices"]:
        asyncio.create_task(_touch_device(user_id, device_id))
        return True

    if len(info["devices"]) >= info["max_devices"]:
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/user_devices",
                headers=_supabase_admin_headers(),
                json={"user_id": user_id, "device_id": device_id},
                timeout=10,
            )
        if resp.status_code < 400:
            info["devices"].add(device_id)
    except Exception as e:
        logger.warning(f"Falha ao registrar dispositivo {device_id} de {user_id}: {e}")

    return True


# ============================================================
# Estado por usuário — cada usuário tem sua própria "memória" isolada
# (histórico, placar, sinais). Guardado em memória do processo, num
# dicionário indexado pelo ID do usuário. Reinicia se o servidor reiniciar
# (igual antes), só que agora não cruza dados entre usuários diferentes.
# ============================================================
AUTO_RESET_MINUTES: int = 30  # reseta após X minutos sem uso

def new_user_state() -> Dict[str, Any]:
    now = time.time()
    return {
        # ---- Bac Bo ----
        "game_history": [],
        "stats": {"wins": 0, "losses": 0, "total_signals": 0},
        "logs": [],
        "resolved_signals": [],
        "current_signal": None,
        "current_tie_watch": None,
        "tie_watch_registry": {},
        "signal_strategy_map": {},
        "active_strategy": "consensus",
        "min_probability": 60,
        "auto_select": True,
        "number_window": NUMBER_20_WINDOW,  # tamanho da janela pra Número 20 / Número 20 PRO
        "cooldown_rounds": 2,  # quantas rodadas de "descanso" após um sinal ser resolvido
        "strategy_stats": {
            "adaptive":      {"wins": 0, "losses": 0, "total": 0},
            "number":        {"wins": 0, "losses": 0, "total": 0},
            "number_pro":    {"wins": 0, "losses": 0, "total": 0},
            "number_20":     {"wins": 0, "losses": 0, "total": 0},
            "number_20_pro": {"wins": 0, "losses": 0, "total": 0},
            "consensus":     {"wins": 0, "losses": 0, "total": 0},
        },
        "last_signal_strategy": None,
        "user_triggers": [],
        "cooldown_results": 0,
        "last_activity": now,
        "session_token": str(int(now)),
        "session_start_time": now,
        # ---- Football Studio ----
        "fs_game_history": [],
        "fs_stats": {"wins": 0, "losses": 0, "total_signals": 0},
        "fs_logs": [],
        "fs_current_signal": None,
        "fs_active_strategy": "adaptive",
        "fs_min_probability": 60,
        "fs_auto_select": True,
        "fs_strategy_stats": {
            "adaptive":  {"wins": 0, "losses": 0, "total": 0},
            "pressure":  {"wins": 0, "losses": 0, "total": 0},
            "consensus": {"wins": 0, "losses": 0, "total": 0},
        },
        "fs_last_signal_strategy": None,
        "fs_signal_strategy_map": {},
        "fs_user_triggers": [],
        "fs_cooldown_results": 0,
        "fs_last_activity": now,
        "fs_session_token": str(int(now)) + "_fs",
        "fs_seq_min": 3,
    }

user_states: Dict[str, Dict[str, Any]] = {}

def get_state(user_id: str) -> Dict[str, Any]:
    if user_id not in user_states:
        user_states[user_id] = new_user_state()
    return user_states[user_id]


# ============================================================
# Analysis Engine — funções puras, recebem history como parâmetro.
# Não guardam nada, não precisam de nenhuma mudança pro multi-usuário.
# ============================================================
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
# IMPORTANTE: agora recebem min_probability como parâmetro explícito, em vez
# de ler uma variável global — necessário pro multi-usuário, já que cada
# usuário pode ter configurado um mínimo diferente.

def analyze_adaptive(history: List[Dict], min_probability: float) -> Dict[str, Any]:
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


def analyze_pressure(history: List[Dict], min_probability: float) -> Dict[str, Any]:
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


def _number_pull_raw(history: List[Dict], min_probability: float, window: Optional[int] = None) -> Dict[str, Any]:
    """
    Cálculo puro (sem consenso): pega o número (2-12) do lado vencedor da
    última rodada e verifica, em todas as ocorrências desse mesmo número
    no histórico, o que veio na rodada SEGUINTE.

    Se `window` for passado, olha só as últimas N rodadas (ex: window=20)
    em vez do histórico inteiro.
    """
    if window:
        history = history[-window:] if len(history) > window else history

    clean = [r for r in history if r.get("winner") in ("Player", "Banker")]
    window_label = f" (últimas {window} rodadas)" if window else ""

    if len(clean) < 6:
        return {"signal": None, "probability": 0, "reason": f"Aguardando mais resultados para análise por número{window_label}"}

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
            "reason": f"Número {current_number} apareceu só {total}x{window_label} — dados insuficientes",
            "number": current_number, "pulls": pulls
        }

    best = "Player" if pulls["Player"] > pulls["Banker"] else "Banker"
    probability = round((max(pulls["Player"], pulls["Banker"]) / total) * 100, 1)
    base_msg = f"Número {current_number} apareceu {total}x{window_label} e puxou {best} {pulls[best]}x ({probability}%)"

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


def analyze_number(history: List[Dict], min_probability: float) -> Dict[str, Any]:
    """
    Estratégia Número 🎲 (solo): usa só o critério do número puxando cor,
    sem exigir concordância de nenhuma outra estratégia.
    """
    raw = _number_pull_raw(history, min_probability)
    raw["strategy"] = "number"
    return raw


def analyze_number_pro(history: List[Dict], min_probability: float) -> Dict[str, Any]:
    """
    Estratégia Número PRO 🎲: igual à Número, mas só confirma o sinal se a
    estratégia Adaptativo concordar com a mesma cor (consenso obrigatório).
    """
    raw = _number_pull_raw(history, min_probability)
    number, pulls = raw.get("number"), raw.get("pulls")

    if not raw["signal"]:
        return {**raw, "strategy": "number_pro"}

    adaptive = analyze_adaptive(history, min_probability)
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


NUMBER_20_WINDOW = 20  # valor padrão — cada usuário pode ajustar em state["number_window"]

def analyze_number_20(history: List[Dict], min_probability: float, window: int = NUMBER_20_WINDOW) -> Dict[str, Any]:
    """
    Estratégia Número 20 🎯 (solo): igual à Número, mas olha só as últimas
    N rodadas em vez do histórico inteiro — reage mais rápido a mudança
    de padrão da mesa. N é configurável (padrão 20).
    """
    raw = _number_pull_raw(history, min_probability, window=window)
    raw["strategy"] = "number_20"
    return raw


def analyze_number_20_pro(history: List[Dict], min_probability: float, window: int = NUMBER_20_WINDOW) -> Dict[str, Any]:
    """
    Estratégia Número 20 PRO 🎯: igual à Número 20, mas só confirma o sinal
    se a estratégia Adaptativo concordar com a mesma cor (consenso obrigatório).
    """
    raw = _number_pull_raw(history, min_probability, window=window)
    number, pulls = raw.get("number"), raw.get("pulls")

    if not raw["signal"]:
        return {**raw, "strategy": "number_20_pro"}

    adaptive = analyze_adaptive(history, min_probability)
    best, probability, total = raw["best"], raw["probability"], raw["total"]
    base_msg = f"Número {number} apareceu {total}x (últimas {window} rodadas) e puxou {best} {pulls[best]}x ({probability}%)"

    if adaptive["signal"] != best:
        return {
            "signal": None, "probability": probability,
            "reason": f"{base_msg}, mas o Adaptativo aponta outro lado — sem consenso, aguardando",
            "strategy": "number_20_pro", "number": number, "pulls": pulls
        }

    return {
        "signal": best,
        "probability": probability,
        "reason": f"{base_msg} + Adaptativo concorda — CONSENSO, entrada {best}",
        "strategy": "number_20_pro", "number": number, "pulls": pulls
    }


def analyze_consensus(history: List[Dict], min_probability: float) -> Dict[str, Any]:
    """
    Roda Adaptativo + Pressure + Tendência de curto prazo.
    - 2 de 3 concordam → sinal normal
    - 3 de 3 concordam → sinal FORTE (priority=True)
    Tie em alta (>10%) é avisado mas não bloqueia o sinal.
    """
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

    adaptive = analyze_adaptive(history, min_probability)
    pressure = analyze_pressure(history, min_probability)

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
        "priority": priority,
        "tie_warning": tie_warning
    }


def analyze_sequential(history: List[Dict], min_probability: float, seq_min: int = 3) -> Dict[str, Any]:
    """
    Sequencial: ignora Empates, detecta sequência de 3+ iguais seguida de alternância
    e aposta na cor principal (que apareceu mais).
    """
    clean = [r for r in history if r.get("winner") not in ("Tie", "Empate")]

    if len(clean) < 5:
        return {
            "signal": None, "probability": 0,
            "reason": "Aguardando mais resultados (ignorando Empates)",
            "strategy": "sequential"
        }

    recent = clean[-10:]

    current = recent[-1]["winner"]
    streak = 1
    for i in range(len(recent) - 2, -1, -1):
        if recent[i]["winner"] == current:
            streak += 1
        else:
            break

    if len(recent) >= 4:
        prev_idx = len(recent) - 1 - streak
        if prev_idx >= 0:
            prev_winner = recent[prev_idx]["winner"]
            if prev_winner != current and streak >= 1:
                last8 = recent[-8:]
                count = Counter([r["winner"] for r in last8])
                main_color = count.most_common(1)[0][0]
                main_count = count.most_common(1)[0][1]
                total = len(last8)
                prob = round((main_count / total) * 100, 1)

                if prob >= min_probability and main_count >= seq_min:
                    opposite = "Banker" if main_color == "Player" else "Player"
                    if streak >= seq_min:
                        return {
                            "signal": opposite,
                            "probability": min(90, 50 + streak * 8),
                            "reason": f"Sequência de {streak}x {main_color} — aguardando alternância para {opposite}",
                            "strategy": "sequential"
                        }
                    elif streak == 1 and prev_winner == main_color:
                        return {
                            "signal": main_color,
                            "probability": prob,
                            "reason": f"Alternância detectada — cor principal {main_color} ({prob}%)",
                            "strategy": "sequential"
                        }

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


def analyze_alternancia(history: List[Dict], min_probability: float) -> Dict[str, Any]:
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

    if len(recent) >= 6:
        r = recent[-6:]
        dupla_ok2 = (
            r[0] == r[1] and
            r[2] == r[3] and
            r[4] == r[5] and
            r[0] != r[2] and
            r[2] != r[4] and
            r[0] == r[4]
        )

        if dupla_ok2:
            opposite = "Banker" if recent[-1] == "Player" else "Player"
            return {
                "signal": opposite if 72 >= min_probability else None,
                "probability": 72,
                "reason": f"Duplas seguidas (2x2) — bloco {recent[-1]} fechado → entra {opposite}",
                "strategy": "alternancia"
            }

        if len(recent) >= 4:
            r4 = recent[-4:]
            if r4[0] == r4[1] and r4[2] == r4[3] and r4[0] != r4[2]:
                signal = r4[0]
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
    alerta separado.
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
    "number_20": analyze_number_20,
    "number_20_pro": analyze_number_20_pro,
    "consensus": analyze_consensus,
    "sequential": analyze_sequential,
    "alternancia": analyze_alternancia,
}

def call_strategy(name: str, history: List[Dict], min_probability: float, seq_min: int = 3, number_window: int = NUMBER_20_WINDOW, default: str = "consensus") -> Dict[str, Any]:
    """Chama a função de estratégia certa, passando seq_min ou number_window só pra quem precisa."""
    func = STRATEGY_MAP.get(name, STRATEGY_MAP[default])
    if func is analyze_sequential:
        return func(history, min_probability, seq_min)
    if func in (analyze_number_20, analyze_number_20_pro):
        return func(history, min_probability, number_window)
    return func(history, min_probability)


def evaluate_triggers(history: List[Dict], triggers: List[Dict]) -> List[Dict]:
    """Avalia cada gatilho ativo no histórico e retorna stats + se está ativo agora."""
    if len(history) < 4:
        return []

    results = []
    recent = [r["winner"][0] for r in history if r["winner"] != "Tie"][-3:]
    current_seq = " ".join(recent).upper()

    for t in triggers:
        if not t.get("active", True):
            results.append({**t, "hits": 0, "total": 0, "rate": 0, "active_now": False})
            continue

        pattern = t["pattern"].strip().upper()
        signal = t["signal"]
        pat_parts = pattern.split()
        pat_len = len(pat_parts)

        if pat_len < 1:
            continue

        seq = [r["winner"][0].upper() for r in history if r["winner"] != "Tie"]
        hits = 0
        total = 0
        for i in range(len(seq) - pat_len):
            window = seq[i:i + pat_len]
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


def _strategy_rate(strategy_stats: Dict[str, Dict], strat: str) -> float:
    s = strategy_stats.get(strat, {})
    total = s.get("total", 0)
    if total == 0:
        return 0.0
    return round((s["wins"] / total) * 100, 1)


def _pick_best_strategy(strategy_stats: Dict[str, Dict]) -> Optional[str]:
    """Retorna a estratégia com maior taxa de acerto (mínimo 3 sinais pra contar)."""
    candidates = {
        k: _strategy_rate(strategy_stats, k)
        for k, v in strategy_stats.items()
        if v["total"] >= 3
    }
    if not candidates:
        return None
    return max(candidates, key=candidates.get)


async def run_analysis(state: Dict[str, Any]) -> Dict[str, Any]:
    game_history = state["game_history"]

    if len(game_history) < 5:
        return {"signal": None, "reason": "Aguardando mais resultados"}

    # Empate Seco 🟡 — independente do sinal de cor, roda sempre que houver resultado novo
    tw = analyze_tie_watch(game_history)
    state["current_tie_watch"] = None
    if tw["active"]:
        watch_id = f"tiewatch_{int(time.time()*1000)}"
        last = game_history[-1]
        number = last.get("player") if last.get("winner") in ("Player", "Tie") else last.get("banker")
        state["current_tie_watch"] = {
            "id": watch_id,
            "number": number,
            "alerts": tw["alerts"],
        }
        state["tie_watch_registry"][watch_id] = state["current_tie_watch"]
        state["logs"].append({
            "type": "analysis",
            "message": "🟡 Empate Seco ativo: " + " | ".join(a["reason"] for a in tw["alerts"]),
            "timestamp": "now"
        })

    # LOCK: sinal ativo não resolvido → não gera novo
    if state["current_signal"] is not None:
        state["logs"].append({
            "type": "analysis",
            "message": "⏳ Aguardando resolução do sinal anterior...",
            "timestamp": "now"
        })
        if len(state["logs"]) > 100:
            state["logs"] = state["logs"][-100:]
        return {"signal": state["current_signal"], "reason": "Sinal pendente"}

    # COOLDOWN: após win/loss, espera 1 resultado antes de gerar novo sinal
    if state["cooldown_results"] > 0:
        state["cooldown_results"] -= 1
        state["logs"].append({
            "type": "analysis",
            "message": "⏸️ Cooldown — aguardando próximo resultado para analisar...",
            "timestamp": "now"
        })
        if len(state["logs"]) > 100:
            state["logs"] = state["logs"][-100:]
        return {"signal": None, "reason": "Cooldown"}

    analysis = call_strategy(state["active_strategy"], game_history, state["min_probability"], number_window=state["number_window"])

    patterns = AnalysisEngine.detect_patterns(game_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(game_history)
    drift = AnalysisEngine.detect_drift(game_history)
    percentages = AnalysisEngine.calculate_percentages(game_history)
    tie_warning = analysis.get("tie_warning", percentages.get("Tie", 0) >= 7)
    priority = analysis.get("priority", False)

    # Verifica gatilhos ativos com boa taxa — podem reforçar ou gerar sinal
    if not analysis.get("signal") and state["user_triggers"]:
        trigger_results = evaluate_triggers(game_history, state["user_triggers"])
        for tr in trigger_results:
            if tr.get("active_now") and tr.get("rate", 0) >= state["min_probability"] and tr.get("total", 0) >= 5:
                analysis = {
                    "signal": tr["signal"],
                    "probability": tr["rate"],
                    "reason": f"Gatilho '{tr['pattern']}' → {tr['signal']} ({tr['rate']}% em {tr['total']} ocorrências)",
                    "strategy": "trigger",
                    "priority": tr["rate"] >= 75,
                }
                break

    if analysis.get("signal"):
        state["last_signal_strategy"] = analysis["strategy"]
        state["current_signal"] = {
            "id": f"signal_{int(time.time()*1000)}",
            "signal": analysis["signal"],
            "probability": analysis["probability"],
            "reason": analysis["reason"],
            "strategy": analysis["strategy"],
            "tie_warning": tie_warning,
            "priority": priority,
            "source": "Estatística"
        }
        state["signal_strategy_map"][state["current_signal"]["id"]] = analysis["strategy"]
        state["logs"].append({
            "type": "signal",
            "message": f"{'⚡ FORTE' if priority else 'SINAL'}: {analysis['signal']} ({analysis['probability']}%)",
            "timestamp": "now"
        })
    else:
        state["current_signal"] = None
        state["logs"].append({
            "type": "analysis",
            "message": analysis["reason"],
            "timestamp": "now"
        })

    if len(state["logs"]) > 100:
        state["logs"] = state["logs"][-100:]

    return {
        "analysis": analysis,
        "monte_carlo": monte_carlo,
        "drift": drift,
        "patterns": dict(list(patterns.items())[:10]),
        "percentages": percentages,
        "tie_warning": tie_warning,
        "priority": priority,
        "current_tie_watch": state["current_tie_watch"]
    }


# ============================================================
# API Endpoints — Bac Bo
# ============================================================
@api_router.get("/")
async def root():
    return {"message": "AlphaSignal API v2.0 (multi-usuário)"}


@api_router.post("/session/start")
async def session_start(user: str = Depends(get_current_user)):
    """
    Chamado pelo front logo depois do login no Supabase. Zera o estado desse
    usuário pra começar do zero (igual o /login antigo fazia).
    """
    state = get_state(user)
    now = time.time()
    state["game_history"] = []
    state["logs"] = []
    state["current_signal"] = None
    state["cooldown_results"] = 0
    state["session_token"] = str(int(now))
    state["session_start_time"] = now
    state["signal_strategy_map"] = {}
    state["resolved_signals"] = []
    state["current_tie_watch"] = None
    state["tie_watch_registry"] = {}
    state["fs_game_history"] = []
    state["fs_logs"] = []
    state["fs_current_signal"] = None
    state["fs_cooldown_results"] = 0
    state["fs_session_token"] = str(int(now)) + "_fs"
    state["fs_signal_strategy_map"] = {}
    return {"success": True, "message": "Sessão iniciada"}


@api_router.post("/historico")
async def receive_historico(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["last_activity"] = time.time()
    state["session_token"] = str(int(time.time()))

    history = []
    for r in data.get("resultados", []):
        history.append({
            "winner": r.get("winner", ""),
            "player": r.get("player", 0),
            "banker": r.get("banker", 0)
        })
    if len(history) > 150:
        history = history[-150:]
    state["game_history"] = history

    state["current_signal"] = None
    state["cooldown_results"] = 0

    state["logs"].append({
        "type": "info",
        "message": f"Histórico inicial recebido: {len(state['game_history'])} resultados",
        "timestamp": "now"
    })

    analysis = await run_analysis(state)

    return {
        "success": True,
        "received": len(state["game_history"]),
        "analysis": analysis
    }


@api_router.post("/resultado")
async def receive_resultado(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["last_activity"] = time.time()

    new_result = {
        "winner": data.get("winner", ""),
        "player": data.get("player", 0),
        "banker": data.get("banker", 0)
    }

    state["game_history"].append(new_result)
    if len(state["game_history"]) > 150:
        state["game_history"] = state["game_history"][-150:]

    state["logs"].append({
        "type": "result",
        "message": f"Novo resultado: {new_result['winner']} (P:{new_result['player']} B:{new_result['banker']})",
        "timestamp": "now"
    })

    analysis = await run_analysis(state)

    return {
        "success": True,
        "total": len(state["game_history"]),
        "analysis": analysis
    }


@api_router.get("/state")
async def get_full_state(user: str = Depends(get_current_user)):
    state = get_state(user)

    # Auto-reset se passou mais de AUTO_RESET_MINUTES sem atividade
    elapsed = (time.time() - state["last_activity"]) / 60
    if elapsed > AUTO_RESET_MINUTES and len(state["game_history"]) > 0:
        state["game_history"] = []
        state["logs"] = []
        state["stats"] = {"wins": 0, "losses": 0, "total_signals": 0}
        state["current_signal"] = None
        state["cooldown_results"] = 0
        state["last_signal_strategy"] = None
        state["current_tie_watch"] = None
        state["tie_watch_registry"] = {}
        state["resolved_signals"] = []
        state["session_start_time"] = time.time()
        for k in state["strategy_stats"]:
            state["strategy_stats"][k] = {"wins": 0, "losses": 0, "total": 0}
        state["logs"].append({"type": "system", "message": f"🔄 Reset automático após {int(elapsed)}min de inatividade", "timestamp": "now"})

    game_history = state["game_history"]
    percentages = AnalysisEngine.calculate_percentages(game_history)
    patterns = AnalysisEngine.detect_patterns(game_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(game_history)
    drift = AnalysisEngine.detect_drift(game_history)

    trigger_results = evaluate_triggers(game_history, state["user_triggers"])

    return {
        "history": game_history[-150:],
        "stats": state["stats"],
        "logs": state["logs"][-50:],
        "current_signal": state["current_signal"],
        "active_strategy": state["active_strategy"],
        "min_probability": state["min_probability"],
        "number_window": state["number_window"],
        "cooldown_rounds": state["cooldown_rounds"],
        "auto_select": state["auto_select"],
        "strategy_stats": state["strategy_stats"],
        "percentages": percentages,
        "patterns": dict(list(patterns.items())[:10]),
        "monte_carlo": monte_carlo,
        "drift": drift,
        "tie_warning": percentages.get("Tie", 0) >= 7,
        "trigger_results": trigger_results,
        "session_token": state["session_token"],
        "resolved_signals": state["resolved_signals"][-100:],
        "current_tie_watch": state["current_tie_watch"],
        "session_start_time": state["session_start_time"],
    }


@api_router.post("/strategy")
async def change_strategy(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)

    if data.get("strategy") not in STRATEGY_MAP:
        raise HTTPException(status_code=400, detail="Estratégia inválida.")

    state["active_strategy"] = data.get("strategy")
    state["current_signal"] = None
    state["logs"].append({
        "type": "config",
        "message": f"Estratégia alterada para: {state['active_strategy']}",
        "timestamp": "now"
    })
    return {"success": True, "strategy": state["active_strategy"]}


@api_router.post("/probability")
async def change_probability(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    prob = data.get("min_probability", 60)
    if prob < 40 or prob > 90:
        raise HTTPException(status_code=400, detail="Probabilidade deve estar entre 40 e 90")

    state["min_probability"] = prob
    state["logs"].append({
        "type": "config",
        "message": f"Probabilidade mínima alterada para: {state['min_probability']}%",
        "timestamp": "now"
    })

    return {"success": True, "min_probability": state["min_probability"]}


@api_router.post("/number_window")
async def change_number_window(request: Request, user: str = Depends(get_current_user)):
    """Muda quantas rodadas as estratégias Número 20 / Número 20 PRO olham pra trás."""
    data = await request.json()
    state = get_state(user)
    window = data.get("number_window", NUMBER_20_WINDOW)
    if window < 5 or window > 100:
        raise HTTPException(status_code=400, detail="Janela deve estar entre 5 e 100 rodadas")

    state["number_window"] = window
    state["logs"].append({
        "type": "config",
        "message": f"Janela da estratégia Número alterada para: últimas {window} rodadas",
        "timestamp": "now"
    })
    return {"success": True, "number_window": state["number_window"]}


@api_router.post("/cooldown")
async def change_cooldown(request: Request, user: str = Depends(get_current_user)):
    """Muda quantas rodadas de 'descanso' o app espera depois de um sinal resolvido."""
    data = await request.json()
    state = get_state(user)
    rounds = data.get("cooldown_rounds", 2)
    if rounds < 0 or rounds > 10:
        raise HTTPException(status_code=400, detail="Cooldown deve estar entre 0 e 10 rodadas")

    state["cooldown_rounds"] = rounds
    state["logs"].append({
        "type": "config",
        "message": f"Cooldown alterado para: {rounds} rodada(s) após cada sinal",
        "timestamp": "now"
    })
    return {"success": True, "cooldown_rounds": state["cooldown_rounds"]}


@api_router.post("/signal/feedback")
async def signal_feedback(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["current_signal"] = None  # libera o lock — sinal resolvido

    signal_id = data.get("signal_id")

    # Trava anti-duplicidade: se esse signal_id já foi contabilizado (ou nunca existiu), ignora
    if signal_id is not None and signal_id not in state["signal_strategy_map"]:
        return {"success": True, "stats": state["stats"], "strategy_stats": state["strategy_stats"], "duplicate": True}

    strat = state["signal_strategy_map"].pop(signal_id, None) if signal_id else (state["last_signal_strategy"] or state["active_strategy"])
    if not strat:
        strat = state["last_signal_strategy"] or state["active_strategy"]

    if data.get("result") == "win":
        state["stats"]["wins"] += 1
    else:
        state["stats"]["losses"] += 1
    state["stats"]["total_signals"] += 1

    if strat in state["strategy_stats"]:
        state["strategy_stats"][strat]["total"] += 1
        if data.get("result") == "win":
            state["strategy_stats"][strat]["wins"] += 1
        else:
            state["strategy_stats"][strat]["losses"] += 1

    # Grava no histórico de desempenho por horário (não trava a resposta)
    asyncio.create_task(_record_hourly_history(user, "bacbo", strat, data.get("result"), data.get("local_hour")))

    # Se esse sinal venceu por causa de um Empate, e tinha um Empate Seco pendente
    # NO MESMO ROUND, resolve ele aqui também — mas SEM contar de novo no placar.
    tie_watch_id = data.get("tie_watch_id")
    if data.get("actual_winner") == "Tie" and tie_watch_id and tie_watch_id in state["tie_watch_registry"]:
        auto_watch = state["tie_watch_registry"].pop(tie_watch_id)
        if state["current_tie_watch"] and state["current_tie_watch"].get("id") == tie_watch_id:
            state["current_tie_watch"] = None
        auto_number = auto_watch.get("number")
        auto_source = " + ".join(sorted(set(a["source"] for a in auto_watch.get("alerts", []))))
        auto_detail = " | ".join(a["reason"] for a in auto_watch.get("alerts", []))
        state["resolved_signals"].append({
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

    state["resolved_signals"].append({
        "id": signal_id or f"resolved_{int(time.time()*1000)}",
        "strategy": strat,
        "entry_signal": data.get("entry_signal"),
        "result": data.get("result"),
        "gale": data.get("gale", 0),
        "actual_winner": data.get("actual_winner"),
        "player": data.get("player"),
        "banker": data.get("banker"),
        "timestamp": now_hm()
    })
    if len(state["resolved_signals"]) > 200:
        state["resolved_signals"] = state["resolved_signals"][-200:]

    state["logs"].append({
        "type": "feedback",
        "message": f"{'✅ VITÓRIA' if data.get('result') == 'win' else '❌ DERROTA'} ({strat})",
        "timestamp": "now"
    })

    # Auto-seleção: avalia a cada 8 sinais resolvidos
    if state["auto_select"] and state["stats"]["total_signals"] % 8 == 0:
        best = _pick_best_strategy(state["strategy_stats"])
        if best and best != state["active_strategy"]:
            old = state["active_strategy"]
            state["active_strategy"] = best
            state["logs"].append({
                "type": "auto_select",
                "message": f"🔄 Auto-seleção: {old} → {best} ({_strategy_rate(state['strategy_stats'], best)}% de acerto recente)",
                "timestamp": "now"
            })
            logger.info(f"[{user}] Auto-seleção: {old} → {best}")

    state["cooldown_results"] = state["cooldown_rounds"]

    return {"success": True, "stats": state["stats"], "strategy_stats": state["strategy_stats"]}


@api_router.post("/tiewatch/feedback")
async def tiewatch_feedback(request: Request, user: str = Depends(get_current_user)):
    """
    Resolve o Empate Seco 🟡. Só entra no placar geral quando BATE (win).
    Se não bater, fica registrado no histórico mas NÃO mexe no placar.
    Nunca entra no placar por estratégia (strategy_stats).
    """
    data = await request.json()
    state = get_state(user)

    watch_id = data.get("watch_id")
    if not watch_id or watch_id not in state["tie_watch_registry"]:
        return {"success": True, "stats": state["stats"], "duplicate": True}

    watch = state["tie_watch_registry"].pop(watch_id)
    if state["current_tie_watch"] and state["current_tie_watch"].get("id") == watch_id:
        state["current_tie_watch"] = None

    result = data.get("result")
    number = watch.get("number")
    multiplier = data.get("multiplier") or get_tie_multiplier(number)
    source = " + ".join(sorted(set(a["source"] for a in watch.get("alerts", []))))
    detail = " | ".join(a["reason"] for a in watch.get("alerts", []))

    counted = False
    if result == "win":
        state["stats"]["wins"] += 1
        state["stats"]["total_signals"] += 1
        counted = True

        state["resolved_signals"].append({
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
        if len(state["resolved_signals"]) > 200:
            state["resolved_signals"] = state["resolved_signals"][-200:]

    state["logs"].append({
        "type": "feedback",
        "message": f"{'✅ EMPATE SECO BATEU' if result == 'win' else '❌ Empate Seco não bateu'} (número {number}{f', {multiplier}x' if multiplier else ''})",
        "timestamp": "now"
    })

    return {"success": True, "stats": state["stats"]}


@api_router.post("/triggers")
async def save_triggers(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["user_triggers"] = data.get("triggers", [])
    return {"success": True, "count": len(state["user_triggers"])}


@api_router.get("/triggers")
async def get_triggers(user: str = Depends(get_current_user)):
    state = get_state(user)
    results = evaluate_triggers(state["game_history"], state["user_triggers"])
    return {"triggers": results}


@api_router.post("/auto_select")
async def toggle_auto_select(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["auto_select"] = data.get("enabled", True)
    state["logs"].append({
        "type": "config",
        "message": f"Auto-seleção: {'ativada' if state['auto_select'] else 'desativada'}",
        "timestamp": "now"
    })
    return {"success": True, "auto_select": state["auto_select"]}


@api_router.post("/reset")
async def reset_stats(user: str = Depends(get_current_user)):
    state = get_state(user)

    state["stats"] = {"wins": 0, "losses": 0, "total_signals": 0}
    state["strategy_stats"] = {
        "adaptive":      {"wins": 0, "losses": 0, "total": 0},
        "number":        {"wins": 0, "losses": 0, "total": 0},
        "number_pro":    {"wins": 0, "losses": 0, "total": 0},
        "number_20":     {"wins": 0, "losses": 0, "total": 0},
        "number_20_pro": {"wins": 0, "losses": 0, "total": 0},
        "consensus":     {"wins": 0, "losses": 0, "total": 0},
    }
    state["current_signal"] = None
    state["signal_strategy_map"] = {}
    state["resolved_signals"] = []
    state["current_tie_watch"] = None
    state["tie_watch_registry"] = {}
    state["cooldown_results"] = 0
    state["session_start_time"] = time.time()
    state["logs"].append({
        "type": "reset",
        "message": "Estatísticas resetadas",
        "timestamp": "now"
    })
    return {"success": True, "stats": state["stats"]}


@api_router.post("/analyze")
async def force_analyze(user: str = Depends(get_current_user)):
    state = get_state(user)
    analysis = await run_analysis(state)
    return analysis


@api_router.get("/hourly-performance")
async def get_hourly_performance(game: str = "bacbo", days: int = 7, user: str = Depends(get_current_user)):
    """
    Desempenho (win rate) por hora do dia, olhando os últimos N dias (padrão
    7). Ajuda a ver se alguma estratégia performa melhor em certos horários.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        return {"hourly": [], "days": days}

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    resp = await _supabase_request(
        "GET", f"{SUPABASE_URL}/rest/v1/resolved_signals_history",
        headers=_supabase_admin_headers(),
        params={
            "user_id": f"eq.{user}",
            "game": f"eq.{game}",
            "created_at": f"gte.{since}",
            "select": "hour,result",
        },
    )

    if resp.status_code >= 400:
        logger.error(f"Supabase (hourly-performance) {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=resp.status_code, detail="Falha ao buscar histórico de horários.")

    rows = resp.json()
    buckets = {h: {"wins": 0, "losses": 0} for h in range(24)}
    for r in rows:
        h = r.get("hour")
        if h is None or h not in buckets:
            continue
        if r.get("result") == "win":
            buckets[h]["wins"] += 1
        else:
            buckets[h]["losses"] += 1

    hourly = []
    for h in range(24):
        total = buckets[h]["wins"] + buckets[h]["losses"]
        rate = round((buckets[h]["wins"] / total) * 100, 1) if total > 0 else None
        hourly.append({"hour": h, "wins": buckets[h]["wins"], "losses": buckets[h]["losses"], "total": total, "rate": rate})

    return {"hourly": hourly, "days": days}


# ============================================================
# FOOTBALL STUDIO — estado separado (dentro do mesmo state por usuário) +
# rotas /api/fs/...
# ============================================================
fs_router = APIRouter(prefix="/api/fs")

FS_STRATEGY_MAP = {
    "adaptive": analyze_adaptive,
    "sequential": analyze_sequential,
    "alternancia": analyze_alternancia,
}

def _fs_normalize(winner: str) -> str:
    w = (winner or "").strip().lower()
    if w in ("casa", "home", "banker", "b"):
        return "Banker"
    if w in ("visitante", "away", "player", "p"):
        return "Player"
    if w in ("empate", "tie", "draw", "t"):
        return "Tie"
    return winner


def _fs_translate_signal(signal: Optional[str]) -> str:
    if signal == "Banker":
        return "Casa"
    if signal == "Player":
        return "Visitante"
    if signal == "Tie":
        return "Empate"
    return signal or ""


def _fs_translate_reason(reason: str) -> str:
    if not reason:
        return reason
    return (
        reason.replace("Player", "Visitante")
              .replace("Banker", "Casa")
    )


async def fs_run_analysis(state: Dict[str, Any]) -> Dict[str, Any]:
    fs_game_history = state["fs_game_history"]

    if len(fs_game_history) < 5:
        return {"signal": None, "reason": "Aguardando mais resultados"}

    if state["fs_current_signal"] is not None:
        return {"signal": state["fs_current_signal"], "reason": "Sinal pendente"}

    if state["fs_cooldown_results"] > 0:
        state["fs_cooldown_results"] -= 1
        return {"signal": None, "reason": "Cooldown"}

    func = FS_STRATEGY_MAP.get(state["fs_active_strategy"], analyze_adaptive)
    if func is analyze_sequential:
        analysis = func(fs_game_history, state["fs_min_probability"], state["fs_seq_min"])
    else:
        analysis = func(fs_game_history, state["fs_min_probability"])

    patterns = AnalysisEngine.detect_patterns(fs_game_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(fs_game_history)
    drift = AnalysisEngine.detect_drift(fs_game_history)
    percentages = AnalysisEngine.calculate_percentages(fs_game_history)
    tie_warning = analysis.get("tie_warning", percentages.get("Tie", 0) >= 7)
    priority = analysis.get("priority", False)

    if analysis.get("signal"):
        state["fs_last_signal_strategy"] = analysis["strategy"]
        state["fs_current_signal"] = {
            "id": f"fs_signal_{int(time.time()*1000)}",
            "signal": analysis["signal"],
            "probability": analysis["probability"],
            "reason": _fs_translate_reason(analysis["reason"]),
            "strategy": analysis["strategy"],
            "tie_warning": tie_warning,
            "priority": priority,
            "source": "Estatística",
        }
        state["fs_signal_strategy_map"][state["fs_current_signal"]["id"]] = analysis["strategy"]
        label = _fs_translate_signal(analysis["signal"])
        state["fs_logs"].append({"type": "signal", "message": f"{'⚡ FORTE' if priority else 'SINAL'}: {label} ({analysis['probability']}%)", "timestamp": "now"})
    else:
        state["fs_current_signal"] = None
        state["fs_logs"].append({"type": "analysis", "message": _fs_translate_reason(analysis["reason"]), "timestamp": "now"})

    if len(state["fs_logs"]) > 100:
        state["fs_logs"] = state["fs_logs"][-100:]

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
async def fs_receive_historico(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["fs_last_activity"] = time.time()
    state["fs_session_token"] = str(int(time.time())) + "_fs"

    history = []
    for r in data.get("resultados", []):
        w = r.get("winner", "")
        history.append({
            "winner": _fs_normalize(w),
            "player": r.get("visitante", r.get("player", 0)),
            "banker": r.get("casa", r.get("banker", 0)),
        })
    if len(history) > 150:
        history = history[-150:]
    state["fs_game_history"] = history

    state["fs_current_signal"] = None
    state["fs_cooldown_results"] = 0
    state["fs_logs"].append({"type": "info", "message": f"FS Histórico recebido: {len(state['fs_game_history'])} resultados", "timestamp": "now"})
    analysis = await fs_run_analysis(state)
    return {"success": True, "received": len(state["fs_game_history"]), "analysis": analysis}


@fs_router.post("/resultado")
async def fs_receive_resultado(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["fs_last_activity"] = time.time()
    w = data.get("winner", "")
    new_result = {
        "winner": _fs_normalize(w),
        "player": data.get("visitante", data.get("player", 0)),
        "banker": data.get("casa", data.get("banker", 0)),
    }
    state["fs_game_history"].append(new_result)
    if len(state["fs_game_history"]) > 150:
        state["fs_game_history"] = state["fs_game_history"][-150:]
    state["fs_logs"].append({"type": "result", "message": f"FS Resultado: {w}", "timestamp": "now"})
    analysis = await fs_run_analysis(state)
    return {"success": True, "total": len(state["fs_game_history"]), "analysis": analysis}


@fs_router.get("/state")
async def fs_get_state(user: str = Depends(get_current_user)):
    state = get_state(user)
    elapsed = (time.time() - state["fs_last_activity"]) / 60
    if elapsed > AUTO_RESET_MINUTES and len(state["fs_game_history"]) > 0:
        state["fs_game_history"] = []
        state["fs_logs"] = []
        state["fs_stats"] = {"wins": 0, "losses": 0, "total_signals": 0}
        state["fs_current_signal"] = None

    norm_history = [{"winner": r["winner"], "player": r.get("player", 0), "banker": r.get("banker", 0)} for r in state["fs_game_history"]]
    percentages = AnalysisEngine.calculate_percentages(norm_history)
    patterns = AnalysisEngine.detect_patterns(norm_history)
    monte_carlo = AnalysisEngine.monte_carlo_simulation(norm_history)
    drift = AnalysisEngine.detect_drift(norm_history)
    trigger_results = evaluate_triggers(norm_history, state["fs_user_triggers"])

    return {
        "history": state["fs_game_history"][-150:],
        "stats": state["fs_stats"],
        "logs": state["fs_logs"][-50:],
        "current_signal": state["fs_current_signal"],
        "active_strategy": state["fs_active_strategy"],
        "min_probability": state["fs_min_probability"],
        "auto_select": state["fs_auto_select"],
        "strategy_stats": state["fs_strategy_stats"],
        "percentages": percentages,
        "patterns": dict(list(patterns.items())[:10]),
        "monte_carlo": monte_carlo,
        "drift": drift,
        "tie_warning": percentages.get("Tie", 0) >= 7,
        "trigger_results": trigger_results,
        "session_token": state["fs_session_token"],
        "seq_min": state["fs_seq_min"],
    }


@fs_router.post("/strategy")
async def fs_change_strategy(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    if data.get("strategy") not in FS_STRATEGY_MAP:
        raise HTTPException(status_code=400, detail="Estratégia inválida")
    state["fs_active_strategy"] = data.get("strategy")
    state["fs_current_signal"] = None
    return {"success": True, "strategy": state["fs_active_strategy"]}


@fs_router.post("/probability")
async def fs_change_probability(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    prob = data.get("min_probability", 60)
    if prob < 40 or prob > 90:
        raise HTTPException(status_code=400, detail="Probabilidade deve estar entre 40 e 90")
    state["fs_min_probability"] = prob
    return {"success": True, "min_probability": state["fs_min_probability"]}


@fs_router.post("/signal/feedback")
async def fs_signal_feedback(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["fs_current_signal"] = None

    signal_id = data.get("signal_id")
    if signal_id is not None and signal_id not in state["fs_signal_strategy_map"]:
        return {"success": True, "stats": state["fs_stats"], "duplicate": True}

    strat = state["fs_signal_strategy_map"].pop(signal_id, None) if signal_id else None
    if not strat:
        strat = state["fs_last_signal_strategy"] or state["fs_active_strategy"]

    if data.get("result") == "win":
        state["fs_stats"]["wins"] += 1
    else:
        state["fs_stats"]["losses"] += 1
    state["fs_stats"]["total_signals"] += 1
    if strat in state["fs_strategy_stats"]:
        state["fs_strategy_stats"][strat]["total"] += 1
        if data.get("result") == "win":
            state["fs_strategy_stats"][strat]["wins"] += 1
        else:
            state["fs_strategy_stats"][strat]["losses"] += 1

    asyncio.create_task(_record_hourly_history(user, "fs", strat, data.get("result"), data.get("local_hour")))

    state["fs_cooldown_results"] = 2
    return {"success": True, "stats": state["fs_stats"]}


@fs_router.post("/triggers")
async def fs_save_triggers(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["fs_user_triggers"] = data.get("triggers", [])
    return {"success": True, "count": len(state["fs_user_triggers"])}


@fs_router.get("/triggers")
async def fs_get_triggers(user: str = Depends(get_current_user)):
    state = get_state(user)
    norm_history = [{"winner": r["winner"], "player": r.get("player", 0), "banker": r.get("banker", 0)} for r in state["fs_game_history"]]
    results = evaluate_triggers(norm_history, state["fs_user_triggers"])
    return {"triggers": results}


@fs_router.post("/auto_select")
async def fs_toggle_auto_select(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    state["fs_auto_select"] = data.get("enabled", True)
    return {"success": True, "auto_select": state["fs_auto_select"]}


@fs_router.post("/seq_min")
async def fs_set_seq_min(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    state = get_state(user)
    val = data.get("seq_min", 3)
    if val < 2 or val > 5:
        raise HTTPException(status_code=400, detail="seq_min deve estar entre 2 e 5")
    state["fs_seq_min"] = val
    return {"success": True, "seq_min": state["fs_seq_min"]}


@fs_router.post("/reset")
async def fs_reset_stats(user: str = Depends(get_current_user)):
    state = get_state(user)
    state["fs_stats"] = {"wins": 0, "losses": 0, "total_signals": 0}
    state["fs_strategy_stats"] = {
        "adaptive":  {"wins": 0, "losses": 0, "total": 0},
        "pressure":  {"wins": 0, "losses": 0, "total": 0},
        "consensus": {"wins": 0, "losses": 0, "total": 0},
    }
    state["fs_current_signal"] = None
    state["fs_signal_strategy_map"] = {}
    state["fs_cooldown_results"] = 0
    state["fs_logs"].append({"type": "reset", "message": "FS Estatísticas resetadas", "timestamp": "now"})
    return {"success": True}


# ============================================================
# PAINEL DE ADMIN — criar/listar/remover login de cliente.
# Só quem loga com o e-mail definido em ADMIN_EMAIL consegue usar essas
# rotas (ver get_current_admin). Usa a service_role key do Supabase, que
# tem poder total — por isso fica só aqui no backend, nunca no frontend.
# ============================================================

@admin_router.post("/users")
async def admin_create_user(request: Request, admin=Depends(get_current_admin)):
    """Cria um login novo (e-mail + senha) — já funciona no AlphaSignal e no MetaEdge."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    data = await request.json()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="E-mail inválido.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Senha precisa ter pelo menos 6 caracteres.")

    resp = await _supabase_request(
        "POST", f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_supabase_admin_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )

    if resp.status_code >= 400:
        try:
            detail = resp.json().get("msg") or resp.json().get("error_description") or resp.text
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=f"Supabase recusou: {detail}")

    created = resp.json()
    logger.info(f"[admin] Usuário criado: {email} (por {admin.get('email')})")
    return {"success": True, "user": {"id": created.get("id"), "email": created.get("email")}}


@admin_router.get("/users")
async def admin_list_users(admin=Depends(get_current_admin)):
    """Lista os usuários cadastrados no Supabase (pra conferir quem já tem acesso)."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    resp = await _supabase_request(
        "GET", f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_supabase_admin_headers(),
        params={"per_page": 200},
    )

    if resp.status_code >= 400:
        logger.error(f"Supabase (list users) {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=resp.status_code, detail=f"Falha ao listar usuários: {resp.text[:200]}")

    data = resp.json()
    users = data.get("users", data if isinstance(data, list) else [])
    return {
        "users": [
            {
                "id": u.get("id"),
                "email": u.get("email"),
                "created_at": u.get("created_at"),
                "last_sign_in_at": u.get("last_sign_in_at"),
                "is_admin": bool(ADMIN_EMAIL) and (u.get("email") or "").strip().lower() == ADMIN_EMAIL,
            }
            for u in users
        ]
    }


@admin_router.delete("/users/{user_id}")
async def admin_delete_user(user_id: str, admin=Depends(get_current_admin)):
    """Remove o acesso de um cliente (apaga o login dele do Supabase)."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    resp = await _supabase_request(
        "DELETE", f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers=_supabase_admin_headers(),
    )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail="Falha ao remover usuário no Supabase.")

    logger.info(f"[admin] Usuário removido: {user_id} (por {admin.get('email')})")
    return {"success": True}


# ============================================================
# FILA DE APROVAÇÃO — cliente pede um usuário/senha, fica pendente até o
# Fernando aprovar manualmente pelo painel de admin.
# ============================================================

@api_router.post("/signup-request")
async def signup_request(request: Request):
    """Rota PÚBLICA — qualquer um pode pedir um login, mas fica pendente até aprovação."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Servidor não configurado pra receber pedidos agora.")

    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Usuário precisa ter pelo menos 3 caracteres.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Senha precisa ter pelo menos 6 caracteres.")

    resp = await _supabase_request(
        "POST", f"{SUPABASE_URL}/rest/v1/pending_signups",
        headers={**_supabase_admin_headers(), "Prefer": "return=representation"},
        json={"username": username, "password": password},
    )

    if resp.status_code >= 400:
        logger.error(f"Supabase (signup-request) {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=400, detail="Esse usuário já foi pedido antes. Tenta outro nome.")

    return {"success": True}


@admin_router.get("/pending-signups")
async def admin_list_pending_signups(admin=Depends(get_current_admin)):
    """Lista os pedidos de cadastro esperando aprovação."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    resp = await _supabase_request(
        "GET", f"{SUPABASE_URL}/rest/v1/pending_signups",
        headers=_supabase_admin_headers(),
        params={"status": "eq.pending", "order": "created_at.desc"},
    )

    if resp.status_code >= 400:
        logger.error(f"Supabase (pending-signups) {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=resp.status_code, detail=f"Falha ao listar pedidos: {resp.text[:200]}")

    return {"pending": resp.json()}


@admin_router.post("/pending-signups/{pending_id}/approve")
async def admin_approve_signup(pending_id: str, admin=Depends(get_current_admin)):
    """Aprova um pedido — cria o login de verdade no Supabase."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    find_resp = await _supabase_request(
        "GET", f"{SUPABASE_URL}/rest/v1/pending_signups",
        headers=_supabase_admin_headers(),
        params={"id": f"eq.{pending_id}"},
    )

    if find_resp.status_code >= 400 or not find_resp.json():
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")

    pending = find_resp.json()[0]
    username = pending["username"]
    password = pending["password"]
    email = f"{username.lower()}@alphasignal.local"

    create_resp = await _supabase_request(
        "POST", f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_supabase_admin_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )

    if create_resp.status_code >= 400:
        try:
            detail = create_resp.json().get("msg", create_resp.text)
        except Exception:
            detail = create_resp.text
        raise HTTPException(status_code=create_resp.status_code, detail=f"Supabase recusou: {detail}")

    await _supabase_request(
        "PATCH", f"{SUPABASE_URL}/rest/v1/pending_signups",
        headers=_supabase_admin_headers(),
        params={"id": f"eq.{pending_id}"},
        json={"status": "approved"},
    )

    logger.info(f"[admin] Pedido aprovado: {username} (por {admin.get('email')})")
    return {"success": True, "username": username}


@admin_router.post("/pending-signups/{pending_id}/reject")
async def admin_reject_signup(pending_id: str, admin=Depends(get_current_admin)):
    """Rejeita um pedido — não cria login nenhum."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    resp = await _supabase_request(
        "PATCH", f"{SUPABASE_URL}/rest/v1/pending_signups",
        headers=_supabase_admin_headers(),
        params={"id": f"eq.{pending_id}"},
        json={"status": "rejected"},
    )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail="Falha ao rejeitar pedido.")

    return {"success": True}


# ============================================================
# GESTÃO DE DISPOSITIVOS — ver/ajustar quantos aparelhos cada cliente pode usar
# ============================================================

@admin_router.get("/users/{user_id}/devices")
async def admin_get_user_devices(user_id: str, admin=Depends(get_current_admin)):
    """Mostra os dispositivos conhecidos de um usuário e o limite dele."""
    info = await _load_user_devices(user_id, force=True)
    return {"devices": list(info["devices"]), "max_devices": info["max_devices"]}


@admin_router.post("/users/{user_id}/max-devices")
async def admin_set_max_devices(user_id: str, request: Request, admin=Depends(get_current_admin)):
    """Muda quantos aparelhos esse usuário pode usar ao mesmo tempo."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    data = await request.json()
    max_devices = data.get("max_devices", 1)
    if max_devices < 1 or max_devices > 10:
        raise HTTPException(status_code=400, detail="Deve ser entre 1 e 10 dispositivos.")

    resp = await _supabase_request(
        "POST", f"{SUPABASE_URL}/rest/v1/user_device_limits",
        headers={**_supabase_admin_headers(), "Prefer": "resolution=merge-duplicates"},
        json={"user_id": user_id, "max_devices": max_devices},
    )

    if resp.status_code >= 400:
        logger.error(f"Supabase (max-devices) {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=resp.status_code, detail=f"Falha ao salvar o limite: {resp.text[:200]}")

    device_cache.pop(user_id, None)  # força recarregar na próxima checagem
    return {"success": True, "max_devices": max_devices}


@admin_router.delete("/users/{user_id}/devices/{device_id}")
async def admin_remove_device(user_id: str, device_id: str, admin=Depends(get_current_admin)):
    """Remove um dispositivo específico, liberando espaço pra outro novo."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_ROLE_KEY não configurado no servidor.")

    resp = await _supabase_request(
        "DELETE", f"{SUPABASE_URL}/rest/v1/user_devices",
        headers=_supabase_admin_headers(),
        params={"user_id": f"eq.{user_id}", "device_id": f"eq.{device_id}"},
    )

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail="Falha ao remover dispositivo.")

    device_cache.pop(user_id, None)
    return {"success": True}


# Include router
app.include_router(api_router)
app.include_router(fs_router)
app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[
        "https://alpha-sginal-2-0.vercel.app",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("AlphaSignal API iniciada (multi-usuário via Supabase Auth)")
    logger.info("Modo: análise estatística pura (sem IA externa)")
