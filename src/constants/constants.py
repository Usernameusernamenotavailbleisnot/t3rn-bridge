"""
Constants used throughout the application.
"""

# API Endpoints
API_ENDPOINTS = {
    "price": "/prices/usd/{chain}/{token}/{amount}",
    "estimate": "/estimate",
    "order": "/order/{order_id}"
}

# Transaction Status
TX_STATUS = {
    "PENDING": "Pending",
    "BID": "Bid",
    "EXECUTED": "Executed",
    "FAILED": "Failed"
}

# Headers
DEFAULT_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://unlock3d.t3rn.io",
    "referer": "https://unlock3d.t3rn.io/"
}

# Request Timeout (seconds)
DEFAULT_TIMEOUT = 30

# Gas limits
DEFAULT_GAS_LIMIT = 135000

# Banner text
BANNER_TEXT = """
████████╗██████╗ ██████╗ ███╗   ██╗
╚══██╔══╝╚════██╗██╔══██╗████╗  ██║
   ██║    █████╔╝██████╔╝██╔██╗ ██║
   ██║   ██╔═══╝ ██╔══██╗██║╚██╗██║
   ██║   ███████╗██║  ██║██║ ╚████║
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝
     Bridge Testnet Automation
"""