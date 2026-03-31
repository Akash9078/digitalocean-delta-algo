"""
Risk Management Module
Handles position sizing, stop-loss, and take-profit calculations
"""

import logging
from typing import Dict, Optional, Tuple


logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk Manager for trading bot
    
    Features:
    - Configurable position sizing (fixed or percentage-based)
    - Dynamic SL/TP calculation
    - Bracket order creation
    - Risk limits validation
    """
    
    def __init__(
        self,
        position_size_type: str = "fixed",
        fixed_size: int = 1,
        risk_percentage: float = 2.0,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 4.0,
        sl_order_type: str = "limit_order",
        tp_order_type: str = "limit_order",
        max_positions: int = 1,
        max_position_size: int = 10,
        max_daily_loss: float = 5.0,
        use_trailing_sl: bool = False,
        trail_amount: str = "50"
    ):
        """
        Initialize risk manager with configurable parameters
        
        Args:
            position_size_type: "fixed" or "percentage"
            fixed_size: Fixed position size in contracts
            risk_percentage: Risk per trade as percentage of balance
            stop_loss_pct: Stop loss percentage from entry
            take_profit_pct: Take profit percentage from entry
            sl_order_type: Stop loss order type
            tp_order_type: Take profit order type
            max_positions: Maximum number of open positions
            max_position_size: Maximum size per position
            max_daily_loss: Maximum daily loss percentage
            use_trailing_sl: Enable trailing stop loss
            trail_amount: Trailing stop amount
        """
        self.position_size_type = position_size_type
        self.fixed_size = fixed_size
        self.risk_percentage = risk_percentage
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.sl_order_type = sl_order_type
        self.tp_order_type = tp_order_type
        self.max_positions = max_positions
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.use_trailing_sl = use_trailing_sl
        self.trail_amount = trail_amount
        
        # Track daily metrics
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.starting_balance = 0.0
        
        logger.info(
            f"Risk Manager initialized: Size type={position_size_type}, "
            f"SL={stop_loss_pct}%, TP={take_profit_pct}%, "
            f"Max positions={max_positions}, Max daily loss={max_daily_loss}%"
        )
    
    def calculate_position_size(
        self,
        account_balance: float,
        current_price: float
    ) -> int:
        """
        Calculate position size based on risk parameters
        
        Args:
            account_balance: Available account balance
            current_price: Current market price
            
        Returns:
            Position size in contracts
        """
        if self.position_size_type == "fixed":
            size = self.fixed_size
            logger.debug(f"Using fixed position size: {size} contracts")
        
        elif self.position_size_type == "percentage":
            # Calculate position size based on risk percentage
            risk_amount = account_balance * (self.risk_percentage / 100)
            stop_loss_amount = current_price * (self.stop_loss_pct / 100)
            
            if stop_loss_amount > 0:
                size = int(risk_amount / stop_loss_amount)
            else:
                size = self.fixed_size
            
            logger.debug(
                f"Calculated position size: {size} contracts "
                f"(risk ${risk_amount:.2f}, SL distance ${stop_loss_amount:.2f})"
            )
        
        else:
            logger.warning(f"Invalid position size type: {self.position_size_type}, using fixed")
            size = self.fixed_size
        
        # Apply maximum position size limit
        if size > self.max_position_size:
            logger.warning(f"Position size {size} exceeds max {self.max_position_size}, limiting")
            size = self.max_position_size
        
        # Ensure minimum size of 1
        if size < 1:
            logger.warning("Calculated position size < 1, setting to 1")
            size = 1
        
        return size
    
    def calculate_sl_tp_prices(
        self,
        entry_price: float,
        side: str
    ) -> Tuple[str, str, str, str]:
        """
        Calculate stop loss and take profit prices
        
        Args:
            entry_price: Entry price
            side: "buy" or "sell"
            
        Returns:
            Tuple of (sl_trigger, sl_limit, tp_trigger, tp_limit) as strings
        """
        if side == "buy":
            # For long positions
            # Stop loss below entry price
            sl_trigger_price = entry_price * (1 - self.stop_loss_pct / 100)
            sl_limit_price = sl_trigger_price * 0.995  # Slightly below trigger
            
            # Take profit above entry price
            tp_trigger_price = entry_price * (1 + self.take_profit_pct / 100)
            tp_limit_price = tp_trigger_price * 0.995  # Slightly below trigger for execution
        
        elif side == "sell":
            # For short positions
            # Stop loss above entry price
            sl_trigger_price = entry_price * (1 + self.stop_loss_pct / 100)
            sl_limit_price = sl_trigger_price * 1.005  # Slightly above trigger
            
            # Take profit below entry price
            tp_trigger_price = entry_price * (1 - self.take_profit_pct / 100)
            tp_limit_price = tp_trigger_price * 1.005  # Slightly above trigger for execution
        
        else:
            raise ValueError(f"Invalid side: {side}")
        
        # Format prices with appropriate precision
        sl_trigger = f"{sl_trigger_price:.2f}"
        sl_limit = f"{sl_limit_price:.2f}"
        tp_trigger = f"{tp_trigger_price:.2f}"
        tp_limit = f"{tp_limit_price:.2f}"
        
        logger.info(
            f"Calculated SL/TP for {side.upper()} at ${entry_price:.2f}: "
            f"SL={sl_trigger} ({-self.stop_loss_pct}%), "
            f"TP={tp_trigger} (+{self.take_profit_pct}%)"
        )
        
        return sl_trigger, sl_limit, tp_trigger, tp_limit
    
    def create_bracket_order_params(
        self,
        entry_price: float,
        side: str
    ) -> Dict[str, str]:
        """
        Create bracket order parameters for API call
        
        Args:
            entry_price: Entry price
            side: "buy" or "sell"
            
        Returns:
            Dictionary with bracket order parameters
        """
        sl_trigger, sl_limit, tp_trigger, tp_limit = self.calculate_sl_tp_prices(
            entry_price, side
        )
        
        params = {
            'bracket_stop_loss_price': sl_trigger,
            'bracket_stop_loss_limit_price': sl_limit,
            'bracket_take_profit_price': tp_trigger,
            'bracket_take_profit_limit_price': tp_limit
        }
        
        # Add trailing stop loss if enabled
        if self.use_trailing_sl:
            params['bracket_trail_amount'] = self.trail_amount
            logger.info(f"Using trailing stop loss: {self.trail_amount}")
        
        return params
    
    def can_trade(
        self,
        current_positions: int,
        account_balance: float
    ) -> Tuple[bool, str]:
        """
        Check if trading is allowed based on risk limits
        
        Args:
            current_positions: Number of current open positions
            account_balance: Current account balance
            
        Returns:
            Tuple of (can_trade, reason)
        """
        # Check maximum positions
        if current_positions >= self.max_positions:
            return False, f"Maximum positions limit reached: {self.max_positions}"
        
        # Check daily loss limit
        if self.starting_balance > 0:
            daily_loss_pct = (self.daily_pnl / self.starting_balance) * 100
            
            if daily_loss_pct < -self.max_daily_loss:
                return False, f"Daily loss limit exceeded: {daily_loss_pct:.2f}% < -{self.max_daily_loss}%"
        
        # Check sufficient balance
        min_required_balance = 100.0  # Minimum balance threshold
        if account_balance < min_required_balance:
            return False, f"Insufficient balance: ${account_balance:.2f} < ${min_required_balance}"
        
        return True, "OK"
    
    def update_daily_pnl(self, pnl: float):
        """
        Update daily PnL tracking
        
        Args:
            pnl: Profit/Loss from closed trade
        """
        self.daily_pnl += pnl
        self.trades_today += 1
        
        logger.info(f"Daily PnL updated: ${self.daily_pnl:.2f} ({self.trades_today} trades)")
        
        # Check if daily loss limit reached
        if self.starting_balance > 0:
            daily_loss_pct = (self.daily_pnl / self.starting_balance) * 100
            if daily_loss_pct < -self.max_daily_loss:
                logger.critical(f"DAILY LOSS LIMIT REACHED: {daily_loss_pct:.2f}%")
    
    def reset_daily_metrics(self, starting_balance: float):
        """
        Reset daily metrics (call at start of new trading day)
        
        Args:
            starting_balance: Starting balance for the day
        """
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.starting_balance = starting_balance
        
        logger.info(f"Daily metrics reset - Starting balance: ${starting_balance:.2f}")
    
    def update_config(
        self,
        position_size_type: Optional[str] = None,
        fixed_size: Optional[int] = None,
        risk_percentage: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        max_positions: Optional[int] = None,
        max_position_size: Optional[int] = None,
        max_daily_loss: Optional[float] = None,
        use_trailing_sl: Optional[bool] = None,
        trail_amount: Optional[str] = None
    ):
        """
        Update risk management configuration dynamically
        
        Args:
            position_size_type: New position size type
            fixed_size: New fixed size
            risk_percentage: New risk percentage
            stop_loss_pct: New stop loss percentage
            take_profit_pct: New take profit percentage
            max_positions: New max positions
            max_position_size: New max position size
            max_daily_loss: New max daily loss
            use_trailing_sl: Enable/disable trailing SL
            trail_amount: New trail amount
        """
        if position_size_type is not None:
            self.position_size_type = position_size_type
            logger.info(f"Updated position size type to {position_size_type}")
        
        if fixed_size is not None:
            self.fixed_size = fixed_size
            logger.info(f"Updated fixed size to {fixed_size}")
        
        if risk_percentage is not None:
            self.risk_percentage = risk_percentage
            logger.info(f"Updated risk percentage to {risk_percentage}%")
        
        if stop_loss_pct is not None:
            self.stop_loss_pct = stop_loss_pct
            logger.info(f"Updated stop loss to {stop_loss_pct}%")
        
        if take_profit_pct is not None:
            self.take_profit_pct = take_profit_pct
            logger.info(f"Updated take profit to {take_profit_pct}%")
        
        if max_positions is not None:
            self.max_positions = max_positions
            logger.info(f"Updated max positions to {max_positions}")
        
        if max_position_size is not None:
            self.max_position_size = max_position_size
            logger.info(f"Updated max position size to {max_position_size}")
        
        if max_daily_loss is not None:
            self.max_daily_loss = max_daily_loss
            logger.info(f"Updated max daily loss to {max_daily_loss}%")
        
        if use_trailing_sl is not None:
            self.use_trailing_sl = use_trailing_sl
            logger.info(f"Updated use_trailing_sl to {use_trailing_sl}")
        
        if trail_amount is not None:
            self.trail_amount = trail_amount
            logger.info(f"Updated trail amount to {trail_amount}")
