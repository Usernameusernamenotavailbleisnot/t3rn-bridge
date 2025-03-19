import os
from loguru import logger

class ProxyManager:
    """Manager for handling proxies."""
    
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
                proxies = [line.strip() for line in file.readlines() if line.strip()]
            
            if not proxies:
                logger.warning("No proxies found in proxy.txt! Running without proxies.")
                self.use_proxy = False
                return
            
            self.proxies = proxies
            logger.info(f"Loaded {len(proxies)} proxies")
        except Exception as e:
            logger.error(f"Error loading proxies: {str(e)}")
            self.use_proxy = False
    
    def get_proxy(self, index):
        """
        Get proxy configuration for the given index.
        
        Args:
            index (int): Index of the wallet
            
        Returns:
            dict or None: Proxy configuration for requests
        """
        if not self.use_proxy or not self.proxies:
            return None
        
        proxy_index = index % len(self.proxies)
        proxy_url = self.proxies[proxy_index]
        
        # Format proxy URL
        if not proxy_url.startswith("http"):
            if "://" in proxy_url:
                protocol = proxy_url.split("://")[0]
                proxy_url = f"{protocol}://{proxy_url.split('://')[1]}"
            else:
                proxy_url = f"http://{proxy_url}"
        
        return {
            "http": proxy_url,
            "https": proxy_url
        }