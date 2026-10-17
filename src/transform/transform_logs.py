"""
Bridge Log Parser
=================
Decodes raw Etherscan logs into human-readable format.
"""

import sys
import ast
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.config import BRIDGE_LOGS_FILE, PROCESSED_DATA_DIR
from utils.date_range import filter_date_range


# =============================================================================
# FUNCTIONS
# =============================================================================

def hex_to_int(hex_str):
    """Convert hex string to integer."""
    if pd.isna(hex_str) or hex_str == "0x":
        return 0
    return int(hex_str, 16)


def hex_to_address(hex_str):
    """Extract address from 32-byte padded hex (topic)."""
    if pd.isna(hex_str):
        return None
    # Last 40 chars = 20 bytes = address
    return "0x" + hex_str[-40:]


def parse_topics(topics_str):
    """Parse topics string into list."""
    if pd.isna(topics_str):
        return []
    # Topics stored as string representation of list
    return ast.literal_eval(topics_str)


def decode_data(data_hex):
    """
    Decode MessageSent event data.
    
    Data layout (each param = 32 bytes = 64 hex chars):
    - [0]: fee (uint256)
    - [1]: value (uint256) - the ETH amount being bridged
    - [2]: nonce (uint256)
    - [3]: calldata offset
    - [4]: calldata length
    """
    if pd.isna(data_hex) or len(data_hex) < 130:
        return None, None, None
    
    # Remove '0x' prefix
    data = data_hex[2:]
    
    # Each slot = 64 hex chars
    fee = int(data[0:64], 16)
    value = int(data[64:128], 16)
    nonce = int(data[128:192], 16)
    
    return fee, value, nonce


def wei_to_eth(wei):
    """Convert wei to ETH."""
    if wei is None:
        return None
    return wei / 1e18


def parse_logs(df):
    """Parse raw logs into decoded DataFrame."""
    print(f"📊 Parsing {len(df):,} logs...")
    
    # Parse topics column
    df["topics_list"] = df["topics"].apply(parse_topics)
    
    # Extract from topics (indexed params)
    # topic[0] = event signature
    # topic[1] = _from address
    # topic[2] = _to address  
    # topic[3] = _messageHash
    df["from_address"] = df["topics_list"].apply(lambda x: hex_to_address(x[1]) if len(x) > 1 else None)
    df["to_address"] = df["topics_list"].apply(lambda x: hex_to_address(x[2]) if len(x) > 2 else None)
    df["message_hash"] = df["topics_list"].apply(lambda x: x[3] if len(x) > 3 else None)
    
    # Decode data field
    decoded = df["data"].apply(decode_data)
    df["fee_wei"] = decoded.apply(lambda x: x[0])
    df["value_wei"] = decoded.apply(lambda x: x[1])
    df["nonce"] = decoded.apply(lambda x: x[2])
    
    # Convert to ETH
    df["fee_eth"] = df["fee_wei"].apply(wei_to_eth)
    df["value_eth"] = df["value_wei"].apply(wei_to_eth)
    
    # Convert hex fields
    df["block_number"] = df["blockNumber"].apply(hex_to_int)
    df["timestamp"] = df["timeStamp"].apply(hex_to_int)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df["gas_price"] = df["gasPrice"].apply(hex_to_int)
    df["gas_used"] = df["gasUsed"].apply(hex_to_int)
    df["log_index"] = df["logIndex"].apply(hex_to_int)
    df["tx_index"] = df["transactionIndex"].apply(hex_to_int)
    
    # Rename for clarity
    df = df.rename(columns={
        "transactionHash": "tx_hash",
        "blockHash": "block_hash"
    })
    
    # Select final columns
    cols = [
        "tx_hash", "block_number", "timestamp", "datetime",
        "from_address", "to_address", "message_hash",
        "value_eth", "fee_eth", "nonce",
        "gas_price", "gas_used", "log_index", "tx_index"
    ]
    
    return df[cols]


def save_processed(df, output_path):
    """Save processed data to CSV."""
    output_path = Path(PROJECT_ROOT) / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_path, index=False)
    print(f"💾 Saved {len(df):,} rows to {output_path}")
    return df


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    
    print("🚀 Linea Bridge Log Parser")
    print("=" * 50)
    
    # Read raw logs
    input_path = Path(PROJECT_ROOT) / BRIDGE_LOGS_FILE
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        print("   Run extract_logs_from_etherscan.py first!")
        exit(1)
    
    print(f"📥 Reading {input_path}...")
    df_raw = pd.read_csv(input_path)
    print(f"   Found {len(df_raw):,} raw logs")
    
    # Parse logs
    df_parsed = parse_logs(df_raw)
    df_parsed = filter_date_range(df_parsed)

    # MessageSent also carries data-only messages. Select ETH-bearing sends
    # before creating the wallet list used by the Linea extractor.
    df_parsed = df_parsed.loc[df_parsed["value_eth"] > 0].copy()
    print(f"   Kept {len(df_parsed):,} ETH-bearing logs in the configured UTC window")
    
    # Save processed
    output_file = f"{PROCESSED_DATA_DIR}/transformed_logs.csv"
    save_processed(df_parsed, output_file)
    
    # Show sample
    print(f"\n📄 Sample parsed row:")
    sample = df_parsed.iloc[0].to_dict()
    for k, v in sample.items():
        print(f"   {k}: {v}")
    
    # Quick stats
    print(f"\n📈 Quick Stats:")
    print(f"   Total bridges: {len(df_parsed):,}")
    print(f"   Total ETH bridged: {df_parsed['value_eth'].sum():,.2f}")
    print(f"   Date range: {df_parsed['datetime'].min()} → {df_parsed['datetime'].max()}")
