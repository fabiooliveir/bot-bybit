"""
Estratégia IFR (RSI) simples, recriada a partir dos parâmetros presentes
em `optimized_params.json` (rsi_period, oversold_level, overbought_level, volatility_period).
"""

from dataclasses import dataclass
from typing import List

import pandas as pd
import pandas_ta as ta

from bybit_api.types import Kline
from .base import BaseStrategy, StrategyResult, Signal


@dataclass
class IFRParams:
    rsi_period: int = 14
    oversold_level: float = 30.0
    overbought_level: float = 70.0
    volatility_period: int = 14  # reservado para futuros usos
    atr_period: int = 14  # período para cálculo do ATR
    atr_lookback_period: int = 20  # período para calcular média histórica do ATR
    atr_min_multiplier: float = 0.5  # múltiplo mínimo da média ATR (ex: 0.5 = 50% da média)
    atr_max_multiplier: float = 2.0  # múltiplo máximo da média ATR (ex: 2.0 = 200% da média)


class IFRStrategy(BaseStrategy):
    """Estratégia baseada em IFR (RSI) usando pandas-ta."""

    def __init__(self, params: dict):
        super().__init__(params)
        self.cfg = IFRParams(
            rsi_period=int(params.get("rsi_period", 14)),
            oversold_level=float(params.get("oversold_level", 30.0)),
            overbought_level=float(params.get("overbought_level", 70.0)),
            volatility_period=int(params.get("volatility_period", 14)),
            atr_period=int(params.get("atr_period", 14)),
            atr_lookback_period=int(params.get("atr_lookback_period", 20)),
            atr_min_multiplier=float(params.get("atr_min_multiplier", 0.0)),  # 0.0 = desabilitar filtro
            atr_max_multiplier=float(params.get("atr_max_multiplier", 999.0)),  # 999.0 = desabilitar filtro
        )
        # Último valor de RSI calculado (para logging/monitoramento)
        self.last_rsi: float | None = None
        # Último valor de ATR calculado (para logging/monitoramento)
        self.last_atr: float | None = None

    def get_max_klines(self) -> int:
        # Precisamos histórico suficiente para RSI, ATR e lookback do ATR
        max_period = max(
            self.cfg.rsi_period,
            self.cfg.atr_period,
            self.cfg.atr_lookback_period
        )
        return max(max_period * 3, 100)

    def _compute_rsi(self, closes: List[float]) -> pd.Series:
        """
        Calcula RSI usando pandas-ta (Wilder's method).
        """
        if not closes:
            return pd.Series(dtype="float64")
            
        df = pd.DataFrame({"close": closes})
        # Calcular RSI
        try:
            rsi = df.ta.rsi(close="close", length=self.cfg.rsi_period)
            return rsi
        except Exception:
            return pd.Series(dtype="float64")
    
    def _compute_atr(self, klines: List[Kline]) -> pd.Series:
        """
        Calcula ATR usando pandas-ta.
        Retorna série completa de valores ATR.
        """
        if len(klines) < self.cfg.atr_period + 1:
            return pd.Series(dtype="float64")
        
        df = pd.DataFrame({
            "high": [k.high for k in klines],
            "low": [k.low for k in klines],
            "close": [k.close for k in klines]
        })
        
        try:
            atr_series = df.ta.atr(length=self.cfg.atr_period)
            return atr_series if atr_series is not None else pd.Series(dtype="float64")
        except Exception:
            return pd.Series(dtype="float64")

    def calculate_signal(self) -> StrategyResult:
        """Calcula sinal baseado em RSI com filtro de volatilidade ATR."""
        if len(self.klines) < self.cfg.rsi_period + 2:
            # Histórico insuficiente
            last_price = self.klines[-1].close if self.klines else 0.0
            return StrategyResult(signal=Signal.NEUTRAL, confidence=0.0, entry_price=last_price)

        current_price = self.klines[-1].close if self.klines else 0.0
        
        # Calcular RSI primeiro (sempre, para logging)
        closes = [k.close for k in self.klines]
        rsi = self._compute_rsi(closes)
        if rsi.empty:
             return StrategyResult(signal=Signal.NEUTRAL, confidence=0.0, entry_price=current_price)

        current_rsi = float(rsi.iloc[-1])
        # Guardar para acesso externo (ex: logs do trader) - SEMPRE calcular e setar
        self.last_rsi = current_rsi
        
        # Calcular série de ATR para filtro de volatilidade
        atr_series = self._compute_atr(self.klines)
        # #region agent log
        import json
        import time
        try:
            from pathlib import Path
            debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
            with open(str(debug_log), 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"strategies/ifr_rsi.py:102","message":"ATR series computed","data":{"atr_series_empty":atr_series.empty,"atr_series_len":len(atr_series) if not atr_series.empty else 0,"atr_lookback_period":self.cfg.atr_lookback_period,"atr_min_mult":self.cfg.atr_min_multiplier,"atr_max_mult":self.cfg.atr_max_multiplier},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # Aplicar filtro ATR se houver histórico suficiente e filtro estiver habilitado
        if (not atr_series.empty and 
            len(atr_series) >= self.cfg.atr_lookback_period and
            self.cfg.atr_min_multiplier > 0.0 and 
            self.cfg.atr_max_multiplier < 999.0):
            
            # Calcular média dos últimos atr_lookback_period valores
            recent_atr = atr_series.tail(self.cfg.atr_lookback_period)
            atr_mean = float(recent_atr.mean())
            
            # Calcular limites dinâmicos baseados na média
            atr_min = atr_mean * self.cfg.atr_min_multiplier
            atr_max = atr_mean * self.cfg.atr_max_multiplier
            
            # ATR atual
            current_atr = float(atr_series.iloc[-1])
            self.last_atr = current_atr
            # #region agent log
            try:
                from pathlib import Path
                debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
                with open(str(debug_log), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"strategies/ifr_rsi.py:120","message":"ATR filter check","data":{"atr_mean":atr_mean,"atr_min":atr_min,"atr_max":atr_max,"current_atr":current_atr,"is_outlier":current_atr < atr_min or current_atr > atr_max},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            
            # Filtro de volatilidade: verificar se ATR atual está no range da média
            if current_atr < atr_min or current_atr > atr_max:
                # Outlier de volatilidade - bloquear entrada (mas RSI já foi calculado para logging)
                return StrategyResult(
                    signal=Signal.NEUTRAL,
                    confidence=0.0,
                    entry_price=current_price
                )
        elif not atr_series.empty:
            # Guardar ATR atual mesmo se filtro não estiver ativo
            self.last_atr = float(atr_series.iloc[-1])
            # #region agent log
            try:
                from pathlib import Path
                debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
                with open(str(debug_log), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"strategies/ifr_rsi.py:132","message":"ATR set but filter disabled","data":{"last_atr":self.last_atr},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
        else:
            self.last_atr = None
            # #region agent log
            try:
                from pathlib import Path
                debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
                with open(str(debug_log), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"strategies/ifr_rsi.py:134","message":"ATR series empty","data":{},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion

        # ATR OK (dentro do range normal ou filtro desabilitado) - aplicar lógica RSI

        # Lógica básica:
        # - RSI abaixo de oversold_level -> possível compra (LONG)
        # - RSI acima de overbought_level -> possível venda (SHORT)
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
            "atr_period": (10, 30),  # período para cálculo do ATR
            "atr_lookback_period": (10, 50),  # período para calcular média histórica
            "atr_min_multiplier": (0.1, 1.0),  # múltiplo mínimo da média (ex: 0.3 = 30% da média)
            "atr_max_multiplier": (1.0, 3.0),  # múltiplo máximo da média (ex: 2.0 = 200% da média)
        }
