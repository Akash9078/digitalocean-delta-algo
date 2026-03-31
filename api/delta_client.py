"""
Delta Exchange API Client
Handles all API interactions with Delta Exchange India

Fixes applied (2026-03-31):
- POST/PUT/DELETE payload in HMAC signature now uses json.dumps() to match
  the actual request body, preventing signature mismatch errors.
- Query string in signature uses urllib.parse.urlencode for consistency.
"""

import hmac
import hashlib
import json
import time
import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode


logger = logging.getLogger(__name__)


class DeltaExchangeClient:
    """
    Delta Exchange API Client for trading operations
    
    Features:
    - HMAC-SHA256 authentication
    - Market data fetching (OHLC candles, tickers)
    - Order placement with bracket orders (TP/SL)
    - Position management
    - Error handling and retries
    """
    
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.india.delta.exchange"):
        """
        Initialize Delta Exchange API client
        
        Args:
            api_key: API key from Delta Exchange
            api_secret: API secret from Delta Exchange
            base_url: Base URL for API endpoints
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.session = requests.Session()
        
        logger.info(f"Initialized Delta Exchange client for {base_url}")
    
    def generate_signature(self, message: str) -> str:
        """
        Generate HMAC-SHA256 signature for authentication
        
        Args:
            message: Message to sign (METHOD + TIMESTAMP + PATH + QUERY_STRING + PAYLOAD)
            
        Returns:
            Hex-encoded signature
        """
        message_bytes = bytes(message, 'utf-8')
        secret_bytes = bytes(self.api_secret, 'utf-8')
        hash_obj = hmac.new(secret_bytes, message_bytes, hashlib.sha256)
        return hash_obj.hexdigest()
    
    def make_request(
        self, 
        method: str, 
        path: str, 
        params: Optional[Dict] = None, 
        data: Optional[Dict] = None,
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """
        Make authenticated HTTP request to Delta Exchange API
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API endpoint path
            params: Query parameters
            data: Request body data
            retry_count: Number of retry attempts
            
        Returns:
            API response as dictionary
        """
        url = f"{self.base_url}{path}"
        
        # Prepare request parameters
        timestamp = str(int(time.time()))
        # Query string must be consistent with what requests will actually send
        query_string = ('?' + urlencode(params)) if params else ''
        # CRITICAL FIX: payload in signature must match the actual request body.
        # str(dict) uses single quotes and Python booleans – NOT valid JSON.
        # json.dumps() matches the body sent via requests' json= kwarg.
        payload = '' if data is None else json.dumps(data, separators=(',', ':'))
        
        # Generate signature
        signature_data = method + timestamp + path + query_string + payload
        signature = self.generate_signature(signature_data)
        
        # Prepare headers
        headers = {
            'api-key': self.api_key,
            'timestamp': timestamp,
            'signature': signature,
            'Content-Type': 'application/json',
            'User-Agent': 'python-trading-bot/1.0'
        }
        
        # Make request with retries
        for attempt in range(retry_count):
            try:
                logger.debug(f"{method} {url} (attempt {attempt + 1}/{retry_count})")
                
                if method == 'GET':
                    response = self.session.get(url, params=params, headers=headers, timeout=(5, 30))
                elif method == 'POST':
                    response = self.session.post(url, json=data, headers=headers, timeout=(5, 30))
                elif method == 'PUT':
                    response = self.session.put(url, json=data, headers=headers, timeout=(5, 30))
                elif method == 'DELETE':
                    response = self.session.delete(url, json=data, headers=headers, timeout=(5, 30))
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                result = response.json()
                
                if result.get('success'):
                    return result
                else:
                    error = result.get('error', {})
                    logger.error(f"API error: {error}")
                    return {'success': False, 'error': error}
                
            except requests.exceptions.HTTPError as e:
                body = response.json() if response.content else response.text
                logger.error(f"HTTP error: {e} - Status: {response.status_code} - Body: {body}")
                
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    return {'success': False, 'error': str(e), 'status_code': response.status_code}
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    return {'success': False, 'error': str(e)}
    
    # ========== Market Data Methods ==========
    
    def get_ohlc_candles(
        self, 
        symbol: str, 
        resolution: str = "5m", 
        lookback_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLC candle data
        
        Args:
            symbol: Trading symbol (e.g., BTCUSD)
            resolution: Candle resolution (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 1d)
            lookback_hours: Hours of historical data to fetch
            
        Returns:
            List of candle dictionaries with keys: time, open, high, low, close, volume
        """
        end_time = int(time.time())
        start_time = end_time - (lookback_hours * 3600)
        
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'start': start_time,
            'end': end_time
        }
        
        response = self.make_request('GET', '/v2/history/candles', params=params)
        
        if response.get('success'):
            candles = response.get('result', [])
            logger.info(f"Retrieved {len(candles)} candles for {symbol} ({resolution})")
            return candles
        else:
            logger.error(f"Failed to get candles: {response.get('error')}")
            return []
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get current ticker/price information
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Ticker data dictionary
        """
        response = self.make_request('GET', f'/v2/tickers/{symbol}')
        
        if response.get('success'):
            return response.get('result', {})
        else:
            logger.error(f"Failed to get ticker: {response.get('error')}")
            return {}
    
    def get_product(self, symbol: str) -> Dict[str, Any]:
        """
        Get product details
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Product information dictionary
        """
        response = self.make_request('GET', f'/v2/products/{symbol}')
        
        if response.get('success'):
            return response.get('result', {})
        else:
            logger.error(f"Failed to get product: {response.get('error')}")
            return {}
    
    # ========== Order Management Methods ==========
    
    def place_order(
        self,
        symbol: str,
        side: str,
        size: int,
        order_type: str = "market_order",
        limit_price: Optional[str] = None,
        bracket_stop_loss_price: Optional[str] = None,
        bracket_stop_loss_limit_price: Optional[str] = None,
        bracket_take_profit_price: Optional[str] = None,
        bracket_take_profit_limit_price: Optional[str] = None,
        bracket_stop_trigger_method: str = "last_traded_price",
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a new order with optional bracket orders (TP/SL)
        
        Args:
            symbol: Trading symbol (e.g., BTCUSD)
            side: Order side ("buy" or "sell")
            size: Order size in contracts
            order_type: "market_order" or "limit_order"
            limit_price: Limit price (required for limit orders)
            bracket_stop_loss_price: Stop loss trigger price
            bracket_stop_loss_limit_price: Stop loss limit price
            bracket_take_profit_price: Take profit trigger price
            bracket_take_profit_limit_price: Take profit limit price
            bracket_stop_trigger_method: Trigger method for bracket orders
            client_order_id: Custom order ID
            
        Returns:
            Order response dictionary
        """
        order_data = {
            'product_symbol': symbol,
            'side': side,
            'size': size,
            'order_type': order_type
        }
        
        if limit_price:
            order_data['limit_price'] = limit_price
        
        # Add bracket order parameters if provided
        if bracket_stop_loss_price:
            order_data['bracket_stop_loss_price'] = bracket_stop_loss_price
        if bracket_stop_loss_limit_price:
            order_data['bracket_stop_loss_limit_price'] = bracket_stop_loss_limit_price
        if bracket_take_profit_price:
            order_data['bracket_take_profit_price'] = bracket_take_profit_price
        if bracket_take_profit_limit_price:
            order_data['bracket_take_profit_limit_price'] = bracket_take_profit_limit_price
        if bracket_stop_loss_price or bracket_take_profit_price:
            order_data['bracket_stop_trigger_method'] = bracket_stop_trigger_method
        
        if client_order_id:
            order_data['client_order_id'] = client_order_id
        
        logger.info(f"Placing {side} order: {size} contracts of {symbol} ({order_type})")
        
        response = self.make_request('POST', '/v2/orders', data=order_data)
        
        if response.get('success'):
            order = response.get('result', {})
            logger.info(f"Order placed successfully: ID {order.get('id')}")
            return order
        else:
            logger.error(f"Failed to place order: {response.get('error')}")
            return response
    
    def cancel_order(self, order_id: int, product_symbol: str) -> Dict[str, Any]:
        """
        Cancel an existing order
        
        Args:
            order_id: Order ID to cancel
            product_symbol: Product symbol
            
        Returns:
            Cancellation response
        """
        data = {
            'id': order_id,
            'product_symbol': product_symbol
        }
        
        logger.info(f"Cancelling order {order_id}")
        response = self.make_request('DELETE', '/v2/orders', data=data)
        
        if response.get('success'):
            logger.info(f"Order {order_id} cancelled successfully")
        else:
            logger.error(f"Failed to cancel order: {response.get('error')}")
        
        return response
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get list of open orders
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of open orders
        """
        params = {'state': 'open'}
        if symbol:
            # Get product_id first
            product = self.get_product(symbol)
            if product:
                params['product_ids'] = str(product.get('id'))
        
        response = self.make_request('GET', '/v2/orders', params=params)
        
        if response.get('success'):
            orders = response.get('result', [])
            logger.info(f"Retrieved {len(orders)} open orders")
            return orders
        else:
            logger.error(f"Failed to get open orders: {response.get('error')}")
            return []
    
    # ========== Position Management Methods ==========
    
    def get_position(self, symbol: str) -> Dict[str, Any]:
        """
        Get current position for a symbol (real-time data)
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position data with size and entry_price
        """
        product = self.get_product(symbol)
        if not product:
            return {}
        
        product_id = product.get('id')
        params = {'product_id': product_id}
        
        response = self.make_request('GET', '/v2/positions', params=params)
        
        if response.get('success'):
            position = response.get('result', {})
            logger.debug(f"Position for {symbol}: size={position.get('size', 0)}")
            return position
        else:
            logger.error(f"Failed to get position: {response.get('error')}")
            return {}
    
    def get_margined_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get margined positions (includes margin details but may have delay)
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of positions with full margin details
        """
        params = {}
        if symbol:
            product = self.get_product(symbol)
            if product:
                params['product_ids'] = str(product.get('id'))
        
        response = self.make_request('GET', '/v2/positions/margined', params=params)
        
        if response.get('success'):
            positions = response.get('result', [])
            logger.info(f"Retrieved {len(positions)} margined positions")
            return positions
        else:
            logger.error(f"Failed to get margined positions: {response.get('error')}")
            return []
    
    # ========== Wallet Methods ==========
    
    def get_wallet_balances(self) -> List[Dict[str, Any]]:
        """
        Get wallet balances for all assets
        
        Returns:
            List of wallet balances
        """
        response = self.make_request('GET', '/v2/wallet/balances')
        
        if response.get('success'):
            balances = response.get('result', [])
            meta = response.get('meta', {})
            logger.info(f"Retrieved wallet balances - Net Equity: {meta.get('net_equity')}")
            return balances
        else:
            logger.error(f"Failed to get wallet balances: {response.get('error')}")
            return []
    
    def get_balance_for_asset(self, asset_symbol: str = "USD") -> Dict[str, Any]:
        """
        Get balance for specific asset
        
        Args:
            asset_symbol: Asset symbol (default: USD)
            
        Returns:
            Balance information for the asset
        """
        balances = self.get_wallet_balances()
        
        for balance in balances:
            if balance.get('asset_symbol') == asset_symbol:
                return balance
        
        return {}

    # ========== Position Close Methods ==========
    
    def close_position(self, symbol: str, size: Optional[int] = None) -> Dict[str, Any]:
        """
        Close a specific position by placing an opposite market order with reduce_only
        
        Args:
            symbol: Trading symbol (e.g., BTCUSD)
            size: Size to close (if None, closes full position)
            
        Returns:
            Order response dictionary
        """
        # Get current position first
        position = self.get_position(symbol)
        
        if not position:
            logger.warning(f"No position found for {symbol}")
            return {'success': False, 'error': 'No position found'}
        
        current_size = int(position.get('size', 0))
        
        if current_size == 0:
            logger.warning(f"No open position for {symbol}")
            return {'success': False, 'error': 'No open position'}
        
        # Determine close size and side
        close_size = abs(size) if size else abs(current_size)
        close_side = 'sell' if current_size > 0 else 'buy'  # Opposite of position
        
        # Place reduce-only market order
        order_data = {
            'product_symbol': symbol,
            'side': close_side,
            'size': close_size,
            'order_type': 'market_order',
            'time_in_force': 'ioc',  # Immediate or cancel
            'reduce_only': True
        }
        
        logger.info(f"Closing position: {close_side} {close_size} contracts of {symbol}")
        
        response = self.make_request('POST', '/v2/orders', data=order_data)
        
        if response.get('success'):
            order = response.get('result', {})
            logger.info(f"Position close order placed: ID {order.get('id')}")
            return {'success': True, 'order': order}
        else:
            logger.error(f"Failed to close position: {response.get('error')}")
            return response
    
    def close_all_positions(self) -> Dict[str, Any]:
        """
        Close all open positions using Delta's close_all endpoint
        
        Returns:
            Response dictionary with close results
        """
        data = {
            'close_all_portfolio': True,
            'close_all_isolated': True
        }
        
        logger.info("Closing all positions")
        
        response = self.make_request('POST', '/v2/positions/close_all', data=data)
        
        if response.get('success'):
            logger.info("All positions closed successfully")
            return {'success': True, 'result': response.get('result', {})}
        else:
            logger.error(f"Failed to close all positions: {response.get('error')}")
            return response
