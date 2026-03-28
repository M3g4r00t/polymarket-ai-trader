"""
Polymarket AI Trader - Main Entry Point

Usage:
    python main.py --dry-run          # Run in simulation mode
    python main.py --strategy arbitrage --live
    python main.py --help
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from client import PolymarketClient, Market
from strategies.arbitrage import ArbitrageStrategy, ArbitrageOpportunity
from strategies.mispricing import MispricingStrategy, MispricingOpportunity
from risk.manager import RiskManager, RiskConfig
from utils.logger import setup_logging, TradeLogger

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class PolymarketTrader:
    """
    Main trading bot class.
    
    Orchestrates:
    - Market data fetching
    - Strategy execution
    - Risk management
    - Position tracking
    """
    
    def __init__(
        self,
        config_path: str = "config/settings.yaml",
        dry_run: bool = False
    ):
        self.config = self._load_config(config_path)
        self.dry_run = dry_run
        
        # Setup logging
        log_level = os.getenv("LOG_LEVEL", "INFO")
        log_file = self.config.get('logging', {}).get('file_path', 'logs/trader.log')
        setup_logging(level=log_level, log_file=log_file)
        
        # Trade logger
        self.trade_logger = TradeLogger()
        
        # Initialize components
        self.client: Optional[PolymarketClient] = None
        self.arbitrage_strategy: Optional[ArbitrageStrategy] = None
        self.mispricing_strategy: Optional[MispricingStrategy] = None
        self.risk_manager: Optional[RiskManager] = None
        
        # State
        self.running = False
        self.last_cycle = None
        self.total_pnl = 0.0
    
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return {}
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Polymarket AI Trader...")
        
        # Get private key
        private_key = os.getenv("PRIVATE_KEY")
        if not private_key and not self.dry_run:
            logger.error("PRIVATE_KEY not set and not in dry-run mode")
            raise ValueError("PRIVATE_KEY environment variable required")
        
        # Initialize client
        self.client = PolymarketClient(
            private_key=private_key,
            dry_run=self.dry_run
        )
        await self.client.initialize()
        logger.info("Client initialized")
        
        # Initialize strategies
        arb_config = self.config.get('strategies', {}).get('arbitrage', {})
        self.arbitrage_strategy = ArbitrageStrategy(
            min_spread_usd=arb_config.get('min_spread_usd', 0.02),
            min_profit_pct=arb_config.get('min_profit_pct', 0.02),
            min_liquidity_usd=arb_config.get('min_liquidity_usd', 1000.0),
            max_trade_size_usd=self.config.get('trading', {}).get('max_trade_size_usd', 10.0),
            exclude_markets=arb_config.get('exclude_markets', [])
        )
        
        misp_config = self.config.get('strategies', {}).get('mispricing', {})
        self.mispricing_strategy = MispricingStrategy(
            min_deviation_pct=misp_config.get('min_deviation_pct', 0.10),
            min_confidence=misp_config.get('min_confidence', 'medium'),
            max_markets_per_cycle=misp_config.get('max_markets_per_cycle', 5),
            ai_model=misp_config.get('ai_model', 'gpt-4o-mini'),
            max_api_calls_per_day=misp_config.get('max_api_calls_per_day', 100)
        )
        
        # Initialize risk manager
        risk_config = self.config.get('risk', {})
        self.risk_manager = RiskManager(RiskConfig(
            min_trade_size_usd=self.config.get('trading', {}).get('min_trade_size_usd', 1.0),
            max_trade_size_usd=self.config.get('trading', {}).get('max_trade_size_usd', 10.0),
            max_position_size_usd=risk_config.get('max_position_size_usd', 50.0),
            max_total_exposure_usd=risk_config.get('max_total_exposure_usd', 200.0),
            stop_loss_pct=risk_config.get('stop_loss_pct', 0.15),
            take_profit_pct=risk_config.get('take_profit_pct', 0.05),
            max_daily_loss_usd=risk_config.get('max_daily_loss_usd', 20.0),
            max_consecutive_losses=risk_config.get('max_consecutive_losses', 3),
            pause_after_losses_minutes=risk_config.get('pause_after_losses_minutes', 60)
        ))
        
        logger.info("All components initialized")
    
    async def run(self):
        """Main trading loop"""
        logger.info("Starting trading loop...")
        self.running = True
        
        poll_interval = self.config.get('data', {}).get('poll_interval_seconds', 30)
        
        while self.running:
            try:
                await self._trading_cycle()
                self.last_cycle = datetime.now()
                
                logger.info(f"Cycle complete. Waiting {poll_interval}s...")
                await asyncio.sleep(poll_interval)
                
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in trading cycle: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _trading_cycle(self):
        """Execute one trading cycle"""
        logger.info("--- Starting trading cycle ---")
        
        # 1. Fetch markets
        categories = self.config.get('data', {}).get('categories', [])
        markets = []
        
        for category in categories:
            cat_markets = await self.client.get_markets(
                category=category,
                active_only=True,
                min_liquidity=self.config.get('strategies', {}).get('arbitrage', {}).get('min_liquidity_usd', 1000.0)
            )
            markets.extend(cat_markets)
        
        logger.info(f"Found {len(markets)} markets to analyze")
        
        # 2. Check risk limits
        if not self.risk_manager.can_open_position():
            logger.warning("Cannot open new positions - risk limits reached")
            return
        
        # 3. Find arbitrage opportunities
        if self.config.get('strategies', {}).get('arbitrage', {}).get('enabled', True):
            arb_opportunities = await self.arbitrage_strategy.scan_markets(markets, self.client)
            
            if arb_opportunities:
                # Execute best opportunity
                best_opp = max(arb_opportunities, key=lambda x: x.profit_pct)
                logger.info(f"Best arbitrage opportunity: {best_opp}")
                
                if not self.dry_run:
                    result = await self.arbitrage_strategy.execute(best_opp, self.client)
                    self.trade_logger.log_opportunity(
                        strategy="arbitrage",
                        market=best_opp.market.question,
                        expected_profit=best_opp.spread,
                        confidence=best_opp.profit_pct
                    )
                else:
                    logger.info("[DRY RUN] Would execute arbitrage opportunity")
        
        # 4. Find mispricing opportunities (if enabled and AI available)
        if self.config.get('strategies', {}).get('mispricing', {}).get('enabled', False):
            if os.getenv('OPENAI_API_KEY') or os.getenv('ANTHROPIC_API_KEY'):
                try:
                    misp_opportunities = await self.mispricing_strategy.scan_markets(markets[:5], self.client)
                    
                    for opp in misp_opportunities[:1]:  # Take top opportunity
                        logger.info(f"Mispricing opportunity: {opp}")
                        
                        if not self.dry_run:
                            # Execute trade
                            size = self.risk_manager.calculate_position_size(
                                confidence=0.5,  # TODO: Map from assessment.confidence
                                market_liquidity=opp.liquidity
                            )
                            
                            # TODO: Execute trade via client
                            logger.info(f"Would trade {size} on {opp.token_id}")
                except Exception as e:
                    logger.error(f"Error in mispricing strategy: {e}")
        
        # 5. Manage existing positions
        await self._manage_positions()
        
        # 6. Log summary
        self._log_status()
    
    async def _manage_positions(self):
        """Manage open positions (stops, take profits)"""
        positions = self.risk_manager.get_positions_summary()
        
        if positions['open_positions'] > 0:
            logger.info(f"Managing {positions['open_positions']} open positions")
            # TODO: Check stops and take profits
        else:
            logger.debug("No open positions to manage")
    
    def _log_status(self):
        """Log current status"""
        positions = self.risk_manager.get_positions_summary()
        risk_level = self.risk_manager.get_risk_level()
        
        logger.info(
            f"Status: {positions['open_positions']} positions, "
            f"${positions['total_exposure']:.2f} exposure, "
            f"${positions['daily_pnl']:+.2f} daily PnL, "
            f"risk={risk_level.value}"
        )
    
    async def shutdown(self):
        """Clean shutdown"""
        logger.info("Shutting down...")
        
        # Cancel all open orders
        if self.client and not self.dry_run:
            await self.client.cancel_all_orders()
        
        # Close client
        if self.client:
            await self.client.close()
        
        # Log final summary
        self.trade_logger.log_daily_summary(
            trades=len(self.risk_manager._trades),
            wins=sum(1 for t in self.risk_manager._trades if t.pnl and t.pnl > 0),
            losses=sum(1 for t in self.risk_manager._trades if t.pnl and t.pnl < 0),
            total_pnl=self.risk_manager._daily_pnl,
            win_rate=sum(1 for t in self.risk_manager._trades if t.pnl and t.pnl > 0) / max(1, len(self.risk_manager._trades))
        )
        
        logger.info("Shutdown complete")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Polymarket AI Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py --dry-run              # Run in simulation mode
    python main.py --live                 # Run in production mode
    python main.py --config custom.yaml  # Use custom config
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in simulation mode (no real trades)"
    )
    
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in production mode (real trades)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.yaml",
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--strategy",
        type=str,
        default="all",
        choices=["arbitrage", "mispricing", "all"],
        help="Which strategy to run"
    )
    
    args = parser.parse_args()
    
    # Determine mode
    dry_run = not args.live
    if args.dry_run and args.live:
        print("Error: Cannot specify both --dry-run and --live")
        sys.exit(1)
    
    # Create trader
    trader = PolymarketTrader(
        config_path=args.config,
        dry_run=dry_run
    )
    
    # Enable strategies
    if args.strategy == "arbitrage":
        trader.config.setdefault('strategies', {})['mispricing'] = {'enabled': False}
    elif args.strategy == "mispricing":
        trader.config.setdefault('strategies', {})['arbitrage'] = {'enabled': False}
    
    try:
        await trader.initialize()
        await trader.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await trader.shutdown()


if __name__ == "__main__":
    asyncio.run(main())