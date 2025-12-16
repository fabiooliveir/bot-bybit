# Strategies module
from .base import BaseStrategy, StrategyResult, Signal
from .ifr_rsi import IFRStrategy

__all__ = [
    "BaseStrategy",
    "StrategyResult",
    "Signal",
    "IFRStrategy",
]