import json
import os
from loguru import logger

class ConfigManager:
    """Configuration manager for the application."""
    
    def __init__(self, config_path="config.json"):
        """Initialize configuration manager."""
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON file."""
        try:
            if not os.path.exists(self.config_path):
                logger.error(f"Configuration file {self.config_path} not found!")
                raise FileNotFoundError(f"Configuration file {self.config_path} not found!")
            
            with open(self.config_path, "r") as file:
                config = json.load(file)
            
            return config
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in configuration file {self.config_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            raise
    
    def get_config(self):
        """Get the configuration."""
        return self.config
    
    def get_chain_config(self, chain_name):
        """Get configuration for a specific chain."""
        chains = self.config.get("chains", {})
        chain_config = chains.get(chain_name)
        
        if not chain_config:
            logger.error(f"Configuration for chain {chain_name} not found!")
            raise ValueError(f"Configuration for chain {chain_name} not found!")
        
        return chain_config
    
    def get_api_config(self):
        """Get API configuration."""
        api_config = self.config.get("api", {})
        
        if not api_config:
            logger.error("API configuration not found!")
            raise ValueError("API configuration not found!")
        
        return api_config