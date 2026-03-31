"""
Technical Indicators Module
Calculates technical indicators for trading strategy

All indicators are fully configurable via parameters
"""

import logging
from typing import List, Tuple, Optional
import pandas as pd
import numpy as np


logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """
    Calculate technical indicators for trading
    
    Supports:
    - Simple Moving Average (SMA) - fully configurable periods
    - Relative Strength Index (RSI) - configurable period and thresholds
    - Crossover detection
    """
    
    @staticmethod
    def sma(prices: List[float], period: int) -> List[float]:
        """
        Calculate Simple Moving Average
        
        Args:
            prices: List of prices
            period: SMA period (e.g., 9, 21, 30, 50, 200,356)
            
        Returns:
            List of SMA values
        """
        if len(prices) < period:
            logger.warning(f"Insufficient data for SMA({period}): got {len(prices)} prices")
            return []
        
        sma_values = []
        for i in range(period - 1, len(prices)):
            avg = sum(prices[i - period + 1:i + 1]) / period
            sma_values.append(avg)
        
        logger.debug(f"Calculated SMA({period}): {len(sma_values)} values")
        return sma_values
    
    @staticmethod
    def ema(prices: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average
        
        Args:
            prices: List of prices
            period: EMA period
            
        Returns:
            List of EMA values
        """
        if len(prices) < period:
            logger.warning(f"Insufficient data for EMA({period}): got {len(prices)} prices")
            return []
        
        multiplier = 2 / (period + 1)
        ema_values = []
        
        # First EMA is SMA
        sma_first = sum(prices[:period]) / period
        ema_values.append(sma_first)
        
        # Calculate subsequent EMA values
        for i in range(period, len(prices)):
            ema = (prices[i] - ema_values[-1]) * multiplier + ema_values[-1]
            ema_values.append(ema)
        
        logger.debug(f"Calculated EMA({period}): {len(ema_values)} values")
        return ema_values
    
    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> List[float]:
        """
        Calculate Relative Strength Index
        
        Args:
            prices: List of closing prices
            period: RSI period (default: 14)
            
        Returns:
            List of RSI values (0-100)
        """
        if len(prices) < period + 1:
            logger.warning(f"Insufficient data for RSI({period}): got {len(prices)} prices")
            return []
        
        # Calculate price changes
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        
        rsi_values = []
        
        # Calculate first average gain and loss (SMA)
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        # First RSI value
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
        
        # Calculate subsequent RSI values using smoothed averages
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
        
        logger.debug(f"Calculated RSI({period}): {len(rsi_values)} values, last={rsi_values[-1]:.2f}")
        return rsi_values
    
    @staticmethod
    def detect_crossover(
        short_ma: List[float], 
        long_ma: List[float],
        confirmation_candles: int = 1
    ) -> Tuple[bool, bool]:
        """
        Detect golden cross (bullish) and death cross (bearish) with confirmation
        
        FIXED: Now checks that crossover happened N candles ago and is confirmed by current candle
        
        Logic:
        - With confirmation_candles=1: 
          * Candle -2: Before crossover (short <= long for golden cross)
          * Candle -1: Crossover happens (short crosses above long)
          * Current (0): Confirmation (short still > long) -> Generate signal
        
        Args:
            short_ma: Short-term moving average values
            long_ma: Long-term moving average values
            confirmation_candles: Number of candles to wait after crossover for confirmation (default: 1)
            
        Returns:
            Tuple of (golden_cross, death_cross)
            golden_cross: True if bullish crossover confirmed
            death_cross: True if bearish crossover confirmed
        """
        # Need enough candles: before crossover + crossover candle + confirmation candles
        required_length = confirmation_candles + 2
        if len(short_ma) < required_length or len(long_ma) < required_length:
            return False, False
        
        # Check if crossover happened N candles ago
        # Example with confirmation_candles=1:
        # - Index -(1+1+1) = -3: before crossover
        # - Index -(1+1) = -2: crossover candle
        # - Index -1 to current: confirmation candles
        
        crossover_candle_idx = -(confirmation_candles + 1)
        before_crossover_idx = -(confirmation_candles + 2)
        
        # Values before and at crossover
        short_before = short_ma[before_crossover_idx]
        long_before = long_ma[before_crossover_idx]
        short_at_cross = short_ma[crossover_candle_idx]
        long_at_cross = long_ma[crossover_candle_idx]
        
        # Golden Cross: Short MA crosses above Long MA
        # Before: short <= long, At crossover: short > long
        golden_cross = (short_before <= long_before) and (short_at_cross > long_at_cross)
        
        # Death Cross: Short MA crosses below Long MA  
        # Before: short >= long, At crossover: short < long
        death_cross = (short_before >= long_before) and (short_at_cross < long_at_cross)
        
        # Confirm the crossover is sustained through all confirmation candles
        if golden_cross or death_cross:
            for i in range(1, confirmation_candles + 1):
                short_confirm = short_ma[-i]
                long_confirm = long_ma[-i]
                
                # For golden cross, short must stay above long
                if golden_cross and short_confirm <= long_confirm:
                    logger.debug(f"Golden cross not confirmed: at candle -{i}, short ({short_confirm:.2f}) <= long ({long_confirm:.2f})")
                    golden_cross = False
                    break
                
                # For death cross, short must stay below long
                if death_cross and short_confirm >= long_confirm:
                    logger.debug(f"Death cross not confirmed: at candle -{i}, short ({short_confirm:.2f}) >= long ({long_confirm:.2f})")
                    death_cross = False
                    break
        
        # Log confirmed signals
        if golden_cross:
            short_current = short_ma[-1]
            long_current = long_ma[-1]
            logger.info(f"✓ GOLDEN CROSS CONFIRMED! Crossover at candle {crossover_candle_idx}, confirmed over {confirmation_candles} candle(s). Short MA ({short_current:.2f}) > Long MA ({long_current:.2f})")
        if death_cross:
            short_current = short_ma[-1]
            long_current = long_ma[-1]
            logger.info(f"✓ DEATH CROSS CONFIRMED! Crossover at candle {crossover_candle_idx}, confirmed over {confirmation_candles} candle(s). Short MA ({short_current:.2f}) < Long MA ({long_current:.2f})")
        
        return golden_cross, death_cross
    
    @staticmethod
    def check_volume_confirmation(
        volumes: List[float],
        volume_lookback: int = 20,
        min_volume_ratio: float = 1.5
    ) -> bool:
        """
        Check if current volume is significantly higher than average
        Strong signals typically have volume support
        
        Args:
            volumes: List of volume values
            volume_lookback: Period to calculate average volume (default: 20)
            min_volume_ratio: Minimum ratio of current/average volume (default: 1.5)
            
        Returns:
            True if volume confirms the signal
        """
        if len(volumes) < volume_lookback + 1:
            logger.warning(f"Insufficient volume data: need {volume_lookback + 1}, got {len(volumes)}")
            return False
        
        current_volume = volumes[-1]
        avg_volume = sum(volumes[-volume_lookback-1:-1]) / volume_lookback
        
        if avg_volume == 0:
            return False
        
        volume_ratio = current_volume / avg_volume
        confirmed = volume_ratio >= min_volume_ratio
        
        if confirmed:
            logger.info(f"✓ Volume confirmed: {volume_ratio:.2f}x average (current: {current_volume:.0f}, avg: {avg_volume:.0f})")
        else:
            logger.debug(f"✗ Volume too low: {volume_ratio:.2f}x average (need {min_volume_ratio}x)")
        
        return confirmed
    
    @staticmethod
    def check_price_action_confirmation(
        high_prices: List[float],
        low_prices: List[float],
        close_prices: List[float],
        signal_type: str
    ) -> bool:
        """
        Check if price action confirms the signal strength
        - BUY signal: Current close should break above previous high
        - SELL signal: Current close should break below previous low
        
        Args:
            high_prices: List of high prices
            low_prices: List of low prices
            close_prices: List of close prices
            signal_type: "buy" or "sell"
            
        Returns:
            True if price action confirms the signal
        """
        if len(close_prices) < 2 or len(high_prices) < 2 or len(low_prices) < 2:
            logger.warning("Insufficient price data for price action confirmation")
            return False
        
        current_close = close_prices[-1]
        prev_high = high_prices[-2]
        prev_low = low_prices[-2]
        
        if signal_type.lower() == "buy":
            confirmed = current_close > prev_high
            if confirmed:
                logger.info(f"✓ Price action confirmed BUY: Close ({current_close:.2f}) > Prev High ({prev_high:.2f})")
            else:
                logger.debug(f"✗ Price action weak for BUY: Close ({current_close:.2f}) <= Prev High ({prev_high:.2f})")
            return confirmed
            
        elif signal_type.lower() == "sell":
            confirmed = current_close < prev_low
            if confirmed:
                logger.info(f"✓ Price action confirmed SELL: Close ({current_close:.2f}) < Prev Low ({prev_low:.2f})")
            else:
                logger.debug(f"✗ Price action weak for SELL: Close ({current_close:.2f}) >= Prev Low ({prev_low:.2f})")
            return confirmed
        
        return False
    
    @staticmethod
    def detect_higher_timeframe_trend(
        close_prices: List[float],
        trend_sma_period: int = 50
    ) -> Optional[str]:
        """
        Detect the higher timeframe trend using a longer SMA
        
        Args:
            close_prices: List of close prices
            trend_sma_period: SMA period for trend detection (default: 50)
            
        Returns:
            "uptrend", "downtrend", or None
        """
        if len(close_prices) < trend_sma_period + 1:
            logger.warning(f"Insufficient data for trend detection: need {trend_sma_period + 1}, got {len(close_prices)}")
            return None
        
        trend_sma = TechnicalIndicators.sma(close_prices, trend_sma_period)
        if not trend_sma:
            return None
        
        current_price = close_prices[-1]
        current_trend_sma = trend_sma[-1]
        
        if current_price > current_trend_sma:
            logger.info(f"Higher timeframe trend: UPTREND (Price {current_price:.2f} > SMA{trend_sma_period} {current_trend_sma:.2f})")
            return "uptrend"
        elif current_price < current_trend_sma:
            logger.info(f"Higher timeframe trend: DOWNTREND (Price {current_price:.2f} < SMA{trend_sma_period} {current_trend_sma:.2f})")
            return "downtrend"
        else:
            logger.info("Higher timeframe trend: NEUTRAL")
            return None
    
    @staticmethod
    def check_rsi_confirmation(
        rsi_values: List[float],
        signal_type: str,
        oversold: float = 30.0,
        overbought: float = 70.0
    ) -> bool:
        """
        Check if RSI confirms the trading signal
        
        Args:
            rsi_values: List of RSI values
            signal_type: "buy" or "sell"
            oversold: RSI oversold threshold (default: 30)
            overbought: RSI overbought threshold (default: 70)
            
        Returns:
            True if RSI confirms the signal
        """
        if not rsi_values:
            logger.warning("No RSI values available for confirmation")
            return False
        
        current_rsi = rsi_values[-1]
        
        if signal_type == "buy":
            # For buy signal, RSI should not be overbought
            # Ideally in neutral or oversold zone
            confirmed = current_rsi < overbought
            if confirmed:
                logger.info(f"RSI confirms BUY signal: RSI={current_rsi:.2f} (not overbought)")
            else:
                logger.warning(f"RSI does NOT confirm BUY: RSI={current_rsi:.2f} (overbought)")
        
        elif signal_type == "sell":
            # For sell signal, RSI should not be oversold
            # Ideally in neutral or overbought zone
            confirmed = current_rsi > oversold
            if confirmed:
                logger.info(f"RSI confirms SELL signal: RSI={current_rsi:.2f} (not oversold)")
            else:
                logger.warning(f"RSI does NOT confirm SELL: RSI={current_rsi:.2f} (oversold)")
        
        else:
            logger.error(f"Invalid signal type: {signal_type}")
            return False
        
        return confirmed
    
    @staticmethod
    def calculate_indicators_from_candles(
        candles: List[dict],
        short_sma_period: int = 9,
        long_sma_period: int = 21,
        rsi_period: int = 14
    ) -> dict:
        """
        Calculate all indicators from candle data
        
        Args:
            candles: List of candle dictionaries with OHLCV data
            short_sma_period: Short SMA period (configurable)
            long_sma_period: Long SMA period (configurable)
            rsi_period: RSI period (configurable)
            
        Returns:
            Dictionary with calculated indicators including OHLCV data
        """
        if not candles:
            logger.error("No candle data provided")
            return {}
    # {'close':234,'high':24.4.'low':234,'open':243,'volume':234}
        # Extract OHLCV data
        close_prices = [float(candle['close']) for candle in candles]
        high_prices = [float(candle.get('high', candle['close'])) for candle in candles]
        low_prices = [float(candle.get('low', candle['close'])) for candle in candles]
        open_prices = [float(candle.get('open', candle['close'])) for candle in candles]
        volumes = [float(candle.get('volume', 0)) for candle in candles]
        
        # Calculate indicators
        short_sma = TechnicalIndicators.sma(close_prices, short_sma_period)
        long_sma = TechnicalIndicators.sma(close_prices, long_sma_period)
        rsi = TechnicalIndicators.rsi(close_prices, rsi_period)
        
        result = {
            'close_prices': close_prices,
            'high_prices': high_prices,
            'low_prices': low_prices,
            'open_prices': open_prices,
            'volumes': volumes,
            'short_sma': short_sma,
            'long_sma': long_sma,
            'rsi': rsi,
            'short_sma_period': short_sma_period,
            'long_sma_period': long_sma_period,
            'rsi_period': rsi_period
        }
        
        logger.info(f"Calculated indicators: SMA({short_sma_period}, {long_sma_period}), RSI({rsi_period})")
        
        return result
    
    @staticmethod
    def get_latest_values(indicators: dict) -> dict:
        """
        Get the latest values of all indicators
        
        Args:
            indicators: Dictionary of calculated indicators
            
        Returns:
            Dictionary with latest values
        """
        latest = {}
        
        if indicators.get('close_prices'):
            latest['price'] = indicators['close_prices'][-1]
        
        if indicators.get('short_sma'):
            latest['short_sma'] = indicators['short_sma'][-1]
        
        if indicators.get('long_sma'):
            latest['long_sma'] = indicators['long_sma'][-1]
        
        if indicators.get('rsi'):
            latest['rsi'] = indicators['rsi'][-1]
        
        return latest
