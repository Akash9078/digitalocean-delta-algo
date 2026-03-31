# Delta Exchange Algo Trading Bot

> **SMA-RSI BTC Futures Trading Bot** running on Delta Exchange India — FastAPI backend and Docker deployment for DigitalOcean.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   DigitalOcean Droplet                   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  FastAPI (port 8501)                             │  │
│  │  + TradingBot                                   │  │
│  │  + RiskManager                                  │  │
│  └──────────────────────────────────────────────────┘  │
│                         │                                │
│                         ▼                                │
│              Delta Exchange India API                    │
│              (HMAC-authenticated REST)                   │
└─────────────────────────────────────────────────────────┘
```

## Strategy: SMA Crossover + RSI Confirmation

| Parameter | Default | Description |
|-----------|---------|-------------|
| Short SMA | 9 | Fast moving average |
| Long SMA | 21 | Slow moving average |
| RSI Period | 14 | RSI lookback |
| RSI Oversold | 30 | BUY confirmation floor |
| RSI Overbought | 70 | SELL confirmation ceiling |
| SL | 2% | Stop-loss from entry |
| TP | 4% | Take-profit from entry (2:1 R:R) |

**Signal logic:**
- **BUY**: Short SMA crosses above Long SMA + RSI < 70 (not overbought)
- **SELL**: Short SMA crosses below Long SMA + RSI > 30 (not oversold)
- Bracket orders (SL + TP) placed atomically with entry

## Quick Start – DigitalOcean

### Option A: One-shot setup (fresh Ubuntu 22.04/24.04 Droplet)

```bash
curl -sL https://raw.githubusercontent.com/Akash9078/digitalocean-delta-algo/main/deploy/setup_droplet.sh | sudo bash
```

Then add your API credentials:
```bash
sudo nano /opt/delta-algo/.env
```

### Option B: Deploy from local

```bash
# Update .env with your credentials and droplet info, then:
python deploy/do_deploy.py
```

### Option C: Manual Docker setup

```bash
# 1. Clone
git clone https://github.com/Akash9078/digitalocean-delta-algo.git
cd digitalocean-delta-algo

# 2. Configure credentials
cp .env.example .env
nano .env    # Add DELTA_API_KEY and DELTA_API_SECRET

# 3. Build & run
docker compose up -d --build

# 4. View logs
docker compose logs -f bot
```

### View Logs Remotely

```bash
python deploy/view_logs.py
```

## Configuration

Edit **`config.yaml`** to tune strategy, risk, and timeframe:

```yaml
trading:
  symbol: "BTCUSD"
  timeframe: "5m"       # 1m 3m 5m 15m 1h 4h 1d

strategy:
  sma:
    short_period: 9
    long_period: 21
  rsi:
    period: 14
    overbought: 70
    oversold: 30

risk:
  position_sizing:
    type: "fixed"        # or "percentage"
    fixed_size: 1
  stop_loss:
    percentage: 2.0
  take_profit:
    percentage: 4.0
```

## API Endpoints

Access at **`http://<droplet-ip>:8501`**

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /bot/status` | Bot running state + config |
| `POST /bot/start` | Start the trading loop |
| `POST /bot/stop` | Stop the trading loop |
| `PUT /bot/strategy` | Live-update strategy params |
| `PUT /bot/risk` | Live-update risk params |
| `GET /positions` | Current open positions |
| `POST /positions/close` | Emergency close position |
| `GET /balance` | Account balance |
| `GET /market/ticker` | Live ticker |
| `GET /bot/logs` | Recent bot activity |

Full Swagger docs: **`http://<droplet-ip>:8501/docs`**

## Project Structure

```
.
├── api/
│   ├── delta_client.py       # Delta Exchange REST client (HMAC auth)
│   └── fastapi_app.py        # REST API endpoints
├── bot/
│   └── trading_bot.py        # Main trading loop orchestrator
├── strategy/
│   ├── indicators.py         # SMA, EMA, RSI calculations
│   └── trading_strategy.py  # Signal generation logic
├── risk/
│   └── risk_manager.py       # Position sizing, SL/TP, limits
├── utils/
│   └── config_loader.py      # YAML + .env config management
├── deploy/
│   ├── do_deploy.py          # Remote deploy script
│   ├── view_logs.py          # Stream logs remotely
│   └── setup_droplet.sh      # One-shot DO droplet setup
├── config.yaml               # Strategy & risk configuration
├── Dockerfile                # Multi-stage production build
├── docker-compose.yml        # Docker Compose for DO
├── .env.example              # Environment variables template
└── requirements.txt          # Python dependencies
```

## Environment Variables (.env)

```env
# DigitalOcean Credentials
DO_HOST=your_droplet_ip
DO_USER=root
DO_PASSWORD=your_ssh_password
APP_DIR=digitalocean-delta-algo

# Delta Exchange API Credentials
DELTA_API_KEY=your_api_key
DELTA_API_SECRET=your_api_secret
```

## Security Notes

- **Never commit `.env`** — it's in `.gitignore`
- API credentials loaded exclusively from environment variables
- Non-root Docker user (`botuser`) runs the container
- CORS locked to same-origin in production (update `allow_origins` in `fastapi_app.py`)

## Key Fixes Applied (2026-03-31)

| # | Bug | Fix |
|---|-----|-----|
| 1 | HMAC signature used `str(dict)` for POST body (wrong encoding) | Now uses `json.dumps()` to match actual request body |
| 2 | `close_position` opened new positions when SL/TP already filled | Now uses `reduce_only=True` + IOC via `api_client.close_position()` |
| 3 | Bracket orders used stale candle close price (not live price) | Live `mark_price` from ticker passed to bracket order calculation |
| 4 | Daily PnL tracking never updated — loss limit always read $0 | `trades_today` counter incremented after every fill |
| 5 | `bot_instance` created without thread lock (race condition) | Double-checked locking pattern added |
| 6 | GET query strings constructed with custom loop (URL encoding issues) | Now uses `urllib.parse.urlencode` |