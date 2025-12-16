"""
Gerenciamento de posições e cálculo de tamanho
"""
from typing import Optional
import logging

from bybit_api.types import Balance, Position
from config.settings import Settings

logger = logging.getLogger(__name__)


class PositionManager:
    """Gerencia tamanho de posições baseado em percentual do capital"""
    
    def __init__(self, position_size_percent: float = None):
        """
        Args:
            position_size_percent: Percentual do capital para usar em cada trade (0-100)
        """
        self.position_size_percent = position_size_percent or Settings.POSITION_SIZE_PERCENT
    
    def calculate_position_size(
        self,
        balance: Balance,
        entry_price: float,
        stop_loss_price: float = None,  # Não usado mais, mas mantido para compatibilidade
        leverage: int = 1
    ) -> float:
        """
        Calcula tamanho da posição baseado em percentual do capital disponível
        
        A quantidade é calculada diretamente do valor em USDT a investir:
        quantidade = (capital_disponivel × percentual × leverage) / preço_entrada
        
        Args:
            balance: Saldo da conta
            entry_price: Preço de entrada
            stop_loss_price: Não usado mais (mantido para compatibilidade)
            leverage: Leverage a ser usado
        
        Returns:
            Quantidade a ser negociada (em unidades do ativo)
        """
        if entry_price <= 0:
            logger.warning("Preço de entrada inválido")
            return 0.0
        
        # Capital disponível para trading
        # Se available_balance for muito baixo ou zero, usar wallet_balance como fallback
        # (pode acontecer em contas demo ou quando há margem bloqueada)
        available_capital = balance.available_balance
        if available_capital < 1.0:  # Se disponível for menos de 1 USDT, usar saldo total
            logger.warning(f"Saldo disponível muito baixo ({available_capital}). Usando saldo total ({balance.wallet_balance})")
            available_capital = balance.wallet_balance * 0.95  # Usar 95% do saldo total como margem de segurança
        
        # Valor a investir (em USDT) = percentual do capital disponível
        capital_to_invest = available_capital * (self.position_size_percent / 100.0)
        
        logger.info(f"Cálculo de posição: capital_disponivel={available_capital:.2f} USDT, percentual={self.position_size_percent}%, capital_a_investir={capital_to_invest:.2f} USDT")
        
        # Quantidade = (valor a investir × leverage) / preço de entrada
        quantity = (capital_to_invest * leverage) / entry_price
        
        logger.info(f"Cálculo de posição: entry_price={entry_price:.2f}, leverage={leverage}, quantity={quantity:.6f}, valor_investido={quantity * entry_price:.2f} USDT")
        
        # Verificar tamanho mínimo de ordem
        if quantity < Settings.MIN_ORDER_SIZE:
            logger.warning(
                f"Quantidade calculada {quantity:.6f} menor que mínimo {Settings.MIN_ORDER_SIZE}. "
                f"Capital disponível: {available_capital:.2f} USDT, "
                f"Capital a investir: {capital_to_invest:.2f} USDT, "
                f"Preço entrada: {entry_price:.2f} USDT"
            )
            return 0.0
        
        # Arredondar para step size de 0.001 (BTCUSDT)
        # Garantir que seja múltiplo de 0.001
        return round(quantity / 0.001) * 0.001
    
    def validate_position_size(self, quantity: float) -> bool:
        """Valida se o tamanho da posição está dentro dos limites"""
        if quantity < Settings.MIN_ORDER_SIZE:
            return False
        return True
    
    def get_max_position_value(self, balance: Balance, leverage: int = 1) -> float:
        """Retorna valor máximo de posição que pode ser aberta"""
        return balance.available_balance * leverage


