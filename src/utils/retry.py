import time
import functools
import random
from loguru import logger

def retry_with_backoff(func):
    """
    Retry decorator with exponential backoff.
    
    Args:
        func: Function to retry
        
    Returns:
        Function wrapper
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Get config from first argument (self)
        if args and hasattr(args[0], 'config'):
            config = args[0].config.get('retries', {})
            max_attempts = config.get('max_attempts', 3)
            backoff_factor = config.get('backoff_factor', 2)
            initial_wait = config.get('initial_wait', 1)
        else:
            max_attempts = 3
            backoff_factor = 2
            initial_wait = 1
        
        last_exception = None
        attempt = 0
        
        while attempt < max_attempts:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                attempt += 1
                last_exception = e
                
                # Special handling for certain errors we want to propagate immediately
                error_str = str(e)
                if "RO#7" in error_str:
                    # Propagate RO#7 errors directly without retrying
                    raise
                    
                if attempt >= max_attempts:
                    logger.error(f"All {max_attempts} retry attempts failed")
                    raise last_exception
                
                wait_time = initial_wait * (backoff_factor ** (attempt - 1))
                # Add jitter to avoid thundering herd
                wait_time = wait_time * (1 + random.uniform(-0.1, 0.1))
                
                logger.warning(f"Attempt {attempt} failed: {str(e)}. Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                
    return wrapper
