# Delta Exchange Algo Trading Bot

> **SMA-RSI BTC Futures Trading Bot** running on Delta Exchange India — FastAPI backend and Docker deployment for DigitalOcean.

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

---

## Deploy to DigitalOcean

### Step 1: Create Droplet

1. Go to [DigitalOcean](https://digitalocean.com)
2. Create a new Droplet:
   - **Image**: Ubuntu 22.04 or 24.04
   - **Size**: $6/mo (1GB RAM) or higher
   - **Region**: Nearest to you

### Step 2: Get API Keys from Delta Exchange

1. Go to https://india.delta.exchange/app/api-keys
2. Create new API key with **Trading** permission
3. Copy the API Key and Secret

### Step 3: Deploy (Two Options)

#### Option A: Run setup script on droplet

```bash
# SSH into your droplet
ssh root@<your-droplet-ip>

# Run the setup script
curl -sL https://raw.githubusercontent.com/Akash9078/digitalocean-delta-algo/main/deploy/setup_droplet.sh | sudo bash

# Edit the .env file
nano /opt/delta-algo/.env
```

Add your Delta API credentials:
```
DELTA_API_KEY=your_delta_api_key
DELTA_API_SECRET=your_delta_api_secret
```

```bash
# Restart the bot
cd /opt/delta-algo
docker compose restart bot
```

#### Option B: Deploy from local machine

1. Clone the repo:
```bash
git clone https://github.com/Akash9078/digitalocean-delta-algo.git
cd digitalocean-delta-algo
```

2. Update `.env` file:
```bash
# Create .env from example
cp .env.example .env

# Edit with your credentials
nano .env
```

```env
# DigitalOcean
DO_HOST=your_droplet_ip
DO_USER=root
DO_PASSWORD=your_ssh_password

# Delta Exchange
DELTA_API_KEY=your_delta_api_key
DELTA_API_SECRET=your_delta_api_secret
```

3. Run deploy script:
```bash
python deploy/do_deploy.py
```

---

## Access the Bot

| Service | URL |
|---------|-----|
| API | `http://<droplet-ip>:8501` |
| API Docs | `http://<droplet-ip>:8501/docs` |
| View Logs | `python deploy/view_logs.py` |

### Control the Bot

```bash
# Start trading
curl -X POST http://<droplet-ip>:8501/bot/start

# Stop trading
curl -X POST http://<droplet-ip>:8501/bot/stop

# Check status
curl http://<droplet-ip>:8501/bot/status

# Check balance
curl http://<droplet-ip>:8501/balance
```

---

## Configuration

Edit **`config.yaml`** to tune strategy:

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
    type: "fixed"
    fixed_size: 1
  stop_loss:
    percentage: 2.0
  take_profit:
    percentage: 4.0
```

---

## Project Structure

```
├── api/
│   ├── delta_client.py       # Delta Exchange REST client (HMAC auth)
│   └── fastapi_app.py        # REST API endpoints
├── bot/
│   └── trading_bot.py        # Main trading loop
├── strategy/
│   ├── indicators.py         # SMA, RSI calculations
│   └── trading_strategy.py  # Signal generation
├── risk/
│   └── risk_manager.py       # Position sizing, SL/TP
├── deploy/
│   ├── do_deploy.py          # Remote deploy script
│   ├── view_logs.py          # Stream logs remotely
│   └── setup_droplet.sh     # One-shot droplet setup
├── config.yaml               # Strategy config
├── Dockerfile                # Production build
└── docker-compose.yml        # Container orchestration
```

---

## Security

- **Never commit `.env`** — it's in `.gitignore`
- API keys stored in environment variables
- Non-root Docker user runs the container

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /bot/status` | Bot status + config |
| `POST /bot/start` | Start trading |
| `POST /bot/stop` | Stop trading |
| `GET /positions` | Open positions |
| `GET /balance` | Wallet balance |
| `GET /market/ticker` | Live ticker |
| `GET /bot/logs` | Recent activity |