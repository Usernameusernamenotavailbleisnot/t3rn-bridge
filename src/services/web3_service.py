from web3 import Web3
from web3.middleware import geth_poa_middleware
from loguru import logger
from eth_account import Account
import time

from src.utils.retry import retry_with_backoff

class Web3Service:
    """Service for interacting with Web3."""
    
    def __init__(self, private_key, config, proxy=None):
        """Initialize Web3 service."""
        self.private_key = private_key
        self.config = config
        self.proxy = proxy
        self.web3_connections = {}
        self.account = Account.from_key(private_key)
    
    def get_account_address(self):
        """Get account address from private key."""
        return self.account.address
    
    def get_web3(self, chain_name):
        """Get Web3 connection for the specified chain."""
        if chain_name in self.web3_connections:
            return self.web3_connections[chain_name]
        
        chain_config = self.config["chains"].get(chain_name)
        if not chain_config:
            raise ValueError(f"Chain configuration for {chain_name} not found")
        
        rpc_url = chain_config["rpc_url"]
        
        # Initialize Web3
        web3 = Web3(Web3.HTTPProvider(rpc_url))
        web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Verify connection
        if not web3.is_connected():
            logger.error(f"Failed to connect to {chain_name} RPC at {rpc_url}")
            raise ConnectionError(f"Failed to connect to {chain_name} RPC")
        
        # Cache connection
        self.web3_connections[chain_name] = web3
        
        return web3
    
    @retry_with_backoff
    def get_gas_price(self, chain_name):
        """Get current gas price for the specified chain."""
        web3 = self.get_web3(chain_name)
        gas_price = web3.eth.gas_price
        logger.debug(f"Current gas price on {chain_name}: {gas_price} wei")
        return gas_price
    
    @retry_with_backoff
    def get_nonce(self, chain_name):
        """Get current nonce for the account on the specified chain."""
        web3 = self.get_web3(chain_name)
        nonce = web3.eth.get_transaction_count(self.account.address)
        logger.debug(f"Current nonce on {chain_name}: {nonce}")
        return nonce
    
    @retry_with_backoff
    def get_balance(self, chain_name):
        """Get account balance on the specified chain."""
        web3 = self.get_web3(chain_name)
        balance_wei = web3.eth.get_balance(self.account.address)
        balance_eth = web3.from_wei(balance_wei, 'ether')
        logger.info(f"Balance on {chain_name}: {balance_eth} ETH")
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
            logger.error(f"Error getting transaction receipt on {chain_name}: {str(e)}")
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
            logger.error(f"Insufficient balance on {chain_name}. Have: {web3.from_wei(balance, 'ether')} ETH, Need: {web3.from_wei(required, 'ether')} ETH")
            return None
        
        # Log transaction details (masked for privacy)
        masked_tx = dict(transaction)
        if "data" in masked_tx and len(str(masked_tx["data"])) > 20:
            data_str = str(masked_tx["data"])
            masked_tx["data"] = f"{data_str[:10]}...{data_str[-8:]}"
        masked_tx['value'] = web3.from_wei(masked_tx.get('value', 0), 'ether')
        masked_tx['gasPrice'] = web3.from_wei(masked_tx.get('gasPrice', 0), 'gwei')
        
        logger.info(f"Sending transaction on {chain_name}: {masked_tx}")
        
        try:
            # Sign transaction
            signed_tx = web3.eth.account.sign_transaction(transaction, self.private_key)
            
            # Send transaction
            tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Convert to hex string
            tx_hash_hex = web3.to_hex(tx_hash)
            
            logger.success(f"Transaction sent: {tx_hash_hex}")
            
            # Wait for transaction to be mined
            try:
                logger.info(f"Waiting for transaction {tx_hash_hex[:10]}... to be mined")
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120, poll_latency=2)
                
                if receipt.status == 1:
                    logger.success(f"Transaction {tx_hash_hex[:10]}... mined successfully in block {receipt.blockNumber}")
                    return tx_hash_hex
                else:
                    logger.error(f"Transaction {tx_hash_hex[:10]}... failed with status: {receipt.status}")
                    
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
                        
                        logger.error(f"Transaction failed reason: {err_msg}")
                    except Exception as err:
                        logger.error(f"Could not determine failure reason: {str(err)}")
                    
                    return None
            except Exception as wait_err:
                logger.error(f"Error waiting for transaction: {str(wait_err)}")
                # Transaction may still have been sent, return hash for further checks
                return tx_hash_hex
                
        except Exception as e:
            logger.error(f"Error sending transaction: {str(e)}")
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
            logger.error(f"Error verifying transaction: {str(e)}")
            return False