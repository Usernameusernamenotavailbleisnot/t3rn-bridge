# T3RN Bridge Testnet Automation

A Python automation tool for bridging ETH between multiple testnets using t3rn's bridge protocol.

## Overview

This application automates the process of bridging ETH tokens between various testnets, including Base Sepolia, Optimism Sepolia, Arbitrum Sepolia, Blast Sepolia, and Unichain Sepolia. The tool supports creating custom bridging paths, allowing you to sequence multiple bridge operations across different networks.

## Features

- **Multi-Network Support**: Bridge between Base Sepolia, Optimism Sepolia, Arbitrum Sepolia, Blast Sepolia, and Unichain Sepolia
- **Custom Bridge Flows**: Define your own bridging paths and sequences
- **Optional Confirmation Waiting**: Choose whether to wait for bridge confirmations between operations
- **Multi-Wallet Processing**: Process multiple wallets in sequence or parallel
- **Robust Error Handling**: Specific handling for common bridge errors (like RO#7)
- **Smart Retries**: Exponential backoff and targeted retry strategies
- **Proxy Support**: Route requests through HTTP or SOCKS proxies

## Prerequisites

- Python 3.8+
- Virtual environment (venv)
- Ethereum wallet(s) with testnet ETH on at least one supported network
- Internet connection

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/Usernameusernamenotavailbleisnot/t3rn-bridge.git
   cd t3rn-bridge
   ```

2. Create and activate a virtual environment:
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

4. Set up configuration files:
   - `config.json`: Bridge configuration (see Configuration section)
   - `pk.txt`: List of private keys (one per line)
   - `proxy.txt` (optional): List of proxies (one per line)

## Configuration

### config.json

The `config.json` file has been expanded to support custom bridge flows and multiple networks:

```json
{
  "use_proxy": true,
  "thread_count": 1,
  "retries": {
    "max_attempts": 5,
    "backoff_factor": 2,
    "initial_wait": 1
  },
  "bridge": {
    "repeat_count": 1,
    "amount": {
      "min": 3.1,
      "max": 3.2
    },
    "gas_multiplier": 1.1,
    "wait_for_completion": false,
    "custom_flow": true,
    "bridge_paths": [
      {
        "from_chain": "base_sepolia",
        "to_chain": "optimism_sepolia"
      },
      {
        "from_chain": "optimism_sepolia",
        "to_chain": "arbitrum_sepolia"
      },
      {
        "from_chain": "arbitrum_sepolia",
        "to_chain": "blast_sepolia"
      },
      {
        "from_chain": "blast_sepolia",
        "to_chain": "unichain_sepolia"
      },
      {
        "from_chain": "unichain_sepolia",
        "to_chain": "base_sepolia"
      }
    ]
  },
  "delay": {
    "between_wallets": 60,
    "between_bridges": 30,
    "after_completion": 90000
  },
  "chains": {
    "base_sepolia": {
      "chain_id": 84532,
      "rpc_url": "https://base-sepolia-rpc.publicnode.com",
      "bridge_contract": "0xCEE0372632a37Ba4d0499D1E2116eCff3A17d3C3",
      "api_name": "bast"
    },
    "optimism_sepolia": {
      "chain_id": 11155420,
      "rpc_url": "https://optimism-sepolia-rpc.publicnode.com",
      "bridge_contract": "0xb6Def636914Ae60173d9007E732684a9eEDEF26E",
      "api_name": "opst"
    },
    "arbitrum_sepolia": {
      "chain_id": 421614,
      "rpc_url": "https://arbitrum-sepolia-rpc.publicnode.com",
      "bridge_contract": "0x22B65d0B9b59af4D3Ed59F18b9Ad53f5F4908B54",
      "api_name": "arbt"
    },
    "blast_sepolia": {
      "chain_id": 168587773,
      "rpc_url": "https://sepolia.blast.io",
      "bridge_contract": "0x36B2415644d47b8f646697b6c4C5a9D55400f2Dd",
      "api_name": "blst"
    },
    "unichain_sepolia": {
      "chain_id": 4338,
      "rpc_url": "https://unichain-sepolia-rpc.publicnode.com",
      "bridge_contract": "0x1cEAb5967E5f078Fa0FEC3DFfD0394Af1fEeBCC9",
      "api_name": "unit"
    }
  },
  "api": {
    "base_url": "https://api.t2rn.io",
    "timeout": 30
  }
}
```

### Key Configuration Options

- **custom_flow**: Enable/disable custom bridge flow
- **wait_for_completion**: Whether to wait for API confirmation between bridges
- **bridge_paths**: List of bridge paths with source and destination chains
- **between_bridges**: Delay between sequential bridges in seconds

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

## Usage

Make sure your virtual environment is activated, then run the main application:

```bash
# Ensure venv is activated
# On Windows: venv\Scripts\activate
# On macOS/Linux: source venv/bin/activate

python -m src.app
```

### Custom Bridge Flow Examples

The tool supports several bridge flow configurations:

#### Linear Chain Walk
```json
"bridge_paths": [
  {"from_chain": "base_sepolia", "to_chain": "optimism_sepolia"},
  {"from_chain": "optimism_sepolia", "to_chain": "arbitrum_sepolia"},
  {"from_chain": "arbitrum_sepolia", "to_chain": "blast_sepolia"}
]
```

#### Circular Flow
```json
"bridge_paths": [
  {"from_chain": "base_sepolia", "to_chain": "blast_sepolia"},
  {"from_chain": "blast_sepolia", "to_chain": "unichain_sepolia"},
  {"from_chain": "unichain_sepolia", "to_chain": "base_sepolia"}
]
```

#### Back-and-Forth
```json
"bridge_paths": [
  {"from_chain": "base_sepolia", "to_chain": "optimism_sepolia"},
  {"from_chain": "optimism_sepolia", "to_chain": "base_sepolia"},
  {"from_chain": "base_sepolia", "to_chain": "optimism_sepolia"}
]
```

## Error Handling

The application has improved error handling, especially for common errors:

- **RO#7 Error**: This error occurs when the bridge is temporarily unavailable. The script will retry up to 100 times.
- **Network Timeouts**: Automatically retries with backoff
- **Insufficient Balance**: Checks and warns before attempting bridges
- **Keyboard Interrupts**: Handles Ctrl+C gracefully with proper cleanup


## Process Flow

1. For each wallet:
   - Initialize bridge service with wallet's private key
   - Process each bridge in the custom flow sequence (or default flow if custom_flow=false)
   - Monitor bridge transaction status based on the wait_for_completion setting
   - Apply delay between bridges and wallets as configured

2. After all wallets are processed:
   - Wait for the configured delay
   - Restart the process if running in continuous mode

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is provided for educational and testing purposes only. Use at your own risk. Always review the code before running automated crypto transactions.
