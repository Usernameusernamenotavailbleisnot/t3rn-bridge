"""
Utilities for thread-safe operations with proxy support.
"""
import threading
import requests
from loguru import logger

# Thread-local storage for thread-specific resources
_thread_local = threading.local()

class SessionManager:
    """Manages thread-specific HTTP sessions with proxy support."""
    
    @staticmethod
    def get_session(proxy=None):
        """
        Get a thread-specific requests session with optional proxy.
        Creates a new session if one doesn't exist.
        
        Args:
            proxy (dict, optional): Proxy configuration to use for this session
            
        Returns:
            requests.Session: A session specific to the current thread
        """
        # Create session attribute if it doesn't exist
        if not hasattr(_thread_local, 'http_session'):
            logger.debug(f"Creating new HTTP session for thread {threading.get_ident()}")
            _thread_local.http_session = requests.Session()
            
            # Set default headers if needed
            _thread_local.http_session.headers.update({
                "accept": "*/*",
                "content-type": "application/json",
                "origin": "https://unlock3d.t3rn.io",
                "referer": "https://unlock3d.t3rn.io/"
            })
        
        # If proxy is provided, update the session's proxies
        if proxy:
            _thread_local.http_session.proxies = proxy
        
        return _thread_local.http_session

    @staticmethod
    def close_sessions():
        """Close the session for the current thread if it exists."""
        if hasattr(_thread_local, 'http_session'):
            logger.debug(f"Closing HTTP session for thread {threading.get_ident()}")
            _thread_local.http_session.close()
            delattr(_thread_local, 'http_session')


class Web3ConnectionManager:
    """Manages thread-specific Web3 connections."""
    
    @staticmethod
    def get_web3_connections():
        """
        Get thread-specific web3 connections dictionary.
        Creates a new dictionary if one doesn't exist.
        
        Returns:
            dict: A dictionary of web3 connections specific to the current thread
        """
        if not hasattr(_thread_local, 'web3_connections'):
            logger.debug(f"Creating new Web3 connections container for thread {threading.get_ident()}")
            _thread_local.web3_connections = {}
        
        return _thread_local.web3_connections
    
    @staticmethod
    def close_connections():
        """Clean up web3 connections for the current thread if they exist."""
        if hasattr(_thread_local, 'web3_connections'):
            logger.debug(f"Cleaning up Web3 connections for thread {threading.get_ident()}")
            # There's no explicit close method for Web3 connections,
            # but we can remove the reference to let the GC handle it
            delattr(_thread_local, 'web3_connections')