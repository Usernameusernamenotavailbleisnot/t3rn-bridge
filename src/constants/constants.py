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
    "PLACED": "Placed",
    "PENDING": "Pending",
    "BID": "Bid",
    "EXECUTED": "Executed",
    "ATTESTED": "Attested",
    "CLAIMED": "Claimed",
    "CLAIMED_INSURANCE": "ClaimedInsurance",  # Added new status
    "EXPIRED": "Expired",
    "PENDING_REFUND": "Pending Refund",
    "ATTESTED_REFUND": "Attested Refund",
    "CLAIMED_REFUND": "Claimed Refund",
    "FAILED": "Failed"
}

# Status Colors for Terminal Output
STATUS_COLORS = {
    "Placed": "white",
    "Pending": "light_pink",
    "Bid": "magenta",
    "Executed": "purple",
    "Attested": "light_blue",
    "Claimed": "green",
    "ClaimedInsurance": "green",  # Added new status
    "Expired": "light_gray",
    "Pending Refund": "light_pink",
    "Attested Refund": "light_blue",
    "Claimed Refund": "green",
    "Failed": "red"
}

# Status Descriptions
STATUS_DESCRIPTIONS = {
    "Placed": "The order has been received and is now in the queue, awaiting processing.",
    "Pending": "The order is now on the Layer 3 network, awaiting bids.",
    "Bid": "The order has now been bid by an executor. It is ready to be executed.",
    "Executed": "The order has been executed.",
    "Attested": "The order has been attested.",
    "Claimed": "The reward for carrying out this order has been claimed by an executor.",
    "ClaimedInsurance": "The insurance for this order has been claimed and the transaction is complete.",  # Added new status
    "Expired": "The order exceeded 30 min and moved to expired. It will be checked if it was executed or qualifies for a refund.",
    "Pending Refund": "The order was not fulfilled in a timely manner. The account that placed the order has not yet requested a refund.",
    "Attested Refund": "The refund has been attested.",
    "Claimed Refund": "The order was not fulfilled in a timely manner. A refund has been initiated for the account that placed the order.",
    "Failed": "The order has failed to process."
}

# Success Statuses (transaction considered complete)
SUCCESS_STATUSES = ["Executed", "Attested", "Claimed", "ClaimedInsurance"]  # Added ClaimedInsurance to success statuses

# Refund Statuses (transaction eligible for refund)
REFUND_STATUSES = ["Expired", "Pending Refund", "Attested Refund", "Claimed Refund"]

# Failed Status (transaction failed)
FAILED_STATUSES = ["Failed"]

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

# Token asset codes
ASSET_CODES = {
    "eth": 0,
    "t3eth": 1,
    "bnb": 2,
    "sol": 3,
    "btc": 4,
    "dot": 100,
    "usdc": 101,
    "usdt": 102,
    "dai": 103,
    "t3usd": 104,
    "fil": 199,
    "mon": 200,
    "t3mon": 201,
    "sei": 500,
    "t3sei": 501,
    "trn": 3333,
    "brn": 3343,
    "lorn": 3330,
    "tia": 4948,
    "t3tia": 4949,
    "t3dot": 1000,
    "t3sol": 2000,
    "t3btc": 5000,
    "ukn": -1
}

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
