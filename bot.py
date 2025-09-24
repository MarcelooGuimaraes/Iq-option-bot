import os
import time
import numpy as np
from iqoptionapi.stable_api import IQ_Option

# ======================
# Conexão
# ======================
email = os.getenv("IQ_EMAIL")
senha = os.getenv("IQ_PASSWORD")

print("🔗 Conectando na IQ Option...")
I_want_money = IQ_Option(email, senha)
I_want_money.connect()
I_want_money.change_balance("PRACTICE")  # segurança: apenas conta demo
print("✅ Conectado:", I_want_money.check_connect())

# ======================
# Configurações
# ======================
PAR = "EURUSD"
TIMEFRAME = 1  # M1
ENTRADA = 20
SOROS_MAOS = 2
STOP_GAIN = 200
STOP_LOSS = 100

lucro_total = 0
soros_mao = 0

# ======================
# Funções auxiliares
# ======================
def ema(values, period):
    return np.mean(values[-period:])

def rsi(values, period=14):
    deltas = np.diff(values)
    ups = deltas[deltas > 0].sum() / period
    downs = -deltas[deltas < 0].sum() / period
    rs = ups / downs if downs != 0 else 0
    return 100 - (100 / (1 + rs))

def estrategia(candles):
    closes = [c["close"] for c in candles]
    ema5 = ema(closes, 5)
    ema12 = ema(closes, 12)
    rsi_val = rsi(np.array(closes))

    print(f"📊 EMA5={ema5:.5f} | EMA12={ema12:.5f} | RSI={rsi_val:.2f}")

    if ema5 > ema12 and rsi_val > 50:
        return "call"
    elif ema5 < ema12 and rsi_val < 50:
        return "put"
    return None

# ======================
# Loop principal
# ======================
while True:
    if lucro_total >= STOP_GAIN:
        print("🏆 Stop Gain atingido! Lucro:", lucro_total)
        break
    if abs(lucro_total) >= STOP_LOSS:
        print("❌ Stop Loss atingido! Perda:", lucro_total)
        break

    candles = I_want_money.get_candles(PAR, 60, 20, time.time())
    direcao = estrategia(candles)

    if direcao:
        valor_entrada = ENTRADA if soros_mao == 0 else ENTRADA + lucro_total
        print(f"🎯 Entrada: {valor_entrada} | Direção: {direcao.upper()} | Soros mão {soros_mao+1}")

        status, id = I_want_money.buy(valor_entrada, PAR, direcao, TIMEFRAME)
        if status:
            print("📌 Ordem enviada! ID:", id)
            # espera expiração da ordem
            time.sleep(70)
            resultado = I_want_money.check_win_v3(id)
            print("📈 Resultado:", resultado)

            lucro_total += resultado
            if resultado > 0:
                soros_mao += 1
                if soros_mao >= SOROS_MAOS:
                    soros_mao = 0
            else:
                soros_mao = 0
        else:
            print("⚠️ Erro ao enviar ordem")
    else:
        print("⏭️ Nenhum sinal, aguardando...")

    time.sleep(5)
