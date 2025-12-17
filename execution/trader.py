"""
Loop principal de trading em tempo real.

Recria├º├úo simplificada que:
- carrega par├ómetros de `optimized_params.json`;
- instancia a estrat├®gia e o trailing stop;
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
# ├Ültimo "bucket" de candle (para logar no ritmo do timeframe, ex: a cada 5 minutos)
_last_log_bucket: Optional[int] = None


def _load_optimized_params() -> dict:
    """Carrega arquivo de par├ómetros otimizados."""
    path = Path(Settings.OPTIMIZED_PARAMS_FILE)
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo '{Settings.OPTIMIZED_PARAMS_FILE}' n├úo encontrado. "
            "Rode primeiro: python main.py --optimize"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_strategy_from_params(opt_params: dict) -> BaseStrategy:
    """Instancia estrat├®gia a partir do JSON de par├ómetros."""
    from importlib import import_module

    strategy_name = opt_params.get("strategy_name", "IFRStrategy")
    mapping = {
        "IFRStrategy": ("strategies.ifr_rsi", "IFRStrategy"),
    }
    if strategy_name not in mapping:
        raise ValueError(f"Estrat├®gia '{strategy_name}' n├úo suportada nesta recria├º├úo.")

    module_name, class_name = mapping[strategy_name]
    module = import_module(module_name)
    cls = getattr(module, class_name)
    params = opt_params.get("strategy", {})
    return cls(params=params)


def _init_historical_buffer(client: BybitClient, strategy: BaseStrategy) -> List[Kline]:
    """Inicializa buffer de klines hist├│ricos para a estrat├®gia."""
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
    # Prote├º├úo contra dados discrepantes (ex: Testnet bug REST vs WS)
    if strategy.klines:
        last_close = strategy.klines[-1].close
        
        
        # price_diff_pct = abs(kline.close - last_close) / last_close
        # if price_diff_pct > 0.05:  # Removendo bloqueio temporariamente para an├ílise
        #    logger.warning(f"DADOS IGNORADOS: Varia├º├úo > 5%: {last_close} -> {kline.close}")
        #    return

    # Atualizar klines da estrat├®gia
    strategy.add_kline(kline)
    
    # Calcular IFR
    # ...calculate_signal()
    res = strategy.calculate_signal()

    price = kline.close
    position = client.get_position(Settings.SYMBOL)
    
    # Sincronizar _current_side com a posição real da API
    global _current_side
    if position and position.size > 0:
        _current_side = position.side
    else:
        _current_side = None

    # Log do indicador no início de cada novo candle (seguindo o padrão do timeframe)
    # Exemplo: se TIMEFRAME=5, loga às 9h05, 9h10, 9h15, etc.
    # Exemplo: se TIMEFRAME=15, loga às 9h00, 9h15, 9h30, etc.
    try:
        interval_minutes = int(Settings.TIMEFRAME)
    except ValueError:
        interval_minutes = 5
    interval_ms = interval_minutes * 60 * 1000
    bucket = kline.open_time // interval_ms

    if bucket != _last_log_bucket:
        _last_log_bucket = bucket
        # Logar valor do IFR e ATR se a estratégia tiver esses atributos
        rsi_value = getattr(strategy, "last_rsi", None)
        atr_value = getattr(strategy, "last_atr", None)
        
        if rsi_value is not None:
            if atr_value is not None:
                logger.info(
                    f"IFR({interval_minutes}) atual = {rsi_value:.2f} | ATR atual = {atr_value:.2f} para {Settings.SYMBOL} (timeframe {Settings.TIMEFRAME})"
                )
            else:
                logger.info(
                    f"IFR({interval_minutes}) atual = {rsi_value:.2f} para {Settings.SYMBOL} (timeframe {Settings.TIMEFRAME})"
                )

    # Atualizar trailing stop se houver posi├º├úo
    if position and position.size > 0:
        pos_side = "LONG" if position.side == PositionSide.LONG else "SHORT"
        if trailing_stop.state is None:
            trailing_stop.activate(entry_price=position.entry_price, position_side=pos_side, klines=strategy.klines)

        stop_price = trailing_stop.update(current_price=price, klines=strategy.klines)
        if stop_price is not None:
            logger.info(f"Pre├ºo atingiu trailing stop ({stop_price:.2f}), fechando posi├º├úo")
            client.close_position(Settings.SYMBOL)
            trailing_stop.deactivate()
            return

    # Sinais de abertura/fechamento
    if res.signal == Signal.LONG:
        # Verificar posição real da API antes de ignorar sinal
        if position and position.size > 0 and position.side == PositionSide.LONG:
            logger.debug("Já em posição LONG (API), ignorando sinal LONG.")
            return
        # Se estado interno está dessincronizado, corrigir
        if _current_side == PositionSide.LONG and (not position or position.size == 0):
            logger.info("Corrigindo estado interno: posição LONG não existe mais na API")
            _current_side = None

        balance = client.get_balance()
        qty = position_manager.calculate_position_size(
            balance=balance,
            entry_price=price,
            leverage=Settings.MAX_LEVERAGE,
        )
        if qty <= 0:
            logger.warning("Quantidade calculada inv├ílida, n├úo abrindo LONG.")
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
        
        # Aguardar um pouco para a posi├º├úo ser confirmada
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
            logger.warning("Trailing stop calculado como 0, n├úo configurando na exchange")

        # Atualizar estado interno
        _current_side = PositionSide.LONG

    elif res.signal == Signal.SHORT:
        # Verificar posição real da API antes de ignorar sinal
        if position and position.size > 0 and position.side == PositionSide.SHORT:
            logger.debug("Já em posição SHORT (API), ignorando sinal SHORT.")
            return
        # Se estado interno está dessincronizado, corrigir
        if _current_side == PositionSide.SHORT and (not position or position.size == 0):
            logger.info("Corrigindo estado interno: posição SHORT não existe mais na API")
            _current_side = None

        balance = client.get_balance()
        qty = position_manager.calculate_position_size(
            balance=balance,
            entry_price=price,
            leverage=Settings.MAX_LEVERAGE,
        )
        if qty <= 0:
            logger.warning("Quantidade calculada inv├ílida, n├úo abrindo SHORT.")
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
        
        # Aguardar um pouco para a posi├º├úo ser confirmada
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
            logger.warning("Trailing stop calculado como 0, n├úo configurando na exchange")

        # Atualizar estado interno
        _current_side = PositionSide.SHORT

    elif res.signal in (Signal.CLOSE_LONG, Signal.CLOSE_SHORT):
        if position and position.size > 0:
            logger.info("Sinal de fechamento recebido, fechando posi├º├úo atual.")
            if client.close_position(Settings.SYMBOL):
                trailing_stop.deactivate()
                _current_side = None


def run_trader() -> None:
    """Fun├º├úo principal para iniciar o trader."""
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
    
    # Configurar alavancagem na exchange para garantir que corresponda ├ás configura├º├Áes
    client.set_leverage(Settings.SYMBOL, Settings.MAX_LEVERAGE)
    
    position_manager = PositionManager()

    _init_historical_buffer(client, strategy)
    
    # Verificar se j├í existe posi├º├úo aberta e configurar trailing stop
    existing_position = client.get_position(Settings.SYMBOL)
    if existing_position and existing_position.size > 0:
        pos_side = "LONG" if existing_position.side == PositionSide.LONG else "SHORT"
        logger.info(f"Posi├º├úo existente encontrada: {pos_side} de {existing_position.size} {Settings.SYMBOL}")
        trailing_stop.activate(
            entry_price=existing_position.entry_price,
            position_side=pos_side,
            klines=strategy.klines
        )
        _current_side = existing_position.side
        # Configurar trailing stop nativo da Bybit para posi├º├úo existente
        if existing_position.trailing_stop > 0:
            logger.info(f"Trailing Stop j├í configurado na exchange ({existing_position.trailing_stop}), mantendo configura├º├úo atual.")
        else:
            trailing_points = trailing_stop.calculate_trailing_stop_points(strategy.klines)
            if trailing_points > 0:
                logger.info(f"Configurando trailing stop para posi├º├úo existente: {trailing_points:.0f} pontos")
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
        logger.info("Interrup├º├úo recebida, parando trader...")
        _stop_event.set()

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while not _stop_event.is_set():
            time.sleep(1)
    finally:
        logger.info("Parando trader...")
        client.disconnect_websocket()
        logger.info("Trader parado")
