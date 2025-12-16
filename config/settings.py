"""
Configurações do sistema de trading Bybit
"""
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from enum import Enum

load_dotenv()


class Environment(Enum):
    """Ambientes disponíveis"""
    PRODUCTION = "production"  # Conta real - api.bybit.com
    DEMO = "demo"  # Conta demo - api-demo.bybit.com
    TESTNET = "testnet"  # Testnet padrão - api-testnet.bybit.com


class Settings:
    """Configurações globais do sistema"""
    
    # Ambiente: production, demo, ou testnet
    # Determina qual URL e credenciais usar
    ENVIRONMENT = os.getenv("BYBIT_ENVIRONMENT", "demo").lower()
    
    # Credenciais por ambiente
    # Production
    BYBIT_API_KEY_PRODUCTION = os.getenv("BYBIT_API_KEY_PRODUCTION", "")
    BYBIT_API_SECRET_PRODUCTION = os.getenv("BYBIT_API_SECRET_PRODUCTION", "")
    
    # Demo (api-demo.bybit.com)
    BYBIT_API_KEY_DEMO = os.getenv("BYBIT_API_KEY_DEMO", "")
    BYBIT_API_SECRET_DEMO = os.getenv("BYBIT_API_SECRET_DEMO", "")
    
    # Testnet padrão (api-testnet.bybit.com)
    BYBIT_API_KEY_TESTNET = os.getenv("BYBIT_API_KEY_TESTNET", "")
    BYBIT_API_SECRET_TESTNET = os.getenv("BYBIT_API_SECRET_TESTNET", "")
    
    # Retrocompatibilidade: usar valores antigos se novos não existirem
    _OLD_KEY = os.getenv("BYBIT_API_KEY", "")
    _OLD_SECRET = os.getenv("BYBIT_API_SECRET", "")
    
    @classmethod
    def get_api_key(cls) -> str:
        """Retorna a API key do ambiente atual"""
        if cls.ENVIRONMENT == Environment.PRODUCTION.value:
            return cls.BYBIT_API_KEY_PRODUCTION or cls._OLD_KEY
        elif cls.ENVIRONMENT == Environment.DEMO.value:
            return cls.BYBIT_API_KEY_DEMO or cls._OLD_KEY
        elif cls.ENVIRONMENT == Environment.TESTNET.value:
            return cls.BYBIT_API_KEY_TESTNET or cls._OLD_KEY
        else:
            # Default para demo se ambiente inválido
            return cls.BYBIT_API_KEY_DEMO or cls._OLD_KEY
    
    @classmethod
    def get_api_secret(cls) -> str:
        """Retorna a API secret do ambiente atual"""
        if cls.ENVIRONMENT == Environment.PRODUCTION.value:
            return cls.BYBIT_API_SECRET_PRODUCTION or cls._OLD_SECRET
        elif cls.ENVIRONMENT == Environment.DEMO.value:
            return cls.BYBIT_API_SECRET_DEMO or cls._OLD_SECRET
        elif cls.ENVIRONMENT == Environment.TESTNET.value:
            return cls.BYBIT_API_SECRET_TESTNET or cls._OLD_SECRET
        else:
            # Default para demo se ambiente inválido
            return cls.BYBIT_API_SECRET_DEMO or cls._OLD_SECRET
    
    @classmethod
    def get_base_url(cls) -> str:
        """Retorna a URL base da API conforme o ambiente"""
        if cls.ENVIRONMENT == Environment.PRODUCTION.value:
            return "https://api.bybit.com"
        elif cls.ENVIRONMENT == Environment.DEMO.value:
            return "https://api-demo.bybit.com"
        elif cls.ENVIRONMENT == Environment.TESTNET.value:
            return "https://api-testnet.bybit.com"
        else:
            # Default para demo
            return "https://api-demo.bybit.com"
    
    @classmethod
    def get_account_type(cls) -> str:
        """Retorna o accountType conforme o ambiente"""
        # Demo e testnet usam UNIFIED, production usa linear
        if cls.ENVIRONMENT == Environment.PRODUCTION.value:
            return "linear"
        else:
            return "UNIFIED"
    
    @classmethod
    def is_testnet(cls) -> bool:
        """Retorna True se estiver em ambiente de teste"""
        return cls.ENVIRONMENT != Environment.PRODUCTION.value
    
    @classmethod
    def get_websocket_domain(cls) -> Optional[str]:
        """Retorna o domínio do WebSocket conforme o ambiente"""
        # Demo precisa usar stream-demo.bybit.com explicitamente
        if cls.ENVIRONMENT == Environment.DEMO.value:
            return "stream-demo.bybit.com"
        # Testnet e production usam configuração padrão do pybit
        return None
    
    # Configurações de Trading
    SYMBOL = "BTCUSDT"
    TIMEFRAME = "5"  # 5 minutos
    MARKET_TYPE = "linear"  # linear ou inverse (para category em orders)
    
    # Tamanho de posição
    POSITION_SIZE_PERCENT = float(os.getenv("POSITION_SIZE_PERCENT", "10.0"))  # % do capital
    
    # Configurações de Otimização
    OPTIMIZATION_DAYS = int(os.getenv("OPTIMIZATION_DAYS", "90"))  # Dias de dados históricos
    OPTIMIZATION_N_ITER = int(os.getenv("OPTIMIZATION_N_ITER", "50"))  # Iterações Bayesian Optimization
    
    # Configurações de Risco
    MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "1"))  # Leverage máximo
    # Tamanho mínimo de ordem (limite técnico da Bybit para BTCUSDT)
    # Não precisa configurar no .env, é um limite fixo da exchange
    MIN_ORDER_SIZE = 0.001  # BTC mínimo por ordem (padrão Bybit)
    
    # Arquivos
    OPTIMIZED_PARAMS_FILE = "optimized_params.json"
    
    # WebSocket
    WS_RECONNECT_INTERVAL = 10  # segundos
    
    @classmethod
    def get_bybit_config(cls) -> Dict[str, Any]:
        """Retorna configuração para cliente Bybit"""
        return {
            "api_key": cls.get_api_key(),
            "api_secret": cls.get_api_secret(),
            "base_url": cls.get_base_url(),
            "environment": cls.ENVIRONMENT,
        }
    
    @classmethod
    def validate(cls) -> bool:
        """Valida se as configurações necessárias estão definidas"""
        api_key = cls.get_api_key()
        api_secret = cls.get_api_secret()
        
        if not api_key:
            env_var_key = f"BYBIT_API_KEY_{cls.ENVIRONMENT.upper()}"
            raise ValueError(
                f"API Key não definida para ambiente '{cls.ENVIRONMENT}'. "
                f"Configure {env_var_key} no arquivo .env"
            )
        
        if not api_secret:
            env_var_secret = f"BYBIT_API_SECRET_{cls.ENVIRONMENT.upper()}"
            raise ValueError(
                f"API Secret não definida para ambiente '{cls.ENVIRONMENT}'. "
                f"Configure {env_var_secret} no arquivo .env"
            )
        
        return True


