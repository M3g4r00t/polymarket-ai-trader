# Guía de Configuración Polymarket

## 📋 Paso a Paso para Configurar tu Cuenta

### 1. Crear una Wallet (MetaMask)

Si no tienes MetaMask:

```bash
# Instalar MetaMask en tu navegador
# Ir a: https://metamask.io/download/
```

1. Instala la extensión de MetaMask en tu navegador
2. Crea una nueva wallet o importa una existente
3. **IMPORTANTE**: Guarda tu "seed phrase" (12 palabras) en un lugar seguro
4. Cambia a la red **Polygon** (Polymarket usa Polygon, no Ethereum mainnet)

Para agregar Polygon a MetaMask:
- Network Name: `Polygon Mainnet`
- RPC URL: `https://polygon-rpc.com`
- Chain ID: `137`
- Currency Symbol: `MATIC`
- Block Explorer: `https://polygonscan.com`

### 2. Obtener USDC y MATIC

Polymarket usa **USDC.e** (USDC bridged) en Polygon como moneda de trading.

**Opciones para obtener USDC.e:**

#### Opción A: Comprar en Exchange Centralizado
```bash
# Ejemplos: Coinbase, Crypto.com, KuCoin, Binance
# 1. Compra USDC
# 2. Retira a tu wallet de Polygon (red POLYGON, no Ethereum)
# 3. Si es USDC nativo, Polymarket lo convierte automáticamente a USDC.e
```

#### Opción B: Usar Polymarket Bridge
1. Ve a https://polymarket.com
2. Click en "Deposit"
3. Selecciona tu método preferido (tarjeta, otro blockchain, etc.)
4. El bridge convierte automáticamente a USDC.e en Polygon

**Para gas fees (MATIC):**
```bash
# Necesitas ~1-2 MATIC para transacciones
# Puedes comprar MATIC en cualquier exchange y enviarlo a tu wallet Polygon
# O usar un faucet: https://polygon.technology/faucet
```

### 3. Crear Cuenta en Polymarket

```bash
# Opciones:
# 1. Con Google: Click "Continue with Google"
# 2. Con Email: Click "Continue with Email"
# 3. Con Wallet: Conecta tu MetaMask directamente
```

**Recomendación**: Conecta directamente con MetaMask para control total de tu wallet.

1. Ve a https://polymarket.com
2. Click en "Sign Up" → "Connect Wallet"
3. Selecciona MetaMask
4. Firma el mensaje para conectar
5. Firma otro mensaje para habilitar trading

### 4. Depositar Fondos

1. En Polymarket, click en "Deposit"
2. Copia tu dirección de depósito de Polygon
3. Envía USDC desde tu exchange/wallet a esa dirección
4. Espera confirmación (1-3 minutos en Polygon)
5. ¡Listo para tradear!

### 5. Exportar Private Key para el Bot

⚠️ **CRÍTICO**: Tu private key es como tu contraseña maestra. ¡Nunca la compartas!

```bash
# En MetaMask:
# 1. Click en los 3 puntos (...) de tu cuenta
# 2. Account Details → Export Private Key
# 3. Ingresa tu contraseña
# 4. Copia la private key (empieza con 0x...)
# 5. Guárdala en un lugar MUY SEGURO
```

**Para el bot:**
```bash
# En el proyecto:
cd /media/dennys/data-linux/projects/polymarket-ai-trader
cp .env.example .env

# Edita .env:
PRIVATE_KEY=0xtu_private_key_aqui
```

### 6. Configurar API Keys (Opcional)

Si quieres usar el bot con IA local, no necesitas API keys externas.
Ollama corre localmente y es gratis.

```bash
# Verificar que Ollama esté corriendo:
ollama serve

# Verificar modelos disponibles:
ollama list
```

---

## 🔒 Seguridad

### Buenas Prácticas:

1. **Nunca compartas tu private key** - Ni con soporte de Polymarket
2. **Usa una wallet dedicada** - Crea una wallet solo para trading
3. **Empieza con poco** - Prueba con $10-20 primero
4. **Verifica URLs** - Solo usa https://polymarket.com
5. **Guarda backup** - Ten tu seed phrase en múltiples lugares seguros

### Para el Bot:

```bash
# El archivo .env con tu private key NUNCA debe ir a git
# Ya está en .gitignore, pero verifica:

cat .gitignore | grep -i env
# Debe mostrar: .env
```

---

## 📊 Verificación de Setup

Antes de ejecutar el bot, verifica:

```bash
# 1. Tienes USDC.e en Polygon?
# Ve a tu wallet y verifica el balance

# 2. Tienes MATIC para gas?
# Necesitas al menos 0.5 MATIC

# 3. Tu private key está en .env?
grep PRIVATE_KEY .env
# Debe mostrar: PRIVATE_KEY=0x... (sin el valor real por seguridad)

# 4. Ollama está corriendo?
curl http://localhost:11434/api/tags
# Debe devolver JSON con tus modelos
```

---

## 🚀 Primer Trade Manual (Recomendado)

Antes de usar el bot, haz un trade manual:

1. Ve a https://polymarket.com
2. Busca un mercado con alta liquidez
3. Compra $1 de YES o NO
4. Observa cómo funciona el orderbook
5. Vende tu posición
6. ¡Ahora ya entendiste el flujo!

---

## 📞 Soporte

- Docs: https://docs.polymarket.com
- Discord: https://discord.gg/polymarket
- Twitter: @Polymarket