# T3RN Bridge Testnet Automation

A Python automation tool for bridging ETH between Base Sepolia and Optimism Sepolia testnets using t3rn's bridge protocol.

## Overview

This application automates the process of bridging ETH tokens between Base Sepolia and Optimism Sepolia testnets. It supports:

- Multi-wallet processing from a list of private keys
- Configurable bridging parameters (amounts, gas multipliers, etc.)
- Robust transaction monitoring and status tracking
- Multi-threaded operation for parallel wallet processing
- Optional proxy support for network requests
- Detailed logging and error handling

## Features

- **Bidirectional Bridging**: Automatically bridges ETH from Base Sepolia to Optimism Sepolia and back
- **Multiple Wallet Support**: Process multiple wallets in sequence or parallel
- **Automated Retries**: Built-in retry mechanism with exponential backoff
- **Transaction Monitoring**: Tracks bridge transaction status through the entire process
- **Thread Safety**: Designed for concurrent operation with thread-local resources
- **Configurable Parameters**: Customize amounts, delays, gas settings via configuration

## Prerequisites

- Python 3.8+
- Virtual environment (venv)
- Ethereum wallet(s) with testnet ETH on Base Sepolia
- Internet connection

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/Usernameusernamenotavailbleisnot/t3rn-bridge.git
   cd t3rn-bridge
   ```

2. Create and activate a virtual environment (mandatory):
   ```
   # Create virtual environment
   python -m venv venv
   
   # Activate virtual environment
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up your configuration files:
   - `config.json`: Bridge configuration parameters
   - `pk.txt`: List of private keys (one per line)
   - `proxy.txt` (optional): List of proxies (one per line)

## Configuration

### config.json

```json
{
  "use_proxy": false,
  "thread_count": 2,
  "retries": {
    "max_attempts": 3,
    "backoff_factor": 2,
    "initial_wait": 1
  },
  "bridge": {
    "repeat_count": 2,
    "amount": {
      "min": 0.11,
      "max": 0.15
    },
    "gas_multiplier": 1.1
  },
  "delay": {
    "between_wallets": 60,
    "after_completion": 90000
  },
  "chains": {
    "base_sepolia": {
      "chain_id": 84532,
      "rpc_url": "https://sepolia.base.org",
      "bridge_contract": "0xCEE0372632a37Ba4d0499D1E2116eCff3A17d3C3",
      "api_name": "bast"
    },
    "optimism_sepolia": {
      "chain_id": 11155420,
      "rpc_url": "https://sepolia.optimism.io",
      "bridge_contract": "0xb6Def636914Ae60173d9007E732684a9eEDEF26E",
      "api_name": "opst"
    }
  },
  "api": {
    "base_url": "https://api.t2rn.io",
    "timeout": 30
  }
}
```

### Private Keys (pk.txt)

Store your private keys in a file named `pk.txt`, one key per line. You can add comments by starting a line with `#`.

Example:
```
# Wallet 1
0x123abc...
# Wallet 2
0x456def...
```

### Proxies (proxy.txt) - Optional

Store your proxies in a file named `proxy.txt`, one proxy per line.

Supported proxy formats:
- IP:PORT
- user:password@IP:PORT
- http://IP:PORT
- socks5://user:password@IP:PORT

Example:
```
# Proxy 1
192.168.1.1:8080
# Proxy 2
user:pass@192.168.1.2:8080
```

## Usage

Make sure your virtual environment is activated, then run the main application:

```
# Ensure venv is activated
# On Windows: venv\Scripts\activate
# On macOS/Linux: source venv/bin/activate

python -m src.app
```

The application will:
1. Load your private keys from `pk.txt`
2. Process each wallet in sequence (or in parallel based on thread count)
3. Bridge ETH from Base Sepolia to Optimism Sepolia
4. Wait for the bridge to complete
5. Bridge ETH back from Optimism Sepolia to Base Sepolia
6. Repeat based on configuration settings

## Process Flow

1. For each wallet:
   - Initialize bridge service with wallet's private key
   - Bridge ETH from Base Sepolia to Optimism Sepolia
   - Monitor bridge transaction status
   - After completion, bridge ETH back from Optimism Sepolia to Base Sepolia
   - Monitor return bridge transaction status
   - Wait for specified delay before processing next wallet

2. After all wallets are processed:
   - Wait for the configured delay
   - Restart the process if running in continuous mode

## Logging

Logs are stored in the `logs` directory with timestamps. The application provides detailed logging for each operation, including:
- Transaction hashes
- Bridge status updates
- Error details with retry information
- Wallet processing status

## Error Handling

The application includes robust error handling:
- Automatic retries with exponential backoff
- Transaction validation
- Timeout protection
- Error logging with stack traces

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is provided for educational and testing purposes only. Use at your own risk. Always review the code before running automated crypto transactions.
