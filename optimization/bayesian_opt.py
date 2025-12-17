"""
Otimização bayesiana de estratégias de trading.

Recriação simplificada usando scikit-optimize (skopt).
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
from skopt import gp_minimize
from skopt.space import Real, Integer

from bybit_api.types import Kline
from config.settings import Settings
from optimization.data_collector import DataCollector
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


def _convert_to_native_types(obj: Any) -> Any:
    """Converte valores numpy para tipos Python nativos para serialização JSON."""
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_to_native_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_to_native_types(item) for item in obj]
    return obj


def _load_strategy_class(strategy_name: str):
    """Carrega classe de estratégia a partir do nome."""
    from importlib import import_module

    mapping = {
        "ifr": ("strategies.ifr_rsi", "IFRStrategy"),
        "IFRStrategy": ("strategies.ifr_rsi", "IFRStrategy"),
    }

    if strategy_name is None:
        params_file = Path(Settings.OPTIMIZED_PARAMS_FILE)
        if params_file.exists():
            try:
                data = json.loads(params_file.read_text(encoding="utf-8"))
                name = data.get("strategy_name")
                if name:
                    strategy_name = name
            except Exception:
                pass

    if strategy_name not in mapping:
        raise ValueError(
            f"Estratégia '{strategy_name}' não suportada nesta recriação. "
            "Use por exemplo: --strategy ifr"
        )

    module_name, class_name = mapping[strategy_name]
    module = import_module(module_name)
    cls = getattr(module, class_name)
    if not issubclass(cls, BaseStrategy):
        raise TypeError(f"{class_name} não é uma subclasse de BaseStrategy")
    return cls


def _build_search_space(strategy_cls: type) -> List:
    """Constroi espaço de busca unindo espaço da estratégia e do trailing stop."""
    dummy = strategy_cls(params={})
    strat_space = dummy.get_optimization_space()

    from risk_management.trailing_stop import TrailingStop

    ts = TrailingStop()
    ts_space = ts.get_optimization_space()

    space = []
    for key, bounds in strat_space.items():
        low, high = bounds
        if isinstance(low, int) and isinstance(high, int):
            space.append(Integer(low, high, name=f"strategy__{key}"))
        else:
            space.append(Real(float(low), float(high), name=f"strategy__{key}"))

    for key, bounds in ts_space.items():
        low, high = bounds
        if isinstance(low, int) and isinstance(high, int):
            space.append(Integer(low, high, name=f"trailing_stop__{key}"))
        else:
            space.append(Real(float(low), float(high), name=f"trailing_stop__{key}"))

    return space


def _params_from_vector(dim_names: List[str], x: List[float]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Separa vetor de parâmetros em dicionários de estratégia e trailing stop."""
    strategy_params: Dict[str, Any] = {}
    ts_params: Dict[str, Any] = {}

    for name, value in zip(dim_names, x):
        if name.startswith("strategy__"):
            key = name.split("__", 1)[1]
            strategy_params[key] = value
        elif name.startswith("trailing_stop__"):
            key = name.split("__", 1)[1]
            ts_params[key] = value

    return strategy_params, ts_params


def _backtest(
    strategy_cls: type,
    strategy_params: Dict[str, Any],
    ts_params: Dict[str, Any],
    klines: List[Kline],
) -> Tuple[float, int]:
    """Backtest com simulação de Trailing Stop."""
    strat: BaseStrategy = strategy_cls(params=strategy_params)
    strat.update_klines(klines[: strat.get_max_klines()])

    from risk_management.trailing_stop import TrailingStop
    ts = TrailingStop(
        atr_multiplier=float(ts_params.get("atr_multiplier", 2.0)),
        atr_period=int(ts_params.get("atr_period", 14))
    )

    position_side = None
    entry_price = 0.0
    equity = 1.0
    trade_count = 0

    # Iterar a partir do ponto onde temos histórico suficiente
    start_idx = strat.get_max_klines()
    
    # Simulação barra a barra
    for i in range(start_idx, len(klines)):
        current_kline = klines[i]
        strat.add_kline(current_kline)
        res = strat.calculate_signal()
        price = current_kline.close
        
        # 1. Verificar Stops e Saídas se estiver posicionado
        if position_side is not None:
            # Verificar Trailing Stop
            stop_price = ts.update(price, strat.klines)
            hit_stop = False
            
            if stop_price:
                if position_side == "LONG" and price <= stop_price:
                    hit_stop = True
                elif position_side == "SHORT" and price >= stop_price:
                    hit_stop = True
            
            # Verificar Sinal de Saída da Estratégia
            signal_close = False
            if position_side == "LONG" and res.signal.name in ("CLOSE_LONG", "SHORT"):
                signal_close = True
            elif position_side == "SHORT" and res.signal.name in ("CLOSE_SHORT", "LONG"):
                signal_close = True
            
            # Executar saída
            if hit_stop or signal_close:
                # Calcular PnL
                if position_side == "LONG":
                    # Se foi stop, saiu no preço do stop (slippage ignorado)
                    exit_p = stop_price if hit_stop else price
                    ret = (exit_p - entry_price) / entry_price
                else:
                    exit_p = stop_price if hit_stop else price
                    ret = (entry_price - exit_p) / entry_price
                    
                equity *= (1.0 + ret)
                position_side = None
                ts.deactivate()
        
        # 2. Verificar Entradas (se não estiver posicionado)
        # Nota: Se acabou de fechar, aguarda próximo candle (simplificação)
        if position_side is None:
            if res.signal.name == "LONG":
                position_side = "LONG"
                entry_price = price
                trade_count += 1
                ts.activate(entry_price, "LONG", strat.klines)
            elif res.signal.name == "SHORT":
                position_side = "SHORT"
                entry_price = price
                trade_count += 1
                ts.activate(entry_price, "SHORT", strat.klines)

    return equity - 1.0, trade_count


def run_optimization(strategy_name: str = None) -> None:
    """Executa processo de otimização bayesiana."""
    collector = DataCollector()
    klines = collector.collect_historical_data(days=Settings.OPTIMIZATION_DAYS)

    if not klines:
        logger.error("Nenhum kline retornado para otimização.")
        return

    strategy_cls = _load_strategy_class(strategy_name or "ifr")
    search_space = _build_search_space(strategy_cls)
    dim_names = [dim.name for dim in search_space]

    logger.info(f"Estratégia: {strategy_cls.__name__}")
    logger.info(f"Número de parâmetros a otimizar: {len(dim_names)}")

    def objective(x: List[float]) -> float:
        strategy_params, ts_params = _params_from_vector(dim_names, x)
        logger.info(f"Avaliando params: strategy={strategy_params}, trailing={ts_params}")
        total_return, trade_count = _backtest(strategy_cls, strategy_params, ts_params, klines)
        logger.info(f"Retorno total: {total_return:.4f} | Trades: {trade_count}")
        
        # Penalizar estratégias com poucos trades (ex: menos de 5) para evitar overfitting em outliers
        if trade_count < 5:
            return 1.0  # Penalidade

        return -float(total_return)

    res = gp_minimize(
        objective,
        search_space,
        n_calls=Settings.OPTIMIZATION_N_ITER,
        random_state=42,
        verbose=True,
    )

    best_strategy_params, best_ts_params = _params_from_vector(dim_names, res.x)
    
    # Re-executar backtest com melhores parâmetros para obter métricas detalhadas
    best_return, best_trade_count = _backtest(strategy_cls, best_strategy_params, best_ts_params, klines)

    logger.info("=" * 60)
    logger.info("Otimização concluída")
    logger.info(f"Melhor retorno: {best_return:.4f}")
    logger.info(f"Total trades: {best_trade_count}")
    logger.info(f"Melhores parâmetros da estratégia: {best_strategy_params}")
    logger.info(f"Melhores parâmetros do trailing stop: {best_ts_params}")
    logger.info("=" * 60)

    result: Dict[str, Any] = {
        "strategy": best_strategy_params,
        "strategy_name": strategy_cls.__name__,
        "trailing_stop": best_ts_params,
        "symbol": Settings.SYMBOL,
        "timeframe": Settings.TIMEFRAME,
        "metrics": {
            "total_return": best_return,
            "total_trades": best_trade_count,
        },
    }

    # Converter valores numpy para tipos Python nativos
    result = _convert_to_native_types(result)

    Path(Settings.OPTIMIZED_PARAMS_FILE).write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(f"Parâmetros otimizados salvos em {Settings.OPTIMIZED_PARAMS_FILE}")
