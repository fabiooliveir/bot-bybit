"""
Classe base para estratégias de trading
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List
from dataclasses import dataclass

from bybit_api.types import Kline


class Signal(Enum):
    """Sinais de trading"""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


@dataclass
class StrategyResult:
    """Resultado da avaliação da estratégia"""
    signal: Signal
    confidence: float  # 0.0 a 1.0
    entry_price: float


class BaseStrategy(ABC):
    """Classe base abstrata para estratégias"""
    
    def __init__(self, params: dict):
        self.params = params
        self.klines: List[Kline] = []
    
    def update_klines(self, klines: List[Kline]):
        """Atualiza lista de klines"""
        self.klines = klines
    
    def add_kline(self, kline: Kline):
        """Adiciona um novo kline"""
        self.klines.append(kline)
        # Manter apenas os últimos N klines necessários
        max_klines = self.get_max_klines()
        if len(self.klines) > max_klines:
            self.klines = self.klines[-max_klines:]
    
    @abstractmethod
    def get_max_klines(self) -> int:
        """Retorna número máximo de klines necessários"""
        pass
    
    @abstractmethod
    def calculate_signal(self) -> StrategyResult:
        """Calcula sinal da estratégia"""
        pass
    
    @abstractmethod
    def get_optimization_space(self) -> dict:
        """Retorna espaço de busca para otimização"""
        pass

