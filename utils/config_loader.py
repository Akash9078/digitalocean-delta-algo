"""
Configuration Loader
Loads configuration from YAML file and environment variables
"""

import os
import yaml
from typing import Dict, Any, Optional
from dotenv import load_dotenv


class ConfigLoader:
    """Load and manage bot configuration"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize configuration loader
        
        Args:
            config_path: Path to YAML configuration file
        """
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file and environment variables
        
        Returns:
            Configuration dictionary
        """
        # Load environment variables from .env file
        load_dotenv()
        
        # Load YAML configuration
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        # Override with environment variables if present
        self._apply_env_overrides()
        
        return self.config
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration"""
        # API credentials from environment
        api_key = os.getenv('DELTA_API_KEY')
        api_secret = os.getenv('DELTA_API_SECRET')
        
        if api_key:
            if 'exchange' not in self.config:
                self.config['exchange'] = {}
            self.config['exchange']['api_key'] = api_key
        
        if api_secret:
            if 'exchange' not in self.config:
                self.config['exchange'] = {}
            self.config['exchange']['api_secret'] = api_secret
        
        # Trading symbol override
        trading_symbol = os.getenv('TRADING_SYMBOL')
        if trading_symbol:
            if 'trading' not in self.config:
                self.config['trading'] = {}
            self.config['trading']['symbol'] = trading_symbol
        
        # Strategy parameter overrides
        timeframe = os.getenv('TIMEFRAME')
        if timeframe:
            self.config['trading']['timeframe'] = timeframe
        
        short_sma = os.getenv('SHORT_SMA')
        if short_sma:
            self.config['strategy']['sma']['short_period'] = int(short_sma)
        
        long_sma = os.getenv('LONG_SMA')
        if long_sma:
            self.config['strategy']['sma']['long_period'] = int(long_sma)
        
        rsi_period = os.getenv('RSI_PERIOD')
        if rsi_period:
            self.config['strategy']['rsi']['period'] = int(rsi_period)
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Configuration key path (e.g., 'strategy.sma.short_period')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value: Any):
        """
        Set configuration value using dot notation
        
        Args:
            key_path: Configuration key path
            value: Value to set
        """
        keys = key_path.split('.')
        config = self.config
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
    
    def save(self, file_path: Optional[str] = None):
        """
        Save current configuration to YAML file
        
        Args:
            file_path: Path to save configuration (default: original config_path)
        """
        save_path = file_path or self.config_path
        
        # Don't save API credentials to file
        config_to_save = self.config.copy()
        if 'exchange' in config_to_save and 'api_key' in config_to_save['exchange']:
            del config_to_save['exchange']['api_key']
        if 'exchange' in config_to_save and 'api_secret' in config_to_save['exchange']:
            del config_to_save['exchange']['api_secret']
        
        with open(save_path, 'w') as f:
            yaml.dump(config_to_save, f, default_flow_style=False, sort_keys=False)
    
    def validate(self) -> bool:
        """
        Validate configuration
        
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        # Check required fields
        required_fields = [
            'exchange.base_url',
            'trading.symbol',
            'trading.timeframe',
            'strategy.sma.short_period',
            'strategy.sma.long_period',
        ]
        
        for field in required_fields:
            if self.get(field) is None:
                raise ValueError(f"Missing required configuration: {field}")
        
        # Validate API credentials
        if not self.get('exchange.api_key'):
            raise ValueError("DELTA_API_KEY not set in environment variables")
        if not self.get('exchange.api_secret'):
            raise ValueError("DELTA_API_SECRET not set in environment variables")
        
        # Validate SMA periods
        short_period = self.get('strategy.sma.short_period')
        long_period = self.get('strategy.sma.long_period')
        
        if short_period >= long_period:
            raise ValueError(f"Short SMA period ({short_period}) must be less than long SMA period ({long_period})")
        
        # Validate RSI parameters
        rsi_period = self.get('strategy.rsi.period')
        if rsi_period < 2:
            raise ValueError(f"RSI period must be at least 2, got {rsi_period}")
        
        overbought = self.get('strategy.rsi.overbought')
        oversold = self.get('strategy.rsi.oversold')
        
        if oversold >= overbought:
            raise ValueError(f"RSI oversold ({oversold}) must be less than overbought ({overbought})")
        
        # Validate risk parameters
        stop_loss = self.get('risk.stop_loss.percentage')
        take_profit = self.get('risk.take_profit.percentage')
        
        if stop_loss <= 0:
            raise ValueError(f"Stop loss percentage must be positive, got {stop_loss}")
        if take_profit <= 0:
            raise ValueError(f"Take profit percentage must be positive, got {take_profit}")
        
        return True
