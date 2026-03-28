"""
Simulation Mode - Paper Trading without Real Money

Allows testing strategies with simulated trades using live market data.
Tracks performance metrics and provides detailed logging.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path

from ..client import Market, OrderSide

logger = logging.getLogger(__name__)


class SimulationMode(Enum):
    PAPER = "paper"  # Simulated trades, fake money
    BACKTEST = "backtest"  # Historical data
    LIVE = "live"  # Real trades


@dataclass
class SimulatedPosition:
    """Simulated position tracking"""
    token_id: str
    market_question: str
    side: OrderSide
    size: float
    entry_price: float
    current_price: float
    opened_at: datetime
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class SimulatedTrade:
    """Record of a simulated trade"""
    trade_id: str
    market_id: str
    market_question: str
    token_id: str
    side: OrderSide
    size: float
    price: float
    timestamp: datetime
    status: str  # open, closed
    close_price: Optional[float] = None
    pnl: Optional[float] = None
    close_timestamp: Optional[datetime] = None


@dataclass
class SimulationStats:
    """Performance statistics"""
    starting_capital: float
    current_capital: float
    total_trades: int
    open_positions: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    total_pnl_pct: float
    win_rate: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float
    best_trade: float
    worst_trade: float
    
    def to_dict(self) -> dict:
        return {
            "starting_capital": self.starting_capital,
            "current_capital": round(self.current_capital, 2),
            "total_trades": self.total_trades,
            "open_positions": self.open_positions,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": f"{self.total_pnl_pct:.2%}",
            "win_rate": f"{self.win_rate:.1%}",
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "max_drawdown": f"{self.max_drawdown:.2%}",
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "best_trade": round(self.best_trade, 2),
            "worst_trade": round(self.worst_trade, 2)
        }


class SimulationEngine:
    """
    Paper trading engine for testing strategies.
    
    Simulates:
    - Order execution at market/midpoint prices
    - Position tracking and PnL calculation
    - Slippage and fees (configurable)
    - Performance metrics
    """
    
    def __init__(
        self,
        starting_capital: float = 100.0,
        slippage_pct: float = 0.001,  # 0.1% slippage
        fee_pct: float = 0.0,  # Polymarket has no fees
        simulation_id: Optional[str] = None
    ):
        self.starting_capital = starting_capital
        self.current_capital = starting_capital
        self.slippage_pct = slippage_pct
        self.fee_pct = fee_pct
        self.simulation_id = simulation_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Positions and trades
        self.positions: Dict[str, SimulatedPosition] = {}
        self.trades: List[SimulatedTrade] = []
        self.trade_counter = 0
        
        # Performance tracking
        self.equity_curve: List[float] = [starting_capital]
        self.returns: List[float] = []
        self.peak_capital = starting_capital
        
        # Logging
        self.log_dir = Path("data/simulations")
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute_trade(
        self,
        market: Market,
        token_id: str,
        side: OrderSide,
        size: float,
        price: float,
        strategy: str = "unknown"
    ) -> Optional[SimulatedTrade]:
        """
        Simulate executing a trade.
        
        Args:
            market: Market being traded
            token_id: Token ID (YES or NO)
            side: BUY or SELL
            size: Position size in USD
            price: Execution price (will apply slippage)
            strategy: Strategy name for logging
            
        Returns:
            SimulatedTrade record
        """
        # Check capital
        if side == OrderSide.BUY and size > self.current_capital:
            logger.warning(f"Insufficient capital: need ${size:.2f}, have ${self.current_capital:.2f}")
            return None
        
        # Apply slippage
        if side == OrderSide.BUY:
            execution_price = price * (1 + self.slippage_pct)
        else:
            execution_price = price * (1 - self.slippage_pct)
        
        # Apply fee
        fee = size * self.fee_pct
        
        # Create trade record
        self.trade_counter += 1
        trade_id = f"sim_{self.simulation_id}_{self.trade_counter}"
        
        trade = SimulatedTrade(
            trade_id=trade_id,
            market_id=market.condition_id,
            market_question=market.question,
            token_id=token_id,
            side=side,
            size=size,
            price=execution_price,
            timestamp=datetime.now(),
            status="open"
        )
        
        self.trades.append(trade)
        
        # Update capital
        if side == OrderSide.BUY:
            self.current_capital -= (size + fee)
            
            # Create position
            position = SimulatedPosition(
                token_id=token_id,
                market_question=market.question,
                side=side,
                size=size,
                entry_price=execution_price,
                current_price=execution_price,
                opened_at=datetime.now()
            )
            self.positions[token_id] = position
            
            logger.info(
                f"[SIM] BUY {size:.2f} shares @ {execution_price:.3f} "
                f"of '{market.question[:50]}...' | "
                f"Capital: ${self.current_capital:.2f}"
            )
        else:  # SELL
            if token_id not in self.positions:
                logger.warning(f"No position to sell for {token_id}")
                return None
            
            position = self.positions[token_id]
            pnl = size * (execution_price - position.entry_price)
            self.current_capital += size + fee + pnl
            
            # Close position
            trade.status = "closed"
            trade.close_price = execution_price
            trade.pnl = pnl
            trade.close_timestamp = datetime.now()
            
            del self.positions[token_id]
            
            logger.info(
                f"[SIM] SELL {size:.2f} shares @ {execution_price:.3f} "
                f"of '{market.question[:50]}...' | "
                f"PnL: ${pnl:+.2f} | Capital: ${self.current_capital:.2f}"
            )
        
        # Update equity curve
        self._update_equity()
        
        return trade
    
    async def close_all_positions(self, current_prices: Dict[str, float]) -> List[SimulatedTrade]:
        """
        Close all open positions at current prices.
        
        Args:
            current_prices: Dict of token_id -> current_price
            
        Returns:
            List of closed trades
        """
        closed = []
        
        for token_id, position in list(self.positions.items()):
            current_price = current_prices.get(token_id, position.current_price)
            
            # Create market stub
            market = Market(
                condition_id="close_all",
                question=position.market_question,
                description="",
                category="",
                end_date=None,
                tokens={},
                prices={},
                liquidity=0,
                active=True
            )
            
            trade = await self.execute_trade(
                market=market,
                token_id=token_id,
                side=OrderSide.SELL,
                size=position.size,
                price=current_price,
                strategy="close_all"
            )
            
            if trade:
                closed.append(trade)
        
        return closed
    
    def update_position_prices(self, current_prices: Dict[str, float]):
        """Update current prices for all positions"""
        for token_id, price in current_prices.items():
            if token_id in self.positions:
                position = self.positions[token_id]
                position.current_price = price
                
                # Calculate unrealized PnL
                if position.side == OrderSide.BUY:
                    position.pnl = position.size * (price - position.entry_price)
                    position.pnl_pct = (price - position.entry_price) / position.entry_price
    
    def _update_equity(self):
        """Update equity curve and track peak"""
        # Calculate total equity (cash + position values)
        total_equity = self.current_capital
        
        for position in self.positions.values():
            total_equity += position.size * position.current_price
        
        self.equity_curve.append(total_equity)
        
        # Track peak for drawdown
        if total_equity > self.peak_capital:
            self.peak_capital = total_equity
        
        # Calculate returns
        if len(self.equity_curve) > 1:
            ret = (self.equity_curve[-1] - self.equity_curve[-2]) / self.equity_curve[-2]
            self.returns.append(ret)
    
    def get_stats(self) -> SimulationStats:
        """Calculate and return performance statistics"""
        closed_trades = [t for t in self.trades if t.status == "closed"]
        
        if not closed_trades:
            return SimulationStats(
                starting_capital=self.starting_capital,
                current_capital=self.current_capital,
                total_trades=0,
                open_positions=len(self.positions),
                winning_trades=0,
                losing_trades=0,
                total_pnl=0.0,
                total_pnl_pct=0.0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                best_trade=0.0,
                worst_trade=0.0
            )
        
        pnls = [t.pnl for t in closed_trades if t.pnl is not None]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        
        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        
        # Calculate max drawdown
        max_dd = 0.0
        peak = self.starting_capital
        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
        
        # Calculate Sharpe ratio (simplified)
        if len(self.returns) > 1:
            avg_ret = sum(self.returns) / len(self.returns)
            var_ret = sum((r - avg_ret) ** 2 for r in self.returns) / len(self.returns)
            std_ret = var_ret ** 0.5
            # Annualized Sharpe (assuming daily returns)
            sharpe = (avg_ret * 365) / (std_ret * (365 ** 0.5)) if std_ret > 0 else 0
        else:
            sharpe = 0.0
        
        return SimulationStats(
            starting_capital=self.starting_capital,
            current_capital=self.current_capital + sum(p.size * p.current_price for p in self.positions.values()),
            total_trades=len(closed_trades),
            open_positions=len(self.positions),
            winning_trades=len(wins),
            losing_trades=len(losses),
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl / self.starting_capital,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            best_trade=max(pnls) if pnls else 0,
            worst_trade=min(pnls) if pnls else 0
        )
    
    def save_results(self, filename: Optional[str] = None):
        """Save simulation results to JSON"""
        filename = filename or f"simulation_{self.simulation_id}.json"
        filepath = self.log_dir / filename
        
        data = {
            "simulation_id": self.simulation_id,
            "config": {
                "starting_capital": self.starting_capital,
                "slippage_pct": self.slippage_pct,
                "fee_pct": self.fee_pct
            },
            "stats": self.get_stats().to_dict(),
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "market_question": t.market_question,
                    "side": t.side.value,
                    "size": t.size,
                    "price": t.price,
                    "timestamp": t.timestamp.isoformat(),
                    "status": t.status,
                    "close_price": t.close_price,
                    "pnl": t.pnl,
                    "close_timestamp": t.close_timestamp.isoformat() if t.close_timestamp else None
                }
                for t in self.trades
            ],
            "equity_curve": self.equity_curve
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved simulation results to {filepath}")
        
        return str(filepath)
    
    def print_summary(self):
        """Print a summary of the simulation"""
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("📊 SIMULATION SUMMARY")
        print("="*60)
        print(f"  Starting Capital: ${stats.starting_capital:.2f}")
        print(f"  Current Capital:   ${stats.current_capital:.2f}")
        print(f"  Total PnL:          ${stats.total_pnl:+.2f} ({stats.total_pnl_pct})")
        print("-"*60)
        print(f"  Total Trades:       {stats.total_trades}")
        print(f"  Open Positions:     {stats.open_positions}")
        print(f"  Win Rate:           {stats.win_rate}")
        print(f"  Avg Win:            ${stats.avg_win:+.2f}")
        print(f"  Avg Loss:           ${stats.avg_loss:.2f}")
        print(f"  Best Trade:         ${stats.best_trade:+.2f}")
        print(f"  Worst Trade:        ${stats.worst_trade:.2f}")
        print("-"*60)
        print(f"  Max Drawdown:       {stats.max_drawdown}")
        print(f"  Sharpe Ratio:       {stats.sharpe_ratio:.2f}")
        print("="*60 + "\n")