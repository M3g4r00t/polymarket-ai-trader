"""
Polymarket API Client Wrapper

Handles authentication and all API interactions with Polymarket's CLOB API.
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

import aiohttp
from pydantic import BaseModel

# Conditional import for py-clob-client
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, OrderType, OpenOrderParams
    from py_clob_client.order_builder.constants import BUY, SELL
    POLYMARKET_SDK = True
except ImportError:
    POLYMARKET_SDK = False
    ClobClient = None

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    LIVE = "LIVE"
    MATCHED = "MATCHED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


@dataclass
class Market:
    """Represents a Polymarket market"""
    condition_id: str
    question: str
    description: str
    category: str
    end_date: Optional[str]
    tokens: Dict[str, str]  # {"YES": token_id, "NO": token_id}
    prices: Dict[str, float]  # {"YES": 0.54, "NO": 0.43}
    liquidity: float
    active: bool


@dataclass
class OrderBook:
    """Order book for a token"""
    token_id: str
    bids: List[tuple]  # [(price, size), ...]
    asks: List[tuple]  # [(price, size), ...]
    midpoint: float
    spread: float
    timestamp: float


@dataclass
class Position:
    """Open position"""
    token_id: str
    market_question: str
    side: OrderSide
    size: float
    entry_price: float
    current_price: float
    pnl: float
    stop_loss: Optional[float]
    take_profit: Optional[float]


@dataclass
class Trade:
    """Executed trade"""
    trade_id: str
    market_id: str
    token_id: str
    side: OrderSide
    size: float
    price: float
    timestamp: float
    status: OrderStatus
    pnl: Optional[float] = None


class PolymarketClient:
    """
    Wrapper for Polymarket API interactions.
    
    Handles:
    - Authentication (L1/L2)
    - Market data fetching
    - Order management
    - Position tracking
    """
    
    CLOB_API = "https://clob.polymarket.com"
    GAMMA_API = "https://gamma-api.polymarket.com"
    DATA_API = "https://data-api.polymarket.com"
    CHAIN_ID = 137  # Polygon mainnet
    
    def __init__(
        self,
        private_key: Optional[str] = None,
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        funder_address: Optional[str] = None,
        signature_type: int = 0,  # 0=EOA, 1=Magic/Email, 2=Browser proxy
        dry_run: bool = False
    ):
        self.private_key = private_key
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.funder_address = funder_address
        self.signature_type = signature_type
        self.dry_run = dry_run
        
        self._client: Optional[ClobClient] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Cache
        self._markets_cache: Dict[str, Market] = {}
        self._positions: Dict[str, Position] = {}
        
    async def initialize(self):
        """Initialize the client and establish connection"""
        if POLYMARKET_SDK and self.private_key:
            self._client = ClobClient(
                host=self.CLOB_API,
                chain_id=self.CHAIN_ID,
                key=self.private_key,
                signature_type=self.signature_type,
                funder=self.funder_address
            )
            # Create or derive API credentials
            creds = self._client.create_or_derive_api_creds()
            self._client.set_api_creds(creds)
            logger.info("Polymarket client initialized with authentication")
        else:
            logger.warning("Running in read-only mode (no private key or SDK not installed)")
        
        self._session = aiohttp.ClientSession()
        
    async def close(self):
        """Close connections"""
        if self._session:
            await self._session.close()
            
    async def get_markets(
        self,
        category: Optional[str] = None,
        active_only: bool = True,
        min_liquidity: float = 1000.0,
        limit: int = 100
    ) -> List[Market]:
        """
        Fetch available markets from Gamma API.
        
        Args:
            category: Filter by category (Politics, Crypto, Sports, etc.)
            active_only: Only return active markets
            min_liquidity: Minimum liquidity in USD
            limit: Maximum number of markets to return
            
        Returns:
            List of Market objects
        """
        markets = []
        
        if self._client and POLYMARKET_SDK:
            try:
                # Use SDK if available
                simplified = self._client.get_simplified_markets()
                raw_markets = simplified.get("data", [])
            except Exception as e:
                logger.error(f"Error fetching markets via SDK: {e}")
                raw_markets = []
        else:
            # Fallback to HTTP
            async with self._session.get(
                f"{self.GAMMA_API}/markets",
                params={"active": active_only, "limit": limit}
            ) as resp:
                if resp.status == 200:
                    raw_markets = await resp.json()
                else:
                    logger.error(f"Failed to fetch markets: {resp.status}")
                    raw_markets = []
        
        # Parse markets
        for m in raw_markets[:limit]:
            try:
                # Extract token IDs
                tokens = {}
                prices = {}
                
                outcomes = m.get("outcomes", [])
                outcome_prices = m.get("outcome_prices", [])
                
                for i, outcome in enumerate(outcomes):
                    token_name = outcome.get("outcome", "UNKNOWN")
                    token_id = outcome.get("token_id", "")
                    tokens[token_name.upper()] = token_id
                    
                    # Parse price
                    if i < len(outcome_prices):
                        try:
                            prices[token_name.upper()] = float(outcome_prices[i])
                        except (ValueError, TypeError):
                            prices[token_name.upper()] = 0.0
                
                # Calculate liquidity
                liquidity = float(m.get("liquidity", 0) or 0)
                
                # Skip if below minimum liquidity
                if liquidity < min_liquidity:
                    continue
                    
                market = Market(
                    condition_id=m.get("condition_id", ""),
                    question=m.get("question", ""),
                    description=m.get("description", ""),
                    category=m.get("category", "Unknown"),
                    end_date=m.get("end_date"),
                    tokens=tokens,
                    prices=prices,
                    liquidity=liquidity,
                    active=m.get("active", True)
                )
                
                # Cache
                self._markets_cache[market.condition_id] = market
                
                # Filter by category
                if category and market.category != category:
                    continue
                    
                markets.append(market)
                
            except Exception as e:
                logger.debug(f"Error parsing market: {e}")
                continue
        
        logger.info(f"Fetched {len(markets)} markets")
        return markets
    
    async def get_order_book(self, token_id: str) -> OrderBook:
        """
        Fetch order book for a token.
        
        Args:
            token_id: The token ID (YES or NO token)
            
        Returns:
            OrderBook object with bids, asks, midpoint, spread
        """
        if self._client and POLYMARKET_SDK:
            book = self._client.get_order_book(token_id)
            midpoint = self._client.get_midpoint(token_id)
            
            bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", [])]
            asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", [])]
            
            # Calculate spread
            if bids and asks:
                best_bid = max(b[0] for b in bids)
                best_ask = min(a[0] for a in asks)
                spread = best_ask - best_bid
            else:
                spread = 0.0
            
            return OrderBook(
                token_id=token_id,
                bids=bids,
                asks=asks,
                midpoint=midpoint,
                spread=spread,
                timestamp=asyncio.get_event_loop().time()
            )
        else:
            # HTTP fallback
            async with self._session.get(
                f"{self.CLOB_API}/book",
                params={"token_id": token_id}
            ) as resp:
                data = await resp.json()
                # Parse similarly
                bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
                asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]
                
                if bids and asks:
                    best_bid = max(b[0] for b in bids)
                    best_ask = min(a[0] for a in asks)
                    midpoint = (best_bid + best_ask) / 2
                    spread = best_ask - best_bid
                else:
                    midpoint = 0.5
                    spread = 0.0
                
                return OrderBook(
                    token_id=token_id,
                    bids=bids,
                    asks=asks,
                    midpoint=midpoint,
                    spread=spread,
                    timestamp=asyncio.get_event_loop().time()
                )
    
    async def place_limit_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
        order_type: str = "GTC",
        dry_run: bool = False
    ) -> Optional[Dict]:
        """
        Place a limit order.
        
        Args:
            token_id: Token to trade
            side: BUY or SELL
            price: Limit price (0.01 - 0.99)
            size: Size in USD
            order_type: GTC, GTD, FOK, FAK
            dry_run: If True, don't actually place the order
            
        Returns:
            Order confirmation or None if failed
        """
        if self.dry_run or dry_run:
            logger.info(f"[DRY RUN] Would place {side.value} order: {size} @ {price} for token {token_id}")
            return {
                "id": "dry_run",
                "token_id": token_id,
                "side": side.value,
                "price": price,
                "size": size,
                "status": "LIVE"
            }
        
        if not self._client:
            logger.error("Cannot place order: client not authenticated")
            return None
        
        if not POLYMARKET_SDK:
            logger.error("Cannot place order: SDK not installed")
            return None
        
        try:
            side_const = BUY if side == OrderSide.BUY else SELL
            order_type_enum = getattr(OrderType, order_type.upper(), OrderType.GTC)
            
            order = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=side_const
            )
            
            signed_order = self._client.create_order(order)
            response = self._client.post_order(signed_order, order_type_enum)
            
            logger.info(f"Placed order: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would cancel order {order_id}")
            return True
            
        if not self._client:
            return False
            
        try:
            self._client.cancel(order_id)
            logger.info(f"Cancelled order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    async def cancel_all_orders(self) -> int:
        """Cancel all open orders, return count cancelled"""
        if self.dry_run:
            logger.info("[DRY RUN] Would cancel all orders")
            return 0
            
        if not self._client:
            return 0
            
        try:
            self._client.cancel_all()
            logger.info("Cancelled all orders")
            return 1
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return 0
    
    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        if not self._client:
            return []
            
        try:
            orders = self._client.get_orders(OpenOrderParams())
            return orders
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return []
    
    async def get_positions(self) -> List[Dict]:
        """Get current positions"""
        if not self._client:
            return []
            
        try:
            # Use Data API for positions
            async with self._session.get(
                f"{self.DATA_API}/positions",
                params={"user": self._client.address}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    async def get_server_time(self) -> float:
        """Get server timestamp"""
        if self._client and POLYMARKET_SDK:
            return self._client.get_server_time()
        
        async with self._session.get(f"{self.CLOB_API}/time") as resp:
            data = await resp.json()
            return data.get("timestamp", 0)