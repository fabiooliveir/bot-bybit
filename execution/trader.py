"""
Loop principal de trading em tempo real.

Recriação simplificada que:
- carrega parâmetros de `optimized_params.json`;
- instancia a estratégia e o trailing stop;
- usa `BybitClient` para WebSocket e ordens.
"""

import json
import logging
import signal
import threading
import time
from pathlib import Path
from typing import Optional, List

from bybit_api.client import BybitClient
from bybit_api.types import Kline, Side, OrderType, PositionSide
from config.settings import Settings
from optimization.data_collector import DataCollector
from risk_management.position_manager import PositionManager
from risk_management.trailing_stop import TrailingStop
from strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_current_side: Optional[PositionSide] = None
# Último "bucket" de candle (para logar no ritmo do timeframe, ex: a cada 5 minutos)
_last_log_bucket: Optional[int] = None


def _load_optimized_params() -> dict:
    """Carrega arquivo de parâmetros otimizados."""
    path = Path(Settings.OPTIMIZED_PARAMS_FILE)
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo '{Settings.OPTIMIZED_PARAMS_FILE}' não encontrado. "
            "Rode primeiro: python main.py --optimize"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_strategy_from_params(opt_params: dict) -> BaseStrategy:
    """Instancia estratégia a partir do JSON de parâmetros."""
    from importlib import import_module

    strategy_name = opt_params.get("strategy_name", "IFRStrategy")
    mapping = {
        "IFRStrategy": ("strategies.ifr_rsi", "IFRStrategy"),
    }
    if strategy_name not in mapping:
        raise ValueError(f"Estratégia '{strategy_name}' não suportada nesta recriação.")

    module_name, class_name = mapping[strategy_name]
    module = import_module(module_name)
    cls = getattr(module, class_name)
    params = opt_params.get("strategy", {})
    return cls(params=params)


def _init_historical_buffer(client: BybitClient, strategy: BaseStrategy) -> List[Kline]:
    """Inicializa buffer de klines históricos para a estratégia."""
    collector = DataCollector()
    klines = collector.collect_historical_data(days=3)
    strategy.update_klines(klines[-strategy.get_max_klines() :])
    logger.info(f"Buffer inicializado com {len(strategy.klines)} klines")
    return strategy.klines


def _handle_new_kline(
    kline: Kline,
    strategy: BaseStrategy,
    client: BybitClient,
    position_manager: PositionManager,
    trailing_stop: TrailingStop,
):
    """Processa novo kline em tempo real."""
    global _current_side, _last_log_bucket

    strategy.add_kline(kline)
    res = strategy.calculate_signal()

    price = kline.close
    position = client.get_position(Settings.SYMBOL)

    # Log do indicador no ritmo do timeframe (ex: exatamente a cada 5 minutos)
    try:
        interval_minutes = int(Settings.TIMEFRAME)
    except ValueError:
        interval_minutes = 5
    interval_ms = interval_minutes * 60 * 1000
    bucket = kline.open_time // interval_ms

    if bucket != _last_log_bucket:
        _last_log_bucket = bucket
        # Logar valor do IFR se a estratégia tiver esse atributo
        rsi_value = getattr(strategy, "last_rsi", None)
        if rsi_value is not None:
            logger.info(
                f"IFR({interval_minutes}) atual = {rsi_value:.2f} para {Settings.SYMBOL} (timeframe {Settings.TIMEFRAME})"
            )

    # Atualizar trailing stop se houver posição
    if position and position.size > 0:
        pos_side = "LONG" if position.side == PositionSide.LONG else "SHORT"
        if trailing_stop.state is None:
            trailing_stop.activate(entry_price=position.entry_price, position_side=pos_side, klines=strategy.klines)

        stop_price = trailing_stop.update(current_price=price, klines=strategy.klines)
        if stop_price is not None:
            logger.info(f"Preço atingiu trailing stop ({stop_price:.2f}), fechando posição")
            client.close_position(Settings.SYMBOL)
            trailing_stop.deactivate()
            return

    # Sinais de abertura/fechamento
    if res.signal == Signal.LONG:
        # Usar estado interno para evitar múltiplas entradas antes da posição aparecer na API
        if _current_side == PositionSide.LONG:
            logger.debug("Já em posição LONG (estado interno), ignorando sinal LONG.")
            return

        balance = client.get_balance()
        qty = position_manager.calculate_position_size(
            balance=balance,
            entry_price=price,
            leverage=Settings.MAX_LEVERAGE,
        )
        if qty <= 0:
            logger.warning("Quantidade calculada inválida, não abrindo LONG.")
            return

        # Tentar obter valor do IFR para log
        rsi_val = getattr(strategy, "last_rsi", None)
        rsi_log = f" (IFR={rsi_val:.2f})" if rsi_val is not None else ""
        
        logger.info(f"Abrindo LONG de {qty} {Settings.SYMBOL} a mercado{rsi_log}")
        client.place_order(
            symbol=Settings.SYMBOL,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            qty=qty,
        )
        
        # Aguardar um pouco para a posição ser confirmada
        time.sleep(1)
        
        # Ativar trailing stop localmente
        trailing_stop.activate(entry_price=price, position_side="LONG", klines=strategy.klines)
        
        # Configurar trailing stop nativo da Bybit
        trailing_points = trailing_stop.calculate_trailing_stop_points(strategy.klines)
        if trailing_points > 0:
            logger.info(f"Configurando trailing stop nativo da Bybit: {trailing_points:.0f} pontos")
            success = client.set_trading_stop(Settings.SYMBOL, trailing_points)
            if success:
                logger.info("Trailing stop configurado com sucesso na Bybit")
            else:
                logger.warning("Falha ao configurar trailing stop nativo, usando apenas controle local")
        else:
            logger.warning("Trailing stop calculado como 0, não configurando na exchange")

        # Atualizar estado interno
        _current_side = PositionSide.LONG

    elif res.signal == Signal.SHORT:
        # Usar estado interno para evitar múltiplas entradas antes da posição aparecer na API
        if _current_side == PositionSide.SHORT:
            logger.debug("Já em posição SHORT (estado interno), ignorando sinal SHORT.")
            return

        balance = client.get_balance()
        qty = position_manager.calculate_position_size(
            balance=balance,
            entry_price=price,
            leverage=Settings.MAX_LEVERAGE,
        )
        if qty <= 0:
            logger.warning("Quantidade calculada inválida, não abrindo SHORT.")
            return

        # Tentar obter valor do IFR para log
        rsi_val = getattr(strategy, "last_rsi", None)
        rsi_log = f" (IFR={rsi_val:.2f})" if rsi_val is not None else ""

        logger.info(f"Abrindo SHORT de {qty} {Settings.SYMBOL} a mercado{rsi_log}")
        client.place_order(
            symbol=Settings.SYMBOL,
            side=Side.SELL,
            order_type=OrderType.MARKET,
            qty=qty,
        )
        
        # Aguardar um pouco para a posição ser confirmada
        time.sleep(1)
        
        # Ativar trailing stop localmente
        trailing_stop.activate(entry_price=price, position_side="SHORT", klines=strategy.klines)
        
        # Configurar trailing stop nativo da Bybit
        trailing_points = trailing_stop.calculate_trailing_stop_points(strategy.klines)
        if trailing_points > 0:
            logger.info(f"Configurando trailing stop nativo da Bybit: {trailing_points:.0f} pontos")
            success = client.set_trading_stop(Settings.SYMBOL, trailing_points)
            if success:
                logger.info("Trailing stop configurado com sucesso na Bybit")
            else:
                logger.warning("Falha ao configurar trailing stop nativo, usando apenas controle local")
        else:
            logger.warning("Trailing stop calculado como 0, não configurando na exchange")

        # Atualizar estado interno
        _current_side = PositionSide.SHORT

    elif res.signal in (Signal.CLOSE_LONG, Signal.CLOSE_SHORT):
        if position and position.size > 0:
            logger.info("Sinal de fechamento recebido, fechando posição atual.")
            if client.close_position(Settings.SYMBOL):
                trailing_stop.deactivate()
                _current_side = None


def run_trader() -> None:
    """Função principal para iniciar o trader."""
    global _stop_event, _current_side, _last_log_bucket
    _stop_event.clear()
    _current_side = None
    _last_log_bucket = None

    opt_params = _load_optimized_params()
    strategy = _load_strategy_from_params(opt_params)
    trailing_params = opt_params.get("trailing_stop", {})
    trailing_stop = TrailingStop(
        atr_multiplier=trailing_params.get("atr_multiplier", 2.0),
        atr_period=int(trailing_params.get("atr_period", 14)),
    )

    client = BybitClient()
    
    # Configurar alavancagem na exchange para garantir que corresponda às configurações
    client.set_leverage(Settings.SYMBOL, Settings.MAX_LEVERAGE)
    
    position_manager = PositionManager()

    _init_historical_buffer(client, strategy)
    
    # Verificar se já existe posição aberta e configurar trailing stop
    existing_position = client.get_position(Settings.SYMBOL)
    if existing_position and existing_position.size > 0:
        pos_side = "LONG" if existing_position.side == PositionSide.LONG else "SHORT"
        logger.info(f"Posição existente encontrada: {pos_side} de {existing_position.size} {Settings.SYMBOL}")
        trailing_stop.activate(
            entry_price=existing_position.entry_price,
            position_side=pos_side,
            klines=strategy.klines
        )
        _current_side = existing_position.side
        # Configurar trailing stop nativo da Bybit para posição existente
        trailing_points = trailing_stop.calculate_trailing_stop_points(strategy.klines)
        if trailing_points > 0:
            logger.info(f"Configurando trailing stop para posição existente: {trailing_points:.0f} pontos")
            client.set_trading_stop(Settings.SYMBOL, trailing_points)

    logger.info("Iniciando trader e aguardando sinais...")

    def ws_callback(k: Kline):
        if _stop_event.is_set():
            return
        try:
            _handle_new_kline(
                kline=k,
                strategy=strategy,
                client=client,
                position_manager=position_manager,
                trailing_stop=trailing_stop,
            )
        except Exception as e:
            logger.error(f"Erro no processamento de kline em tempo real: {e}")

    client.setup_websocket(Settings.SYMBOL, ws_callback)

    def handle_sigint(signum, frame):
        logger.info("Interrupção recebida, parando trader...")
        _stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while not _stop_event.is_set():
            time.sleep(1)
    finally:
        logger.info("Parando trader...")
        client.disconnect_websocket()
        logger.info("Trader parado")
