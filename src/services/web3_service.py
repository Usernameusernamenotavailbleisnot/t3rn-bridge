from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.providers.rpc import HTTPProvider
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse
from loguru import logger
from eth_account import Account
import time
import traceback
from hexbytes import HexBytes

from src.utils.thread_safe import Web3ConnectionManager
from src.utils.retry import retry_with_backoff
from src.utils.logger import log

class ProxiedHTTPProvider(HTTPProvider):
    """Custom HTTP Provider with proxy support."""
    
    def __init__(self, endpoint_uri, proxy_url=None, request_kwargs=None, **kwargs):
        self.proxy_url = proxy_url
        # Make sure request_kwargs exists and has a timeout
        if request_kwargs is None:
            request_kwargs = {}
        if 'timeout' not in request_kwargs:
            request_kwargs['timeout'] = 30  # Default timeout
        
        # Initialize parent class with our request_kwargs
        super().__init__(endpoint_uri, request_kwargs=request_kwargs, **kwargs)
    
    def make_request(self, method, params):
        self.logger.debug("Making request HTTP. URI: %s, Method: %s",
                     self.endpoint_uri, method)
        
        request_data = self.encode_rpc_request(method, params)
        
        session = requests.Session()
        if self.proxy_url:
            session.proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url
            }
        
        # Access _request_kwargs (with underscore) and get timeout
        timeout = self._request_kwargs.get('timeout', 30)
        
        raw_response = session.post(
            self.endpoint_uri,
            data=request_data,
            headers=self.get_request_headers(),
            timeout=timeout
        )
        
        response = self.decode_rpc_response(raw_response.content)
        return response

class Web3Service:
    """Service for interacting with Web3."""
    
    def __init__(self, private_key, config, proxy=None):
        """Initialize Web3 service."""
        self.private_key = private_key
        self.config = config
        
        # Store both proxy dict and proxy URL
        if isinstance(proxy, tuple) and len(proxy) == 2:
            self.proxy_dict, self.proxy_url = proxy
        else:
            self.proxy_dict = proxy
            self.proxy_url = None if proxy is None else proxy.get("http") if isinstance(proxy, dict) else None
            
        self.account = Account.from_key(private_key)
    
    def get_account_address(self):
        """Get account address from private key."""
        return self.account.address
    
    def get_web3(self, chain_name):
        """Get Web3 connection for the specified chain."""
        # Get thread-specific web3 connections dictionary
        web3_connections = Web3ConnectionManager.get_web3_connections()
        
        # Check if connection exists for this chain in the current thread
        if chain_name in web3_connections:
            return web3_connections[chain_name]
        
        chain_config = self.config["chains"].get(chain_name)
        if not chain_config:
            raise ValueError(f"Chain configuration for {chain_name} not found")
        
        rpc_url = chain_config["rpc_url"]
        
        # Initialize Web3 with proxy if available
        if self.proxy_url:
            log().debug(f"Creating Web3 connection for {chain_name} using proxy")
            provider = ProxiedHTTPProvider(
                rpc_url, 
                proxy_url=self.proxy_url,
                request_kwargs={'timeout': 30}
            )
            web3 = Web3(provider)
        else:
            web3 = Web3(Web3.HTTPProvider(rpc_url))
            
        web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Verify connection
        if not web3.is_connected():
            log().error(f"Failed to connect to {chain_name} RPC at {rpc_url}")
            raise ConnectionError(f"Failed to connect to {chain_name} RPC")
        
        # Cache connection in thread-local storage
        web3_connections[chain_name] = web3
        
        return web3
    
    @retry_with_backoff
    def get_gas_price(self, chain_name):
        """Get current gas price for the specified chain."""
        web3 = self.get_web3(chain_name)
        gas_price = web3.eth.gas_price
        log().debug(f"Current gas price on {chain_name}: {gas_price} wei")
        return gas_price
    
    @retry_with_backoff
    def estimate_gas(self, chain_name, tx_params):
        """
        Estimate gas needed for a transaction.
        
        Args:
            chain_name (str): Chain name
            tx_params (dict): Transaction parameters
            
        Returns:
            int: Estimated gas amount
            
        Raises:
            Exception: Passes through any error from the chain to allow specific handling
        """
        web3 = self.get_web3(chain_name)
        
        # Create a copy of tx_params without the gas parameter
        tx_for_estimation = {k: v for k, v in tx_params.items() if k != 'gas'}
        
        try:
            estimated_gas = web3.eth.estimate_gas(tx_for_estimation)
            # Add a small buffer to ensure transaction success (10%)
            gas_with_buffer = int(estimated_gas * 1.1)
            log().debug(f"Estimated gas on {chain_name}: {estimated_gas} (with buffer: {gas_with_buffer})")
            return gas_with_buffer
        except Exception as e:
            # Log the error but don't catch it - let it propagate up
            error_message = str(e)
            log().error(f"Error estimating gas on {chain_name}: {error_message}")
            
            # Important: Re-raise the original exception to allow specific error handling
            raise
    
    @retry_with_backoff
    def get_nonce(self, chain_name):
        """Get current nonce for the account on the specified chain."""
        web3 = self.get_web3(chain_name)
        nonce = web3.eth.get_transaction_count(self.account.address)
        log().debug(f"Current nonce on {chain_name}: {nonce}")
        return nonce
    
    @retry_with_backoff
    def get_balance(self, chain_name):
        """Get account balance on the specified chain."""
        web3 = self.get_web3(chain_name)
        balance_wei = web3.eth.get_balance(self.account.address)
        balance_eth = web3.from_wei(balance_wei, 'ether')
        log().info(f"Balance on {chain_name}: {balance_eth} ETH")
        return balance_wei
    
    @retry_with_backoff
    def get_transaction_receipt(self, chain_name, tx_hash):
        """
        Get transaction receipt for a transaction hash.
        
        Args:
            chain_name (str): Chain name
            tx_hash (str): Transaction hash
            
        Returns:
            dict or None: Transaction receipt if successful, None otherwise
        """
        web3 = self.get_web3(chain_name)
        
        try:
            # Ensure tx_hash is properly formatted
            if isinstance(tx_hash, str) and not tx_hash.startswith('0x'):
                tx_hash = '0x' + tx_hash
                
            receipt = web3.eth.get_transaction_receipt(tx_hash)
            return receipt
        except Exception as e:
            log().error(f"Error getting transaction receipt on {chain_name}: {str(e)}")
            return None
    
    @retry_with_backoff
    def send_transaction(self, chain_name, transaction):
        """
        Sign and send a transaction.
        
        Args:
            chain_name (str): Chain name
            transaction (dict): Transaction object
            
        Returns:
            str or None: Transaction hash if successful, None otherwise
        """
        web3 = self.get_web3(chain_name)
        
        # Check if we have enough balance
        balance = self.get_balance(chain_name)
        required = transaction.get('value', 0) + (transaction.get('gas', 0) * transaction.get('gasPrice', 0))
        
        if balance < required:
            log().error(f"Insufficient balance on {chain_name}. Have: {web3.from_wei(balance, 'ether')} ETH, Need: {web3.from_wei(required, 'ether')} ETH")
            return None
        
        # Create a more concise log message
        to_addr = transaction.get('to', 'N/A')
        to_addr_short = f"{to_addr[:6]}...{to_addr[-4:]}" if to_addr and len(to_addr) > 10 else to_addr
        value_eth = web3.from_wei(transaction.get('value', 0), 'ether')
        gas_price_gwei = web3.from_wei(transaction.get('gasPrice', 0), 'gwei')
        gas_limit = transaction.get('gas', 0)
        
        # Log a more concise transaction message
        log().info(
            f"Tx: {chain_name} | To: {to_addr_short} | Value: {value_eth} ETH | Gas: {gas_price_gwei} Gwei | Limit: {gas_limit}"
        )
        
        try:
            # Sign transaction
            signed_tx = web3.eth.account.sign_transaction(transaction, self.private_key)
            
            # Send transaction
            tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Convert to hex string
            tx_hash_hex = web3.to_hex(tx_hash)
            
            log().success(f"Transaction sent: {tx_hash_hex}")
            
            # Wait for transaction to be mined
            try:
                log().info(f"Waiting for transaction {tx_hash_hex[:10]}... to be mined")
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120, poll_latency=2)
                
                if receipt.status == 1:
                    log().success(f"Transaction {tx_hash_hex[:10]}... mined successfully in block {receipt.blockNumber}")
                    return tx_hash_hex
                else:
                    log().error(f"Transaction {tx_hash_hex[:10]}... failed with status: {receipt.status}")
                    
                    # Try to get failure reason
                    try:
                        # Replay the transaction to get the revert reason
                        tx = web3.eth.get_transaction(tx_hash)
                        err_msg = "Unknown reason"
                        
                        try:
                            web3.eth.call(
                                {
                                    'to': tx['to'],
                                    'from': tx['from'],
                                    'data': tx['input'],
                                    'value': tx['value'],
                                    'gas': tx['gas'],
                                    'gasPrice': tx['gasPrice'],
                                    'nonce': tx['nonce']
                                },
                                block_identifier=receipt.blockNumber
                            )
                        except Exception as call_err:
                            err_msg = str(call_err)
                        
                        log().error(f"Transaction failed reason: {err_msg}")
                    except Exception as err:
                        log().error(f"Could not determine failure reason: {str(err)}")
                    
                    return None
            except Exception as wait_err:
                log().error(f"Error waiting for transaction: {str(wait_err)}")
                # Transaction may still have been sent, return hash for further checks
                return tx_hash_hex
                
        except Exception as e:
            log().error(f"Error sending transaction: {str(e)}")
            return None
        
    def verify_transaction(self, chain_name, tx_hash, timeout=120):
        """
        Verify transaction status.
        
        Args:
            chain_name (str): Chain name
            tx_hash (str): Transaction hash
            timeout (int): Timeout in seconds
            
        Returns:
            bool: True if successful, False otherwise
        """
        web3 = self.get_web3(chain_name)
        
        try:
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return receipt.status == 1
        except Exception as e:
            log().error(f"Error verifying transaction: {str(e)}")
            return False
