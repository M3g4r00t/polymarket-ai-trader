# Polymarket AI Trader

Bot de trading automatizado para Polymarket que aprovecha ineficiencias pequeñas del mercado mediante operaciones en corto con órdenes limitadas.

## 🎯 Objetivo

Capitalizar ineficiencias de precio en mercados de predicción usando IA para:
- Detectar oportunidades de arbitraje (YES + NO ≠ $1.00)
- Identificar precios desalineados vs probabilidad real
- Ejecutar operaciones pequeñas con gestión de riesgo estricta
- Crecer capital de forma iterativa con posición mínima

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                      POLYMARKET AI TRADER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  DATA LAYER  │───▶│ STRATEGY LAYER│───▶│EXECUTION LAYER│     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│        │                    │                    │              │
│        ▼                    ▼                    ▼              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │ - Gamma API  │    │ - Arbitrage  │    │ - Limit Orders│     │
│  │ - CLOB API   │    │ - Mispricing │    │ - Risk Mgmt   │     │
│  │ - WebSocket  │    │ - Sentiment  │    │ - Position    │     │
│  │ - Price Feed │    │ - AI Models  │    │ - Portfolio   │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                 │
│                    ┌──────────────┐                             │
│                    │  AI/ML LAYER │                             │
│                    └──────────────┘                             │
│                           │                                     │
│                           ▼                                     │
│                    ┌──────────────┐                             │
│                    │ - LLM Sent.  │                             │
│                    │ - Price Pred │                             │
│                    │ - Anomaly Det│                             │
│                    └──────────────┘                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

```bash
# Clonar y configurar
cd polymarket-ai-trader
pip install -r requirements.txt

# Configurar entorno
cp .env.example .env
# Editar .env con tu private key de Polygon

# Asegurarse que Ollama esté corriendo
ollama serve  # En otra terminal

# Ejecutar en modo simulación (recomendado empezar así)
python main.py --dry-run

# Ejecutar en producción
python main.py --live
```

## 🤖 IA Local con Ollama

Este proyecto usa **Ollama** para análisis con IA local - **¡100% gratis!**

Modelos disponibles:
- **glm-4.7-flash** (19GB) - Principal, mejor razonamiento
- **qwen3:14b** (9.3GB) - Fallback, buen modelo local
- **llama3** (4.7GB) - Alternativa ligera

```bash
# Instalar Ollama si no lo tienes
# Ver: https://ollama.ai

# Descargar modelos necesarios
ollama pull glm-4.7-flash
ollama pull qwen3:14b

# Verificar que funciona
ollama run glm-4.7-flash "Hello"
```

## 🤖 IA Local con Ollama

Este proyecto usa **Ollama** para análisis con IA local - **¡100% gratis!**

Modelos disponibles:
- **glm-4.7-flash** (19GB) - Principal, mejor razonamiento
- **qwen3:14b** (9.3GB) - Fallback, buen modelo local
- **llama3** (4.7GB) - Alternativa ligera

```bash
# Instalar Ollama si no lo tienes
# Ver: https://ollama.ai

# Descargar modelos necesarios
ollama pull glm-4.7-flash
ollama pull qwen3:14b

# Verificar que funciona
ollama run glm-4.7-flash "Hello"
```

## 📊 Modo Simulación

**IMPORTANTE**: Siempre prueba primero en modo simulación:

```bash
# Simulación de 30 minutos con $100 ficticios
python run_simulation.py --capital 100 --duration 30

# Simulación rápida de 5 minutos
python run_simulation.py --quick

# Solo estrategia de arbitraje
python run_simulation.py --strategies arbitrage --capital 50

# Arbitraje + mispricing
python run_simulation.py --strategies arbitrage,mispricing --capital 100

# Con logs detallados
python run_simulation.py --verbose
```

### Resultados de Simulación

El modo simulación genera:
- Estadísticas de rendimiento (PnL, win rate, Sharpe ratio)
- Historial de trades en `data/simulations/`
- Equity curve y drawdown

## 📖 Guía de Configuración Polymarket

Ver [SETUP.md](SETUP.md) para instrucciones detalladas de:
1. Crear wallet MetaMask
2. Obtener USDC en Polygon
3. Crear cuenta Polymarket
4. Exportar private key para el bot

## ⚙️ Configuración

Ver `config/settings.yaml` para todos los parámetros configurables:
- `min_trade_size`: Tamaño mínimo de operación ($1-5 recomendado)
- `max_position_size`: Límite de posición por mercado
- `target_profit_pct`: Margen de beneficio objetivo
- `stop_loss_pct`: Límite de pérdida aceptable

## 📁 Estructura del Proyecto

```
polymarket-ai-trader/
├── README.md
├── PROMPT.md              # Prompt detallado de implementación
├── requirements.txt
├── .env.example
├── main.py                # Entry point
├── config/
│   ├── settings.yaml      # Configuración principal
│   └── secrets.yaml       # Credenciales (gitignore)
├── src/
│   ├── __init__.py
│   ├── client.py          # Cliente Polymarket API
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── arbitrage.py   # Estrategia de arbitraje
│   │   ├── mispricing.py  # Detección de errores de precio
│   │   └── sentiment.py   # Análisis de sentimiento con IA
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── price_predictor.py
│   │   └── news_analyzer.py
│   ├── risk/
│   │   ├── __init__.py
│   │   └── manager.py     # Gestión de riesgo
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── helpers.py
└── tests/
    └── test_strategies.py
```

## ⚠️ Disclaimer

Este bot es para uso educativo y de investigación. El trading en mercados de predicción conlleva riesgos significativos. Nunca inviertas más de lo que puedes perder.

## 📚 Recursos

- [Polymarket Docs](https://docs.polymarket.com/)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)
- [Gamma API](https://gamma-api.polymarket.com)s para uso educativo y de investigación. El trading en mercados de predicción conlleva riesgos significativos. Nunca inviertas más de lo que puedes perder.

## 📚 Recursos

- [Polymarket Docs](https://docs.polymarket.com/)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)
- [Gamma API](https://gamma-api.polymarket.com)