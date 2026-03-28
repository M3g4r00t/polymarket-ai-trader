"""
Additional Trading Strategies for Polymarket

Based on research of profitable prediction market strategies.
"""

import asyncio
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..client import Market, OrderBook, OrderSide

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    ARBITRAGE = "arbitrage"
    MISPRICING = "mispricing"
    MARKET_MAKING = "market_making"
    SETTLEMENT_EDGE = "settlement_edge"
    WHALE_COPYING = "whale_copying"
    MOMENTUM = "momentum"


@dataclass
class Opportunity:
    """Base opportunity class"""
    strategy: StrategyType
    market: Market
    expected_profit_pct: float
    confidence: float
    metadata: Dict
    timestamp: datetime


# ============================================================
# STRATEGY 1: Market Making
# ============================================================

@dataclass
class MarketMakingOpportunity(Opportunity):
    """Market making opportunity"""
    spread: float  # Bid-ask spread
    liquidity_score: float
    volume_24h: float
    suggested_bid: float
    suggested_ask: float


class MarketMakingStrategy:
    """
    Market Making Strategy
    
    Provide liquidity by posting limit orders on both sides.
    Profit from the bid-ask spread.
    
    Advantages:
    - Consistent profits from spread
    - Lower risk than directional bets
    - Works in any market condition
    
    Risks:
    - Adverse selection (informed traders)
    - Inventory risk
    - Requires active management
    """
    
    def __init__(
        self,
        min_spread_pct: float = 0.02,  # Minimum 2% spread
        min_liquidity_usd: float = 5000,
        max_position_size: float = 50.0,
        target_spread_pct: float = 0.03,  # Target 3% spread
        inventory_limit: float = 0.3  # Max 30% of capital in one position
    ):
        self.min_spread_pct = min_spread_pct
        self.min_liquidity_usd = min_liquidity_usd
        self.max_position_size = max_position_size
        self.target_spread_pct = target_spread_pct
        self.inventory_limit = inventory_limit
        
        self._positions: Dict[str, float] = {}  # token_id -> size
    
    async def find_opportunities(
        self,
        markets: List[Market],
        client
    ) -> List[MarketMakingOpportunity]:
        """
        Find markets suitable for market making.
        
        Ideal markets:
        - High liquidity (tight spreads are better)
        - Low volatility
        - Clear resolution criteria
        - Active trading volume
        """
        opportunities = []
        
        for market in markets:
            # Check liquidity
            if market.liquidity < self.min_liquidity_usd:
                continue
            
            yes_token = market.tokens.get("YES")
            no_token = market.tokens.get("NO")
            
            if not yes_token or not no_token:
                continue
            
            try:
                # Get order books
                yes_book = await client.get_order_book(yes_token)
                
                # Calculate spread
                if not yes_book.bids or not yes_book.asks:
                    continue
                
                best_bid = max(b[0] for b in yes_book.bids)
                best_ask = min(a[0] for a in yes_book.asks)
                spread = best_ask - best_bid
                spread_pct = spread / yes_book.midpoint
                
                # Skip if spread too tight
                if spread_pct < self.min_spread_pct:
                    continue
                
                # Calculate our spread (slightly tighter than market)
                our_spread = spread * 0.8  # 20% tighter
                
                # Suggested prices
                suggested_bid = yes_book.midpoint - our_spread / 2
                suggested_ask = yes_book.midpoint + our_spread / 2
                
                # Clamp to valid range
                suggested_bid = max(0.01, min(0.99, suggested_bid))
                suggested_ask = max(0.01, min(0.99, suggested_ask))
                
                opportunity = MarketMakingOpportunity(
                    strategy=StrategyType.MARKET_MAKING,
                    market=market,
                    expected_profit_pct=our_spread / yes_book.midpoint,
                    confidence=0.7,  # Moderate confidence
                    metadata={
                        "spread": spread,
                        "spread_pct": spread_pct,
                        "midpoint": yes_book.midpoint
                    },
                    timestamp=datetime.now(),
                    spread=spread,
                    liquidity_score=market.liquidity / 10000,  # Normalize
                    volume_24h=market.liquidity,  # Approximation
                    suggested_bid=suggested_bid,
                    suggested_ask=suggested_ask
                )
                
                opportunities.append(opportunity)
                
            except Exception as e:
                logger.debug(f"Error analyzing market {market.condition_id}: {e}")
                continue
        
        logger.info(f"Found {len(opportunities)} market making opportunities")
        return opportunities
    
    def calculate_orders(
        self,
        opportunity: MarketMakingOpportunity,
        capital: float
    ) -> Dict:
        """
        Calculate optimal bid and ask orders.
        
        Returns size and prices for both sides.
        """
        # Position sizing based on spread
        # Wider spread = more profit but more risk
        spread_ratio = opportunity.spread / opportunity.spread_pct
        
        # Size inversely proportional to spread
        base_size = min(
            self.max_position_size,
            capital * self.inventory_limit
        )
        
        # Adjust for spread quality
        size_multiplier = 1.0 / (1.0 + spread_ratio)
        position_size = base_size * size_multiplier
        
        return {
            "bid": {
                "price": opportunity.suggested_bid,
                "size": position_size,
                "side": "BUY"
            },
            "ask": {
                "price": opportunity.suggested_ask,
                "size": position_size,
                "side": "SELL"
            },
            "expected_profit": position_size * opportunity.spread,
            "expected_profit_pct": opportunity.expected_profit_pct
        }


# ============================================================
# STRATEGY 2: Settlement Edge
# ============================================================

@dataclass
class SettlementOpportunity(Opportunity):
    """Settlement edge opportunity"""
    resolution_criteria: str
    ambiguity_score: float
    historical_precedent: Optional[str]
    recommended_position: str  # YES or NO


class SettlementEdgeStrategy:
    """
    Settlement Edge Strategy
    
    Exploit ambiguous resolution criteria.
    Some markets can resolve partially even if the "obvious" outcome didn't occur.
    
    Advantages:
    - Low competition
    - Based on understanding of rules, not probability
    - Can be very profitable
    
    Risks:
    - Requires deep understanding of market rules
    - May need to wait for resolution
    - Resolution may not go your way
    """
    
    # Known ambiguous resolution patterns
    AMBIGUITY_PATTERNS = {
        "by_end_of_year": "May resolve based on announcement, not completion",
        "before": "May have grace period or timezone ambiguity",
        "announce": "May resolve on announcement vs confirmation",
        "major": "Subjective threshold",
        "significant": "Vague criteria",
        "first": "May have multiple interpretations"
    }
    
    def __init__(
        self,
        min_ambiguity_score: float = 0.5,
        min_liquidity_usd: float = 1000
    ):
        self.min_ambiguity_score = min_ambiguity_score
        self.min_liquidity_usd = min_liquidity_usd
    
    async def find_opportunities(
        self,
        markets: List[Market],
        client
    ) -> List[SettlementOpportunity]:
        """
        Find markets with ambiguous resolution criteria.
        
        Look for:
        - Vague wording
        - Multiple interpretations possible
        - Historical precedents
        """
        opportunities = []
        
        for market in markets:
            if market.liquidity < self.min_liquidity_usd:
                continue
            
            # Analyze description for ambiguity
            ambiguity = self._analyze_ambiguity(
                market.question,
                market.description or ""
            )
            
            if ambiguity["score"] >= self.min_ambiguity_score:
                opportunity = SettlementOpportunity(
                    strategy=StrategyType.SETTLEMENT_EDGE,
                    market=market,
                    expected_profit_pct=ambiguity["potential_edge"],
                    confidence=ambiguity["confidence"],
                    metadata={
                        "ambiguities": ambiguity["ambiguities"],
                        "resolution_notes": ambiguity["resolution_notes"]
                    },
                    timestamp=datetime.now(),
                    resolution_criteria=market.description or "",
                    ambiguity_score=ambiguity["score"],
                    historical_precedent=ambiguity.get("precedent"),
                    recommended_position=ambiguity["recommended"]
                )
                
                opportunities.append(opportunity)
        
        logger.info(f"Found {len(opportunities)} settlement edge opportunities")
        return opportunities
    
    def _analyze_ambiguity(
        self,
        question: str,
        description: str
    ) -> Dict:
        """Analyze market for ambiguous resolution criteria"""
        text = (question + " " + description).lower()
        
        ambiguities = []
        score = 0.0
        
        # Check for known ambiguity patterns
        for pattern, issue in self.AMBIGUITY_PATTERNS.items():
            if pattern in text:
                ambiguities.append(f"{pattern}: {issue}")
                score += 0.2
        
        # Check for vague terms
        vague_terms = ["major", "significant", "substantial", "minor", "brief"]
        for term in vague_terms:
            if term in text:
                ambiguities.append(f"Vague term: '{term}'")
                score += 0.1
        
        # Determine recommended position
        recommended = "WAIT"  # Default: need more analysis
        if "before" in text and "end of" in text:
            recommended = "NO"  # Often resolve YES even if slightly late
        elif "announce" in text:
            recommended = "YES"  # Announcements often count
        
        return {
            "score": min(score, 1.0),
            "ambiguities": ambiguities,
            "resolution_notes": [],
            "potential_edge": min(score * 0.1, 0.2),
            "confidence": min(score + 0.3, 0.8),
            "recommended": recommended
        }


# ============================================================
# STRATEGY 3: Whale Copying
# ============================================================

@dataclass
class WhaleActivity:
    """Activity from a profitable trader"""
    wallet_address: str
    position: str  # YES or NO
    size: float
    price: float
    market: Market
    win_rate: float
    total_profit: float


@dataclass
class WhaleOpportunity(Opportunity):
    """Whale copying opportunity"""
    whale_address: str
    whale_win_rate: float
    whale_total_profit: float
    copy_position: str
    copy_size: float


class WhaleCopyingStrategy:
    """
    Whale Copying Strategy
    
    Follow profitable traders (whales/smart money).
    Polymarket is on-chain, so all trades are public.
    
    Advantages:
    - Leverage others' research
    - Can be very profitable
    - Simple to implement
    
    Risks:
    - Whales can be wrong
    - Front-running possible
    - Delay in copying may miss moves
    """
    
    def __init__(
        self,
        min_whale_win_rate: float = 0.6,
        min_whale_profit: float = 1000.0,
        max_copy_size: float = 10.0,
        copy_delay_seconds: float = 5.0
    ):
        self.min_whale_win_rate = min_whale_win_rate
        self.min_whale_profit = min_whale_profit
        self.max_copy_size = max_copy_size
        self.copy_delay_seconds = copy_delay_seconds
        
        # Cache of known whales
        self._whale_cache: Dict[str, Dict] = {}
    
    async def identify_whales(
        self,
        client
    ) -> List[Dict]:
        """
        Identify profitable traders to follow.
        
        This would require:
        1. Query blockchain for recent large trades
        2. Analyze win rate and profit
        3. Rank by profitability
        """
        # Placeholder: In production, this would query on-chain data
        # or use a service like PolymarketAnalytics
        
        logger.warning("Whale identification requires on-chain data access")
        return []
    
    async def find_opportunities(
        self,
        markets: List[Market],
        client
    ) -> List[WhaleOpportunity]:
        """
        Find opportunities from whale activity.
        """
        # This would require:
        # 1. Track whale wallets
        # 2. Monitor their trades in real-time
        # 3. Identify when they make new positions
        
        logger.warning("Whale copying requires real-time monitoring")
        return []
    
    def add_whale(self, address: str, stats: Dict):
        """Add a whale to follow"""
        self._whale_cache[address] = stats


# ============================================================
# STRATEGY 4: Momentum / News Scalping
# ============================================================

@dataclass
class MomentumOpportunity(Opportunity):
    """Momentum trading opportunity"""
    price_change_1h: float
    price_change_24h: float
    volume_change: float
    momentum_direction: str  # UP or DOWN
    news_sentiment: Optional[float]


class MomentumStrategy:
    """
    Momentum / News Scalping Strategy
    
    Trade based on price momentum and news events.
    Buy when strong upward momentum, sell on downward.
    
    Advantages:
    - Captures quick moves
        - News-driven markets very volatile
    - Can be automated with sentiment analysis
    
    Risks:
    - High volatility = high risk
    - News can reverse quickly
    - Needs fast execution
    """
    
    def __init__(
        self,
        min_momentum: float = 0.05,  # 5% price change
        max_momentum: float = 0.20,  # Avoid extreme moves
        min_volume_increase: float = 2.0,  # 2x normal volume
        holding_period_minutes: int = 30
    ):
        self.min_momentum = min_momentum
        self.max_momentum = max_momentum
        self.min_volume_increase = min_volume_increase
        self.holding_period_minutes = holding_period_minutes
        
        # Price history cache
        self._price_history: Dict[str, List[Dict]] = {}
    
    async def find_opportunities(
        self,
        markets: List[Market],
        client
    ) -> List[MomentumOpportunity]:
        """
        Find markets with strong momentum.
        """
        opportunities = []
        
        for market in markets:
            yes_token = market.tokens.get("YES")
            if not yes_token:
                continue
            
            try:
                # Get current price
                book = await client.get_order_book(yes_token)
                current_price = book.midpoint
                
                # Check for price history
                if yes_token not in self._price_history:
                    self._price_history[yes_token] = []
                
                # Record price
                self._price_history[yes_token].append({
                    "price": current_price,
                    "timestamp": datetime.now()
                })
                
                # Need at least 2 data points
                if len(self._price_history[yes_token]) < 2:
                    continue
                
                # Calculate momentum
                history = self._price_history[yes_token]
                price_change = abs(current_price - history[0]["price"]) / history[0]["price"]
                
                # Check momentum thresholds
                if price_change < self.min_momentum:
                    continue
                if price_change > self.max_momentum:
                    continue  # Too volatile
                
                # Determine direction
                direction = "UP" if current_price > history[0]["price"] else "DOWN"
                
                opportunity = MomentumOpportunity(
                    strategy=StrategyType.MOMENTUM,
                    market=market,
                    expected_profit_pct=price_change * 0.5,  # Capture half the move
                    confidence=0.6,
                    metadata={
                        "current_price": current_price,
                        "price_history": len(history)
                    },
                    timestamp=datetime.now(),
                    price_change_1h=price_change,
                    price_change_24h=price_change,  # Simplified
                    volume_change=1.0,  # Placeholder
                    momentum_direction=direction,
                    news_sentiment=None
                )
                
                opportunities.append(opportunity)
                
            except Exception as e:
                logger.debug(f"Error analyzing momentum for {market.condition_id}: {e}")
                continue
        
        logger.info(f"Found {len(opportunities)} momentum opportunities")
        return opportunities


# ============================================================
# STRATEGY REGISTRY
# ============================================================

STRATEGIES = {
    StrategyType.ARBITRAGE: "ArbitrageStrategy",
    StrategyType.MISPRICING: "MispricingStrategy",
    StrategyType.MARKET_MAKING: "MarketMakingStrategy",
    StrategyType.SETTLEMENT_EDGE: "SettlementEdgeStrategy",
    StrategyType.WHALE_COPYING: "WhaleCopyingStrategy",
    StrategyType.MOMENTUM: "MomentumStrategy"
}


def get_strategy(strategy_type: StrategyType):
    """Get strategy class by type"""
    strategy_map = {
        StrategyType.MARKET_MAKING: MarketMakingStrategy,
        StrategyType.SETTLEMENT_EDGE: SettlementEdgeStrategy,
        StrategyType.WHALE_COPYING: WhaleCopyingStrategy,
        StrategyType.MOMENTUM: MomentumStrategy
    }
    return strategy_map.get(strategy_type)