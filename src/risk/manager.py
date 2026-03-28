"""
Risk Manager and Position Manager

Handles position sizing, stop losses, take profits, and risk controls.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import os

from ..client import Position, OrderSide

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskConfig:
    """Risk management configuration"""
    min_trade_size_usd: float = 1.0
    max_trade_size_usd: float = 10.0
    max_position_size_usd: float = 50.0
    max_total_exposure_usd: float = 200.0
    stop_loss_pct: float = 0.15
    take_profit_pct: float = 0.05
    max_daily_loss_usd: float = 20.0
    max_consecutive_losses: int = 3
    pause_after_losses_minutes: int = 60
    trailing_stop: bool = True
    trailing_stop_pct: float = 0.03
    max_open_positions: int = 10


@dataclass
class TradeRecord:
    """Record of an executed trade"""
    trade_id: str
    market_id: str
    token_id: str
    side: OrderSide
    size: float
    price: float
    timestamp: datetime
    pnl: Optional[float] = None
    status: str = "open"


@dataclass
class PositionTracker:
    """Tracks an open position"""
    token_id: str
    market_question: str
    side: OrderSide
    size: float
    entry_price: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    highest_price: float = 0.0  # For trailing stop
    lowest_price: float = 1.0   # For trailing stop
    opened_at: datetime = field(default_factory=datetime.now)
    order_ids: List[str] = field(default_factory=list)


class RiskManager:
    """
    Main risk management class.
    
    Handles:
    - Position sizing
    - Stop losses and take profits
    - Daily loss limits
    - Consecutive loss tracking
    - Exposure limits
    """
    
    def __init__(self, config: RiskConfig):
        self.config = config
        
        # State
        self._positions: Dict[str, PositionTracker] = {}
        self._trades: List[TradeRecord] = []
        self._daily_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._paused_until: Optional[datetime] = None
        
        # Load trade history if exists
        self._load_history()
    
    def can_open_position(self) -> bool:
        """Check if we can open a new position"""
        # Check if paused
        if self._paused_until and datetime.now() < self._paused_until:
            logger.warning(f"Trading paused until {self._paused_until}")
            return False
        
        # Check max positions
        if len(self._positions) >= self.config.max_open_positions:
            logger.warning(f"Max positions reached: {len(self._positions)}")
            return False
        
        # Check daily loss
        if self._daily_pnl <= -self.config.max_daily_loss_usd:
            logger.warning(f"Daily loss limit reached: ${abs(self._daily_pnl):.2f}")
            return False
        
        # Check consecutive losses
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            logger.warning(f"Too many consecutive losses: {self._consecutive_losses}")
            return False
        
        return True
    
    def calculate_position_size(
        self,
        confidence: float = 0.5,
        market_liquidity: float = 10000.0,
        current_capital: float = 100.0
    ) -> float:
        """
        Calculate optimal position size using Kelly Criterion.
        
        Args:
            confidence: Confidence level (0-1)
            market_liquidity: Market liquidity in USD
            current_capital: Available capital in USD
            
        Returns:
            Position size in USD
        """
        # Fractional Kelly (25% of full Kelly for safety)
        kelly_fraction = 0.25
        
        # Simplified Kelly: f = (p - (1-p)/odds) / 1
        # For prediction markets: odds are implicit (win prob = price)
        # Simplified: size based on confidence and capital
        
        base_size = current_capital * kelly_fraction * confidence
        
        # Apply limits
        size = min(
            base_size,
            self.config.max_trade_size_usd,
            self.config.max_position_size_usd,
            market_liquidity * 0.01  # Max 1% of market liquidity
        )
        
        # Ensure minimum
        size = max(size, self.config.min_trade_size_usd)
        
        return round(size, 2)
    
    def open_position(
        self,
        token_id: str,
        market_question: str,
        side: OrderSide,
        size: float,
        entry_price: float
    ) -> PositionTracker:
        """
        Open a new position with risk management.
        
        Args:
            token_id: Token being traded
            market_question: Market question for reference
            side: BUY or SELL
            size: Position size in USD
            entry_price: Entry price
            
        Returns:
            PositionTracker for the new position
        """
        # Calculate stop loss and take profit
        if side == OrderSide.BUY:
            stop_loss = entry_price * (1 - self.config.stop_loss_pct)
            take_profit = entry_price * (1 + self.config.take_profit_pct)
            trailing_stop = entry_price * (1 - self.config.trailing_stop_pct)
        else:  # SELL/SHORT
            stop_loss = entry_price * (1 + self.config.stop_loss_pct)
            take_profit = entry_price * (1 - self.config.take_profit_pct)
            trailing_stop = entry_price * (1 + self.config.trailing_stop_pct)
        
        position = PositionTracker(
            token_id=token_id,
            market_question=market_question,
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            trailing_stop_price=trailing_stop if self.config.trailing_stop else None,
            highest_price=entry_price,
            lowest_price=entry_price,
            opened_at=datetime.now()
        )
        
        self._positions[token_id] = position
        
        # Record trade
        trade = TradeRecord(
            trade_id=f"{token_id}_{datetime.now().timestamp()}",
            market_id=token_id,
            token_id=token_id,
            side=side,
            size=size,
            price=entry_price,
            timestamp=datetime.now()
        )
        self._trades.append(trade)
        
        logger.info(
            f"Opened position: {side.value} {size} @ {entry_price:.3f} "
            f"Stop: {stop_loss:.3f}, TP: {take_profit:.3f}"
        )
        
        return position
    
    def check_position(
        self,
        token_id: str,
        current_price: float
    ) -> Optional[str]:
        """
        Check if position should be closed.
        
        Args:
            token_id: Token ID
            current_price: Current market price
            
        Returns:
            Reason for close, or None if should hold
        """
        if token_id not in self._positions:
            return None
        
        position = self._positions[token_id]
        
        # Update high/low for trailing stop
        if self.config.trailing_stop:
            if current_price > position.highest_price:
                position.highest_price = current_price
                # Update trailing stop
                if position.side == OrderSide.BUY:
                    position.trailing_stop_price = current_price * (1 - self.config.trailing_stop_pct)
                else:
                    position.trailing_stop_price = current_price * (1 + self.config.trailing_stop_pct)
            
            if current_price < position.lowest_price:
                position.lowest_price = current_price
        
        # Check stop loss
        if position.side == OrderSide.BUY:
            if current_price <= position.stop_loss_price:
                return "stop_loss"
            if current_price >= position.take_profit_price:
                return "take_profit"
            if self.config.trailing_stop and current_price <= position.trailing_stop_price:
                return "trailing_stop"
        else:  # SELL
            if current_price >= position.stop_loss_price:
                return "stop_loss"
            if current_price <= position.take_profit_price:
                return "take_profit"
            if self.config.trailing_stop and current_price >= position.trailing_stop_price:
                return "trailing_stop"
        
        return None
    
    def close_position(
        self,
        token_id: str,
        exit_price: float,
        reason: str = "manual"
    ) -> Optional[float]:
        """
        Close a position and calculate PnL.
        
        Args:
            token_id: Token ID
            exit_price: Exit price
            reason: Reason for closing
            
        Returns:
            PnL in USD, or None if position not found
        """
        if token_id not in self._positions:
            return None
        
        position = self._positions[token_id]
        
        # Calculate PnL
        if position.side == OrderSide.BUY:
            pnl = position.size * (exit_price - position.entry_price)
        else:  # SELL
            pnl = position.size * (position.entry_price - exit_price)
        
        # Update daily PnL
        self._daily_pnl += pnl
        
        # Update consecutive losses
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        
        # Check if we should pause
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            self._paused_until = datetime.now() + timedelta(
                minutes=self.config.pause_after_losses_minutes
            )
            logger.warning(f"Pausing trading until {self._paused_until}")
        
        # Log
        logger.info(
            f"Closed position: {position.side.value} {position.size} "
            f"@ {position.entry_price:.3f} -> {exit_price:.3f} "
            f"PnL: ${pnl:+.2f} ({reason})"
        )
        
        # Remove position
        del self._positions[token_id]
        
        # Update trade record
        for trade in self._trades:
            if trade.token_id == token_id and trade.status == "open":
                trade.pnl = pnl
                trade.status = reason
                break
        
        # Save history
        self._save_history()
        
        return pnl
    
    def get_total_exposure(self) -> float:
        """Get total exposure across all positions"""
        return sum(p.size for p in self._positions.values())
    
    def get_positions_summary(self) -> Dict:
        """Get summary of all positions"""
        return {
            "open_positions": len(self._positions),
            "total_exposure": self.get_total_exposure(),
            "daily_pnl": self._daily_pnl,
            "consecutive_losses": self._consecutive_losses,
            "is_paused": self._paused_until is not None and datetime.now() < self._paused_until,
            "paused_until": self._paused_until.isoformat() if self._paused_until else None
        }
    
    def get_risk_level(self) -> RiskLevel:
        """Get current risk level"""
        exposure = self.get_total_exposure()
        loss_ratio = abs(min(self._daily_pnl, 0)) / self.config.max_daily_loss_usd
        
        if exposure > self.config.max_total_exposure_usd * 0.8 or loss_ratio > 0.8:
            return RiskLevel.HIGH
        elif exposure > self.config.max_total_exposure_usd * 0.5 or loss_ratio > 0.5:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _load_history(self):
        """Load trade history from file"""
        history_path = "data/trades.json"
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r') as f:
                    data = json.load(f)
                    for trade_data in data.get('trades', []):
                        trade = TradeRecord(
                            trade_id=trade_data['trade_id'],
                            market_id=trade_data['market_id'],
                            token_id=trade_data['token_id'],
                            side=OrderSide(trade_data['side']),
                            size=trade_data['size'],
                            price=trade_data['price'],
                            timestamp=datetime.fromisoformat(trade_data['timestamp']),
                            pnl=trade_data.get('pnl'),
                            status=trade_data.get('status', 'closed')
                        )
                        self._trades.append(trade)
                    logger.info(f"Loaded {len(self._trades)} trades from history")
            except Exception as e:
                logger.error(f"Error loading trade history: {e}")
    
    def _save_history(self):
        """Save trade history to file"""
        os.makedirs("data", exist_ok=True)
        history_path = "data/trades.json"
        
        try:
            data = {
                'trades': [
                    {
                        'trade_id': t.trade_id,
                        'market_id': t.market_id,
                        'token_id': t.token_id,
                        'side': t.side.value,
                        'size': t.size,
                        'price': t.price,
                        'timestamp': t.timestamp.isoformat(),
                        'pnl': t.pnl,
                        'status': t.status
                    }
                    for t in self._trades
                ]
            }
            with open(history_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trade history: {e}")


class PositionManager:
    """
    High-level position management.
    
    Coordinates between RiskManager and trading client.
    """
    
    def __init__(self, client, risk_manager: RiskManager):
        self.client = client
        self.risk = risk_manager
    
    async def manage_positions(self):
        """Check all open positions and manage stops"""
        for token_id, position in list(self.risk._positions.items()):
            try:
                # Get current price
                book = await self.client.get_order_book(token_id)
                current_price = book.midpoint
                
                # Check if should close
                reason = self.risk.check_position(token_id, current_price)
                
                if reason:
                    # Close position
                    await self.close_position(token_id, current_price, reason)
                    
            except Exception as e:
                logger.error(f"Error managing position {token_id}: {e}")
    
    async def close_position(
        self,
        token_id: str,
        price: float,
        reason: str
    ) -> bool:
        """Close a position via client"""
        # Place opposite order
        position = self.risk._positions.get(token_id)
        if not position:
            return False
        
        close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
        
        # Place market order to close
        result = await self.client.place_limit_order(
            token_id=token_id,
            side=close_side,
            price=price,
            size=position.size,
            order_type="FOK",  # Fill or kill for immediate close
            dry_run=False
        )
        
        if result:
            self.risk.close_position(token_id, price, reason)
            return True
        
        return False