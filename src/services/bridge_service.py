import time
import json
import random
import threading
from web3 import Web3
import requests
from loguru import logger
import traceback
from datetime import datetime
import sys

from src.services.web3_service import Web3Service
from src.constants.constants import API_ENDPOINTS, TX_STATUS, STATUS_DESCRIPTIONS, SUCCESS_STATUSES, REFUND_STATUSES, FAILED_STATUSES
from src.utils.retry import retry_with_backoff
from src.utils.logger import log
from src.utils.thread_safe import SessionManager
from hexbytes import HexBytes

# Thread-safe lock for status updates
status_lock = threading.RLock()

class BridgeService:
    """Service for interacting with the t3rn bridge."""
    
    def __init__(self, private_key, config, proxy=None):
        """Initialize bridge service."""
        self.private_key = private_key
        self.config = config
        
        # Store proxy with proper handling for tuple format
        if isinstance(proxy, tuple) and len(proxy) == 2:
            self.proxy_dict, self.proxy_url = proxy
        else:
            self.proxy_dict = proxy
            self.proxy_url = None if proxy is None else proxy.get("http") if isinstance(proxy, dict) else None
            
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
            # Get the thread-specific session with proxy
            session = SessionManager.get_session(self.proxy_dict)
            
            response = session.get(
                url, 
                timeout=self.config["api"]["timeout"]
            )
            response.raise_for_status()
            return float(response.text)
        except requests.RequestException as e:
            log().error(f"Error getting price: {str(e)}")
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
        
        log().debug(f"Estimate payload: {payload}")
        
        try:
            # Get the thread-specific session with proxy
            session = SessionManager.get_session(self.proxy_dict)
            
            response = session.post(
                url, 
                json=payload,
                timeout=self.config["api"]["timeout"]
            )
            response.raise_for_status()
            estimate_data = response.json()
            log().debug(f"Estimate response: {json.dumps(estimate_data, indent=2)}")
            return estimate_data
        except requests.RequestException as e:
            log().error(f"Error estimating bridge: {str(e)}")
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
        # Make sure amount has limited decimal places (max 5)
        amount = round(amount, 5)
        
        log().info(f"Preparing to bridge {amount} ETH from {from_chain} to {to_chain}")
        
        # Convert amount to Wei
        amount_wei = Web3.to_wei(amount, 'ether')
        amount_wei_str = str(amount_wei)
        
        # Get chain configurations
        from_chain_config = self.config["chains"][from_chain]
        to_chain_config = self.config["chains"][to_chain]
        
        # Get price in USD
        usd_price = self.get_price(from_chain_config["api_name"], "eth", amount_wei_str)
        log().info(f"Current ETH value: ${usd_price:.2f}")
        
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
            # Use the actual bridge amount as max reward instead of hardcoded value
            max_reward_hex = hex(amount_wei)[2:]  # Convert to hex and remove '0x'
            
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
        
        # Build initial transaction without gas limit for estimation
        tx_for_estimation = {
            "from": self.wallet_address,
            "to": bridge_contract,
            "value": amount_wei,
            "gasPrice": gas_price_with_multiplier,
            "nonce": nonce,
            "chainId": from_chain_config["chain_id"],
            "data": calldata
        }
        
        # Estimate gas for this transaction
        estimated_gas = self.web3_service.estimate_gas(from_chain, tx_for_estimation)
        
        # Build final transaction with estimated gas
        tx = {
            "from": self.wallet_address,
            "to": bridge_contract,
            "value": amount_wei,
            "gas": estimated_gas,
            "gasPrice": gas_price_with_multiplier,
            "nonce": nonce,
            "chainId": from_chain_config["chain_id"],
            "data": calldata
        }
        
        log().debug(f"Transaction data: {calldata}")
        
        # Send transaction
        tx_hash = self.web3_service.send_transaction(from_chain, tx)
        
        # Check if transaction was successful
        if tx_hash:
            # Verify transaction status
            is_successful = self.web3_service.verify_transaction(from_chain, tx_hash)
            
            if not is_successful:
                log().error(f"Transaction failed: {tx_hash}")
                return None
                
            return tx_hash
        
        return None
    
    @retry_with_backoff
    def get_order_status(self, order_id):
        """Get order status."""
        url = f"{self.api_base_url}{API_ENDPOINTS['order'].format(order_id=order_id)}"
        
        try:
            # Get the thread-specific session with proxy
            session = SessionManager.get_session(self.proxy_dict)
            
            response = session.get(
                url, 
                timeout=self.config["api"]["timeout"]
            )
            
            if response.status_code == 404:
                return None
                
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            log().error(f"Error getting order status: {str(e)}")
            raise
    
    def extract_order_id_from_receipt(self, chain_name, tx_hash):
        """
        Extract order ID from transaction receipt logs.
        
        Args:
            chain_name (str): Chain name
            tx_hash (str): Transaction hash
            
        Returns:
            str or None: Order ID if found, None otherwise
        """
        try:
            # Get transaction receipt
            receipt = self.web3_service.get_transaction_receipt(chain_name, tx_hash)
            
            if not receipt or not hasattr(receipt, 'logs') or not receipt.logs:
                log().error(f"No logs found in transaction receipt: {tx_hash[:10]}...")
                return None
            
            # The order ID is in the first topic[1] of the first log with the specific event signature
            # The signature is 0x3bb399125b923176baf5098f432689e4843dee54b68daf1d7cadd91d99a63601
            target_event_signature = "0x3bb399125b923176baf5098f432689e4843dee54b68daf1d7cadd91d99a63601"
            
            # Convert the signature to bytes if needed
            if not isinstance(target_event_signature, bytes) and target_event_signature.startswith('0x'):
                target_event_signature_bytes = HexBytes(target_event_signature)
            else:
                target_event_signature_bytes = HexBytes(target_event_signature)
            
            for log_entry in receipt.logs:
                if hasattr(log_entry, 'topics') and len(log_entry.topics) >= 2:
                    # Convert log topic to string for comparison if needed
                    topic_0 = log_entry.topics[0]
                    
                    if topic_0 == target_event_signature_bytes:
                        # The second topic contains the order ID
                        order_id = log_entry.topics[1].hex()
                        log().info(f"Extracted order ID from logs: {order_id}")
                        return order_id
            
            # Try alternative event signature if first one fails
            # Some contracts use different event signatures
            for log_entry in receipt.logs:
                if hasattr(log_entry, 'topics') and len(log_entry.topics) >= 2:
                    order_id = log_entry.topics[1].hex()
                    log().info(f"Extracted possible order ID from logs (alternative method): {order_id}")
                    return order_id
            
            log().error(f"Order ID not found in transaction logs for tx: {tx_hash[:10]}...")
            return None
        except Exception as e:
            log().error(f"Error extracting order ID from receipt: {str(e)}")
            log().error(traceback.format_exc())
            return None
    
    def wait_for_completion(self, tx_hash, max_attempts=60, delay=5, timeout_minutes=15, source_chain=None):
        """
        Wait for bridge transaction to complete with improved error handling and timeouts.
        
        Args:
            tx_hash (str): Transaction hash
            max_attempts (int): Maximum number of attempts for status checks
            delay (int): Delay between attempts in seconds
            timeout_minutes (int): Overall timeout in minutes to prevent indefinite waiting
            source_chain (str, optional): Source chain where the transaction was initiated
            
        Returns:
            bool: True if completed, False otherwise
        """
        if not tx_hash:
            log().error("No transaction hash provided - cannot wait for completion")
            return False
            
        log().info(f"Waiting for bridge transaction {tx_hash[:10]}... to complete")
        
        # Calculate overall timeout
        timeout_seconds = timeout_minutes * 60
        start_time = time.time()
        
        # Determine the source chain
        from_chain = source_chain
        if not from_chain:
            # Try to determine which chain the transaction is on
            for chain_name in self.config["chains"]:
                try:
                    receipt = self.web3_service.get_transaction_receipt(chain_name, tx_hash)
                    if receipt and receipt.status == 1:
                        from_chain = chain_name
                        log().info(f"Determined transaction source chain: {from_chain}")
                        break
                except Exception as e:
                    log().debug(f"Error checking receipt on {chain_name}: {str(e)}")
                    continue
        
            if not from_chain:
                log().error(f"Could not determine source chain for tx: {tx_hash[:10]}...")
                # Try to find the most recently used chain
                from_chain = "base_sepolia"  # Default fallback
                log().warning(f"Using fallback source chain: {from_chain}")
        else:
            log().info(f"Using provided source chain: {from_chain}")
        
        # Determine destination chain based on the source chain
        to_chain = "optimism_sepolia" if from_chain == "base_sepolia" else "base_sepolia"
        
        # Add a timeout for extracting order ID to prevent getting stuck
        extract_attempts = 3
        order_id = None
        
        for attempt in range(extract_attempts):
            try:
                order_id = self.extract_order_id_from_receipt(from_chain, tx_hash)
                if order_id:
                    break
                time.sleep(2)  # Short delay between attempts
            except Exception as e:
                log().error(f"Error extracting order ID (attempt {attempt+1}/{extract_attempts}): {str(e)}")
                time.sleep(2)
        
        if not order_id:
            log().error(f"Failed to extract order ID after {extract_attempts} attempts: {tx_hash[:10]}...")
            return False
        
        log().info(f"Monitoring order ID: {order_id[:10]}... for completion")
        
        # Track the last status to avoid repeated updates
        last_status = None
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        # Track time spent in unknown status
        unknown_status_start = None
        unknown_status_timeout = 120  # 2 minutes in unknown status before considering successful
        
        # Function to check for transaction confirmation on the destination chain
        def check_destination_confirmation():
            try:
                # Format the order ID properly for API call if needed
                order_id_str = order_id
                if isinstance(order_id, HexBytes):
                    order_id_str = order_id.hex()
                elif isinstance(order_id, str) and not order_id.startswith('0x'):
                    order_id_str = '0x' + order_id
                    
                # Get order status to check confirmation TX hash
                order_status = self.get_order_status(order_id_str)
                if order_status and "confirmationTxHash" in order_status:
                    conf_tx_hash = order_status["confirmationTxHash"]
                    if conf_tx_hash:
                        # Check if transaction exists on destination chain
                        receipt = self.web3_service.get_transaction_receipt(to_chain, conf_tx_hash)
                        if receipt and receipt.status == 1:
                            log().success(f"Confirmed transaction on destination chain: {conf_tx_hash[:10]}...")
                            return True
                return False
            except Exception as e:
                log().error(f"Error checking destination chain confirmation: {str(e)}")
                return False
        
        for attempt in range(max_attempts):
            # Check overall timeout
            if time.time() - start_time > timeout_seconds:
                log().error(f"Overall timeout of {timeout_minutes} minutes reached for order: {order_id[:10]}...")
                return False
                
            try:
                # First, check if we can confirm the transaction on the destination chain directly
                if attempt % 4 == 0 and attempt > 8:  # Check every 4th attempt after the 8th attempt
                    if check_destination_confirmation():
                        log().success(f"Transaction confirmed directly on destination chain for order: {order_id[:10]}...")
                        return True
                        
                # Ensure order_id is a string with correct format for API
                order_id_str = order_id
                if isinstance(order_id, HexBytes):
                    order_id_str = order_id.hex()
                elif isinstance(order_id, str) and not order_id.startswith('0x'):
                    order_id_str = '0x' + order_id
                
                order_status = self.get_order_status(order_id_str)
                
                # Reset consecutive error counter on successful API call
                consecutive_errors = 0
                
                if not order_status:
                    current_status = "Placed"  # Assume it's placed but not yet registered in API
                    
                    # Only update the status if it changed
                    if current_status != last_status:
                        status_desc = STATUS_DESCRIPTIONS.get(current_status, "Unknown status")
                        log().info(f"Order status: {current_status} : {status_desc} ({attempt+1}/{max_attempts})")
                        last_status = current_status
                else:
                    current_status = order_status.get("status")
                    
                    # Only update the status if it changed
                    if current_status != last_status:
                        # Get description or use "Unknown status" if not defined
                        status_desc = STATUS_DESCRIPTIONS.get(current_status, "Unknown status")
                        log().info(f"Order status: {current_status} : {status_desc} ({attempt+1}/{max_attempts})")
                        
                        # If we encounter an unknown status, record when we first saw it
                        if status_desc == "Unknown status" and unknown_status_start is None:
                            unknown_status_start = time.time()
                            log().warning(f"Encountered unknown status '{current_status}'. Will monitor for {unknown_status_timeout}s")
                        elif status_desc != "Unknown status":
                            # Reset unknown status tracking if we see a known status
                            unknown_status_start = None
                            
                        last_status = current_status
                    
                    # Check if the unknown status has persisted long enough
                    if unknown_status_start is not None and time.time() - unknown_status_start > unknown_status_timeout:
                        # Check the transaction on the destination chain directly
                        if check_destination_confirmation():
                            log().success(f"Status '{current_status}' persisted and transaction confirmed on destination chain")
                            return True
                        else:
                            log().info(f"Status '{current_status}' persisted but couldn't confirm on destination chain. Continuing to monitor.")
                            # Reset the unknown status timer to check again later
                            unknown_status_start = time.time()
                    
                    # Check if we've reached a terminal status
                    if current_status in SUCCESS_STATUSES:
                        log().success(f"Bridge transaction completed successfully: {order_id[:10]}...")
                        return True
                    elif current_status in REFUND_STATUSES:
                        # Special handling for EXPIRED status - check if it was actually executed first
                        if current_status == "Expired" and "executionTxHash" in order_status and order_status["executionTxHash"]:
                            log().info(f"Transaction marked as Expired but has execution hash: {order_status['executionTxHash'][:10]}...")
                            if check_destination_confirmation():
                                log().success(f"Expired order confirmed on destination chain. Considering successful.")
                                return True
                        
                        log().warning(f"Bridge transaction eligible for refund: {order_id[:10]}...")
                        # Continue monitoring to see if it transitions to a refund state
                    elif current_status in FAILED_STATUSES:
                        log().error(f"Bridge transaction failed: {order_id[:10]}...")
                        return False
            except Exception as e:
                consecutive_errors += 1
                log().error(f"Error checking order status (attempt {attempt+1}, error #{consecutive_errors}): {str(e)}")
                
                # If we've had too many consecutive errors, abort to prevent getting stuck
                if consecutive_errors >= max_consecutive_errors:
                    log().error(f"Too many consecutive errors ({consecutive_errors}). Aborting order monitoring.")
                    return False
            
            # Sleep before the next attempt
            time.sleep(delay)
        
        log().warning(f"Max attempts reached. Transaction may still be in progress: {order_id[:10]}...")
        
        # Last chance - check if the transaction went through on the destination chain
        if check_destination_confirmation():
            log().success(f"Final check: Transaction confirmed on destination chain for order: {order_id[:10]}...")
            return True
            
        return False