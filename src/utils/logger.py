import os
import sys
from datetime import datetime
from loguru import logger as loguru_logger

def setup_logger():
    """Setup loguru logger with custom format."""
    log_format = (
        "<green>{time:DD/MM/YYYY - HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{module}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Remove default handler
    loguru_logger.remove()
    
    # Add console handler
    loguru_logger.add(
        sys.stdout,
        format=log_format,
        level="INFO",
        colorize=True
    )
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Add file handler
    log_file = f"logs/t3rn_bridge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    loguru_logger.add(
        log_file,
        format=log_format,
        level="DEBUG",
        rotation="10 MB",
        retention="1 week"
    )
    
    # Configure logger with wallet context
    loguru_logger.configure(extra={"wallet": None})
    
    return loguru_logger

def get_masked_address(address):
    """Get masked address (first 6 and last 4 characters)."""
    if not address or len(address) < 10:
        return address
    
    return f"{address[:6]}...{address[-4:]}"

def set_wallet_context(address):
    """Set wallet address in logger context."""
    masked = get_masked_address(address)
    loguru_logger.configure(extra={"wallet": masked})