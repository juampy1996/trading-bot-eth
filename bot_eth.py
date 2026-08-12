import ccxt
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# Archivos de persistencia para ETH
ARCHIVO_ESTADO = "estado_bot.json"
ARCHIVO_HISTORIAL = "historial_trades.csv"

# Cargar o inicializar estado desde JSON
if os.path.exists(ARCHIVO_ESTADO):
    with open(ARCHIVO_ESTADO, "r") as f:
        estado = json.load(f)
else:
    estado = {
        "posicion_abierta": False,
        "precio_entrada": 0.0,
        "stop_loss": 0.0,
        "capital_simulado": 100.0
    }

# Inicializar historial CSV si no existe
if not os.path.exists(ARCHIVO_HISTORIAL):
    df_historial = pd.DataFrame(columns=[
        'fecha_hora', 'tipo_salida', 'precio_entrada', 'precio_salida', 
        'rendimiento_pct', 'capital_resultante'
    ])
    df_historial.to_csv(ARCHIVO_HISTORIAL, index=False)

# Conexión a KuCoin para ETH/USDT
exchange = ccxt.kucoin()
simbolo = "ETH/USDT"
temporalidad = "1h"

try:
    ohlcv = exchange.fetch_ohlcv(simbolo, timeframe=temporalidad, limit=50)
except Exception as e:
    print(f"Error al conectar con el exchange: {e}")
    exit(1)

df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

# Indicadores (RSI y ATR)
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
df['RSI'] = 100 - (100 / (1 + rs))

high_low = df['high'] - df['low']
high_close = (df['high'] - df['close'].shift()).abs()
low_close = (df['low'] - df['close'].shift()).abs()
ranges = pd.concat([high_low, high_close, low_close], axis=1)
df['ATR'] = ranges.max(axis=1).rolling(14).mean()

# Evaluación de la última vela cerrada
ultima_vela = df.iloc[-2]
precio_actual = ultima_vela['close']
rsi_actual = ultima_vela['RSI']
atr_actual = ultima_vela['ATR']
comision = 0.0015

hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"[{hora_actual}] Reviso mercado | ETH: ${precio_actual:.2f} | RSI: {rsi_actual:.2f}")

def registrar_trade(tipo_salida, precio_salida, rendimiento_pct, capital_final):
    nuevo_registro = pd.DataFrame([{
        'fecha_hora': hora_actual,
        'tipo_salida': tipo_salida,
        'precio_entrada': estado["precio_entrada"],
        'precio_salida': precio_salida,
        'rendimiento_pct': round(rendimiento_pct * 100, 2),
        'capital_resultante': round(capital_final, 2)
    }])
    nuevo_registro.to_csv(ARCHIVO_HISTORIAL, mode='a', header=False, index=False)

# Lógica de Trading (misma regla: RSI < 30 entrada, RSI >= 50 o Stop Loss salida)
if estado["posicion_abierta"]:
    if ultima_vela['low'] <= estado["stop_loss"]:
        rendimiento = (estado["stop_loss"] - estado["precio_entrada"]) / estado["precio_entrada"] - comision
        estado["capital_simulado"] *= (1 + rendimiento)
        print(f"❌ STOP LOSS TOCADO en ${estado['stop_loss']:.2f}. Capital: ${estado['capital_simulado']:.2f} USDT")
        
        registrar_trade('STOP_LOSS', estado['stop_loss'], rendimiento, estado["capital_simulado"])
        estado["posicion_abierta"] = False

    elif rsi_actual >= 50:
        rendimiento = (precio_actual - estado["precio_entrada"]) / estado["precio_entrada"] - comision
        estado["capital_simulado"] *= (1 + rendimiento)
        print(f"🎯 TAKE PROFIT/RSI TOCADO en ${precio_actual:.2f}. Capital: ${estado['capital_simulado']:.2f} USDT")
        
        registrar_trade('TAKE_PROFIT', precio_actual, rendimiento, estado["capital_simulado"])
        estado["posicion_abierta"] = False

elif not estado["posicion_abierta"] and rsi_actual < 30:
    estado["posicion_abierta"] = True
    estado["precio_entrada"] = precio_actual
    estado["stop_loss"] = precio_actual - (1.5 * atr_actual)
    estado["capital_simulado"] *= (1 - comision)
    print(f"🚀 COMPRA SIMULADA ETH en ${precio_actual:.2f} | Stop Loss a ${estado['stop_loss']:.2f}")

# Guardar estado actualizado
with open(ARCHIVO_ESTADO, "w") as f:
    json.dump(estado, f, indent=4)

print("Estado guardado correctamente.")