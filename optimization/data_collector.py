"""
Coleta e prepara dados históricos para otimização
"""
import logging
from typing import List

from bybit_api.client import BybitClient
from bybit_api.types import Kline
from config.settings import Settings

logger = logging.getLogger(__name__)


class DataCollector:
    """Coleta dados históricos da Bybit para otimização"""
    
    def __init__(self):
        self.client = BybitClient()
    
    def collect_historical_data(self, days: int = None) -> List[Kline]:
        """
        Coleta dados históricos
        
        Args:
            days: Número de dias de dados históricos
        
        Returns:
            Lista de klines históricos
        """
        days = days or Settings.OPTIMIZATION_DAYS
        
        logger.info(f"Coletando {days} dias de dados históricos para {Settings.SYMBOL}...")
        
        try:
            klines = self.client.get_historical_klines(
                symbol=Settings.SYMBOL,
                interval=Settings.TIMEFRAME,
                days=days
            )
            
            logger.info(f"Coletados {len(klines)} candles históricos")
            return klines
            
        except Exception as e:
            logger.error(f"Erro ao coletar dados históricos: {e}")
            raise






