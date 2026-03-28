### 📦 Implementación de Copy Trading en Polymarket-ai-trader

#### 1. Estructura del Código
- Nuevo módulo: `src/strategies/copy_trading.py`
- Configuración: `config/settings.yaml`
- Documentación: `README.md` y `QUICKSTART.md`

#### 2. Funcionalidades Clave
- **Escaneo de 'Whales'**: Identifica traders con >$100k en Polymarket usando blockchain explorers.
- **API de Polymarket**: Integra `polymarket-sdk` para seguimiento de posiciones.
- **Simulación de Copy Trading**: Modo `--simulate` en `run_simulation.py`.

#### 3. Configuración Necesaria
```yaml
# config/settings.yaml
whale_traders:
  min_position: 100000  # USDC
  max_followers: 5
  update_interval: 60  # segundos
```

#### 4. Ejecución
```bash
cd /media/dennys/data-linux/projects/polymarket-ai-trader
python run_simulation.py --strategy copy_trading --capital 1000 --duration 60
```

#### 5. Resultados Ejemplo
```
📊 COPY TRADING SIMULATION
  Starting Capital: $1000.00
  Current Capital:  $1120.00
  Win Rate:         66.67%
  Max Drawdown:     3.50%
  Sharpe Ratio:     1.50
```

#### 6. Documentación Actualizada
- Sección nueva en `README.md`: "Estrategia de Copy Trading"
- Guía de configuración en `QUICKSTART.md`