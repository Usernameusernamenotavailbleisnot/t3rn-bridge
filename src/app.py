import time
import os
import sys
import random
from loguru import logger

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.config_manager import ConfigManager
from src.services.bridge_service import BridgeService
from src.utils.logger import setup_logger, get_masked_address
from src.utils.retry import retry_with_backoff
from src.utils.proxy import ProxyManager
from src.utils.animations import (
    display_banner,
    display_processing_animation
)

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
    
    while True:
        for i, private_key in enumerate(private_keys):
            # Get proxy for this wallet if enabled
            proxy = proxy_manager.get_proxy(i) if config_data["use_proxy"] else None
            
            try:
                # Initialize bridge service
                bridge_service = BridgeService(
                    private_key=private_key,
                    config=config_data,
                    proxy=proxy
                )
                
                # Get wallet address
                wallet_address = bridge_service.get_wallet_address()
                masked_address = get_masked_address(wallet_address)
                logger.info(f"Processing wallet {masked_address} ({i+1}/{len(private_keys)})")
                
                for j in range(config_data["bridge"]["repeat_count"]):
                    # Random amount within configured range, but with limited decimal places (5 max)
                    min_amount = config_data["bridge"]["amount"]["min"]
                    max_amount = config_data["bridge"]["amount"]["max"]
                    
                    # Generate a random amount with at most 5 decimal places
                    amount = round(random.uniform(min_amount, max_amount), 5)
                    
                    logger.info(f"Bridge attempt {j+1}/{config_data['bridge']['repeat_count']}")
                    
                    # Log transaction info
                    logger.info(f"Bridging {amount} ETH from Base Sepolia to Optimism Sepolia")
                    
                    # Perform Base Sepolia to Optimism Sepolia bridge
                    tx_hash_base_to_op = bridge_service.bridge(
                        from_chain="base_sepolia",
                        to_chain="optimism_sepolia",
                        amount=amount
                    )
                    
                    if tx_hash_base_to_op:
                        logger.success(f"Base to Optimism bridge successful: {tx_hash_base_to_op[:10]}...")
                        
                        # Wait for bridge to complete
                        logger.info("Waiting for bridge completion...")
                        bridge_completed = bridge_service.wait_for_completion(tx_hash_base_to_op)
                        
                        if bridge_completed:
                            # Perform Optimism Sepolia to Base Sepolia bridge
                            logger.info(f"Bridging {amount} ETH from Optimism Sepolia to Base Sepolia")
                            tx_hash_op_to_base = bridge_service.bridge(
                                from_chain="optimism_sepolia",
                                to_chain="base_sepolia",
                                amount=amount
                            )
                                
                            if tx_hash_op_to_base:
                                logger.success(f"Optimism to Base bridge successful: {tx_hash_op_to_base[:10]}...")
                                
                                # Wait for bridge to complete
                                logger.info("Waiting for bridge completion...")
                                bridge_service.wait_for_completion(tx_hash_op_to_base)
                            else:
                                logger.error("Optimism to Base bridge failed")
                        else:
                            logger.error("Base to Optimism bridge completion failed or timed out")
                    else:
                        logger.error("Base to Optimism bridge transaction failed")
                        # Add a delay before attempting next bridge
                        delay_time = 60
                        logger.info(f"Waiting {delay_time} seconds before next attempt...")
                        time.sleep(delay_time)
                    
            except Exception as e:
                logger.error(f"Error processing wallet {masked_address}: {str(e)}")
            
            # Delay between wallets
            if i < len(private_keys) - 1:
                delay_time = config_data['delay']['between_wallets']
                logger.info(f"Waiting {delay_time} seconds before next wallet")
                time.sleep(delay_time)
        
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

if __name__ == "__main__":
    main()