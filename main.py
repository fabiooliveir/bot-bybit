"""
Ponto de entrada do sistema de trading Bybit.

Suporta três modos principais:
- --optimize : roda a otimização bayesiana da estratégia
- --validate : valida parâmetros otimizados em dados out-of-sample
- --trade    : inicia o trader em tempo real usando parâmetros otimizados
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from config.settings import Settings


def setup_logging() -> None:
    """Configura logging básico para o sistema."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trading.log", encoding="utf-8"),
        ],
    )


def run_optimize(args) -> None:
    """Executa processo de otimização."""
    from optimization.bayesian_opt import run_optimization

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Iniciando processo de otimização")
    logger.info("=" * 60)

    Settings.validate()
    run_optimization(strategy_name=args.strategy)


def run_validate() -> None:
    """Executa validação out-of-sample dos parâmetros otimizados.

    Nesta recriação, apenas verificamos se o arquivo de parâmetros existe e é válido.
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Iniciando validação out-of-sample")
    logger.info("=" * 60)

    params_path = Path(Settings.OPTIMIZED_PARAMS_FILE)
    if not params_path.exists():
        logger.error(
            f"Arquivo de parâmetros otimizados não encontrado: {params_path}. "
            "Rode primeiro: python main.py --optimize"
        )
        return

    try:
        data = json.loads(params_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Erro ao ler '{params_path}': {e}")
        return

    logger.info("Parâmetros otimizados carregados com sucesso:")
    logger.info(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info("Validação detalhada ainda não implementada nesta recriação.")


def run_trade() -> None:
    """Inicia o trader em tempo real."""
    from execution.trader import run_trader

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Iniciando trader")
    logger.info("=" * 60)

    Settings.validate()
    run_trader()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sistema de Trading Bybit")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--optimize",
        action="store_true",
        help="Roda a otimização bayesiana da estratégia",
    )
    group.add_argument(
        "--validate",
        action="store_true",
        help="Valida parâmetros otimizados em dados out-of-sample",
    )
    group.add_argument(
        "--trade",
        action="store_true",
        help="Inicia o trader em tempo real com parâmetros otimizados",
    )

    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="Nome da estratégia para otimização (ex: 'macd', 'larry_williams', 'ifr')",
    )

    return parser


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    if args.optimize:
        run_optimize(args)
    elif args.validate:
        run_validate()
    elif args.trade:
        run_trade()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


