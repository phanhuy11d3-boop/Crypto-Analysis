"""
Block Utilities
===============
Convert dates to block numbers using Etherscan/Lineascan API.
"""

import requests
from datetime import datetime, timezone
from .config import ETHEREUM_CHAIN_ID, LINEA_CHAIN_ID, EXTRACTION_START_DATE


def get_block_by_date(date_str: str, chain_id: int, api_key: str, closest: str = "before", end_of_day: bool = False) -> int:
    """
    Get block number for a specific date.
    
    Args:
        date_str: Date in format "YYYY-MM-DD"
        chain_id: 1 for Ethereum, 59144 for Linea
        api_key: Etherscan/Lineascan API key
        closest: "before" or "after" - which block to return
    
    Returns:
        Block number as integer
    """
    # Convert date to Unix timestamp (midnight UTC)
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    timestamp = int(dt.timestamp())
    if end_of_day:
        timestamp += 86400 - 1
    print(timestamp)

    # Use Etherscan v2 API
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": chain_id,
        "module": "block",
        "action": "getblocknobytime",
        "timestamp": timestamp,
        "closest": closest,
        "apikey": api_key
    }
    
    response = requests.get(url, params=params, timeout=30)
    data = response.json()
    
    if data.get("status") == "1":
        return int(data.get("result"))
    else:
        raise ValueError(f"API error: {data.get('message')} - {data.get('result')}")


def get_eth_block_by_date(date_str: str, api_key: str, closest: str = "before", end_of_day: bool = False) -> int:
    """Get Ethereum mainnet block number for a date."""
    return get_block_by_date(date_str, chain_id=ETHEREUM_CHAIN_ID, api_key=api_key, closest=closest, end_of_day=end_of_day)


def get_linea_block_by_date(date_str: str, api_key: str, closest: str = "before", end_of_day: bool = False) -> int:
    """Get Linea mainnet block number for a date."""
    return get_block_by_date(date_str, chain_id=LINEA_CHAIN_ID, api_key=api_key, closest=closest, end_of_day=end_of_day)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    api_key = os.getenv("ETHERSCAN_API_KEY")
    
    if not api_key:
        print("❌ No ETHERSCAN_API_KEY in .env!")
        exit(1)
    
    test_date = EXTRACTION_START_DATE
    
    print(f"🔍 Looking up blocks for {test_date}...")
    
    eth_block = get_eth_block_by_date(test_date, api_key)
    print(f"   Ethereum: block {eth_block:}")
    
    linea_block = get_linea_block_by_date(test_date, api_key)
    print(f"   Linea: block {linea_block:}")
