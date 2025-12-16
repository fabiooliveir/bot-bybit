"""
Otimização bayesiana de estratégias de trading.

Recriação simplificada usando scikit-optimize (skopt).
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

from skopt import gp_minimize
from skopt.space import Real, Integer

from bybit_api.types import Kline
from config.settings import Settings
from optimization.data_collector import DataCollector
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


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
    klines: List[Kline],
) -> float:
    """Backtest muito simplificado baseado em sinais da estratégia."""
    strat: BaseStrategy = strategy_cls(params=strategy_params)
    strat.update_klines(klines[: strat.get_max_klines()])

    position_side = None
    entry_price = 0.0
    equity = 1.0

    for k in klines:
        strat.add_kline(k)
        res = strat.calculate_signal()
        price = k.close

        if position_side is None:
            if res.signal.name == "LONG":
                position_side = "LONG"
                entry_price = price
            elif res.signal.name == "SHORT":
                position_side = "SHORT"
                entry_price = price
        else:
            if position_side == "LONG" and res.signal.name in ("CLOSE_LONG", "SHORT"):
                ret = (price - entry_price) / entry_price
                equity *= (1.0 + ret)
                position_side = None
            elif position_side == "SHORT" and res.signal.name in ("CLOSE_SHORT", "LONG"):
                ret = (entry_price - price) / entry_price
                equity *= (1.0 + ret)
                position_side = None

    return equity - 1.0


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
        total_return = _backtest(strategy_cls, strategy_params, klines)
        logger.info(f"Retorno total: {total_return:.4f}")
        return -float(total_return)

    res = gp_minimize(
        objective,
        search_space,
        n_calls=Settings.OPTIMIZATION_N_ITER,
        random_state=42,
        verbose=True,
    )

    best_strategy_params, best_ts_params = _params_from_vector(dim_names, res.x)
    best_return = -res.fun

    logger.info("=" * 60)
    logger.info("Otimização concluída")
    logger.info(f"Melhor retorno: {best_return:.4f}")
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
        },
    }

    Path(Settings.OPTIMIZED_PARAMS_FILE).write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(f"Parâmetros otimizados salvos em {Settings.OPTIMIZED_PARAMS_FILE}")
