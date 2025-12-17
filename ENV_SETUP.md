# Configuração do Ambiente (.env)

Este sistema suporta três ambientes diferentes para a Bybit:

## Ambientes Disponíveis

### 1. Production (Conta Real)
- **URL**: `https://api.bybit.com`
- **Use para**: Trading real com dinheiro real
- **Gere credenciais em**: https://www.bybit.com/app/user/api-management

### 2. Demo (Conta Demo)
- **URL**: `https://api-demo.bybit.com`
- **Use para**: Contas de teste que requerem api-demo.bybit.com
- **Gere credenciais em**: https://testnet.bybit.com/app/user/api-management
- **Nota**: Algumas contas de teste requerem este endpoint específico

### 3. Testnet (Testnet Padrão)
- **URL**: `https://api-testnet.bybit.com`
- **Use para**: Testnet padrão da Bybit
- **Gere credenciais em**: https://testnet.bybit.com/app/user/api-management

## Como Configurar

1. Copie o arquivo `.env.example` para `.env` (se ainda não existir):
   ```bash
   cp .env.example .env
   ```

2. Edite o arquivo `.env` e configure:

   ```env
   # Escolha o ambiente (production, demo, ou testnet)
   BYBIT_ENVIRONMENT=demo
   
   # Credenciais Production (apenas se usar production)
   BYBIT_API_KEY_PRODUCTION=sua_chave_aqui
   BYBIT_API_SECRET_PRODUCTION=seu_secret_aqui
   
   # Credenciais Demo (apenas se usar demo)
   BYBIT_API_KEY_DEMO=sua_chave_aqui
   BYBIT_API_SECRET_DEMO=seu_secret_aqui
   
   # Credenciais Testnet (apenas se usar testnet)
   BYBIT_API_KEY_TESTNET=sua_chave_aqui
   BYBIT_API_SECRET_TESTNET=seu_secret_aqui
   ```

3. Defina `BYBIT_ENVIRONMENT` para o ambiente desejado:
   - `production` - Para trading real
   - `demo` - Para conta demo
   - `testnet` - Para testnet padrão

4. Preencha apenas as credenciais do ambiente que você vai usar.

## Retrocompatibilidade

Se você já tinha um `.env` com `BYBIT_API_KEY` e `BYBIT_API_SECRET` (sem sufixo), 
o sistema ainda funcionará usando esses valores como fallback.

## Segurança

⚠️ **IMPORTANTE**:
- NUNCA compartilhe seu arquivo `.env`
- NUNCA faça commit do `.env` no Git (já está no .gitignore)
- Para produção, certifique-se de que `BYBIT_ENVIRONMENT=production`
- Use apenas credenciais de produção quando realmente for fazer trading real

## Exemplo Completo

```env
# Ambiente
BYBIT_ENVIRONMENT=demo

# Credenciais Demo
BYBIT_API_KEY_DEMO=U8Gb5yu7xQABC123...
BYBIT_API_SECRET_DEMO=DEF456...

# Configurações de Trading
SYMBOL=BTCUSDT
TIMEFRAME=5
POSITION_SIZE_PERCENT=10.0
MAX_LEVERAGE=1
MIN_ORDER_SIZE=0.001

# Configurações de Otimização
OPTIMIZATION_DAYS=90
OPTIMIZATION_N_ITER=50
```

## Verificação

Para verificar se está configurado corretamente:

```python
from config.settings import Settings

print(f"Ambiente: {Settings.ENVIRONMENT}")
print(f"Base URL: {Settings.get_base_url()}")
print(f"Account Type: {Settings.get_account_type()}")
```












