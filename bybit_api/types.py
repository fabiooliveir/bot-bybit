"""
Tipos e enums para Bybit API
"""
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


class Side(Enum):
    """Lado da posição/ordem"""
    BUY = "Buy"
    SELL = "Sell"


class OrderType(Enum):
    """Tipo de ordem"""
    MARKET = "Market"
    LIMIT = "Limit"


class PositionSide(Enum):
    """Lado da posição"""
    LONG = "Long"
    SHORT = "Short"
    NONE = "None"


@dataclass
class Kline:
    """Representa um candle/kline"""
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @classmethod
    def from_bybit(cls, data: list) -> "Kline":
        """Cria Kline a partir de dados da Bybit"""
        return cls(
            open_time=int(data[0]),
            close_time=int(data[0]) + 1000 * 60 * 5,  # Assumindo 5 min
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5])
        )


@dataclass
class Position:
    """Representa uma posição aberta"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    mark_price: float
    leverage: int
    unrealised_pnl: float
    margin: float
    
    @classmethod
    def from_bybit(cls, data: Dict[str, Any]) -> Optional["Position"]:
        """Cria Position a partir de dados da Bybit"""
        if not data or float(data.get("size", 0)) == 0:
            return None
        
        side = PositionSide.LONG if data.get("side") == "Buy" else PositionSide.SHORT
        
        return cls(
            symbol=data.get("symbol", ""),
            side=side,
            size=float(data.get("size", 0)),
            entry_price=float(data.get("avgPrice", 0)),
            mark_price=float(data.get("markPrice", 0)),
            leverage=int(data.get("leverage", 1)),
            unrealised_pnl=float(data.get("unrealisedPnl", 0)),
            margin=float(data.get("positionMargin", 0))
        )


@dataclass
class Balance:
    """Saldo da conta"""
    available_balance: float
    wallet_balance: float
    used_margin: float
    
    @classmethod
    def from_bybit(cls, data: Dict[str, Any]) -> "Balance":
        """Cria Balance a partir de dados da Bybit"""
        return cls(
            available_balance=float(data.get("availableBalance", 0)),
            wallet_balance=float(data.get("walletBalance", 0)),
            used_margin=float(data.get("usedMargin", 0))
        )






