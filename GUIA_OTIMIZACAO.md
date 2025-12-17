# Guia de Otimização de Estratégias

Este guia explica como otimizar diferentes estratégias de trading usando o sistema de Bayesian Optimization.

## Estratégias Disponíveis

1. **Larry Williams** (`larry_williams`) - Estratégia de pullback com média móvel
2. **MACD Crossover** (`macd` ou `macd_crossover`) - Estratégia baseada em cruzamento de linhas MACD

## Como Otimizar

### 1. Otimizar Estratégia Larry Williams (Padrão)

```bash
python main.py --optimize
```

ou explicitamente:

```bash
python main.py --optimize --strategy larry_williams
```

### 2. Otimizar Estratégia MACD Crossover

```bash
python main.py --optimize --strategy macd
```

ou:

```bash
python main.py --optimize --strategy macd_crossover
```

## Processo de Otimização

A otimização:

1. **Coleta dados históricos** (90 dias por padrão, configurável via `OPTIMIZATION_DAYS` no `.env`)
2. **Otimiza parâmetros da estratégia** usando Bayesian Optimization
3. **Otimiza parâmetros do trailing stop** simultaneamente
4. **Salva resultados** em `optimized_params.json`

### Parâmetros Otimizados - MACD Crossover

- `fast_period`: Período da EMA rápida (8-16)
- `slow_period`: Período da EMA lenta (20-35)
- `signal_period`: Período da linha de sinal (6-12)
- `volatility_period`: Período ATR para trailing stop (10-20)
- `atr_multiplier`: Multiplicador ATR para trailing stop (1.0-4.0)
- `atr_period`: Período ATR para trailing stop (10-20)

### Parâmetros Otimizados - Larry Williams

- `ma_period`: Período da média móvel (6-15)
- `lookback_period`: Período de lookback (10-30)
- `trend_threshold`: Threshold para tendência (0.3-0.7)
- `volatility_period`: Período ATR (10-20)
- `atr_multiplier`: Multiplicador ATR (1.0-4.0)
- `atr_period`: Período ATR (10-20)

## Validação Out-of-Sample

Após otimizar, valide os parâmetros em dados diferentes:

```bash
python main.py --validate
```

Isso testa os parâmetros otimizados em dados mais recentes (30 dias por padrão) para verificar se não houve overfitting.

## Executar Trading

Após otimizar, inicie o trader:

```bash
python main.py --trade
```

O sistema automaticamente:
- Carrega os parâmetros otimizados do arquivo `optimized_params.json`
- Identifica qual estratégia foi otimizada
- Usa a estratégia correta com os parâmetros otimizados

## Configurações

No arquivo `.env`, você pode configurar:

- `OPTIMIZATION_DAYS`: Dias de dados históricos para otimização (padrão: 90)
- `OPTIMIZATION_N_ITER`: Número de iterações da otimização (padrão: 50)
- `VALIDATION_DAYS`: Dias de dados para validação (padrão: 30)

## Exemplo Completo

```bash
# 1. Otimizar estratégia MACD
python main.py --optimize --strategy macd

# 2. Validar parâmetros
python main.py --validate

# 3. Iniciar trading
python main.py --trade
```

## Arquivo de Parâmetros Otimizados

O arquivo `optimized_params.json` contém:

```json
{
  "strategy": {
    "fast_period": 12,
    "slow_period": 26,
    "signal_period": 9,
    "volatility_period": 14
  },
  "strategy_name": "MACDCrossoverStrategy",
  "trailing_stop": {
    "atr_multiplier": 2.0,
    "atr_period": 14
  },
  "symbol": "BTCUSDT",
  "timeframe": "5",
  "metrics": {
    "total_return": 0.15,
    "sharpe_ratio": 1.5,
    "max_drawdown": 0.10,
    "win_rate": 0.55
  }
}
```

## Notas Importantes

- A otimização pode levar vários minutos dependendo do número de iterações
- Sempre valide os parâmetros em dados out-of-sample antes de usar em produção
- Monitore o sistema regularmente quando estiver em produção
- Use testnet primeiro para testar o sistema











