# Polymarket AI Trader - Quick Start Guide

## Instalación

```bash
# Clonar o navegar al proyecto
cd /media/dennys/data-linux/projects/polymarket-ai-trader

# Crear entorno virtual
python -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Configuración

1. **Configurar wallet de Polygon:**

```bash
cp .env.example .env
```

Edita `.env` con tu private key:

```env
PRIVATE_KEY=0x...
```

**⚠️ IMPORTANTE:** Nunca compartas tu private key ni la subas a GitHub.

2. **Configurar settings (opcional):**

Edita `config/settings.yaml` para ajustar:
- Tamaño mínimo/máximo de trades
- Límites de riesgo
- Categorías de mercados a monitorear

## Uso

### Modo Simulación (Recomendado para empezar)

```bash
# Ver qué haría el bot sin ejecutar trades reales
python main.py --dry-run
```

### Modo Producción

```bash
# Ejecutar con dinero real
python main.py --live
```

### Solo Arbitraje

```bash
python main.py --strategy arbitrage --dry-run
```

### Con IA (requiere API key)

```bash
# Agregar a .env:
# OPENAI_API_KEY=sk-...

# Habilitar en config/settings.yaml:
# strategies:
#   mispricing:
#     enabled: true

python main.py --dry-run
```

## Estrategias

### 1. Arbitraje de Rebalanceo

Detecta cuando YES + NO ≠ $1.00 y compra ambos lados.

**Ventajas:**
- Riesgo casi cero
- Profit garantizado al resolver

**Desventajas:**
- Oportunidades raras
- Competencia alta

### 2. Mispricing con IA (Experimental)

Usa LLM para estimar probabilidades reales y detectar precios desalineados.

**Ventajas:**
- Más oportunidades
- Mayor potencial de profit

**Desventajas:**
- Requiere API key (costo)
- Predicciones pueden estar mal
- Mayor riesgo

## Gestión de Riesgo

El bot incluye:

- **Stop Loss:** 15% por defecto
- **Take Profit:** 5% por defecto
- **Trailing Stop:** Sigue el precio hacia arriba
- **Límite diario:** $20 USD máximo pérdida
- **Pausa automática:** Después de 3 pérdidas consecutivas

## Estructura de Archivos

```
polymarket-ai-trader/
├── main.py              # Entry point
├── config/
│   └── settings.yaml    # Configuración
├── src/
│   ├── client.py        # API client
│   ├── strategies/
│   │   ├── arbitrage.py # Estrategia principal
│   │   └── mispricing.py # Estrategia IA
│   ├── risk/
│   │   └── manager.py    # Gestión de riesgo
│   └── utils/
│       └── logger.py     # Logging
└── tests/
    └── test_strategies.py
```

## Monitoreo

Los logs se guardan en `logs/trader.log`:

```bash
# Ver logs en tiempo real
tail -f logs/trader.log
```

## Próximos Pasos

1. **Probar en modo dry-run** por al menos 24 horas
2. **Verificar oportunidades de arbitraje** reales
3. **Ajustar parámetros** según resultados
4. **Empezar con capital mínimo** ($5-10 USD)
5. **Habilitar IA** solo si tienes confianza

## Troubleshooting

**Error: PRIVATE_KEY not set**
- Configura `.env` con tu private key

**Error: SDK not installed**
- Ejecuta `pip install py-clob-client`

**No encuentra oportunidades**
- Normal, las oportunidades son escasas
- Ajusta `min_spread_usd` a valores más bajos
- Habilita más categorías en `settings.yaml`

**API calls budget exceeded**
- Solo para estrategia IA
- Aumenta `max_api_calls_per_day` en config

## Disclaimer

⚠️ **Esto es software experimental. Trading conlleva riesgos. Nunca inviertas más de lo que puedes perder.**

El autor no se responsabiliza por pérdidas financieras.