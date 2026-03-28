"""
Logging Utilities

Provides structured logging with rich console output.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from rich.logging import RichHandler
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False
) -> logging.Logger:
    """
    Setup logging with rich console output.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for logging
        json_format: Use JSON format for structured logging
        
    Returns:
        Configured logger
    """
    # Create logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if RICH_AVAILABLE:
        console_handler = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_path=True
        )
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        if json_format:
            file_handler.setFormatter(logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                '"logger": "%(name)s", "message": "%(message)s"}'
            ))
        else:
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
        
        root_logger.addHandler(file_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class TradeLogger:
    """
    Specialized logger for trading activity.
    
    Logs trades in a structured format for analysis.
    """
    
    def __init__(self, log_path: str = "logs/trades.log"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("trades")
        
        # Add file handler specifically for trades
        handler = logging.FileHandler(self.log_path)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(message)s'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_trade(
        self,
        action: str,
        market: str,
        side: str,
        size: float,
        price: float,
        pnl: Optional[float] = None,
        extra: Optional[dict] = None
    ):
        """
        Log a trade action.
        
        Args:
            action: Action type (OPEN, CLOSE, STOP_LOSS, TAKE_PROFIT)
            market: Market question or ID
            side: BUY or SELL
            size: Position size
            price: Trade price
            pnl: Profit/loss (for closes)
            extra: Additional metadata
        """
        msg_parts = [
            f"[{action}]",
            f"market={market[:50]}",
            f"side={side}",
            f"size=${size:.2f}",
            f"price={price:.3f}"
        ]
        
        if pnl is not None:
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            msg_parts.append(f"pnl={pnl_str}")
        
        if extra:
            for k, v in extra.items():
                msg_parts.append(f"{k}={v}")
        
        self.logger.info(" | ".join(msg_parts))
    
    def log_opportunity(
        self,
        strategy: str,
        market: str,
        expected_profit: float,
        confidence: Optional[float] = None
    ):
        """Log an identified opportunity"""
        msg_parts = [
            f"[OPPORTUNITY]",
            f"strategy={strategy}",
            f"market={market[:50]}",
            f"expected_profit=${expected_profit:.2f}"
        ]
        
        if confidence:
            msg_parts.append(f"confidence={confidence:.0%}")
        
        self.logger.info(" | ".join(msg_parts))
    
    def log_daily_summary(
        self,
        trades: int,
        wins: int,
        losses: int,
        total_pnl: float,
        win_rate: float
    ):
        """Log daily trading summary"""
        self.logger.info(
            f"[DAILY_SUMMARY] trades={trades} wins={wins} losses={losses} "
            f"total_pnl=${total_pnl:+.2f} win_rate={win_rate:.1%}"
        )