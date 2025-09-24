from iqoptionapi.stable_api import IQ_Option
import time
import numpy as np

# ======================
# Conexão
# ======================
I_want_money = IQ_Option("email", "senha")
I_want_money.connect()
I_want_money.change_balance("PRACTICE")  # PRACTICE ou REAL

# ======================
# Configurações
# ======================
PAR = "EURUSD"
TIMEFRAME = 1
ENTRADA_INICIAL = 20
STOP_WIN = 200
STOP_LOSS = -100
SOROS_MAX = 2

# Controle de banca
lucro = 0
soros_mao = 0
valor_entrada = ENTRADA_INICIAL

# ======================
# Estratégia simples (EMA + RSI)
# ======================
def EMA(values, period):
    return np.mean(values[-period:]) if len(values) >= period else None

def RSI(values, period=14):
    if len(values) < period + 1:
        return None
    deltas = np.diff(values)
    ganhos = deltas[deltas > 0].sum() / period
    perdas = -deltas[deltas < 0].sum() / period
    rs = ganhos / perdas if perdas != 0 else 0
    return 100 - (100 / (1 + rs))

def estrategia(candles):
    closes = [c['close'] for c in candles]
    ema5 = EMA(closes, 5)
    ema12 = EMA(closes, 12)
    rsi = RSI(closes, 14)

    if not ema5 or not ema12 or not rsi:
        return None

    if ema5 > ema12 and rsi > 50:
        return "call"
    if ema5 < ema12 and rsi < 50:
        return "put"
    return None

# ======================
# Loop principal
# ======================
while True:
    if lucro >= STOP_WIN:
        print(f"[STOP WIN] Meta de lucro alcançada: {lucro}")
        break
    if lucro <= STOP_LOSS:
        print(f"[STOP LOSS] Limite de perda atingido: {lucro}")
        break

    candles = I_want_money.get_candles(PAR, 60, 100, time.time())
    direcao = estrategia(candles)

    if direcao:
        status, id = I_want_money.buy(valor_entrada, PAR, direcao, TIMEFRAME)
        print(f"[ORDEM] {direcao.upper()} | Valor: {valor_entrada} | Status: {status} | ID: {id}")

        if status:
            # aguarda resultado
            time.sleep(60)
            resultado = I_want_money.check_win_v3(id)

            if resultado > 0:
                lucro += resultado
                soros_mao += 1
                print(f"[WIN] Lucro: {resultado:.2f} | Banca: {lucro:.2f}")

                if soros_mao <= SOROS_MAX:
                    valor_entrada = ENTRADA_INICIAL + resultado  # reinvestindo lucro (soros)
                    print(f"[SOROS] Indo para mão {soros_mao} com {valor_entrada}")
                else:
                    valor_entrada = ENTRADA_INICIAL
                    soros_mao = 0
            else:
                lucro += resultado
                print(f"[LOSS] Perdeu: {resultado:.2f} | Banca: {lucro:.2f}")
                valor_entrada = ENTRADA_INICIAL
                soros_mao = 0

    time.sleep(5)
