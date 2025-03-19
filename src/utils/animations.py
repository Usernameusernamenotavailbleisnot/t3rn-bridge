import time
import sys
from loguru import logger
from src.constants.constants import BANNER_TEXT

def display_banner():
    """Display ASCII art banner at startup."""
    print("\n")
    print(BANNER_TEXT)
    print("\n")
    print("T3RN Bridge Bot - Testnet Automation")
    print("Chain Support: Base Sepolia, Optimism Sepolia")
    print("=" * 50)
    print("\n")

def display_processing_animation(message="Processing"):
    """
    Create a context manager for displaying a processing animation.
    
    Args:
        message (str): Message to display
        
    Returns:
        Context manager
    """
    class ProcessingAnimation:
        def __init__(self, message):
            self.message = message
            self.is_running = False
        
        def __enter__(self):
            logger.info(f"{self.message}...")
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                logger.info(f"{self.message} completed")
            else:
                logger.error(f"{self.message} failed: {str(exc_val)}")
    
    return ProcessingAnimation(message)