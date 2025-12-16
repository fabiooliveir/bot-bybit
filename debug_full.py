
import logging
import sys
import pandas as pd
from datetime import datetime
from bybit_api.client import BybitClient
from config.settings import Settings

# Configurar log
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("DebugFull")

def analyze_data():
    client = BybitClient()
    
    logger.info(f"=== ANÁLISE PROFUNDA DE DADOS HISTÓRICOS ===")
    logger.info(f"Symbol: {Settings.SYMBOL}")
    logger.info(f"Timeframe: {Settings.TIMEFRAME}")
    
    # 1. Baixar dados (simulando exatamente o trader)
    try:
        days = 3
        logger.info(f"Baixando {days} dias de histórico...")
        
        klines = client.get_historical_klines(
            symbol=Settings.SYMBOL,
            interval=Settings.TIMEFRAME,
            days=days
        )
        
        count = len(klines)
        logger.info(f"Total baixado: {count} klines")
        
        if count == 0:
            logger.error("Nenhum dado retornado!")
            return

        # 2. Converter para DataFrame para análise fácil
        data = []
        for k in klines:
            data.append({
                "time": datetime.fromtimestamp(k.open_time/1000),
                "ts": k.open_time,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close
            })
        
        df = pd.DataFrame(data)
        
        # 3. Verificar Duplicatas
        duplicates = df[df.duplicated(subset=['ts'], keep=False)]
        if not duplicates.empty:
            logger.error(f"!!! DUPLICATAS ENCONTRADAS: {len(duplicates)} !!!")
            print(duplicates.head())
        else:
            logger.info("OK: Sem timestamps duplicados.")

        # 4. Verificar Ordenação
        if not df['ts'].is_monotonic_increasing:
             logger.error("!!! DADOS NÃO ESTÃO EM ORDEM CRONOLÓGICA !!!")
             # Achar onde quebra
             df['delta_ts'] = df['ts'].diff()
             print(df[df['delta_ts'] < 0].head())
        else:
            logger.info("OK: Dados ordenados cronologicamente.")

        # 5. Verificar Gaps de Tempo
        expected_diff = int(Settings.TIMEFRAME) * 60 * 1000
        df['delta_ts'] = df['ts'].diff()
        gaps = df[df['delta_ts'] != expected_diff]
        # Ignorar o primeiro NaN
        gaps = gaps.dropna()
        
        if not gaps.empty:
            logger.info(f"Gaps de tempo encontrados: {len(gaps)}")
            # Mostrar os maiores gaps
            print(gaps.head())
        else:
            logger.info("OK: Continuidade temporal perfeita.")

        # 6. Análise de Preço (Saltos Bruscos)
        df['pct_change'] = df['close'].pct_change().abs()
        big_jumps = df[df['pct_change'] > 0.01] # > 1% em 5 min
        
        if not big_jumps.empty:
            logger.warning(f"!!! SALTOS DE PREÇO > 1% DETECTADOS: {len(big_jumps)} !!!")
            print(big_jumps[['time', 'close', 'pct_change']].head())
            logger.warning("Isso pode indicar mistura de dados ou crash real.")
        else:
            logger.info("OK: Sem variações de preço absurdas (>1%).")

        # 7. Cálculo IFR/ATR (Simulação via pandas-ta)
        import pandas_ta as ta
        
        # ATR (12 periodos - optimized)
        atr_period = 12
        try:
            # pandas-ta requer High, Low, Close
            df.ta.atr(length=atr_period, append=True)
            atr_col = f"ATRr_{atr_period}" # nome padrão do pandas-ta
            
            logger.info(f"ATR Médio (últimos 10): {df[atr_col].tail(10).mean():.2f}")
            logger.info(f"ATR Atual: {df[atr_col].iloc[-1]:.2f}")
        except Exception as e:
            logger.error(f"Erro ao calcular ATR: {e}")
        
        # RSI (9 periodos)
        rsi_period = 9
        try:
            df.ta.rsi(close='close', length=rsi_period, append=True)
            rsi_col = f"RSI_{rsi_period}" # nome padrão do pandas-ta
            
            logger.info(f"RSI Atual: {df[rsi_col].iloc[-1]:.2f}")
        except Exception as e:
            logger.error(f"Erro ao calcular RSI: {e}")
            
        logger.info(f"Preço Atual: {df['close'].iloc[-1]}")

    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_data()
