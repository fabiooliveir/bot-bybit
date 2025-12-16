import pandas_ta as ta  # noqa: F401

@dataclass
class TrailingStopState:
    """Estado do trailing stop"""
    is_active: bool
# ... (manter resto igual até classe TrailingStop)

class TrailingStop:
    """
    Trailing Stop otimizado usando ATR (via pandas-ta)
    
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
    
    # ... (manter activate, deactivate e calculate_trailing_stop_points iguais até chamar _calculate_atr)

    def _calculate_atr(self, klines: list) -> float:
        """Calcula ATR dos últimos klines usando pandas-ta"""
        if len(klines) < self.atr_period + 1:
            return 0.0
        
        df = pd.DataFrame({
            "high": [k.high for k in klines],
            "low": [k.low for k in klines],
            "close": [k.close for k in klines]
        })
        
        # Calcular ATR usando pandas-ta (padrão Wilder's MA/RMA)
        try:
            atr_series = df.ta.atr(length=self.atr_period)
            if atr_series is None or atr_series.empty:
                return 0.0
            return atr_series.iloc[-1]
        except Exception:
            return 0.0
    
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

