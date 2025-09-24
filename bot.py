import os
import time
import math
import traceback
from typing import List, Dict, Optional
from iqoptionapi.stable_api import IQ_Option

# ============================
# CONFIGURAÇÕES (edite aqui)
# ============================
PAR = os.getenv("PAIR", "EURUSD")   # pode trocar por outro par
TIMEFRAME = 1                       # 1 = M1
ENTRADA_INICIAL = float(os.getenv("STAKE", "20"))
SOROS_MAX = int(os.getenv("SOROS_MAX", "2"))
STOP_GAIN = float(os.getenv("STOP_GAIN", "200"))   # para após lucro acumulado >= STOP_GAIN
STOP_LOSS = float(os.getenv("STOP_LOSS", "100"))   # para após perda acumulada >= STOP_LOSS (valor positivo)
MAX_CYCLES = int(os.getenv("MAX_CYCLES", "60"))    # nº de iterações do loop (proteção p/ Actions)

ACCOUNT_TYPE = os.getenv("ACCOUNT_TYPE", "PRACTICE").upper()  # "PRACTICE" ou "REAL"

EMA_FAST = 5
EMA_SLOW = 12
RSI_LEN = 14
RSI_BULL = 50.0
RSI_BEAR = 50.0

# ============================
# FUNÇÕES AUXILIARES
# ============================

def wilders_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """RSI (Wilder). Retorna None se não houver dados suficientes."""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # suavização de Wilder até o último preço
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        rs = math.inf
    else:
        rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def ema_last(closes: List[float], period: int) -> Optional[float]:
    """EMA clássica; retorna apenas o valor final. None se dados insuficientes."""
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    # inicializa com SMA do período
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = ema + k * (price - ema)
    return ema


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def wait_next_candle_tf60():
    """Sincroniza aproximadamente com a virada do minuto."""
    now = time.time()
    wait = 60 - (now % 60) + 1
    if wait < 0:
        wait = 5
    time.sleep(wait)


# ============================
# CONEXÃO
# ============================

def connect_with_retry() -> IQ_Option:
    email = os.getenv("IQ_EMAIL")
    password = os.getenv("IQ_PASSWORD")
    if not email or not password:
        raise RuntimeError("IQ_EMAIL e/ou IQ_PASSWORD não definidos nos Secrets.")

    print(f"[{now_str()}] 🔗 Conectando na IQ Option...")
    api = IQ_Option(email, password)

    for attempt in range(1, 6):
        try:
            api.connect()
            time.sleep(1)
            if api.check_connect():
                print(f"[{now_str()}] ✅ Conectado (tentativa {attempt}).")
                api.change_balance(ACCOUNT_TYPE)  # PRACTICE (padrão) ou REAL
                print(f"[{now_str()}] 💼 Conta selecionada: {ACCOUNT_TYPE}")
                return api
        except Exception as e:
            print(f"[{now_str()}] ❗ Erro na conexão (tentativa {attempt}): {e}")
        time.sleep(2 * attempt)

    raise RuntimeError("Falha ao conectar na IQ Option após várias tentativas.")


# ============================
# LÓGICA DA ESTRATÉGIA
# ============================

def get_candles_safe(api: IQ_Option, par: str, count: int = 100, tf_sec: int = 60) -> List[Dict]:
    """Busca candles com retry básico."""
    for attempt in range(1, 6):
        try:
            candles = api.get_candles(par, tf_sec, count, time.time())
            if candles and isinstance(candles, list):
                return candles
        except Exception as e:
            print(f"[{now_str()}] ⚠️ get_candles tentativa {attempt} falhou: {e}")
        time.sleep(1.5 * attempt)
    raise RuntimeError("Não foi possível obter candles após várias tentativas.")


def decide_direction(candles: List[Dict]) -> Optional[str]:
    closes = [c["close"] for c in candles]
    ema5 = ema_last(closes, EMA_FAST)
    ema12 = ema_last(closes, EMA_SLOW)
    rsi = wilders_rsi(closes, RSI_LEN)

    if ema5 is None or ema12 is None or rsi is None:
        print(f"[{now_str()}] ⏳ Dados insuficientes: len={len(closes)}")
        return None

    print(f"[{now_str()}] 📊 EMA5={ema5:.5f} | EMA12={ema12:.5f} | RSI={rsi:.2f}")

    # Regras simples
    if ema5 > ema12 and rsi > RSI_BULL:
        print(f"[{now_str()}] ✅ Sinal: CALL")
        return "call"
    if ema5 < ema12 and rsi < RSI_BEAR:
        print(f"[{now_str()}] ✅ Sinal: PUT")
        return "put"
    print(f"[{now_str()}] ➖ Sem sinal")
    return None


def place_and_settle(api: IQ_Option, direction: str, amount: float, par: str, tf: int) -> float:
    """Envia ordem e aguarda resultado (lucro líquido positivo, ou negativo em caso de loss)."""
    print(f"[{now_str()}] 🎯 Enviando ordem: {direction.upper()} | Valor: {amount}")
    status, order_id = api.buy(amount, par, direction, tf)
    if not status:
        print(f"[{now_str()}] ❌ Falha ao enviar ordem.")
        return 0.0

    print(f"[{now_str()}] 📌 Ordem enviada! ID: {order_id} — aguardando expiração...")
    # aguarda expiração (um pouco mais que 1 minuto para M1)
    time.sleep(70)
    try:
        result = api.check_win_v3(order_id)  # valor líquido (positivo ou negativo)
        print(f"[{now_str()}] 📈 Resultado da ordem: {result:.2f}")
        return float(result)
    except Exception as e:
        print(f"[{now_str()}] ⚠️ Erro ao checar resultado: {e}")
        return 0.0


# ============================
# MAIN
# ============================

def main():
    api = connect_with_retry()

    lucro_acumulado = 0.0
    soro_mao = 0
    entrada_base = ENTRADA_INICIAL

    # loop limitado para GitHub Actions
    cycles = 0
    while cycles < MAX_CYCLES:
        cycles += 1

        # Stops
        if lucro_acumulado >= STOP_GAIN:
            print(f"[{now_str()}] 🏆 STOP GAIN atingido! Lucro: {lucro_acumulado:.2f}")
            break
        if abs(lucro_acumulado) >= STOP_LOSS:
            print(f"[{now_str()}] 🛑 STOP LOSS atingido! Resultado: {lucro_acumulado:.2f}")
            break

        try:
            candles = get_candles_safe(api, PAR, count=120, tf_sec=60)
            direction = decide_direction(candles)

            if direction:
                # valor da mão atual (Soros reinveste lucro)
                if soro_mao == 0:
                    stake = entrada_base
                else:
                    stake = entrada_base + max(lucro_acumulado, 0.0)

                pnl = place_and_settle(api, direction, stake, PAR, TIMEFRAME)
                lucro_acumulado += pnl

                if pnl > 0:
                    soro_mao += 1
                    if soro_mao >= SOROS_MAX:
                        print(f"[{now_str()}] 🔄 Ciclo Soros completo. Resetando mão.")
                        soro_mao = 0
                        entrada_base = ENTRADA_INICIAL
                else:
                    # perdeu ou zero → reseta mão
                    soro_mao = 0
                    entrada_base = ENTRADA_INICIAL
            else:
                print(f"[{now_str()}] ⏭️ Aguardando próxima vela...")

            # sincroniza com virada do minuto
            wait_next_candle_tf60()

        except Exception as e:
            print(f"[{now_str()}] 💥 EXCEÇÃO no loop: {e}")
            traceback.print_exc()
            time.sleep(5)

    print(f"[{now_str()}] ✅ Encerrado. Lucro final: {lucro_acumulado:.2f}")


if __name__ == "__main__":
    main()
