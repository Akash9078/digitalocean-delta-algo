"""
Delta Exchange Trading Bot - Headless API
This runs the bot and FastAPI server in the background without any dashboard.
"""

import argparse
import logging
import sys
import threading
import uvicorn
import time
from bot.trading_bot import TradingBot, setup_logging
from utils import ConfigLoader

def main():
    """Main entry point for headless API mode"""
    parser = argparse.ArgumentParser(description='Delta Exchange Trading Bot')
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file. Starts both API and Trading bot loop.'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config_loader = ConfigLoader(args.config)
    config = config_loader.config
    
    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)
    
    logger.info("="*70)
    logger.info("DELTA EXCHANGE TRADING BOT - HEADLESS API MODE")
    logger.info("="*70)
    logger.info(f"Symbol: {config['trading']['symbol']}")
    logger.info(f"Timeframe: {config['trading']['timeframe']}")
    logger.info("="*70)
    
    try:
        # Run both bot and API server
        bot = TradingBot(args.config)
        
        # Start bot in background thread by default in Headless mode
        bot_thread = threading.Thread(target=bot.start, daemon=True)
        bot_thread.start()
        logger.info("Trading bot started successfully in background")
        
        # Run FastAPI server in main thread
        logger.info(f"Starting FastAPI server on {config['api']['host']}:{config['api']['port']}")
        
        from api.fastapi_app import app
        uvicorn.run(
            app,
            host=config['api']['host'],
            port=config['api']['port'],
            log_level="info"
        )
        
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
