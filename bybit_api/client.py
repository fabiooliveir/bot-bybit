"""
Cliente wrapper para Bybit API
"""
import time
import json
from typing import List, Optional, Dict, Any
from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket as BybitWebSocket
import logging

from .types import Kline, Position, Balance, Side, OrderType, PositionSide
from config.settings import Settings

logger = logging.getLogger(__name__)


class BybitClient:
    """Cliente para interagir com Bybit API"""
    
    def __init__(self):
        config = Settings.get_bybit_config()
        base_url = config["base_url"]
        
        # Criar cliente HTTP
        # pybit não suporta base_url direto, então usamos testnet=True para testnet/demo
        # e depois patchamos a URL se necessário
        init_params = {
            "api_key": config["api_key"] if config["api_key"] else None,
            "api_secret": config["api_secret"] if config["api_secret"] else None
        }
        
        # Se não for production, usar testnet=True
        # Mas depois vamos patchar a URL para usar a correta (demo ou testnet)
        if config["environment"] != "production":
            init_params["testnet"] = True
        
        self.client = HTTP(**init_params)
        
        # Sempre patchar a URL para garantir que usamos a correta
        # (demo precisa usar api-demo.bybit.com, não api-testnet.bybit.com)
        if config["environment"] != "production":
            self._patch_base_url(base_url)
        
        self.base_url = base_url
        self.ws = None
        self.ws_callbacks = {}
    
    def _patch_base_url(self, target_url: str):
        """Patcheia a URL base do cliente HTTP para usar a URL especificada"""
        try:
            original_prepare = self.client._prepare_request
            
            def patched_prepare_request(method, path, query, headers):
                """Patch que modifica a URL base"""
                prep_req = original_prepare(method, path, query, headers)
                if hasattr(prep_req, 'url') and prep_req.url:
                    # Substituir qualquer URL de bybit pela target_url
                    if 'api.bybit.com' in prep_req.url:
                        prep_req.url = prep_req.url.replace('https://api.bybit.com', target_url)
                    elif 'api-testnet.bybit.com' in prep_req.url:
                        original_url = prep_req.url
                        prep_req.url = prep_req.url.replace('https://api-testnet.bybit.com', target_url)
                        # Muito verboso em produção, manter apenas em nível debug
                        logger.debug(f"URL patchada: {original_url} -> {prep_req.url}")
                    elif 'api-demo.bybit.com' in prep_req.url:
                        prep_req.url = prep_req.url.replace('https://api-demo.bybit.com', target_url)
                        logger.debug(f"URL patchada: {prep_req.url}")
                return prep_req
            
            self.client._prepare_request = patched_prepare_request
            logger.info(f"Cliente configurado para usar: {target_url}")
        except Exception as e:
            logger.warning(f"Não foi possível patchar URL base: {e}. Usando URL padrão do pybit.")
        
    def get_klines(
        self, 
        symbol: str, 
        interval: str, 
        limit: int = 200,
        start: Optional[int] = None,
        end: Optional[int] = None
    ) -> List[Kline]:
        """Obtém dados históricos de klines/candles"""
        try:
            params = {
                "category": Settings.MARKET_TYPE,
                "symbol": symbol,
                "interval": interval,
                "limit": min(limit, 200)  # Máximo da API
            }
            
            if start:
                params["start"] = start
            if end:
                params["end"] = end
                
            response = self.client.get_kline(**params)
            
            if response["retCode"] != 0:
                raise Exception(f"Erro ao obter klines: {response['retMsg']}")
            
            result = response["result"]["list"]
            # A Bybit retorna do mais recente para o mais antigo, inverter
            result.reverse()
            
            return [Kline.from_bybit(kline) for kline in result]
            
        except Exception as e:
            logger.error(f"Erro ao obter klines: {e}")
            raise
    
    def get_historical_klines(
        self, 
        symbol: str, 
        interval: str, 
        days: int = 30
    ) -> List[Kline]:
        """Obtém dados históricos de múltiplos dias (faz múltiplas requisições)"""
        all_klines = []
        end_time = int(time.time() * 1000)
        
        # Calcular quantos candles precisamos
        interval_minutes = {
            "1": 1, "3": 3, "5": 5, "15": 15, "30": 30,
            "60": 60, "120": 120, "240": 240, "360": 360, "720": 720,
            "D": 1440, "W": 10080, "M": 43200
        }
        minutes_per_candle = interval_minutes.get(interval, 5)
        total_candles = (days * 24 * 60) // minutes_per_candle
        
        while len(all_klines) < total_candles:
            remaining = total_candles - len(all_klines)
            limit = min(remaining, 200)
            
            klines = self.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                end=end_time
            )
            
            if not klines:
                break
                
            # klines vem ordenado Antigo -> Novo (pois get_klines inverte)
            # Mas estamos buscando do presente para o passado
            # Então devemos inserir os blocos mais antigos ANTES dos blocos mais novos
            
            # Ex: Primeiro loop pega (Hoje 10h .. Hoje 12h)
            # Segundo loop pega (Hoje 08h .. Hoje 10h)
            # Resultado final deve ser (08h..10h) + (10h..12h)
            
            all_klines = klines + all_klines
            
            end_time = klines[0].open_time - 1
            
            # Rate limiting
            time.sleep(0.2)
        
        # Garantia final de ordenação por tempo
        all_klines.sort(key=lambda k: k.open_time)
        return all_klines
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Obtém posição atual para o símbolo"""
        try:
            response = self.client.get_positions(
                category=Settings.MARKET_TYPE,
                symbol=symbol
            )
            
            if response["retCode"] != 0:
                raise Exception(f"Erro ao obter posição: {response['retMsg']}")
            
            positions = response["result"]["list"]
            for pos_data in positions:
                position = Position.from_bybit(pos_data)
                if position:
                    return position
            
            return None
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                logger.error("=" * 60)
                logger.error("ERRO DE AUTENTICACAO (401)")
                logger.error("=" * 60)
                logger.error("Possiveis causas:")
                logger.error("1. API Key ou Secret incorretos")
                logger.error("2. API Key sem permissao para acessar posicoes")
                logger.error("3. IP nao permitido na API Key")
                logger.error("4. Ambiente incorreto (production/demo/testnet) ou credenciais do ambiente errado")
                logger.error("")
                logger.error(f"Ambiente configurado: {Settings.ENVIRONMENT}")
                logger.error(f"Base URL: {Settings.get_base_url()}")
                logger.error("Verifique BYBIT_ENVIRONMENT e credenciais no arquivo .env")
                logger.error("=" * 60)
            else:
                logger.error(f"Erro ao obter posicao: {e}")
            raise  # Re-raise exception to avoid treating error as "no position"
    
    def get_balance(self) -> Balance:
        """Obtém saldo da conta"""
        try:
            # Usar accountType baseado no ambiente (UNIFIED para demo/testnet, linear para production)
            account_type = Settings.get_account_type()
            
            response = self.client.get_wallet_balance(
                accountType=account_type,
                coin="USDT"
            )
            
            if response["retCode"] != 0:
                raise Exception(f"Erro ao obter saldo: {response['retMsg']}")
            
            coin_list = response["result"]["list"][0]["coin"]
            for coin in coin_list:
                if coin["coin"] == "USDT":
                    return Balance.from_bybit(coin)
            
            raise Exception("USDT não encontrado no saldo")
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                logger.error("Erro de autenticacao ao obter saldo. Verifique suas credenciais.")
            raise
    
    def place_order(
        self,
        symbol: str,
        side: Side,
        order_type: OrderType,
        qty: float,
        price: Optional[float] = None,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """Coloca uma ordem"""
        try:
            # Formatar quantidade para o formato correto da Bybit
            # BTCUSDT requer step size de 0.001 (3 casas decimais)
            # Arredondar para o step size mais próximo
            qty_rounded = round(qty / 0.001) * 0.001
            
            # Garantir que seja pelo menos o mínimo
            if qty_rounded < 0.001:
                logger.warning(f"Quantidade {qty_rounded} menor que mínimo 0.001, ajustando")
                qty_rounded = 0.001
            
            # Formato: 3 casas decimais fixas (padrão Bybit)
            qty_formatted = f"{qty_rounded:.3f}"
            
            params = {
                "category": Settings.MARKET_TYPE,
                "symbol": symbol,
                "side": side.value,
                "orderType": order_type.value,
                "qty": qty_formatted,
                "positionIdx": 0,  # One-way mode
            }
            
            if order_type == OrderType.LIMIT and price:
                params["price"] = str(price)
            else:
                params["timeInForce"] = "IOC"  # Immediate or Cancel
            
            if reduce_only:
                params["reduceOnly"] = True
            
            # Log antes de enviar para verificar
            logger.info(f"Enviando ordem para {self.base_url}: {params}")
            
            response = self.client.place_order(**params)
            
            if response["retCode"] != 0:
                raise Exception(f"Erro ao colocar ordem: {response['retMsg']}")
            
            return response["result"]
            
        except Exception as e:
            error_str = str(e)
            # Remover caracteres Unicode problemáticos para Windows
            error_msg = error_str.replace('→', '->').replace('✓', '[OK]').replace('✗', '[ERRO]')
            
            # Verificar se é erro de permissão
            if "10005" in error_str or "Permission denied" in error_str:
                logger.error("=" * 60)
                logger.error("ERRO DE PERMISSAO (10005)")
                logger.error("=" * 60)
                logger.error("A API Key nao tem permissao para executar trades.")
                logger.error("Verifique no painel da Bybit:")
                logger.error("1. A API Key tem permissao 'Trade' habilitada?")
                logger.error("2. A API Key esta sendo usada no ambiente correto?")
                logger.error(f"3. Ambiente configurado: {Settings.ENVIRONMENT}")
                logger.error(f"4. Base URL esperada: {Settings.get_base_url()}")
                logger.error("=" * 60)
            
            logger.error(f"Erro ao colocar ordem: {error_msg}")
            raise
    
    def set_trading_stop(self, symbol: str, trailing_stop_points: float) -> bool:
        """
        Configura trailing stop nativo da Bybit
        
        Args:
            symbol: Símbolo da posição (ex: "BTCUSDT")
            trailing_stop_points: Distância do trailing stop em pontos
                                 Para LONG: pontos abaixo do preço mais alto
                                 Para SHORT: pontos acima do preço mais baixo
        
        Returns:
            True se configurado com sucesso, False caso contrário
        """
        try:
            # Converter para string e remover casas decimais (Bybit usa pontos inteiros)
            trailing_stop_str = str(int(round(trailing_stop_points)))
            
            params = {
                "category": Settings.MARKET_TYPE,
                "symbol": symbol,
                "trailingStop": trailing_stop_str,
                "positionIdx": 0,  # One-way mode
            }
            
            logger.info(f"Configurando trailing stop nativo da Bybit: {trailing_stop_str} pontos para {symbol}")
            
            response = self.client.set_trading_stop(**params)
            
            if response["retCode"] != 0:
                logger.error(f"Erro ao configurar trailing stop: {response['retMsg']}")
                return False
            
            logger.info(f"Trailing stop configurado com sucesso: {trailing_stop_str} pontos")
            return True
            
        except Exception as e:
            error_msg = str(e).replace('→', '->').replace('✓', '[OK]').replace('✗', '[ERRO]')
            logger.error(f"Erro ao configurar trailing stop nativo: {error_msg}")
            return False

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Define a alavancagem para o símbolo
        
        Args:
            symbol: Símbolo (ex: BTCUSDT)
            leverage: Valor da alavancagem (ex: 10)
            
        Returns:
            True se sucesso ou já configurado, False se erro
        """
        try:
            leverage_str = str(leverage)
            
            logger.info(f"Tentando definir alavancagem para {symbol}: {leverage}x")
            
            # Tentar definir alavancagem
            # Nota: Isso define tanto para Buy quanto para Sell
            self.client.set_leverage(
                category=Settings.MARKET_TYPE,
                symbol=symbol,
                buyLeverage=leverage_str,
                sellLeverage=leverage_str
            )
            
            logger.info(f"Alavancagem definida com sucesso: {leverage}x")
            return True
            
        except Exception as e:
            error_msg = str(e)
            # Code 110043: Leverage not modified (já está setado com esse valor)
            if "110043" in error_msg:
                logger.info(f"Alavancagem já está configurada como {leverage}x")
                return True
            
            logger.error(f"Erro ao definir alavancagem: {error_msg}")
            return False
    
    def close_position(self, symbol: str) -> bool:
        """Fecha a posição atual (se houver)"""
        try:
            # Tentar obter posição
            position = None
            try:
                position = self.get_position(symbol)
            except Exception as e:
                # Se der timeout, assumir que não há posição (já foi fechada ou não existe)
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    logger.info("Timeout ao obter posição - assumindo que já está fechada")
                    return True
                # Para outros erros, logar e tentar continuar
                logger.warning(f"Erro ao obter posição antes de fechar: {e}")
            
            if not position:
                # Já está fechada
                return True
            
            # Determinar lado oposto
            side = Side.SELL if position.side == PositionSide.LONG else Side.BUY
            
            response = self.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                qty=position.size,
                reduce_only=True
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao fechar posição: {e}")
            return False
    
    def setup_websocket(self, symbol: str, callback):
        """Configura WebSocket para receber dados em tempo real"""
        def handle_message(message):
            # #region agent log
            import json
            import time
            try:
                from pathlib import Path
                debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
                with open(str(debug_log), 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"bybit_api/client.py:418","message":"WebSocket message received","data":{"message_type":type(message).__name__,"is_dict":isinstance(message,dict),"topic":message.get("topic","") if isinstance(message,dict) else None},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            try:
                if isinstance(message, dict):
                    topic = message.get("topic", "")
                    if "kline" in topic:
                        data = message.get("data", [])
                        if data:
                            kline_data = data[0]
                            # #region agent log
                            try:
                                from pathlib import Path
                                debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
                                with open(str(debug_log), 'a', encoding='utf-8') as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"bybit_api/client.py:424","message":"Kline data found in message","data":{"topic":topic,"data_len":len(data),"close":kline_data.get("close","0"),"start":kline_data.get("start",0)},"timestamp":int(time.time()*1000)})+"\n")
                            except: pass
                            # #endregion
                            # Validar dados antes de processar
                            try:
                                close_price = float(kline_data.get("close", "0"))
                                if close_price <= 0:
                                    logger.warning(f"Ignorando kline com preço inválido: {close_price}")
                                    return
                            except ValueError:
                                return

                            kline = Kline.from_bybit([
                                kline_data.get("start", 0),
                                kline_data.get("open", "0"),
                                kline_data.get("high", "0"),
                                kline_data.get("low", "0"),
                                kline_data.get("close", "0"),
                                kline_data.get("volume", "0")
                            ])
                            # #region agent log
                            try:
                                from pathlib import Path
                                debug_log = Path(__file__).parent.parent / '.cursor' / 'debug.log'
                                with open(str(debug_log), 'a', encoding='utf-8') as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"bybit_api/client.py:443","message":"Calling callback with kline","data":{"kline_open_time":kline.open_time,"kline_close":kline.close},"timestamp":int(time.time()*1000)})+"\n")
                            except: pass
                            # #endregion
                            callback(kline)
            except Exception as e:
                logger.error(f"Erro ao processar mensagem WebSocket: {e}")
        
        try:
            # Configurar WebSocket baseado no ambiente
            # Para streams públicos (kline), demo deve usar endpoint público do mainnet
            # pois stream-demo.bybit.com só suporta streams privados
            # Os dados públicos são idênticos entre demo e mainnet
            ws_params = {
                "channel_type": "linear"
            }
            
            if Settings.ENVIRONMENT == "demo":
                # Demo: Para streams públicos, usar endpoint do mainnet (dados são idênticos)
                # Para streams privados, usar demo=True (mas não é o caso aqui)
                ws_params["testnet"] = False
                ws_params["demo"] = False
            elif Settings.ENVIRONMENT == "testnet":
                # Testnet: usar testnet=True
                ws_params["testnet"] = True
                ws_params["demo"] = False
            else:
                # Production: ambos False
                ws_params["testnet"] = False
                ws_params["demo"] = False
            
            self.ws = BybitWebSocket(**ws_params)
            
            self.ws.kline_stream(
                interval=Settings.TIMEFRAME,
                symbol=symbol,
                callback=handle_message
            )
            
            logger.info(f"WebSocket conectado para {symbol} no timeframe {Settings.TIMEFRAME}")
        except Exception as e:
            logger.error(f"Erro ao configurar WebSocket: {e}")
            raise
    
    def disconnect_websocket(self):
        """Desconecta WebSocket"""
        if self.ws:
            try:
                self.ws.exit()
            except:
                pass
            self.ws = None
