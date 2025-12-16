
import logging
import sys
from datetime import datetime
from bybit_api.client import BybitClient
from config.settings import Settings

# Configurar log
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("DebugKlines")

def debug_data():
    client = BybitClient()
    
    # 1. Testar método get_historical_klines modificado
    try:
        days = 1
        logger.info(f"Baixando {days} dia(s) de histórico para {Settings.SYMBOL}...")
        
        klines = client.get_historical_klines(
            symbol=Settings.SYMBOL,
            interval=Settings.TIMEFRAME,
            days=days
        )
        
        logger.info(f"Total baixado: {len(klines)} klines")
        
        if not klines:
            logger.error("Nenhum kline retornado!")
            return

        # 2. Verificar continuidade temporal
        logger.info("Verificando continuidade...")
        for i in range(len(klines) - 1):
            curr = klines[i]
            next_k = klines[i+1]
            
            diff_ms = next_k.open_time - curr.open_time
            expected_ms = int(Settings.TIMEFRAME) * 60 * 1000
            
            # Aceitar pequena tolerância ou gap exato
            if diff_ms != expected_ms:
                t1 = datetime.fromtimestamp(curr.open_time/1000)
                t2 = datetime.fromtimestamp(next_k.open_time/1000)
                logger.error(f"GAP DETECTADO! Índice {i}")
                logger.error(f"Candle 1: {t1} (Open: {curr.open})")
                logger.error(f"Candle 2: {t2} (Open: {next_k.open})")
                logger.error(f"Diferença: {diff_ms/1000/60} min (Esperado: {expected_ms/1000/60} min)")
                logger.error(f"Diferença Preço Close->Open: {abs(next_k.open - curr.close)}")
                
                # Se encontrar um gap, pare para analisarmos
                if i > 5: # Mostrar contexto
                    break
        
        # 3. Calcular ATR com esses dados para ver se bate
        import pandas as pd
        atr_period = 14
        if len(klines) > atr_period:
            df = pd.DataFrame({
                "high": [k.high for k in klines],
                "low": [k.low for k in klines],
                "close": [k.close for k in klines]
            })
            df["high_low"] = df["high"] - df["low"]
            df["high_close"] = abs(df["high"] - df["close"].shift())
            df["low_close"] = abs(df["low"] - df["close"].shift())
            df["tr"] = df[["high_low", "high_close", "low_close"]].max(axis=1)
            atr = df["tr"].tail(atr_period).mean()
            
            logger.info(f"ATR Calculado (últimos {atr_period}): {atr:.2f}")
            logger.info(f"Preço Atual: {klines[-1].close}")
            logger.info(f"ATR % do Preço: {(atr/klines[-1].close)*100:.2f}%")
        
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_data()
