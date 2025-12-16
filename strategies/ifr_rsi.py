import pandas_ta as ta  # noqa: F401

@dataclass
# ... (manter resto igual até classe IFRStrategy)

class IFRStrategy(BaseStrategy):
    """Estratégia baseada em IFR (RSI) usando pandas-ta."""

    def __init__(self, params: dict):
        super().__init__(params)
        self.cfg = IFRParams(
            rsi_period=int(params.get("rsi_period", 14)),
            oversold_level=float(params.get("oversold_level", 30.0)),
            overbought_level=float(params.get("overbought_level", 70.0)),
            volatility_period=int(params.get("volatility_period", 14)),
        )
        self.last_rsi: float | None = None

    def get_max_klines(self) -> int:
        return max(self.cfg.rsi_period * 3, 100)

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


