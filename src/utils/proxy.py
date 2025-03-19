import os
import re
from loguru import logger

class ProxyManager:
    """Manager for handling proxies with improved authentication support."""
    
    def __init__(self, use_proxy):
        """Initialize proxy manager."""
        self.use_proxy = use_proxy
        self.proxies = []
        
        if use_proxy:
            self._load_proxies()
    
    def _load_proxies(self):
        """Load proxies from proxy.txt file."""
        try:
            if not os.path.exists("proxy.txt"):
                logger.warning("proxy.txt file not found! Running without proxies.")
                self.use_proxy = False
                return
            
            with open("proxy.txt", "r") as file:
                proxies = [line.strip() for line in file.readlines() if line.strip() and not line.strip().startswith('#')]
            
            if not proxies:
                logger.warning("No proxies found in proxy.txt! Running without proxies.")
                self.use_proxy = False
                return
            
            self.proxies = proxies
            logger.info(f"Loaded {len(proxies)} proxies")
        except Exception as e:
            logger.error(f"Error loading proxies: {str(e)}")
            self.use_proxy = False
    
    def format_proxy_url(self, proxy_url):
        """
        Format proxy URL with proper handling of authentication.
        
        Args:
            proxy_url (str): Raw proxy URL (e.g., user:pw@ip:port)
            
        Returns:
            str: Properly formatted proxy URL with protocol
        """
        # Check if the URL already has a protocol
        if not any(proxy_url.startswith(p) for p in ["http://", "https://", "socks4://", "socks5://"]):
            # Check if it has authentication format (user:pw@ip:port)
            if '@' in proxy_url and ':' in proxy_url:
                # This appears to be a proxy with authentication
                proxy_url = f"http://{proxy_url}"
            else:
                # Just a normal IP:PORT format
                proxy_url = f"http://{proxy_url}"
                
        return proxy_url
    
    def get_proxy(self, index):
        """
        Get proxy configuration for the given index.
        
        Args:
            index (int): Index of the wallet
            
        Returns:
            tuple: (proxy_dict, proxy_url) or (None, None) if no proxy is used
                - proxy_dict: Dictionary for requests library
                - proxy_url: Formatted URL for Web3 provider
        """
        if not self.use_proxy or not self.proxies:
            return None, None
        
        proxy_index = index % len(self.proxies)
        raw_proxy_url = self.proxies[proxy_index]
        
        # Format proxy URL for HTTP requests
        formatted_proxy_url = self.format_proxy_url(raw_proxy_url)
        
        # Create proxy dict for requests library
        proxy_dict = {
            "http": formatted_proxy_url,
            "https": formatted_proxy_url
        }
        
        # Also return the formatted URL for Web3 provider
        return proxy_dict, formatted_proxy_url