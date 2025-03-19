import os
import sys
import threading
from datetime import datetime
from loguru import logger as loguru_logger

# Thread-local storage for wallet context
_thread_local = threading.local()

def setup_logger():
    """Setup loguru logger with custom format."""
    log_format = (
        "<green>{time:DD/MM/YYYY - HH:mm:ss}</green>"
        "{extra[wallet]: <14} | "
        "<level>{level: <8}</level> | "
        "<cyan>{module: <15}</cyan> | "
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
    
    # Initialize thread-local storage with default empty value
    _thread_local.wallet = ""
    
    # Configure logger with wallet context (empty by default)
    loguru_logger.configure(extra={"wallet": ""})
    
    return loguru_logger

def get_masked_address(address):
    """Get masked address (first 6 and last 4 characters)."""
    if not address or len(address) < 10:
        return address
    
    return f"{address[:6]}...{address[-4:]}"

def get_thread_logger():
    """
    Get a thread-specific logger instance with the current thread's wallet context.
    
    Returns:
        logger: A logger instance with the thread's wallet context
    """
    # Get the wallet context for this thread, default to empty string if not set
    wallet_context = getattr(_thread_local, 'wallet', "")
    
    # Create a thread-specific logger with the wallet context
    thread_logger = loguru_logger.bind(wallet=wallet_context)
    
    return thread_logger

def set_wallet_context(address):
    """
    Set wallet address in thread-local logger context.
    
    Args:
        address (str): Wallet address
        
    Returns:
        str: Masked wallet address
    """
    # Get masked address
    masked = get_masked_address(address)
    
    # Store in thread-local storage
    _thread_local.wallet = f" - {masked}"
    
    # Return the masked address for convenience
    return masked

# Create a shorthand for the thread logger
def log():
    """Get thread-specific logger."""
    return get_thread_logger()