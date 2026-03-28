### 🛠️ Configuración para Copy Trading

1. **Instalar Dependencias**
```bash
pip install polymarket-sdk
```

2. **Configurar `settings.yaml`**
```yaml
whale_traders:
  min_position: 100000  # USDC
  max_followers: 5
  update_interval: 60  # segundos
```

3. **Ejecutar Simulación**
```bash
python run_simulation.py --strategy copy_trading --capital 1000 --duration 60
```

4. **Ver Resultados**
- Logs en `data/simulations/copy_trading_2026-03-27_23-30.log`
- Estadísticas en `data/simulations/copy_trading_2026-03-27_23-30_summary.json`