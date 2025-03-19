import time
import os
import sys
import random
import threading
import queue
from loguru import logger

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config_manager import ConfigManager
from src.services.bridge_service import BridgeService
from src.utils.logger import setup_logger, get_masked_address, set_wallet_context, log
from src.utils.retry import retry_with_backoff
from src.utils.proxy import ProxyManager
from src.utils.animations import (
    display_banner,
    display_processing_animation
)

# Create a thread-safe queue for wallets
wallet_queue = queue.Queue()

# Global event to signal threads to terminate
shutdown_event = threading.Event()

def read_private_keys():
    """Read private keys from pk.txt file."""
    try:
        with open("pk.txt", "r") as file:
            keys = [line.strip() for line in file.readlines() 
                   if line.strip() and not line.strip().startswith('#')]
        return keys
    except FileNotFoundError:
        logger.error("pk.txt file not found!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading private keys: {str(e)}")
        sys.exit(1)

def process_wallet(wallet_info):
    """Process a single wallet."""
    private_key = wallet_info["private_key"]
    index = wallet_info["index"]
    total_wallets = wallet_info["total_wallets"]
    proxy = wallet_info["proxy"]
    config_data = wallet_info["config"]
    
    try:
        # Initialize bridge service
        bridge_service = BridgeService(
            private_key=private_key,
            config=config_data,
            proxy=proxy
        )
        
        # Get wallet address and set thread-local logger context
        wallet_address = bridge_service.get_wallet_address()
        masked_address = set_wallet_context(wallet_address)
        
        # Use thread-local logger
        log().info(f"Processing wallet {masked_address} ({index+1}/{total_wallets})")
        
        for j in range(config_data["bridge"]["repeat_count"]):
            # Check if shutdown has been requested
            if shutdown_event.is_set():
                log().info("Shutdown requested, stopping wallet processing")
                return
                
            # Random amount within configured range, but with limited decimal places (5 max)
            min_amount = config_data["bridge"]["amount"]["min"]
            max_amount = config_data["bridge"]["amount"]["max"]
            
            # Generate a random amount with at most 5 decimal places
            amount = round(random.uniform(min_amount, max_amount), 5)
            
            log().info(f"Bridge attempt {j+1}/{config_data['bridge']['repeat_count']}")
            
            # Log transaction info
            log().info(f"Bridging {amount} ETH from Base Sepolia to Optimism Sepolia")
            
            # Perform Base Sepolia to Optimism Sepolia bridge
            tx_hash_base_to_op = bridge_service.bridge(
                from_chain="base_sepolia",
                to_chain="optimism_sepolia",
                amount=amount
            )
            
            if tx_hash_base_to_op:
                log().success(f"Base to Optimism bridge successful: {tx_hash_base_to_op[:10]}...")
                
                # Wait for bridge to complete
                log().info("Waiting for bridge completion...")
                bridge_completed = bridge_service.wait_for_completion(tx_hash_base_to_op)
                
                if bridge_completed:
                    # Check if shutdown has been requested
                    if shutdown_event.is_set():
                        log().info("Shutdown requested, stopping wallet processing")
                        return
                        
                    # Perform Optimism Sepolia to Base Sepolia bridge
                    log().info(f"Bridging {amount} ETH from Optimism Sepolia to Base Sepolia")
                    tx_hash_op_to_base = bridge_service.bridge(
                        from_chain="optimism_sepolia",
                        to_chain="base_sepolia",
                        amount=amount
                    )
                        
                    if tx_hash_op_to_base:
                        log().success(f"Optimism to Base bridge successful: {tx_hash_op_to_base[:10]}...")
                        
                        # Wait for bridge to complete
                        log().info("Waiting for bridge completion...")
                        bridge_service.wait_for_completion(tx_hash_op_to_base)
                    else:
                        log().error("Optimism to Base bridge failed")
                else:
                    log().error("Base to Optimism bridge completion failed or timed out")
            else:
                log().error("Base to Optimism bridge transaction failed")
                # Add a delay before attempting next bridge
                delay_time = 60
                log().info(f"Waiting {delay_time} seconds before next attempt...")
                
                # Wait with timeout check
                for _ in range(delay_time):
                    if shutdown_event.is_set():
                        log().info("Shutdown requested, stopping wallet processing")
                        return
                    time.sleep(1)
            
    except Exception as e:
        log().error(f"Error processing wallet: {str(e)}")
        log().error(traceback.format_exc())

def worker_thread():
    """Worker thread function to process wallets from the queue."""
    # Initialize thread-local context for this thread
    set_wallet_context("")
    
    thread_id = threading.get_ident()
    log().debug(f"Worker thread {thread_id} started")
    
    while not shutdown_event.is_set():
        try:
            # Get a wallet from the queue with a timeout
            try:
                wallet_info = wallet_queue.get(timeout=1)
            except queue.Empty:
                # Queue is empty, check if we should exit
                continue
            
            # Process the wallet
            process_wallet(wallet_info)
            
            # Mark task as done
            wallet_queue.task_done()
            
            # Apply delay between wallets
            config_data = wallet_info["config"]
            delay_time = config_data['delay']['between_wallets']
            
            # Reset wallet context for general logging
            set_wallet_context("")
            log().info(f"Waiting {delay_time} seconds before next wallet")
            
            # Wait with timeout check
            for _ in range(delay_time):
                if shutdown_event.is_set():
                    break
                time.sleep(1)
            
        except Exception as e:
            # Reset wallet context for error logging
            set_wallet_context("")
            log().error(f"Error in worker thread: {str(e)}")
            
            # Mark task as done in case of error
            try:
                wallet_queue.task_done()
            except:
                pass
    
    log().debug(f"Worker thread {thread_id} finished")

def main():
    """Main application entry point."""
    # Display banner
    display_banner()
    
    # Setup logger
    setup_logger()
    
    # Load configuration
    config = ConfigManager()
    config_data = config.get_config()
    
    # Initialize proxy manager if needed
    proxy_manager = ProxyManager(config_data["use_proxy"])
    
    # Read private keys
    private_keys = read_private_keys()
    logger.info(f"Loaded {len(private_keys)} wallets")
    
    try:
        while True:
            # Reset shutdown event
            shutdown_event.clear()
            
            # Get thread count from config (default to 1 if not specified)
            thread_count = config_data.get("thread_count", 1)
            logger.info(f"Using {thread_count} threads for processing")
            
            # Fill the wallet queue
            for i, private_key in enumerate(private_keys):
                wallet_queue.put({
                    "private_key": private_key,
                    "index": i,
                    "total_wallets": len(private_keys),
                    "proxy": proxy_manager.get_proxy(i) if config_data["use_proxy"] else None,
                    "config": config_data
                })
            
            # Create and start worker threads
            threads = []
            for _ in range(min(thread_count, len(private_keys))):
                thread = threading.Thread(target=worker_thread, daemon=True)
                threads.append(thread)
                thread.start()
            
            try:
                # Wait for all tasks to complete
                wallet_queue.join()
                
                # Signal threads to terminate
                shutdown_event.set()
                
                # Wait for all threads to finish with timeout
                for thread in threads:
                    thread.join(timeout=5.0)
                    
                # Delay before restarting
                delay_hours = config_data['delay']['after_completion'] // 3600
                logger.info(f"All wallets processed. Waiting {delay_hours} hours before restarting")
                
                # Simple countdown
                total_seconds = config_data["delay"]["after_completion"]
                for remaining in range(total_seconds, 0, -30):
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    seconds = remaining % 60
                    logger.info(f"Next run in: {hours:02d}:{minutes:02d}:{seconds:02d}")
                    time.sleep(min(30, remaining))
            except KeyboardInterrupt:
                # Handle keyboard interrupt
                logger.info("Keyboard interrupt detected, shutting down...")
                shutdown_event.set()
                
                # Wait for threads to terminate
                for thread in threads:
                    thread.join(timeout=5.0)
                
                break
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
    finally:
        # Make sure to signal shutdown
        shutdown_event.set()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()