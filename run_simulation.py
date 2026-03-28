#!/usr/bin/env python3
"""
Simulation Runner - Test strategies without real money

Uses live market data from Polymarket but simulates all trades.
Tracks performance and provides detailed statistics.

Usage:
    python run_simulation.py --capital 100 --duration 60 --strategies arbitrage,mispricing
    python run_simulation.py --capital 50 --quick  # Quick 5-minute test
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
import json

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from src.client import PolymarketClient
from src.strategies.arbitrage import ArbitrageStrategy
from src.strategies.mispricing import MispricingStrategy
from src.simulation.engine import SimulationEngine
from src.risk.manager import RiskManager, RiskConfig
from src.utils.logger import setup_logging, TradeLogger

logger = logging.getLogger(__name__)


class SimulationRunner:
    """
    Runs paper trading simulation with live market data.
    """
    
    def __init__(
        self,
        starting_capital: float = 100.0,
        strategies: list = None,
        risk_config: RiskConfig = None,
        slippage: float = 0.001
    ):
        self.starting_capital = starting_capital
        self.strategies = strategies or ["arbitrage"]
        self.risk_config = risk_config or RiskConfig()
        
        # Initialize components
        self.client: PolymarketClient = None
        self.simulation = SimulationEngine(
            starting_capital=starting_capital,
            slippage_pct=slippage
        )
        self.trade_logger = TradeLogger()
        
        # Strategies
        self.arbitrage = None
        self.mispricing = None
        
        # Stats
        self.markets_scanned = 0
        self.opportunities_found = 0
        self.trades_executed = 0
        
    async def initialize(self):
        """Initialize client and strategies"""
        logger.info("Initializing simulation...")
        
        # Initialize client (read-only, no private key needed)
        self.client = PolymarketClient(dry_run=True)
        await self.client.initialize()
        
        # Initialize strategies
        if "arbitrage" in self.strategies:
            self.arbitrage = ArbitrageStrategy(
                min_spread_usd=0.01,  # Lower threshold for simulation
                min_profit_pct=0.01,  # 1% minimum
                min_liquidity_usd=500,  # Lower for more opportunities
                max_trade_size_usd=self.risk_config.max_trade_size_usd
            )
        
        if "mispricing" in self.strategies:
            self.mispricing = MispricingStrategy(
                use_ollama=True,
                min_deviation_pct=0.05,  # 5% deviation
                max_markets_per_cycle=3
            )
        
        logger.info(f"Simulation initialized with ${self.starting_capital:.2f}")
        logger.info(f"Strategies: {self.strategies}")
    
    async def run(
        self,
        duration_minutes: int = 60,
        poll_interval: int = 30,
        quick: bool = False
    ):
        """
        Run simulation for specified duration.
        
        Args:
            duration_minutes: How long to run simulation
            poll_interval: Seconds between market scans
            quick: If True, run quick 5-minute test
        """
        if quick:
            duration_minutes = 5
            poll_interval = 15
        
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        cycle = 0
        
        logger.info(f"Starting simulation for {duration_minutes} minutes")
        logger.info(f"Polling every {poll_interval} seconds")
        logger.info(f"Will end at {end_time.strftime('%H:%M:%S')}")
        print("\n" + "="*60)
        print("🚀 SIMULATION STARTED")
        print("="*60)
        print(f"  Starting Capital: ${self.starting_capital:.2f}")
        print(f"  Strategies: {', '.join(self.strategies)}")
        print(f"  Duration: {duration_minutes} minutes")
        print(f"  End Time: {end_time.strftime('%H:%M:%S')}")
        print("="*60 + "\n")
        
        while datetime.now() < end_time:
            cycle += 1
            remaining = (end_time - datetime.now()).total_seconds() / 60
            
            logger.info(f"\n--- Cycle {cycle} ({remaining:.1f} min remaining) ---")
            
            try:
                await self._trading_cycle()
            except Exception as e:
                logger.error(f"Error in cycle {cycle}: {e}", exc_info=True)
            
            # Print intermediate stats
            stats = self.simulation.get_stats()
            print(f"\n📊 Current Status:")
            print(f"   Capital: ${stats.current_capital:.2f}")
            print(f"   PnL: ${stats.total_pnl:+.2f} ({stats.total_pnl_pct})")
            print(f"   Trades: {stats.total_trades} | Win Rate: {stats.win_rate}")
            
            # Wait for next cycle
            await asyncio.sleep(poll_interval)
        
        # Final results
        await self._finish()
    
    async def _trading_cycle(self):
        """Execute one trading cycle"""
        # Fetch markets
        markets = await self.client.get_markets(
            active_only=True,
            min_liquidity=500  # Lower threshold for simulation
        )
        self.markets_scanned += len(markets)
        
        logger.info(f"Scanned {len(markets)} markets")
        
        if not markets:
            logger.warning("No markets found")
            return
        
        # Run arbitrage strategy
        if self.arbitrage and "arbitrage" in self.strategies:
            await self._run_arbitrage(markets)
        
        # Run mispricing strategy
        if self.mispricing and "mispricing" in self.strategies:
            await self._run_mispricing(markets[:5])  # Limit for Ollama calls
        
        # Update position prices
        await self._update_positions()
    
    async def _run_arbitrage(self, markets):
        """Run arbitrage strategy"""
        logger.info("Scanning for arbitrage opportunities...")
        
        opportunities = await self.arbitrage.scan_markets(markets, self.client)
        self.opportunities_found += len(opportunities)
        
        if not opportunities:
            return
        
        # Take best opportunity
        best = max(opportunities, key=lambda x: x.profit_pct)
        logger.info(f"Best opportunity: {best}")
        
        # Check risk limits
        if not self._check_risk():
            logger.warning("Risk limits reached, skipping trade")
            return
        
        # Calculate position size
        size = min(
            10.0,  # Max $10 per trade
            self.simulation.current_capital * 0.1  # Max 10% of capital
        )
        
        # Simulate trade
        # For arbitrage, we buy both YES and NO
        yes_token = best.market.tokens.get("YES")
        no_token = best.market.tokens.get("NO")
        
        if yes_token and no_token:
            # Buy YES
            await self.simulation.execute_trade(
                market=best.market,
                token_id=yes_token,
                side="BUY",
                size=size / 2,
                price=best.yes_price,
                strategy="arbitrage"
            )
            
            # Buy NO
            await self.simulation.execute_trade(
                market=best.market,
                token_id=no_token,
                side="BUY",
                size=size / 2,
                price=best.no_price,
                strategy="arbitrage"
            )
            
            self.trades_executed += 2
            
            self.trade_logger.log_opportunity(
                strategy="arbitrage",
                market=best.market.question,
                expected_profit=best.spread * size,
                confidence=best.profit_pct
            )
    
    async def _run_mispricing(self, markets):
        """Run mispricing strategy"""
        if not self.mispricing:
            return
        
        logger.info("Analyzing markets for mispricing...")
        
        try:
            opportunities = await self.mispricing.scan_markets(markets, self.client)
            self.opportunities_found += len(opportunities)
            
            if not opportunities:
                return
            
            # Take best opportunity
            best = opportunities[0]
            logger.info(f"Best mispricing: {best}")
            
            # Check risk limits
            if not self._check_risk():
                return
            
            # Calculate position size
            size = min(
                5.0,  # Max $5 for mispricing (riskier)
                self.simulation.current_capital * 0.05
            )
            
            # Simulate trade
            await self.simulation.execute_trade(
                market=best.assessment.market,
                token_id=best.token_id,
                side=best.direction.value,
                size=size,
                price=best.assessment.current_price,
                strategy="mispricing"
            )
            
            self.trades_executed += 1
            
        except Exception as e:
            logger.error(f"Error in mispricing strategy: {e}")
    
    async def _update_positions(self):
        """Update current prices for open positions"""
        for token_id, position in list(self.simulation.positions.items()):
            try:
                book = await self.client.get_order_book(token_id)
                self.simulation.update_position_prices({token_id: book.midpoint})
            except Exception as e:
                logger.debug(f"Could not update price for {token_id}: {e}")
    
    def _check_risk(self) -> bool:
        """Check if we can open new positions"""
        stats = self.simulation.get_stats()
        
        # Check capital
        if self.simulation.current_capital < 1.0:
            logger.warning("Insufficient capital")
            return False
        
        # Check max positions
        if stats.open_positions >= 10:
            logger.warning("Max positions reached")
            return False
        
        # Check daily loss
        if stats.total_pnl < -self.starting_capital * 0.2:  # 20% max loss
            logger.warning("Max daily loss reached")
            return False
        
        return True
    
    async def _finish(self):
        """Finish simulation and show results"""
        print("\n\n")
        
        # Close all positions
        print("Closing all positions...")
        
        current_prices = {}
        for token_id, position in self.simulation.positions.items():
            try:
                book = await self.client.get_order_book(token_id)
                current_prices[token_id] = book.midpoint
            except:
                current_prices[token_id] = position.current_price
        
        await self.simulation.close_all_positions(current_prices)
        
        # Get final stats
        stats = self.simulation.get_stats()
        
        # Print summary
        self.simulation.print_summary()
        
        # Print detailed results
        print("\n📈 DETAILED RESULTS")
        print("-"*60)
        print(f"  Markets Scanned:     {self.markets_scanned}")
        print(f"  Opportunities Found: {self.opportunities_found}")
        print(f"  Trades Executed:     {self.trades_executed}")
        print(f"  Final Capital:       ${stats.current_capital:.2f}")
        print(f"  Total PnL:           ${stats.total_pnl:+.2f}")
        print(f"  Return:              {stats.total_pnl_pct}")
        print(f"  Win Rate:            {stats.win_rate}")
        print(f"  Max Drawdown:        {stats.max_drawdown}")
        print("-"*60)
        
        # Save results
        filepath = self.simulation.save_results()
        print(f"\n💾 Results saved to: {filepath}")
        
        # Close client
        await self.client.close()
        
        return stats
    
    async def close(self):
        """Close all connections"""
        if self.client:
            await self.client.close()


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run Polymarket trading simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_simulation.py --capital 100 --duration 30
    python run_simulation.py --quick
    python run_simulation.py --strategies arbitrage --capital 50
        """
    )
    
    parser.add_argument(
        "--capital",
        type=float,
        default=100.0,
        help="Starting capital in USD (default: 100)"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Simulation duration in minutes (default: 60)"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval in seconds (default: 30)"
    )
    
    parser.add_argument(
        "--strategies",
        type=str,
        default="arbitrage",
        help="Comma-separated strategies: arbitrage,mispricing (default: arbitrage)"
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick 5-minute test"
    )
    
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.001,
        help="Simulated slippage percentage (default: 0.001 = 0.1%%)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level, log_file="logs/simulation.log")
    
    # Parse strategies
    strategies = [s.strip() for s in args.strategies.split(",")]
    
    # Create runner
    runner = SimulationRunner(
        starting_capital=args.capital,
        strategies=strategies,
        slippage=args.slippage
    )
    
    try:
        await runner.initialize()
        await runner.run(
            duration_minutes=args.duration,
            poll_interval=args.interval,
            quick=args.quick
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        logger.error(f"Simulation error: {e}", exc_info=True)
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())