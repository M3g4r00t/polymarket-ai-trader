"""
Arbitrage Strategy

Detects and exploits price inefficiencies in binary prediction markets.

Key insight: In binary markets, YES + NO should always equal $1.00.
When they don't, there's an arbitrage opportunity.
"""

import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from ..client import Market, OrderBook, OrderSide

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents an arbitrage opportunity"""
    market: Market
    yes_price: float
    no_price: float
    spread: float  # 1.0 - (yes_price + no_price)
    profit_pct: float
    liquidity: float
    timestamp: datetime
    
    def __str__(self):
        return (
            f"ArbitrageOpportunity(market='{self.market.question[:50]}...', "
            f"YES={self.yes_price:.3f}, NO={self.no_price:.3f}, "
            f"spread={self.spread:.3f}, profit={self.profit_pct:.1%})"
        )


class ArbitrageStrategy:
    """
    Market Rebalancing Arbitrage Strategy
    
    Exploits price inefficiencies where YES + NO != $1.00
    
    Examples:
        YES = $0.54, NO = $0.43
        Sum = $0.97, Spread = $0.03
        
        Strategy: Buy both YES and NO for $0.97
        Guaranteed profit: $1.00 - $0.97 = $0.03 (3.1%)
        
    Risk: Very low (essentially risk-free if positions held to resolution)
    """
    
    def __init__(
        self,
        min_spread_usd: float = 0.02,
        min_profit_pct: float = 0.02,
        min_liquidity_usd: float = 1000.0,
        max_trade_size_usd: float = 10.0,
        exclude_markets: List[str] = None
    ):
        """
        Initialize arbitrage strategy.
        
        Args:
            min_spread_usd: Minimum spread in USD to consider (default $0.02)
            min_profit_pct: Minimum profit percentage to execute (default 2%)
            min_liquidity_usd: Minimum market liquidity required (default $1000)
            max_trade_size_usd: Maximum size per trade (default $10)
            exclude_markets: List of market IDs/slugs to exclude
        """
        self.min_spread_usd = min_spread_usd
        self.min_profit_pct = min_profit_pct
        self.min_liquidity_usd = min_liquidity_usd
        self.max_trade_size_usd = max_trade_size_usd
        self.exclude_markets = exclude_markets or []
        
        # Track recent opportunities to avoid duplicates
        self._recent_opportunities: Dict[str, datetime] = {}
        self._opportunity_ttl_seconds = 300  # 5 minutes
        
    async def scan_markets(
        self,
        markets: List[Market],
        client
    ) -> List[ArbitrageOpportunity]:
        """
        Scan markets for arbitrage opportunities.
        
        Args:
            markets: List of markets to scan
            client: PolymarketClient instance for fetching prices
            
        Returns:
            List of profitable opportunities
        """
        opportunities = []
        
        for market in markets:
            # Skip excluded markets
            if market.condition_id in self.exclude_markets:
                continue
                
            # Skip if below minimum liquidity
            if market.liquidity < self.min_liquidity_usd:
                continue
            
            # Skip if we've seen this opportunity recently
            if market.condition_id in self._recent_opportunities:
                last_seen = self._recent_opportunities[market.condition_id]
                age = (datetime.now() - last_seen).total_seconds()
                if age < self._opportunity_ttl_seconds:
                    continue
            
            # Get both YES and NO tokens
            yes_token = market.tokens.get("YES")
            no_token = market.tokens.get("NO")
            
            if not yes_token or not no_token:
                continue
            
            try:
                # Fetch order books for both tokens
                yes_book = await client.get_order_book(yes_token)
                no_book = await client.get_order_book(no_token)
                
                # Calculate prices (use midpoints)
                yes_price = yes_book.midpoint if yes_book.midpoint else market.prices.get("YES", 0.5)
                no_price = no_book.midpoint if no_book.midpoint else market.prices.get("NO", 0.5)
                
                # Calculate spread
                total = yes_price + no_price
                spread = 1.0 - total  # How much below $1.00
                
                # Check if profitable
                if spread >= self.min_spread_usd:
                    profit_pct = spread / total
                    
                    if profit_pct >= self.min_profit_pct:
                        opp = ArbitrageOpportunity(
                            market=market,
                            yes_price=yes_price,
                            no_price=no_price,
                            spread=spread,
                            profit_pct=profit_pct,
                            liquidity=market.liquidity,
                            timestamp=datetime.now()
                        )
                        opportunities.append(opp)
                        logger.info(f"Found opportunity: {opp}")
                        
                        # Mark as seen
                        self._recent_opportunities[market.condition_id] = datetime.now()
                        
            except Exception as e:
                logger.debug(f"Error scanning market {market.condition_id}: {e}")
                continue
        
        # Clean up old opportunities from cache
        self._cleanup_cache()
        
        logger.info(f"Found {len(opportunities)} arbitrage opportunities")
        return opportunities
    
    def calculate_trade_size(
        self,
        opportunity: ArbitrageOpportunity,
        available_capital: float
    ) -> Tuple[float, float]:
        """
        Calculate optimal trade sizes for both sides.
        
        Args:
            opportunity: The arbitrage opportunity
            available_capital: Total capital available
            
        Returns:
            Tuple of (yes_size, no_size) in USD
        """
        # For arbitrage, we want to invest equally on both sides
        # Total investment = yes_size + no_size
        # Guaranteed payout = $1.00 per complete pair
        
        # Limit by available capital and max trade size
        max_investment = min(
            available_capital,
            self.max_trade_size_usd * 2,  # Both sides
            opportunity.liquidity * 0.01   # Max 1% of market liquidity
        )
        
        # Split between YES and NO based on prices
        total_price = opportunity.yes_price + opportunity.no_price
        
        # Invest proportionally
        yes_size = max_investment * (opportunity.yes_price / total_price)
        no_size = max_investment * (opportunity.no_price / total_price)
        
        # Round to reasonable sizes
        yes_size = round(yes_size, 2)
        no_size = round(no_size, 2)
        
        return yes_size, no_size
    
    async def execute(
        self,
        opportunity: ArbitrageOpportunity,
        client,
        dry_run: bool = False
    ) -> Dict:
        """
        Execute the arbitrage trade.
        
        Strategy:
        1. Buy YES at best available price
        2. Buy NO at best available price
        3. Hold until resolution for guaranteed profit
        
        Args:
            opportunity: The opportunity to execute
            client: PolymarketClient instance
            dry_run: If True, don't actually trade
            
        Returns:
            Execution result
        """
        yes_token = opportunity.market.tokens.get("YES")
        no_token = opportunity.market.tokens.get("NO")
        
        # Calculate trade sizes
        yes_size, no_size = self.calculate_trade_size(
            opportunity,
            available_capital=100.0  # TODO: Get from position manager
        )
        
        result = {
            "opportunity": str(opportunity),
            "yes_order": None,
            "no_order": None,
            "total_investment": yes_size + no_size,
            "expected_profit": opportunity.spread * (yes_size + no_size) / (opportunity.yes_price + opportunity.no_price),
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat()
        }
        
        # Place YES order (buy slightly above current price for immediate fill)
        yes_order = await client.place_limit_order(
            token_id=yes_token,
            side=OrderSide.BUY,
            price=opportunity.yes_price + 0.01,  # Slight premium for quick fill
            size=yes_size,
            order_type="GTC",
            dry_run=dry_run
        )
        result["yes_order"] = yes_order
        
        # Place NO order (buy slightly above current price for immediate fill)
        no_order = await client.place_limit_order(
            token_id=no_token,
            side=OrderSide.BUY,
            price=opportunity.no_price + 0.01,  # Slight premium for quick fill
            size=no_size,
            order_type="GTC",
            dry_run=dry_run
        )
        result["no_order"] = no_order
        
        if yes_order and no_order:
            logger.info(
                f"Executed arbitrage: invested ${yes_size + no_size:.2f}, "
                f"expected profit ${result['expected_profit']:.2f} ({opportunity.profit_pct:.1%})"
            )
        else:
            logger.warning("Arbitrage execution incomplete - check orders")
            
        return result
    
    def _cleanup_cache(self):
        """Remove expired opportunities from cache"""
        now = datetime.now()
        expired = [
            market_id
            for market_id, timestamp in self._recent_opportunities.items()
            if (now - timestamp).total_seconds() > self._opportunity_ttl_seconds
        ]
        for market_id in expired:
            del self._recent_opportunities[market_id]