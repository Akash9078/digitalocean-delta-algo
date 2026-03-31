"""
Trading Strategy Module
Implements SMA crossover with RSI confirmation strategy
"""

import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime


logger = logging.getLogger(__name__)


class TradingStrategy:
    """
    SMA Crossover Strategy with RSI Confirmation
    
    Features:
    - Configurable SMA periods (e.g., 9,21 or 9,30)
    - RSI confirmation with configurable thresholds
    - Candle confirmation (wait N candles after crossover)
    - Signal cooldown to prevent overtrading
    """
    
    def __init__(
        self,
        short_sma_period: int = 9,
        long_sma_period: int = 21,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
        confirmation_candles: int = 1,
        signal_cooldown: int = 300,
        use_rsi: bool = True
    ):
        """
        Initialize trading strategy with configurable parameters
        
        Args:
            short_sma_period: Short SMA period (default: 9)
            long_sma_period: Long SMA period (default: 21)
            rsi_period: RSI calculation period (default: 14)
            rsi_overbought: RSI overbought threshold (default: 70)
            rsi_oversold: RSI oversold threshold (default: 30)
            confirmation_candles: Candles to wait for confirmation (default: 1)
            signal_cooldown: Seconds between signals (default: 300)
            use_rsi: Enable RSI confirmation (default: True)
        """
        self.short_sma_period = short_sma_period
        self.long_sma_period = long_sma_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.confirmation_candles = confirmation_candles
        self.signal_cooldown = signal_cooldown
        self.use_rsi = use_rsi
        
        # Track last signal time
        self.last_signal_time = 0
        
        logger.info(
            f"Strategy initialized: SMA({short_sma_period},{long_sma_period}), "
            f"RSI({rsi_period}), Confirmation: {confirmation_candles} candle(s), "
            f"Cooldown: {signal_cooldown}s, Use RSI: {use_rsi}"
        )
    
    def can_generate_signal(self) -> bool:
        """
        Check if enough time has passed since last signal (cooldown)
        
        Returns:
            True if signal can be generated
        """
        current_time = time.time()
        time_since_last = current_time - self.last_signal_time
        
        if time_since_last < self.signal_cooldown:
            remaining = self.signal_cooldown - time_since_last
            logger.debug(f"Signal cooldown active: {remaining:.0f}s remaining")
            return False
        
        return True
    
    def generate_signal(
        self,
        indicators: dict,
        current_position: int = 0
    ) -> Tuple[Optional[str], Dict]:
        """
        Generate trading signal based on strategy rules
        
        Strategy Rules:
        1. SMA Crossover: Short SMA crosses Long SMA
        2. Confirmation: Wait for N candles after crossover
        3. RSI Confirmation: RSI must confirm the direction
        4. Cooldown: Minimum time between signals
        
        Args:
            indicators: Dictionary with calculated indicators
            current_position: Current position size (0=flat, >0=long, <0=short)
            
        Returns:
            Tuple of (signal, signal_data)
            signal: "buy", "sell", or None
            signal_data: Dictionary with signal details
        """
        from .indicators import TechnicalIndicators
        
        # Check cooldown
        if not self.can_generate_signal():
            return None, {}
        
        # Extract indicators
        short_sma = indicators.get('short_sma', [])
        long_sma = indicators.get('long_sma', [])
        rsi = indicators.get('rsi', [])
        close_prices = indicators.get('close_prices', [])
        
        # Validate data availability
        required_length = max(self.long_sma_period, self.rsi_period) + self.confirmation_candles + 1
        if len(close_prices) < required_length:
            logger.warning(
                f"Insufficient data: need {required_length} candles, "
                f"got {len(close_prices)}"
            )
            return None, {}
        
        # Detect crossover with confirmation
        golden_cross, death_cross = TechnicalIndicators.detect_crossover(
            short_sma, long_sma, self.confirmation_candles
        )
        
        signal = None
        signal_data = {
            'timestamp': datetime.now().isoformat(),
            'price': close_prices[-1],
            'short_sma': short_sma[-1] if short_sma else None,
            'long_sma': long_sma[-1] if long_sma else None,
            'rsi': rsi[-1] if rsi else None,
            'current_position': current_position
        }
        
        # Golden Cross -> BUY signal
        if golden_cross:
            # Skip if already long
            if current_position > 0:
                logger.info("Golden cross detected but already in long position")
                return None, {}
            
            # Check RSI confirmation if enabled
            if self.use_rsi:
                rsi_confirmed = TechnicalIndicators.check_rsi_confirmation(
                    rsi, "buy", self.rsi_oversold, self.rsi_overbought
                )
                if not rsi_confirmed:
                    logger.warning("Golden cross detected but RSI does not confirm BUY")
                    return None, {}
            
            signal = "buy"
            signal_data['signal_type'] = 'golden_cross'
            signal_data['reason'] = f"SMA({self.short_sma_period}) crossed above SMA({self.long_sma_period})"
            
            logger.info(f"BUY SIGNAL generated: {signal_data['reason']}")
        
        # Death Cross -> SELL signal
        elif death_cross:
            # Skip if already short
            if current_position < 0:
                logger.info("Death cross detected but already in short position")
                return None, {}
            
            # Check RSI confirmation if enabled
            if self.use_rsi:
                rsi_confirmed = TechnicalIndicators.check_rsi_confirmation(
                    rsi, "sell", self.rsi_oversold, self.rsi_overbought
                )
                if not rsi_confirmed:
                    logger.warning("Death cross detected but RSI does not confirm SELL")
                    return None, {}
            
            signal = "sell"
            signal_data['signal_type'] = 'death_cross'
            signal_data['reason'] = f"SMA({self.short_sma_period}) crossed below SMA({self.long_sma_period})"
            
            logger.info(f"SELL SIGNAL generated: {signal_data['reason']}")
        
        # Update last signal time if signal generated
        if signal:
            self.last_signal_time = time.time()
        
        return signal, signal_data
    
    def should_close_position(
        self,
        indicators: dict,
        current_position: int
    ) -> bool:
        """
        Check if current position should be closed based on opposite signal
        
        Args:
            indicators: Dictionary with calculated indicators
            current_position: Current position size
            
        Returns:
            True if position should be closed
        """
        if current_position == 0:
            return False
        
        from .indicators import TechnicalIndicators
        
        short_sma = indicators.get('short_sma', [])
        long_sma = indicators.get('long_sma', [])
        
        if not short_sma or not long_sma:
            return False
        
        # Check for opposite crossover
        golden_cross, death_cross = TechnicalIndicators.detect_crossover(
            short_sma, long_sma, self.confirmation_candles
        )
        
        # Close long position on death cross
        if current_position > 0 and death_cross:
            logger.info("Death cross detected - closing long position")
            return True
        
        # Close short position on golden cross
        if current_position < 0 and golden_cross:
            logger.info("Golden cross detected - closing short position")
            return True
        
        return False
    
    def update_config(
        self,
        short_sma_period: Optional[int] = None,
        long_sma_period: Optional[int] = None,
        rsi_period: Optional[int] = None,
        rsi_overbought: Optional[float] = None,
        rsi_oversold: Optional[float] = None,
        confirmation_candles: Optional[int] = None,
        signal_cooldown: Optional[int] = None,
        use_rsi: Optional[bool] = None
    ):
        """
        Update strategy configuration dynamically
        
        Args:
            short_sma_period: New short SMA period
            long_sma_period: New long SMA period
            rsi_period: New RSI period
            rsi_overbought: New RSI overbought threshold
            rsi_oversold: New RSI oversold threshold
            confirmation_candles: New confirmation candles
            signal_cooldown: New signal cooldown
            use_rsi: Enable/disable RSI
        """
        if short_sma_period is not None:
            self.short_sma_period = short_sma_period
            logger.info(f"Updated short SMA period to {short_sma_period}")
        
        if long_sma_period is not None:
            self.long_sma_period = long_sma_period
            logger.info(f"Updated long SMA period to {long_sma_period}")
        
        if rsi_period is not None:
            self.rsi_period = rsi_period
            logger.info(f"Updated RSI period to {rsi_period}")
        
        if rsi_overbought is not None:
            self.rsi_overbought = rsi_overbought
            logger.info(f"Updated RSI overbought to {rsi_overbought}")
        
        if rsi_oversold is not None:
            self.rsi_oversold = rsi_oversold
            logger.info(f"Updated RSI oversold to {rsi_oversold}")
        
        if confirmation_candles is not None:
            self.confirmation_candles = confirmation_candles
            logger.info(f"Updated confirmation candles to {confirmation_candles}")
        
        if signal_cooldown is not None:
            self.signal_cooldown = signal_cooldown
            logger.info(f"Updated signal cooldown to {signal_cooldown}s")
        
        if use_rsi is not None:
            self.use_rsi = use_rsi
            logger.info(f"Updated use_rsi to {use_rsi}")
