"""
Trading Bot - Main Orchestrator
Coordinates all components and runs the trading loop
"""

import logging
import time
import sys
import argparse
import os
from datetime import datetime
from typing import Optional, Dict

from api import DeltaExchangeClient
from strategy import TechnicalIndicators, TradingStrategy
from risk import RiskManager
from utils import ConfigLoader


logger = logging.getLogger(__name__)


class TradingBot:
    """
    Main Trading Bot orchestrator
    
    Coordinates:
    - Market data fetching
    - Signal generation
    - Order execution
    - Risk management
    - Position tracking
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize trading bot
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.config
        
        # Validate configuration
        try:
            self.config_loader.validate()
        except ValueError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
        
        # Initialize components
        self.api_client = DeltaExchangeClient(
            api_key=self.config['exchange']['api_key'],
            api_secret=self.config['exchange']['api_secret'],
            base_url=self.config['exchange']['base_url']
        )
        
        self.strategy = TradingStrategy(
            short_sma_period=self.config['strategy']['sma']['short_period'],
            long_sma_period=self.config['strategy']['sma']['long_period'],
            rsi_period=self.config['strategy']['rsi']['period'],
            rsi_overbought=self.config['strategy']['rsi']['overbought'],
            rsi_oversold=self.config['strategy']['rsi']['oversold'],
            confirmation_candles=self.config['strategy']['confirmation']['candles'],
            signal_cooldown=self.config['strategy']['confirmation']['signal_cooldown'],
            use_rsi=self.config['strategy']['rsi']['enabled']
        )
        
        self.risk_manager = RiskManager(
            position_size_type=self.config['risk']['position_sizing']['type'],
            fixed_size=self.config['risk']['position_sizing']['fixed_size'],
            risk_percentage=self.config['risk']['position_sizing']['risk_percentage'],
            stop_loss_pct=self.config['risk']['stop_loss']['percentage'],
            take_profit_pct=self.config['risk']['take_profit']['percentage'],
            sl_order_type=self.config['risk']['stop_loss']['order_type'],
            tp_order_type=self.config['risk']['take_profit']['order_type'],
            max_positions=self.config['risk']['limits']['max_positions'],
            max_position_size=self.config['risk']['limits']['max_position_size'],
            max_daily_loss=self.config['risk']['limits']['max_daily_loss'],
            use_trailing_sl=self.config['risk']['stop_loss']['trailing'],
            trail_amount=self.config['risk']['stop_loss']['trail_amount']
        )
        
        # Bot state
        self.running = False
        self.symbol = self.config['trading']['symbol']
        self.timeframe = self.config['trading']['timeframe']
        self.loop_interval = self.config['bot']['loop_interval']
        
        logger.info(f"Trading Bot initialized for {self.symbol} ({self.timeframe})")
    
    def start(self):
        """Start the trading bot"""
        if self.running:
            logger.warning("Bot is already running")
            return
        
        self.running = True
        logger.info("=" * 60)
        logger.info("TRADING BOT STARTED")
        logger.info("=" * 60)
        
        # Initialize daily metrics
        balance = self.get_account_balance()
        self.risk_manager.reset_daily_metrics(balance)
        
        # Run main trading loop
        try:
            self.run()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            self.stop()
        except Exception as e:
            logger.exception(f"Bot crashed with error: {e}")
            self.stop()
    
    def stop(self):
        """Stop the trading bot"""
        self.running = False
        logger.info("=" * 60)
        logger.info("TRADING BOT STOPPED")
        logger.info("=" * 60)
    
    def run(self):
        """Main trading loop"""
        while self.running:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Trading Loop - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                # Fetch market data
                candles = self.fetch_market_data()
                if not candles:
                    logger.warning("No market data available, skipping iteration")
                    time.sleep(self.loop_interval)
                    continue
                
                # Calculate indicators
                indicators = TechnicalIndicators.calculate_indicators_from_candles(
                    candles,
                    short_sma_period=self.strategy.short_sma_period,
                    long_sma_period=self.strategy.long_sma_period,
                    rsi_period=self.strategy.rsi_period
                )
                
                # Get real-time ticker price (mark_price) instead of stale candle close
                ticker = self.api_client.get_ticker(self.symbol)
                current_price = float(ticker.get('mark_price') or ticker.get('last_price') or ticker.get('close', 0))
                
                # Log current values
                latest = TechnicalIndicators.get_latest_values(indicators)
                logger.info(f"Current Price: ${current_price:.2f}")
                logger.info(f"Short SMA({self.strategy.short_sma_period}): ${latest.get('short_sma', 0):.2f}")
                logger.info(f"Long SMA({self.strategy.long_sma_period}): ${latest.get('long_sma', 0):.2f}")
                logger.info(f"RSI({self.strategy.rsi_period}): {latest.get('rsi', 0):.2f}")
                
                # Get current position
                position = self.api_client.get_position(self.symbol)
                current_position_size = position.get('size', 0)
                logger.info(f"Current Position: {current_position_size} contracts")
                
                # Generate trading signal
                signal, signal_data = self.strategy.generate_signal(
                    indicators,
                    current_position_size
                )
                
                if signal:
                    # Execute trade, passing live ticker price for accurate bracket order calculation
                    self.execute_trade(signal, signal_data, current_position_size, current_price)
                else:
                    logger.info("No trading signal generated")
                
                # Sleep until next iteration
                logger.info(f"Sleeping for {self.loop_interval} seconds...")
                time.sleep(self.loop_interval)
                
            except Exception as e:
                logger.exception(f"Error in trading loop: {e}")
                time.sleep(self.loop_interval)
    
    def fetch_market_data(self) -> list:
        """
        Fetch market data (OHLC candles)
        
        Returns:
            List of candle dictionaries
        """
        lookback_hours = self.config['strategy']['lookback_hours']
        
        candles = self.api_client.get_ohlc_candles(
            symbol=self.symbol,
            resolution=self.timeframe,
            lookback_hours=lookback_hours
        )
        
        logger.info(f"Fetched {len(candles)} candles")
        return candles
    
    def execute_trade(self, signal: str, signal_data: dict, current_position: int, live_price: float = None):
        """
        Execute a trade based on signal
        
        Args:
            signal: "buy" or "sell"
            signal_data: Signal metadata
            current_position: Current position size
            live_price: Live ticker price (mark_price) for bracket order calculation.
                        Falls back to signal_data candle close if not provided.
        """
        logger.info(f"\n{'*'*60}")
        logger.info(f"EXECUTING {signal.upper()} SIGNAL")
        logger.info(f"{'*'*60}")
        
        # Get account balance
        balance = self.get_account_balance()
        
        # Check if trading is allowed
        num_positions = 1 if current_position != 0 else 0
        can_trade, reason = self.risk_manager.can_trade(num_positions, balance)
        
        if not can_trade:
            logger.warning(f"Trading not allowed: {reason}")
            return
        
        # Close opposite position if exists
        if (signal == "buy" and current_position < 0) or (signal == "sell" and current_position > 0):
            logger.info("Closing opposite position first...")
            self.close_position(current_position)
            time.sleep(2)  # Wait for position to close
        
        # Use live price for bracket order calculation; fall back to candle close
        current_price = live_price if live_price else signal_data.get('price')
        if not current_price:
            logger.error("Cannot execute trade: no price available")
            return
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(balance, current_price)
        
        # Determine order side
        side = "buy" if signal == "buy" else "sell"
        
        # Create bracket order parameters
        bracket_params = {}
        if self.config['risk']['bracket_order']['enabled']:
            bracket_params = self.risk_manager.create_bracket_order_params(
                current_price, side
            )
            bracket_params['bracket_stop_trigger_method'] = self.config['risk']['bracket_order']['trigger_method']
        
        # Place order
        order = self.api_client.place_order(
            symbol=self.symbol,
            side=side,
            size=position_size,
            order_type=self.config['trading']['order_type'],
            **bracket_params
        )
        
        if order.get('success') is not False:
            logger.info(f"✓ Order placed successfully: {order.get('id')}")
            self.log_trade(signal, signal_data, order)
            # Update daily P&L tracking (estimated entry at current_price)
            # Actual P&L will be reconciled when position closes
            self.risk_manager.trades_today += 1
        else:
            logger.error(f"✗ Failed to place order: {order.get('error')}")
    
    def close_position(self, position_size: int):
        """
        Close an existing position using reduce_only market order via API client.
        Using reduce_only prevents accidentally opening a new position if
        the position was already closed by SL/TP.
        
        Args:
            position_size: Current position size (positive=long, negative=short)
        """
        if position_size == 0:
            return
        
        logger.info(f"Closing position: {'long' if position_size > 0 else 'short'} {abs(position_size)} contracts")
        
        # Use api_client.close_position which sends reduce_only=True + IOC
        result = self.api_client.close_position(self.symbol, abs(position_size))
        
        if result.get('success'):
            logger.info("✓ Position closed successfully")
        else:
            logger.error(f"✗ Failed to close position: {result.get('error')}")
    
    def get_account_balance(self) -> float:
        """
        Get available account balance
        
        Returns:
            Available balance as float
        """
        balance_data = self.api_client.get_balance_for_asset("USD")
        available = float(balance_data.get('available_balance', 0))
        logger.debug(f"Available balance: ${available:.2f}")
        return available
    
    def log_trade(self, signal: str, signal_data: dict, order: dict):
        """
        Log trade execution details
        
        Args:
            signal: Trading signal
            signal_data: Signal metadata
            order: Order response
        """
        trade_log = f"""
        ╔═══════════════════════════════════════════════════════════╗
        ║                      TRADE EXECUTED                        ║
        ╠═══════════════════════════════════════════════════════════╣
        ║ Signal:     {signal.upper():<48} ║
        ║ Symbol:     {self.symbol:<48} ║
        ║ Price:      ${signal_data.get('price', 0):<47.2f} ║
        ║ Size:       {order.get('size', 0)} contracts{' ':<38} ║
        ║ Order ID:   {order.get('id', 'N/A'):<48} ║
        ║ RSI:        {signal_data.get('rsi', 0):<47.2f} ║
        ║ Reason:     {signal_data.get('reason', 'N/A'):<48} ║
        ╚═══════════════════════════════════════════════════════════╝
        """
        logger.info(trade_log)


def setup_logging(config: dict):
    """Setup logging configuration"""
    import colorlog
    
    log_level = getattr(logging, config['logging']['level'])
    
    # Create formatters
    console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Console handler
    if config['logging']['console']['enabled']:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if config['logging']['file']['enabled']:
        import os
        from logging.handlers import RotatingFileHandler
        
        log_dir = os.path.dirname(config['logging']['file']['path'])
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = RotatingFileHandler(
            config['logging']['file']['path'],
            maxBytes=config['logging']['file']['max_bytes'],
            backupCount=config['logging']['file']['backup_count']
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Trading Bot runner")
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to YAML config file")
    parser.add_argument("--mode", "-m", choices=["live", "paper"], help="Bot mode to run (overrides config)")
    parser.add_argument("--auto-start", action="store_true", help="Force auto_start=true for this run")

    args = parser.parse_args()

    # Load config for logging setup
    config_loader = ConfigLoader(args.config)
    config = config_loader.config

    # Apply runtime overrides and, if any, save to a temporary config file so multiple instances can run
    tmp_config_path = None
    if args.mode is not None:
        config_loader.set('bot.mode', args.mode)
        config['bot']['mode'] = args.mode

    if args.auto_start:
        config_loader.set('bot.auto_start', True)
        config['bot']['auto_start'] = True

    if args.mode is not None or args.auto_start:
        # Write a temp config under run/configs/ so we don't overwrite the repository config
        tmp_dir = os.path.join('run', 'configs')
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_config_path = os.path.join(tmp_dir, f"config_{args.mode or 'override'}.yaml")
        config_loader.save(tmp_config_path)

    # Which config path will the bot use?
    config_path_for_bot = tmp_config_path or args.config

    # Setup logging with the effective config
    setup_logging(config)

    # Create and start bot using the effective config path
    bot = TradingBot(config_path=config_path_for_bot)

    if config.get('bot', {}).get('auto_start'):
        bot.start()
    else:
        logger.info("Bot initialized but not started (auto_start=false)")
        logger.info("Start the bot via FastAPI endpoint or change config")


if __name__ == "__main__":
    main()
