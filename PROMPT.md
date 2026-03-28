# PROMPT: Polymarket AI Trading Bot

## Contexto

Polymarket es un mercado de predicción descentralizado donde los usuarios negocian acciones basadas en resultados de eventos futuros. Los precios de las acciones oscilan entre $0.00 y $1.00, reflejando la probabilidad implícita del mercado de que ocurra un evento.

### Mecánica del Mercado

- **Mercados binarios**: YES + NO deberían sumar $1.00 exactamente
- **Ineficiencias**: Cuando YES + NO ≠ $1.00, existe oportunidad de arbitraje
- **Ordenes limitadas**: Especificas precio y cantidad, se ejecutan cuando hay contraparte
- **Tipos de orden**: GTC (Good-Til-Cancelled), GTD (Good-Til-Date), FOK (Fill-Or-Kill), FAK (Fill-And-Kill)

### APIs Disponibles

1. **Gamma API** (`https://gamma-api.polymarket.com`)
   - Mercados, eventos, tags, series, comentarios
   - Pública, sin autenticación requerida

2. **Data API** (`https://data-api.polymarket.com`)
   - Posiciones de usuario, trades, actividad
   - Pública

3. **CLOB API** (`https://clob.polymarket.com`)
   - Orderbook, precios, midpoint, spreads
   - Trading requiere autenticación L2 (API Key + Secret + Passphrase)

4. **WebSocket**
   - Datos en tiempo real para baja latencia

## Objetivo del Bot

Crear un bot de trading automatizado que:

1. **Detecte ineficiencias pequeñas** en los mercados de Polymarket
2. **Ejecute operaciones en corto** (vender acciones sobrevaloradas)
3. **Use órdenes limitadas** para maximizar profit
4. **Comience con capital mínimo** ($5-10 USD) y crezca iterativamente
5. **Gestione riesgo** con stops y límites de posición

## Requisitos Técnicos

### Dependencias Python

```
py-clob-client>=0.1.0  # Cliente oficial Polymarket
web3>=6.0.0            # Interacción blockchain
aiohttp>=3.8.0        # Async HTTP
websockets>=11.0       # Tiempo real
pandas>=2.0.0          # Análisis de datos
numpy>=1.24.0          # Cálculos numéricos
pydantic>=2.0.0        # Validación de datos
python-dotenv>=1.0.0   # Variables de entorno
pyyaml>=6.0            # Configuración
structlog>=23.0.0      # Logging estructurado
```

### Autenticación

```python
# L1: Private Key (crear credenciales)
# L2: API Key, Secret, Passphrase (operaciones diarias)

from py_clob_client.client import ClobClient

# Cliente autenticado
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,  # Polygon mainnet
    key=PRIVATE_KEY
)
client.set_api_creds(client.create_or_derive_api_creds())
```

### Estructura de Datos de Mercado

```python
# Token ID identifica cada resultado (YES/NO)
# Obtener desde Gamma API:
# GET /markets?condition_id={condition_id}

# Orderbook
book = client.get_order_book(token_id)
# book.bids: [(price, size), ...]  # Ordenes de compra
# book.asks: [(price, size), ...]  # Ordenes de venta

# Midpoint (precio medio)
mid = client.get_midpoint(token_id)  # Mejor estimación de precio actual
```

## Estrategias a Implementar

### 1. Arbitraje de Rebalanceo (Priority: HIGH)

**Concepto**: En mercados binarios, YES + NO debe sumar $1.00. Si la suma difiere, hay arbitraje.

**Ejemplo**:
```
YES = $0.54
NO  = $0.43
Suma = $0.97 (< $1.00)
Oportunidad: Comprar YES y NO por $0.97, ganar $1.00 al resolver
Profit = $0.03 (3.1%)
```

**Implementación**:
```python
def find_rebalance_opportunities(min_profit_pct=0.02):
    """
    Busca mercados donde YES + NO != $1.00
    
    Args:
        min_profit_pct: Mínimo % de profit para ejecutar (default 2%)
    
    Returns:
        Lista de oportunidades: [{market_id, yes_token, no_token, 
                                 yes_price, no_price, spread, profit_pct}]
    """
    pass
```

### 2. Detección de Mispricing con IA (Priority: MEDIUM)

**Concepto**: Usar IA para estimar la probabilidad real de un evento y comparar con el precio del mercado.

**Implementación**:
```python
class MispricingDetector:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def analyze_market(self, market_data):
        """
        Analiza un mercado y estima probabilidad real
        
        Args:
            market_data: {question, description, current_price, news_context}
        
        Returns:
            {estimated_probability, confidence, reasoning}
        """
        prompt = f"""
        Market Question: {market_data['question']}
        Market Description: {market_data['description']}
        Current Market Price: {market_data['current_price']}
        Recent News Context: {market_data['news_context']}
        
        Estimate the TRUE probability of this event occurring.
        Consider: historical patterns, base rates, news context, potential biases.
        
        Return JSON: {{"probability": 0.XX, "confidence": "high|medium|low", 
                       "reasoning": "...", "key_factors": ["..."]}}
        """
        # Parsear respuesta y comparar con precio del mercado
        pass
```

### 3. Sentiment Analysis (Priority: LOW - FUTURE)

**Concepto**: Monitorear noticias y eventos en tiempo real para anticipar movimientos de precio.

**Fuentes**:
- Noticias políticas (Reuters, AP, etc.)
- Twitter/X trends
- Polymarket comentarios

## Gestión de Riesgo

### Parámetros Configurables

```yaml
risk:
  min_trade_size_usd: 1.0      # Mínimo $1 por operación
  max_trade_size_usd: 10.0     # Máximo $10 por operación inicial
  max_position_size_usd: 50.0  # Máximo $50 por mercado
  max_total_exposure_usd: 200  # Máximo $200 total en juego
  stop_loss_pct: 0.15          # Stop loss al 15% de pérdida
  take_profit_pct: 0.05        # Take profit al 5% de ganancia
  max_open_positions: 10       # Máximo 10 posiciones abiertas
  cooldown_minutes: 5          # Esperar 5 min entre operaciones en mismo mercado
```

### Lógica de Position Sizing

```python
def calculate_position_size(
    confidence: float,
    current_capital: float,
    market_liquidity: float,
    risk_params: dict
) -> float:
    """
    Calcula tamaño de posición basado en:
    - Confianza de la señal (0-1)
    - Capital disponible
    - Liquidez del mercado (spread, depth)
    - Límites de riesgo
    
    Kelly Criterion simplificado:
    size = (p * odds - 1) / (odds - 1)
    
    Donde:
    - p = probabilidad estimada
    - odds = precio / (1 - precio)
    
    Returns:
        Tamaño de posición en USD
    """
    # Para bajo capital, usar fractional Kelly (25% de Kelly)
    kelly_fraction = 0.25
    # Limitar a max_position_size
    # Limitar a disponible capital
    pass
```

### Stop Loss y Take Profit

```python
class PositionManager:
    def __init__(self, client, risk_params):
        self.client = client
        self.risk = risk_params
        self.positions = {}  # {token_id: {entry_price, size, stop_loss, take_profit}}
    
    def open_position(self, token_id, side, size, entry_price):
        """Abre posición y coloca stops"""
        # Calcular stops
        if side == "BUY":
            stop_price = entry_price * (1 - self.risk['stop_loss_pct'])
            take_profit_price = entry_price * (1 + self.risk['take_profit_pct'])
        else:  # SELL/SHORT
            stop_price = entry_price * (1 + self.risk['stop_loss_pct'])
            take_profit_price = entry_price * (1 - self.risk['take_profit_pct'])
        
        # Guardar posición
        # Colocar órdenes de stop (OCO si disponible)
        pass
    
    def check_positions(self):
        """Revisa todas las posiciones abiertas"""
        # Verificar precio actual vs stops
        # Ejecutar stops si necesario
        pass
```

## Flujo Principal del Bot

```python
async def main_loop():
    """Loop principal del bot"""
    while True:
        try:
            # 1. Actualizar datos de mercado
            markets = await fetch_markets()
            
            # 2. Buscar oportunidades
            opportunities = []
            
            # 2a. Arbitraje de rebalanceo
            rebalance_ops = find_rebalance_opportunities()
            opportunities.extend(rebalance_ops)
            
            # 2b. Mispricing con IA (selectivo)
            if random() < 0.1:  # Solo 10% de veces para ahorrar API calls
                mispricing_ops = await find_mispricing_opportunities(markets)
                opportunities.extend(mispricing_ops)
            
            # 3. Filtrar por criterios de riesgo
            valid_ops = filter_opportunities(opportunities, risk_params)
            
            # 4. Ejecutar mejores oportunidades
            for op in valid_ops[:3]:  # Máximo 3 por ciclo
                await execute_trade(op)
            
            # 5. Gestionar posiciones abiertas
            await manage_positions()
            
            # 6. Esperar antes del siguiente ciclo
            await asyncio.sleep(30)  # 30 segundos
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            await asyncio.sleep(60)  # Esperar más tiempo si hay error
```

## Credenciales Necesarias

### Obligatorias

```env
# Wallet de Polygon (con USDC para trading)
PRIVATE_KEY=0x...

# O si usas wallet de email/Magic
POLYMARKET_EMAIL=tu@email.com
POLYMARKET_PASSWORD=tu_password
```

### Opcionales (para IA)

```env
# Para análisis con LLM
OPENAI_API_KEY=sk-...
# o
ANTHROPIC_API_KEY=sk-ant-...
```

## Consideraciones Importantes

1. **Gasless Trading**: Polymarket permite trading sin gas en L2 (Polygon)
2. **Allowances**: Para wallets EOA/MetaMask, necesitas aprobar tokens primero
3. **Rate Limits**: 100 requests/min para API pública, 60 orders/min para trading
4. **Liquidez**: Verificar siempre depth del orderbook antes de operar
5. **Slippage**: Usar limit orders, nunca market orders
6. **Timing**: Oportunidades de arbitraje duran segundos, velocidad crítica

## Métricas de Éxito

```python
class PerformanceTracker:
    def __init__(self):
        self.trades = []  # Lista de trades ejecutados
    
    def calculate_metrics(self):
        return {
            "total_trades": len(self.trades),
            "win_rate": sum(t['pnl'] > 0 for t in self.trades) / len(self.trades),
            "avg_pnl_per_trade": sum(t['pnl'] for t in self.trades) / len(self.trades),
            "sharpe_ratio": self._calculate_sharpe(),
            "max_drawdown": self._calculate_max_drawdown(),
            "total_pnl": sum(t['pnl'] for t in self.trades),
            "capital_growth": self._calculate_growth()
        }
```

## Testing

```bash
# Tests unitarios
pytest tests/

# Backtesting con datos históricos
python backtest.py --strategy arbitrage --start 2024-01-01 --end 2024-12-31

# Paper trading (sin dinero real)
python main.py --dry-run --verbose
```

## Próximos Paspos de Implementación

1. ✅ Setup inicial del proyecto
2. ✅ Cliente Polymarket con autenticación
3. ⬜ Data fetching (mercados, orderbooks)
4. ⬜ Estrategia de arbitraje
5. ⬜ Gestión de riesgo
6. ⬜ Sistema de logging y monitoreo
7. ⬜ Dashboard web (opcional)
8. ⬜ Integración con IA (LLM para análisis)

---

## Ejemplo de Uso

```python
# Inicializar bot
bot = PolymarketBot(
    private_key=os.getenv("PRIVATE_KEY"),
    strategy="arbitrage",
    risk_params={
        "min_trade_size": 1.0,
        "max_position_size": 20.0,
        "stop_loss_pct": 0.10
    }
)

# Ejecutar en modo paper trading primero
bot.run(dry_run=True)

# Cuando validado, ejecutar en producción
bot.run(dry_run=False)
```