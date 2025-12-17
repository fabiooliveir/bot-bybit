
from bybit_api.client import BybitClient
from config.settings import Settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CheckPos")

def check():
    client = BybitClient()
    position = client.get_position(Settings.SYMBOL)
    
    if position:
        logger.info(f"=== POSIÇÃO ATUAL: {Settings.SYMBOL} ===")
        logger.info(f"Lado: {position.side.name}")
        logger.info(f"Tamanho: {position.size}")
        logger.info(f"Preço Entrada: {position.entry_price}")
        logger.info(f"Trailing Stop Configurado: {position.trailing_stop}")
        
        # Calcular distância
        if position.trailing_stop > 0:
            logger.info(f"Distância do Stop: {position.trailing_stop} pontos")
        else:
            logger.warning("ALERTA: SEM TRAILING STOP CONFIGURADO!")
            
    else:
        logger.info("Nenhuma posição aberta no momento.")

if __name__ == "__main__":
    check()
