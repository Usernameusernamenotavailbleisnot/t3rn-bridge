import time
import os
import sys
import random
import threading
import queue
import traceback
import signal
from loguru import logger

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config_manager import ConfigManager
from src.services.bridge_service import BridgeService
from src.utils.logger import setup_logger, get_masked_address, set_wallet_context, log
from src.utils.retry import retry_with_backoff
from src.utils.proxy import ProxyManager
from src.utils.thread_safe import SessionManager, Web3ConnectionManager
from src.utils.animations import (
    display_banner,
    display_processing_animation
)

# Create a thread-safe queue for wallets
wallet_queue = queue.Queue()

# Global event to signal threads to terminate
shutdown_event = threading.Event()

def signal_handler(sig, frame):
    """Handle Ctrl+C properly"""
    logger.info("\nKeyboard interrupt detected (Ctrl+C). Shutting down gracefully...")
    # Set shutdown event to signal all threads to terminate
    shutdown_event.set()
    logger.info("Waiting for threads to terminate (max 5 seconds)...")
    
    # Allow up to 5 seconds for threads to terminate gracefully
    exit_timer = threading.Timer(5.0, force_exit)
    exit_timer.daemon = True
    exit_timer.start()

def force_exit():
    """Force exit if threads won't terminate gracefully"""
    logger.error("Timeout waiting for threads to terminate. Forcing exit.")
    sys.exit(1)

# Register signal handler for keyboard interrupt
signal.signal(signal.SIGINT, signal_handler)

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
    """Process a single wallet with custom bridge flow."""
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
        
        # Set a maximum time for processing this wallet (e.g., 45 minutes)
        wallet_timeout = 45 * 60  # 45 minutes in seconds
        wallet_start_time = time.time()
        
        for j in range(config_data["bridge"]["repeat_count"]):
            # Check if shutdown has been requested
            if shutdown_event.is_set():
                log().info("Shutdown requested, stopping wallet processing")
                return
                
            # Check wallet timeout
            if time.time() - wallet_start_time > wallet_timeout:
                log().warning(f"Wallet processing timeout reached after {wallet_timeout//60} minutes")
                return
                
            # Random amount within configured range, but with limited decimal places (5 max)
            min_amount = config_data["bridge"]["amount"]["min"]
            max_amount = config_data["bridge"]["amount"]["max"]
            
            # Generate a random amount with at most 5 decimal places
            amount = round(random.uniform(min_amount, max_amount), 5)
            
            log().info(f"Bridge attempt {j+1}/{config_data['bridge']['repeat_count']}")
            
            # Use custom bridge flow if configured
            if config_data["bridge"].get("custom_flow", False) and "bridge_paths" in config_data["bridge"]:
                bridge_paths = config_data["bridge"]["bridge_paths"]
                log().info(f"Using custom bridge flow with {len(bridge_paths)} paths")
                
                # Process each bridge path
                for i, path in enumerate(bridge_paths):
                    from_chain = path["from_chain"]
                    to_chain = path["to_chain"]
                    
                    # Log transaction info
                    log().info(f"Bridge {i+1}/{len(bridge_paths)}: {amount} ETH from {from_chain} to {to_chain}")
                    
                    # Set a timeout for this specific bridge operation
                    bridge_timeout = 20 * 60  # 20 minutes in seconds
                    bridge_start_time = time.time()
                    
                    # Perform the bridge
                    tx_hash = bridge_service.bridge(
                        from_chain=from_chain,
                        to_chain=to_chain,
                        amount=amount
                    )
                    
                    if tx_hash:
                        log().success(f"{from_chain} to {to_chain} bridge initiated: {tx_hash[:10]}...")
                        
                        # Check if we should wait for completion
                        if config_data["bridge"].get("wait_for_completion", True):
                            log().info("Waiting for bridge completion...")
                            
                            # Check bridge timeout
                            remaining_timeout = max(10, wallet_timeout - int(time.time() - wallet_start_time))
                            timeout_minutes = min(15, remaining_timeout // 60)
                            
                            bridge_completed = bridge_service.wait_for_completion(
                                tx_hash=tx_hash,
                                timeout_minutes=timeout_minutes,
                                source_chain=from_chain  # Pass the source chain
                            )
                            
                            if not bridge_completed:
                                log().error(f"Bridge from {from_chain} to {to_chain} failed or timed out")
                                # Consider if you want to continue or break the loop
                                # For now, we'll continue to the next bridge path
                    else:
                        log().error(f"Bridge from {from_chain} to {to_chain} transaction failed")
                    
                    # Delay between bridges if not the last bridge
                    if i < len(bridge_paths) - 1:
                        delay_time = config_data['delay'].get('between_bridges', 30)
                        log().info(f"Waiting {delay_time} seconds before next bridge...")
                        
                        # Wait with timeout check
                        for _ in range(delay_time):
                            if shutdown_event.is_set():
                                log().info("Shutdown requested, stopping wallet processing")
                                return
                            
                            # Check wallet timeout
                            if time.time() - wallet_start_time > wallet_timeout:
                                log().warning(f"Wallet processing timeout reached during delay")
                                return
                                
                            time.sleep(1)
            else:
                # Use default bridge flow (Base Sepolia <-> Optimism Sepolia)
                # First bridge: Base Sepolia to Optimism Sepolia
                from_chain_1 = "base_sepolia"
                to_chain_1 = "optimism_sepolia"
                
                # Log transaction info
                log().info(f"Bridging {amount} ETH from {from_chain_1} to {to_chain_1}")
                
                # Set a timeout for this specific bridge operation
                bridge_timeout = 20 * 60  # 20 minutes in seconds
                bridge_start_time = time.time()
                
                # Perform Base Sepolia to Optimism Sepolia bridge
                tx_hash_base_to_op = bridge_service.bridge(
                    from_chain=from_chain_1,
                    to_chain=to_chain_1,
                    amount=amount
                )
                
                if tx_hash_base_to_op:
                    log().success(f"{from_chain_1} to {to_chain_1} bridge successful: {tx_hash_base_to_op[:10]}...")
                    
                    # Wait for bridge to complete only if configured to do so
                    if config_data["bridge"].get("wait_for_completion", True):
                        log().info("Waiting for bridge completion...")
                        
                        # Check bridge timeout
                        remaining_timeout = max(10, wallet_timeout - int(time.time() - wallet_start_time))
                        timeout_minutes = min(15, remaining_timeout // 60)
                        
                        bridge_completed = bridge_service.wait_for_completion(
                            tx_hash=tx_hash_base_to_op,
                            timeout_minutes=timeout_minutes,
                            source_chain=from_chain_1  # Pass the source chain
                        )
                        
                        if bridge_completed:
                            # Second bridge: Optimism Sepolia to Base Sepolia
                            from_chain_2 = "optimism_sepolia"
                            to_chain_2 = "base_sepolia"
                                
                            # Perform Optimism Sepolia to Base Sepolia bridge
                            log().info(f"Bridging {amount} ETH from {from_chain_2} to {to_chain_2}")
                            tx_hash_op_to_base = bridge_service.bridge(
                                from_chain=from_chain_2,
                                to_chain=to_chain_2,
                                amount=amount
                            )
                                
                            if tx_hash_op_to_base:
                                log().success(f"{from_chain_2} to {to_chain_2} bridge successful: {tx_hash_op_to_base[:10]}...")
                                
                                # Wait for bridge to complete with a timeout, passing the source chain
                                if config_data["bridge"].get("wait_for_completion", True):
                                    log().info("Waiting for bridge completion...")
                                    
                                    # Calculate remaining timeout
                                    remaining_timeout = max(10, wallet_timeout - int(time.time() - wallet_start_time))
                                    timeout_minutes = min(15, remaining_timeout // 60)
                                    
                                    bridge_service.wait_for_completion(
                                        tx_hash=tx_hash_op_to_base,
                                        timeout_minutes=timeout_minutes,
                                        source_chain=from_chain_2  # Pass the source chain
                                    )
                            else:
                                log().error(f"{from_chain_2} to {to_chain_2} bridge failed")
                        else:
                            log().error(f"{from_chain_1} to {to_chain_1} bridge completion failed or timed out")
                    else:
                        # Don't wait for completion, directly proceed to the return bridge
                        delay_time = config_data['delay'].get('between_bridges', 30)
                        log().info(f"Not waiting for confirmation, delaying {delay_time} seconds before return bridge...")
                        time.sleep(delay_time)
                        
                        # Second bridge: Optimism Sepolia to Base Sepolia
                        from_chain_2 = "optimism_sepolia"
                        to_chain_2 = "base_sepolia"
                            
                        # Perform Optimism Sepolia to Base Sepolia bridge
                        log().info(f"Bridging {amount} ETH from {from_chain_2} to {to_chain_2}")
                        tx_hash_op_to_base = bridge_service.bridge(
                            from_chain=from_chain_2,
                            to_chain=to_chain_2,
                            amount=amount
                        )
                            
                        if tx_hash_op_to_base:
                            log().success(f"{from_chain_2} to {to_chain_2} bridge successful: {tx_hash_op_to_base[:10]}...")
                            
                            # Wait for bridge to complete with a timeout, passing the source chain
                            if config_data["bridge"].get("wait_for_completion", True):
                                log().info("Waiting for bridge completion...")
                                
                                # Calculate remaining timeout
                                remaining_timeout = max(10, wallet_timeout - int(time.time() - wallet_start_time))
                                timeout_minutes = min(15, remaining_timeout // 60)
                                
                                bridge_service.wait_for_completion(
                                    tx_hash=tx_hash_op_to_base,
                                    timeout_minutes=timeout_minutes,
                                    source_chain=from_chain_2  # Pass the source chain
                                )
                        else:
                            log().error(f"{from_chain_2} to {to_chain_2} bridge failed")
                else:
                    log().error(f"{from_chain_1} to {to_chain_1} bridge transaction failed")
                    # Add a delay before attempting next bridge
                    delay_time = 60
                    log().info(f"Waiting {delay_time} seconds before next attempt...")
                    
                    # Wait with timeout check
                    for _ in range(delay_time):
                        if shutdown_event.is_set():
                            log().info("Shutdown requested, stopping wallet processing")
                            return
                        
                        # Check wallet timeout
                        if time.time() - wallet_start_time > wallet_timeout:
                            log().warning(f"Wallet processing timeout reached during delay")
                            return
                            
                        time.sleep(1)
            
    except Exception as e:
        log().error(f"Error processing wallet: {str(e)}")
        log().error(traceback.format_exc())

def worker_thread():
    """Worker thread function to process wallets from the queue."""
    try:
        # Initialize thread-local context for this thread
        set_wallet_context("")
        
        thread_id = threading.get_ident()
        log().debug(f"Worker thread {thread_id} started")
        
        while not shutdown_event.is_set():
            try:
                # Get a wallet from the queue with a SHORT timeout (this is crucial for Ctrl+C responsiveness)
                try:
                    wallet_info = wallet_queue.get(timeout=0.5)  # Short timeout - 0.5 seconds
                except queue.Empty:
                    # Queue is empty or timeout, check if we should exit
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
                
                # Wait with frequent checks for shutdown event (key for Ctrl+C responsiveness)
                start_time = time.time()
                while time.time() - start_time < delay_time:
                    if shutdown_event.is_set():
                        break
                    time.sleep(min(0.5, delay_time))  # Sleep in small increments
                
            except Exception as e:
                # Reset wallet context for error logging
                set_wallet_context("")
                log().error(f"Error in worker thread: {str(e)}")
                
                # Mark task as done in case of error
                try:
                    wallet_queue.task_done()
                except:
                    pass
                
            # Add brief sleep to allow keyboard interrupt to be processed
            time.sleep(0.1)
    finally:
        # Clean up thread-specific resources when thread exits
        SessionManager.close_sessions()
        Web3ConnectionManager.close_connections()
        log().debug(f"Worker thread {thread_id} finished and resources cleaned up")

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
            
            # Get the initial queue size to track completion
            queued_wallets = len(private_keys)
            
            # Fill the wallet queue
            for i, private_key in enumerate(private_keys):
                # Get proxy for this wallet, both as dict and url
                proxy_pair = proxy_manager.get_proxy(i) if config_data["use_proxy"] else (None, None)
                
                wallet_queue.put({
                    "private_key": private_key,
                    "index": i,
                    "total_wallets": len(private_keys),
                    "proxy": proxy_pair,
                    "config": config_data
                })
            
            # Create and start worker threads
            threads = []
            for _ in range(min(thread_count, len(private_keys))):
                thread = threading.Thread(target=worker_thread, daemon=True)
                threads.append(thread)
                thread.start()
            
            try:
                # Wait for all tasks to complete or KeyboardInterrupt
                # Use a polling approach instead of queue.join() with timeout
                completed = False
                while not completed and not shutdown_event.is_set():
                    # Sleep briefly to avoid consuming CPU
                    time.sleep(0.5)
                    
                    # Check if queue is empty AND all tasks have been marked as done
                    # This is equivalent to what queue.join() does but allows us to check shutdown_event
                    if wallet_queue.empty() and wallet_queue.unfinished_tasks == 0:
                        completed = True
                    
                if shutdown_event.is_set():
                    logger.info("Shutdown event detected, cleaning up...")
                else:
                    logger.info("All wallet processing completed.")
                
                # Signal threads to terminate
                shutdown_event.set()
                
                # Wait for all threads to finish with timeout
                for thread in threads:
                    thread.join(timeout=5.0)
                    
                if shutdown_event.is_set() and hasattr(shutdown_event, "_exit_requested"):
                    # This is an explicit shutdown, not a normal completion
                    logger.info("Exiting program due to shutdown request")
                    break
                    
                # Delay before restarting
                delay_hours = config_data['delay']['after_completion'] // 3600
                logger.info(f"All wallets processed. Waiting {delay_hours} hours before restarting")
                
                # Simple countdown with better Ctrl+C responsiveness
                total_seconds = config_data["delay"]["after_completion"]
                start_time = time.time()
                while time.time() - start_time < total_seconds:
                    if shutdown_event.is_set():
                        break
                        
                    remaining = total_seconds - int(time.time() - start_time)
                    if remaining <= 0:
                        break
                        
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    seconds = remaining % 60
                    
                    # Only update log periodically to avoid spam
                    if remaining % 30 == 0:
                        logger.info(f"Next run in: {hours:02d}:{minutes:02d}:{seconds:02d}")
                    
                    # Sleep in small chunks to remain responsive to Ctrl+C
                    time.sleep(0.5)
                    
                if shutdown_event.is_set():
                    logger.info("Restart interrupted, exiting program")
                    break
                    
            except KeyboardInterrupt:
                # Handle keyboard interrupt explicitly
                logger.info("Keyboard interrupt detected, shutting down...")
                setattr(shutdown_event, "_exit_requested", True)
                shutdown_event.set()
                
                # Wait for threads to terminate
                for thread in threads:
                    thread.join(timeout=5.0)
                
                break
    except Exception as e:
        logger.error(f"Error in main loop: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        # Make sure to signal shutdown
        shutdown_event.set()
        logger.info("Application shutdown complete")
        sys.exit(0)

if __name__ == "__main__":
    main()
