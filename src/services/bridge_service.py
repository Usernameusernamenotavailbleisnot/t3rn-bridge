import time
import json
import random
from web3 import Web3
import requests
from loguru import logger

from src.services.web3_service import Web3Service
from src.constants.constants import API_ENDPOINTS, TX_STATUS
from src.utils.retry import retry_with_backoff

class BridgeService:
    """Service for interacting with the t3rn bridge."""
    
    def __init__(self, private_key, config, proxy=None):
        """Initialize bridge service."""
        self.private_key = private_key
        self.config = config
        self.proxy = proxy
        self.web3_service = Web3Service(private_key, config, proxy)
        self.api_base_url = config["api"]["base_url"]
        self.wallet_address = self.web3_service.get_account_address()
    
    def get_wallet_address(self):
        """Get wallet address."""
        return self.wallet_address
    
    @retry_with_backoff
    def get_price(self, chain, token, amount_wei):
        """Get price in USD for the given amount of token on the specified chain."""
        url = f"{self.api_base_url}{API_ENDPOINTS['price'].format(chain=chain, token=token, amount=amount_wei)}"
        
        try:
            response = requests.get(
                url, 
                timeout=self.config["api"]["timeout"],
                proxies=self.proxy
            )
            response.raise_for_status()
            return float(response.text)
        except requests.RequestException as e:
            logger.error(f"Error getting price: {str(e)}")
            raise
    
    @retry_with_backoff
    def estimate_bridge(self, from_chain, to_chain, amount_wei):
        """
        Estimate bridge transaction.
        
        Args:
            from_chain (str): Source chain name
            to_chain (str): Destination chain name
            amount_wei (str): Amount in wei
            
        Returns:
            dict: Estimation data including fees and expected output
        """
        url = f"{self.api_base_url}{API_ENDPOINTS['estimate']}"
        
        from_chain_config = self.config["chains"][from_chain]
        to_chain_config = self.config["chains"][to_chain]
        
        payload = {
            "fromAsset": "eth",
            "toAsset": "eth",
            "fromChain": from_chain_config["api_name"],
            "toChain": to_chain_config["api_name"],
            "amountWei": amount_wei,
            "executorTipUSD": 0,
            "overpayOptionPercentage": 0,
            "spreadOptionPercentage": 0
        }
        
        logger.debug(f"Estimate payload: {payload}")
        
        try:
            response = requests.post(
                url, 
                json=payload,
                timeout=self.config["api"]["timeout"],
                proxies=self.proxy
            )
            response.raise_for_status()
            estimate_data = response.json()
            logger.debug(f"Estimate response: {json.dumps(estimate_data, indent=2)}")
            return estimate_data
        except requests.RequestException as e:
            logger.error(f"Error estimating bridge: {str(e)}")
            raise
    
    def bridge(self, from_chain, to_chain, amount):
        """
        Bridge ETH from one chain to another using the t3rn bridge.
        
        Args:
            from_chain (str): Source chain name
            to_chain (str): Destination chain name
            amount (float): Amount to bridge in ETH
            
        Returns:
            str or None: Transaction hash if successful, None if failed
        """
        logger.info(f"Preparing to bridge {amount} ETH from {from_chain} to {to_chain}")
        
        # Convert amount to Wei
        amount_wei = Web3.to_wei(amount, 'ether')
        amount_wei_str = str(amount_wei)
        
        # Get chain configurations
        from_chain_config = self.config["chains"][from_chain]
        to_chain_config = self.config["chains"][to_chain]
        
        # Get price in USD
        usd_price = self.get_price(from_chain_config["api_name"], "eth", amount_wei_str)
        logger.info(f"Current ETH value: ${usd_price:.2f}")
        
        # Get bridge estimate
        estimate = self.estimate_bridge(from_chain, to_chain, amount_wei_str)
        
        # Method ID for the bridge function (0x56591d59)
        method_id = "0x56591d59"
        
        # Prepare bridge contract address
        bridge_contract = from_chain_config["bridge_contract"]
        
        # Format destination chain (from HAR file format)
        dest_chain = to_chain_config["api_name"]
        dest_chain_bytes = dest_chain.encode('utf-8').ljust(32, b'\0')
        dest_chain_hex = dest_chain_bytes.hex()
        
        # Format wallet address (target)
        target_address = self.wallet_address.lower()[2:]  # Remove '0x' prefix
        target_address_padded = '0' * (64 - len(target_address)) + target_address
        
        # Get amount from estimate (to ensure correct formatting)
        # If estimatedReceivedAmountWei is available, use it, otherwise use the original amount
        if "estimatedReceivedAmountWei" in estimate and estimate["estimatedReceivedAmountWei"].get("hex"):
            # Amount comes from the estimate response as hex
            amount_hex = estimate["estimatedReceivedAmountWei"]["hex"][2:]  # Remove '0x'
        else:
            # Fallback to original amount
            amount_hex = hex(amount_wei)[2:]  # Remove '0x'
            
        amount_padded = '0' * (64 - len(amount_hex)) + amount_hex
        
        # Zero padding (as per HAR file)
        zeros_padding = '0' * 64
        
        # Format max reward (from estimate or fixed)
        if "maxReward" in estimate and estimate["maxReward"].get("hex"):
            max_reward_hex = estimate["maxReward"]["hex"][2:]  # Remove '0x'
        else:
            # Fallback to a fixed amount (0.2 ETH)
            max_reward_hex = "02c68af0bb140000"
            
        max_reward_padded = '0' * (64 - len(max_reward_hex)) + max_reward_hex
        
        # Build the complete calldata (based on HAR file)
        calldata = (
            method_id +
            dest_chain_hex +
            zeros_padding +  # First padding
            target_address_padded +
            amount_padded +
            zeros_padding +  # Second padding
            zeros_padding +  # Third padding
            max_reward_padded
        )
        
        # Get gas price (from estimate or dynamically)
        if "gasPrice" in estimate:
            gas_price = int(estimate.get("gasPrice", 0))
        else:
            gas_price = self.web3_service.get_gas_price(from_chain)
            
        gas_price_with_multiplier = int(gas_price * self.config["bridge"]["gas_multiplier"])
        
        # Get nonce
        nonce = self.web3_service.get_nonce(from_chain)
        
        # Build transaction
        tx = {
            "from": self.wallet_address,
            "to": bridge_contract,
            "value": amount_wei,
            "gas": 136229,  # Use a reasonable gas limit from HAR file
            "gasPrice": gas_price_with_multiplier,
            "nonce": nonce,
            "chainId": from_chain_config["chain_id"],
            "data": calldata
        }
        
        logger.debug(f"Transaction data: {calldata}")
        
        # Send transaction
        tx_hash = self.web3_service.send_transaction(from_chain, tx)
        
        # Check if transaction was successful
        if tx_hash:
            # Verify transaction status
            is_successful = self.web3_service.verify_transaction(from_chain, tx_hash)
            
            if not is_successful:
                logger.error(f"Transaction failed: {tx_hash}")
                return None
                
            return tx_hash
        
        return None
    
    @retry_with_backoff
    def get_order_status(self, order_id):
        """Get order status."""
        url = f"{self.api_base_url}{API_ENDPOINTS['order'].format(order_id=order_id)}"
        
        try:
            response = requests.get(
                url, 
                timeout=self.config["api"]["timeout"],
                proxies=self.proxy
            )
            
            if response.status_code == 404:
                return None
                
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error getting order status: {str(e)}")
            raise
    
    def wait_for_completion(self, tx_hash, max_attempts=60, delay=5):
        """
        Wait for bridge transaction to complete.
        
        Args:
            tx_hash (str): Transaction hash
            max_attempts (int): Maximum number of attempts
            delay (int): Delay between attempts in seconds
            
        Returns:
            bool: True if completed, False otherwise
        """
        if not tx_hash:
            logger.error("No transaction hash provided - cannot wait for completion")
            return False
            
        logger.info(f"Waiting for bridge transaction {tx_hash[:10]}... to complete")
        
        for attempt in range(max_attempts):
            try:
                order_status = self.get_order_status(tx_hash)
                
                if not order_status:
                    logger.info(f"Order not found yet. Waiting... ({attempt+1}/{max_attempts})")
                    time.sleep(delay)
                    continue
                
                status = order_status.get("status")
                
                if status == TX_STATUS["EXECUTED"]:
                    logger.success(f"Bridge transaction completed: {tx_hash[:10]}...")
                    return True
                elif status == TX_STATUS["FAILED"]:
                    logger.error(f"Bridge transaction failed: {tx_hash[:10]}...")
                    return False
                else:
                    logger.info(f"Bridge status: {status}. Waiting... ({attempt+1}/{max_attempts})")
            except Exception as e:
                logger.error(f"Error checking order status: {str(e)}")
            
            time.sleep(delay)
        
        logger.warning(f"Max attempts reached. Transaction may still be in progress: {tx_hash[:10]}...")
        return False