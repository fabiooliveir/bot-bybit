"""
Trailing Stop baseado em ATR (Average True Range)
"""
from typing import Optional
import pandas as pd
from dataclasses import dataclass

from bybit_api.types import Kline, Position


@dataclass
class TrailingStopState:
    """Estado do trailing stop"""
    is_active: bool
    highest_price: float  # Para LONG: preço mais alto desde entrada
    lowest_price: float   # Para SHORT: preço mais baixo desde entrada
    current_stop: float
    entry_price: float
    position_side: str  # "LONG" ou "SHORT"


class TrailingStop:
    """
    Trailing Stop otimizado usando ATR
    
    O trailing stop acompanha o preço e ajusta dinamicamente o stop loss
    baseado na volatilidade (ATR) do mercado.
    """
    
    def __init__(self, atr_multiplier: float = 2.0, atr_period: int = 14):
        """
        Args:
            atr_multiplier: Multiplicador do ATR para calcular distância do stop
            atr_period: Período para cálculo do ATR
        """
        self.atr_multiplier = atr_multiplier
        self.atr_period = atr_period
        self.state: Optional[TrailingStopState] = None
    
    def activate(self, entry_price: float, position_side: str, klines: list = None):
        """Ativa o trailing stop para uma nova posição"""
        # Calcular stop inicial baseado no ATR
        initial_stop = entry_price
        if klines and len(klines) >= self.atr_period + 1:
            atr = self._calculate_atr(klines)
            if atr > 0:
                stop_distance = atr * self.atr_multiplier
                if position_side == "LONG":
                    initial_stop = entry_price - stop_distance
                else:  # SHORT
                    initial_stop = entry_price + stop_distance
        
        self.state = TrailingStopState(
            is_active=True,
            highest_price=entry_price,
            lowest_price=entry_price,
            current_stop=initial_stop,
            entry_price=entry_price,
            position_side=position_side
        )
    
    def deactivate(self):
        """Desativa o trailing stop"""
        self.state = None
    
    def calculate_trailing_stop_points(self, klines: list) -> float:
        """
        Calcula trailing stop em pontos para usar no trailing stop nativo da Bybit
        
        Args:
            klines: Lista de klines para calcular ATR
            
        Returns:
            Distância do trailing stop em pontos (sempre positivo)
            Para LONG: pontos abaixo do preço mais alto
            Para SHORT: pontos acima do preço mais baixo
        """
        atr = self._calculate_atr(klines)
        if atr == 0.0:
            return 0.0
        
        # Converter ATR multiplicado para pontos
        # Para BTCUSDT, 1 ponto = $1
        stop_distance = atr * self.atr_multiplier
        
        # Retornar como pontos inteiros (Bybit usa pontos)
        return stop_distance
    
    def _calculate_atr(self, klines: list) -> float:
        """Calcula ATR dos últimos klines"""
        if len(klines) < self.atr_period + 1:
            return 0.0
        
        df = pd.DataFrame({
            "high": [k.high for k in klines[-self.atr_period-1:]],
            "low": [k.low for k in klines[-self.atr_period-1:]],
            "close": [k.close for k in klines[-self.atr_period-1:]]
        })
        
        # True Range
        df["high_low"] = df["high"] - df["low"]
        df["high_close"] = abs(df["high"] - df["close"].shift())
        df["low_close"] = abs(df["low"] - df["close"].shift())
        df["tr"] = df[["high_low", "high_close", "low_close"]].max(axis=1)
        
        # ATR (média do TR)
        atr = df["tr"].tail(self.atr_period).mean()
        
        return atr
    
    def update(self, current_price: float, klines: list) -> Optional[float]:
        """
        Atualiza o trailing stop com novo preço
        
        Returns:
            None se não deve fechar posição
            Preço do stop se deve fechar posição
        """
        if not self.state or not self.state.is_active:
            return None
        
        atr = self._calculate_atr(klines)
        
        if atr == 0.0:
            return None
        
        stop_distance = atr * self.atr_multiplier
        
        if self.state.position_side == "LONG":
            # Para posição LONG: stop abaixo do preço atual
            # Atualizar preço mais alto
            if current_price > self.state.highest_price:
                self.state.highest_price = current_price
                # Recalcular stop baseado no novo highest
                new_stop = self.state.highest_price - stop_distance
                # Stop só pode subir, nunca descer
                if new_stop > self.state.current_stop:
                    self.state.current_stop = new_stop
            
            # Verificar se preço atual atingiu o stop
            if current_price <= self.state.current_stop:
                return self.state.current_stop
        
        else:  # SHORT
            # Para posição SHORT: stop acima do preço atual
            # Atualizar preço mais baixo
            if current_price < self.state.lowest_price:
                self.state.lowest_price = current_price
                # Recalcular stop baseado no novo lowest
                new_stop = self.state.lowest_price + stop_distance
                # Stop só pode descer, nunca subir (para SHORT)
                # Se ainda está no preço de entrada, definir pela primeira vez
                if self.state.current_stop == self.state.entry_price or new_stop < self.state.current_stop:
                    self.state.current_stop = new_stop
            
            # Verificar se preço atual atingiu o stop
            if current_price >= self.state.current_stop:
                return self.state.current_stop
        
        return None
    
    def get_current_stop(self) -> Optional[float]:
        """Retorna o stop loss atual"""
        if not self.state or not self.state.is_active:
            return None
        return self.state.current_stop
    
    def get_optimization_space(self) -> dict:
        """Retorna espaço de busca para otimização do multiplicador ATR"""
        return {
            "atr_multiplier": (1.0, 4.0),  # Multiplicador ATR de 1.0 a 4.0
            "atr_period": (10, 20),  # Período ATR de 10 a 20
        }

