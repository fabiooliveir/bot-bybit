"""
Estratégia IFR (RSI) simples, recriada a partir dos parâmetros presentes
em `optimized_params.json` (rsi_period, oversold_level, overbought_level, volatility_period).
"""

from dataclasses import dataclass
from typing import List

import pandas as pd

from bybit_api.types import Kline
from .base import BaseStrategy, StrategyResult, Signal


@dataclass
class IFRParams:
    rsi_period: int = 14
    oversold_level: float = 30.0
    overbought_level: float = 70.0
    volatility_period: int = 14  # reservado para futuros usos


class IFRStrategy(BaseStrategy):
    """Estratégia baseada em IFR (RSI)."""

    def __init__(self, params: dict):
        super().__init__(params)
        self.cfg = IFRParams(
            rsi_period=int(params.get("rsi_period", 14)),
            oversold_level=float(params.get("oversold_level", 30.0)),
            overbought_level=float(params.get("overbought_level", 70.0)),
            volatility_period=int(params.get("volatility_period", 14)),
        )
        # Último valor de RSI calculado (para logging/monitoramento)
        self.last_rsi: float | None = None

    def get_max_klines(self) -> int:
        # Precisamos ao menos rsi_period + um pouco de histórico
        return max(self.cfg.rsi_period * 3, 100)

    def _compute_rsi(self, closes: List[float]) -> pd.Series:
        """
        Calcula RSI usando o método de Wilder (similar ao TradingView / Bybit).
        """
        series = pd.Series(closes, dtype="float64")
        delta = series.diff()

        # Ganhos e perdas separados
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Suavização de Wilder: EMA com alpha = 1 / período
        period = self.cfg.rsi_period
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_signal(self) -> StrategyResult:
        """Calcula sinal baseado em RSI com lógica simples de reversão."""
        if len(self.klines) < self.cfg.rsi_period + 2:
            # Histórico insuficiente
            last_price = self.klines[-1].close if self.klines else 0.0
            return StrategyResult(signal=Signal.NEUTRAL, confidence=0.0, entry_price=last_price)

        closes = [k.close for k in self.klines]
        rsi = self._compute_rsi(closes)
        current_rsi = float(rsi.iloc[-1])
        # Guardar para acesso externo (ex: logs do trader)
        self.last_rsi = current_rsi

        current_price = closes[-1]

        # Lógica básica:
        # - RSI abaixo de oversold_level -> possível compra (LONG)
        # - RSI acima de overbought_level -> possível venda (SHORT)
        # Sem gestão de posição interna aqui; o trader decide fechar com CLOSE_LONG/CLOSE_SHORT
        if current_rsi <= self.cfg.oversold_level:
            return StrategyResult(
                signal=Signal.LONG,
                confidence=min(1.0, (self.cfg.oversold_level - current_rsi) / 20.0),
                entry_price=current_price,
            )
        elif current_rsi >= self.cfg.overbought_level:
            return StrategyResult(
                signal=Signal.SHORT,
                confidence=min(1.0, (current_rsi - self.cfg.overbought_level) / 20.0),
                entry_price=current_price,
            )
        else:
            return StrategyResult(
                signal=Signal.NEUTRAL,
                confidence=0.0,
                entry_price=current_price,
            )

    def get_optimization_space(self) -> dict:
        """Espaço de busca para otimização."""
        return {
            "rsi_period": (5, 30),
            "oversold_level": (20.0, 40.0),
            "overbought_level": (60.0, 80.0),
            "volatility_period": (10, 30),
        }


