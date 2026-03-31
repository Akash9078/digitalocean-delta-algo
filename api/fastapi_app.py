"""
FastAPI Application for Trading Bot Control
Provides REST API endpoints for bot management and monitoring
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from collections import deque
from datetime import datetime
import logging
import threading

from bot import TradingBot
from utils import ConfigLoader


logger = logging.getLogger(__name__)

# Global bot instance
bot_instance: Optional[TradingBot] = None
bot_thread: Optional[threading.Thread] = None
_bot_lock = threading.Lock()  # Thread-safe bot initialization

# In-memory log buffer for frontend (last 100 entries)
log_buffer: deque = deque(maxlen=100)
log_buffer_lock = threading.Lock()


class LogBufferHandler(logging.Handler):
    """Custom logging handler that stores logs in memory for API access"""
    
    def emit(self, record):
        try:
            log_entry = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": self.format(record),
                "timestamp": record.created
            }
            with log_buffer_lock:
                log_buffer.append(log_entry)
        except Exception:
            self.handleError(record)


# Initialize FastAPI
app = FastAPI(
    title="Delta Exchange Trading Bot API",
    description="REST API for managing and monitoring the trading bot",
    version="1.0.0"
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class BotStatusResponse(BaseModel):
    running: bool
    symbol: str
    timeframe: str
    strategy: Dict[str, Any]
    uptime: Optional[float] = None


class ConfigUpdateRequest(BaseModel):
    key_path: str
    value: Any


class StrategyUpdateRequest(BaseModel):
    short_sma_period: Optional[int] = None
    long_sma_period: Optional[int] = None
    rsi_period: Optional[int] = None
    rsi_overbought: Optional[float] = None
    rsi_oversold: Optional[float] = None
    confirmation_candles: Optional[int] = None
    signal_cooldown: Optional[int] = None
    use_rsi: Optional[bool] = None


class RiskUpdateRequest(BaseModel):
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    position_size_type: Optional[str] = None
    fixed_size: Optional[int] = None
    risk_percentage: Optional[float] = None
    max_positions: Optional[int] = None


# Helper Functions
def get_bot() -> TradingBot:
    """Get global bot instance (thread-safe)"""
    global bot_instance
    if bot_instance is None:
        with _bot_lock:
            if bot_instance is None:  # Double-checked locking
                bot_instance = TradingBot()
    return bot_instance


def run_bot_in_thread():
    """Run bot in background thread"""
    bot = get_bot()
    bot.start()


# API Endpoints

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Delta Exchange Trading Bot API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.post("/bot/start")
async def start_bot(background_tasks: BackgroundTasks):
    """Start the trading bot"""
    global bot_thread
    
    bot = get_bot()
    
    if bot.running:
        raise HTTPException(status_code=400, detail="Bot is already running")
    
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()
    
    logger.info("Bot started via API")
    
    return {"message": "Bot started successfully", "status": "running"}


@app.post("/bot/stop")
async def stop_bot():
    """Stop the trading bot"""
    bot = get_bot()
    
    if not bot.running:
        raise HTTPException(status_code=400, detail="Bot is not running")
    
    bot.stop()
    
    logger.info("Bot stopped via API")
    
    return {"message": "Bot stopped successfully", "status": "stopped"}


@app.get("/bot/status", response_model=BotStatusResponse)
async def get_bot_status():
    """Get current bot status"""
    bot = get_bot()
    
    return {
        "running": bot.running,
        "symbol": bot.symbol,
        "timeframe": bot.timeframe,
        "strategy": {
            "short_sma": bot.strategy.short_sma_period,
            "long_sma": bot.strategy.long_sma_period,
            "rsi_period": bot.strategy.rsi_period,
            "use_rsi": bot.strategy.use_rsi,
            "confirmation_candles": bot.strategy.confirmation_candles
        }
    }


@app.get("/bot/config")
async def get_config():
    """Get current configuration"""
    bot = get_bot()
    return bot.config


@app.put("/bot/config")
async def update_config(request: ConfigUpdateRequest):
    """Update configuration dynamically"""
    bot = get_bot()
    
    try:
        bot.config_loader.set(request.key_path, request.value)
        logger.info(f"Config updated: {request.key_path} = {request.value}")
        return {"message": "Configuration updated", "key": request.key_path, "value": request.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/bot/strategy")
async def update_strategy(request: StrategyUpdateRequest):
    """Update strategy parameters"""
    bot = get_bot()
    
    bot.strategy.update_config(
        short_sma_period=request.short_sma_period,
        long_sma_period=request.long_sma_period,
        rsi_period=request.rsi_period,
        rsi_overbought=request.rsi_overbought,
        rsi_oversold=request.rsi_oversold,
        confirmation_candles=request.confirmation_candles,
        signal_cooldown=request.signal_cooldown,
        use_rsi=request.use_rsi
    )
    
    logger.info(f"Strategy updated via API: {request.dict(exclude_none=True)}")
    
    return {"message": "Strategy updated successfully", "updates": request.dict(exclude_none=True)}


@app.put("/bot/risk")
async def update_risk(request: RiskUpdateRequest):
    """Update risk management parameters"""
    bot = get_bot()
    
    bot.risk_manager.update_config(
        stop_loss_pct=request.stop_loss_pct,
        take_profit_pct=request.take_profit_pct,
        position_size_type=request.position_size_type,
        fixed_size=request.fixed_size,
        risk_percentage=request.risk_percentage,
        max_positions=request.max_positions
    )
    
    logger.info(f"Risk parameters updated via API: {request.dict(exclude_none=True)}")
    
    return {"message": "Risk parameters updated successfully", "updates": request.dict(exclude_none=True)}


@app.get("/positions")
async def get_positions():
    """Get current positions"""
    bot = get_bot()
    
    try:
        position = bot.api_client.get_position(bot.symbol)
        return {"symbol": bot.symbol, "position": position}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/positions/margined")
async def get_margined_positions():
    """Get margined positions with full details"""
    bot = get_bot()
    
    try:
        positions = bot.api_client.get_margined_positions(bot.symbol)
        return {"positions": positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/positions/close")
async def close_position():
    """Close the current position for the trading symbol"""
    bot = get_bot()
    
    try:
        result = bot.api_client.close_position(bot.symbol)
        
        if result.get('success'):
            # Add log entry
            with log_buffer_lock:
                log_buffer.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "level": "INFO",
                    "message": f"Position closed for {bot.symbol}",
                    "timestamp": datetime.now().timestamp()
                })
            return {"message": "Position closed successfully", "result": result}
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to close position'))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/positions/close_all")
async def close_all_positions():
    """Close all open positions"""
    bot = get_bot()
    
    try:
        result = bot.api_client.close_all_positions()
        
        if result.get('success'):
            # Add log entry
            with log_buffer_lock:
                log_buffer.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "level": "INFO",
                    "message": "All positions closed",
                    "timestamp": datetime.now().timestamp()
                })
            return {"message": "All positions closed successfully", "result": result}
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to close positions'))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders")
async def get_open_orders():
    """Get open orders"""
    bot = get_bot()
    
    try:
        orders = bot.api_client.get_open_orders(bot.symbol)
        return {"symbol": bot.symbol, "orders": orders, "count": len(orders)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/balance")
async def get_balance():
    """Get account balance"""
    bot = get_bot()
    
    try:
        balance = bot.api_client.get_balance_for_asset("USD")
        return {"asset": "USD", "balance": balance}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market/ticker")
async def get_ticker():
    """Get current ticker data"""
    bot = get_bot()
    
    try:
        ticker = bot.api_client.get_ticker(bot.symbol)
        return {"symbol": bot.symbol, "ticker": ticker}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market/candles")
async def get_candles(hours: int = 24):
    """Get historical candles"""
    bot = get_bot()
    
    try:
        candles = bot.api_client.get_ohlc_candles(
            bot.symbol,
            bot.timeframe,
            hours
        )
        return {
            "symbol": bot.symbol,
            "timeframe": bot.timeframe,
            "candles": candles,
            "count": len(candles)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bot/logs")
async def get_logs(limit: int = 50):
    """Get recent bot activity logs from memory buffer"""
    with log_buffer_lock:
        logs = list(log_buffer)
    
    # Return last 'limit' entries, most recent last
    if limit > 0:
        logs = logs[-limit:]
    
    return {"logs": logs, "count": len(logs)}


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    # Setup log buffer handler to capture logs for API
    log_handler = LogBufferHandler()
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Add handler to root logger and trading bot loggers
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    
    # Add initial log entry
    with log_buffer_lock:
        log_buffer.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "INFO",
            "message": "FastAPI application started",
            "timestamp": datetime.now().timestamp()
        })
    
    logger.info("FastAPI application started")
    
    # Initialize bot but don't auto-start
    get_bot()


if __name__ == "__main__":
    import uvicorn
    
    # Load config
    config_loader = ConfigLoader()
    config = config_loader.config
    
    # Run FastAPI server
    uvicorn.run(
        app,
        host=config['api']['host'],
        port=config['api']['port'],
        log_level="info"
    )
