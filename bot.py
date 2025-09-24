from iqoptionapi.stable_api import IQ_Option
import time
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# ======================
# Configurações
# ======================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")
PAR = "EURUSD"
TIMEFRAME = 1   # 1 minuto
VALOR = 2

# ======================
# Conexão
# ======================
I_want_money = IQ_Option(EMAIL, PASSWORD)
I_want_money.connect()

if I_want_money.check_connect():
    logging.info("Conectado com sucesso!")
else:
    logging.error("Falha na conexão!")
    exit()

# ======================
# Estratégia EMA + RSI simples
# ======================
def estrategia(candles):
    closes = [c["close"] for c in candles]

    ema5 = sum(closes[-5:]) / 5
    ema12 = sum(closes[-12:]) / 12
    rsi = sum(closes[-14:]) / 14  # simplificado (apenas média)

    if ema5 > ema12 and rsi > closes[-1]:
        return "call"
    if ema5 < ema12 and rsi < closes[-1]:
        return "put"
    return None

# ======================
# Loop principal
# ======================
while True:
    candles = I_want_money.get_candles(PAR, 60, 50, time.time())
    direcao = estrategia(candles)

    if direcao:
        status, order_id = I_want_money.buy(VALOR, PAR, direcao, TIMEFRAME)
        logging.info(f"Sinal: {direcao.upper()} | Ordem enviada: {status}")

    time.sleep(60)
