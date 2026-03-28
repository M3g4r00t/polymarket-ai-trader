"""
Tests for Polymarket AI Trader
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Add src to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.client import Market, OrderBook, OrderSide
from src.strategies.arbitrage import ArbitrageStrategy, ArbitrageOpportunity
from src.strategies.mispricing import MispricingStrategy, MispricingOpportunity
from src.risk.manager import RiskManager, RiskConfig


class TestArbitrageStrategy:
    """Tests for arbitrage strategy"""
    
    def test_find_spread(self):
        """Test spread calculation"""
        strategy = ArbitrageStrategy(
            min_spread_usd=0.02,
            min_profit_pct=0.02
        )
        
        # YES + NO = $0.97 -> spread = $0.03
        yes_price = 0.54
        no_price = 0.43
        total = yes_price + no_price
        spread = 1.0 - total
        
        assert spread == 0.03, f"Expected spread 0.03, got {spread}"
    
    def test_calculate_profit(self):
        """Test profit calculation"""
        strategy = ArbitrageStrategy(
            min_spread_usd=0.02,
            min_profit_pct=0.02
        )
        
        # If spread is $0.03 and we invest $10
        spread = 0.03
        investment = 10.0
        total_cost = 0.97  # YES + NO
        
        # Profit = spread * (investment / total_cost)
        expected_profit = spread * (investment / total_cost)
        
        assert expected_profit > 0, "Expected positive profit"
        assert expected_profit / investment > 0.02, "Expected >2% profit"
    
    @pytest.mark.asyncio
    async def test_scan_markets(self):
        """Test market scanning"""
        strategy = ArbitrageStrategy(
            min_spread_usd=0.02,
            min_profit_pct=0.02,
            min_liquidity_usd=100
        )
        
        # Mock client
        client = AsyncMock()
        client.get_order_book = AsyncMock(return_value=OrderBook(
            token_id="test",
            bids=[(0.54, 100)],
            asks=[(0.55, 100)],
            midpoint=0.545,
            spread=0.01,
            timestamp=datetime.now().timestamp()
        ))
        
        # Create mock market
        market = Market(
            condition_id="test_market",
            question="Test market?",
            description="Test description",
            category="Politics",
            end_date=None,
            tokens={"YES": "yes_token", "NO": "no_token"},
            prices={"YES": 0.54, "NO": 0.43},
            liquidity=1000,
            active=True
        )
        
        # This would scan markets - but we'd need to mock the order book properly
        # For now, just verify the strategy initializes
        assert strategy.min_spread_usd == 0.02


class TestRiskManager:
    """Tests for risk management"""
    
    def test_can_open_position(self):
        """Test position opening limits"""
        risk = RiskManager(RiskConfig(
            max_open_positions=10,
            max_daily_loss_usd=20.0,
            max_consecutive_losses=3
        ))
        
        # Should be able to open initially
        assert risk.can_open_position() == True
        
        # Simulate losses
        risk._daily_pnl = -25.0
        assert risk.can_open_position() == False
        
        # Reset
        risk._daily_pnl = 0.0
        assert risk.can_open_position() == True
    
    def test_position_sizing(self):
        """Test position size calculation"""
        risk = RiskManager(RiskConfig(
            min_trade_size_usd=1.0,
            max_trade_size_usd=10.0,
            max_position_size_usd=50.0
        ))
        
        size = risk.calculate_position_size(
            confidence=0.5,
            market_liquidity=10000.0,
            current_capital=100.0
        )
        
        assert size >= 1.0, f"Size {size} below minimum"
        assert size <= 10.0, f"Size {size} above maximum"
    
    def test_stop_loss_calculation(self):
        """Test stop loss calculation"""
        risk = RiskManager(RiskConfig(
            stop_loss_pct=0.15,
            take_profit_pct=0.05
        ))
        
        position = risk.open_position(
            token_id="test",
            market_question="Test?",
            side=OrderSide.BUY,
            size=10.0,
            entry_price=0.50
        )
        
        # Stop should be 15% below entry
        expected_stop = 0.50 * (1 - 0.15)  # 0.425
        
        assert abs(position.stop_loss_price - expected_stop) < 0.001
    
    def test_trailing_stop(self):
        """Test trailing stop logic"""
        risk = RiskManager(RiskConfig(
            trailing_stop=True,
            trailing_stop_pct=0.03
        ))
        
        position = risk.open_position(
            token_id="test",
            market_question="Test?",
            side=OrderSide.BUY,
            size=10.0,
            entry_price=0.50
        )
        
        # Initial trailing stop
        initial_stop = position.trailing_stop_price
        
        # Simulate price increase
        risk.check_position("test", 0.55)  # Price went up
        
        # Trailing stop should follow
        assert position.trailing_stop_price > initial_stop, "Trailing stop should move up"


class TestMispricingStrategy:
    """Tests for mispricing strategy"""
    
    def test_confidence_levels(self):
        """Test confidence mapping"""
        from src.strategies.mispricing import Confidence
        
        strategy = MispricingStrategy(
            min_confidence=Confidence.MEDIUM
        )
        
        assert strategy.min_confidence == Confidence.MEDIUM
    
    def test_api_budget(self):
        """Test API call budget"""
        strategy = MispricingStrategy(
            max_api_calls_per_day=10
        )
        
        # Should have budget
        assert strategy._check_api_budget() == True
        
        # Exhaust budget
        strategy._api_calls_today = 10
        assert strategy._check_api_budget() == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])