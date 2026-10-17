"""
Transaction Transformer
=======================
Cleans and converts raw Linea transactions for analysis.
"""

import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.config import LINEA_TXS_FILE, PROCESSED_DATA_DIR
from utils.date_range import filter_date_range


# =============================================================================
# FUNCTIONS
# =============================================================================

def hex_to_int(hex_str):
    """Convert hex string (or numeric string) to integer."""
    if pd.isna(hex_str):
        return 0
    
    str_val = str(hex_str).strip()
    if str_val == "0x" or str_val == "":
        return 0
        
    try:
        # Check if it looks like hex
        if str_val.lower().startswith("0x"):
            return int(str_val, 16)
        # Handle regular numbers that might be strings
        return int(float(str_val))
    except (ValueError, TypeError):
        return 0


def wei_to_eth(wei_val):
    """Convert Wei to ETH."""
    if pd.isna(wei_val):
        return 0.0
    return float(wei_val) / 1e18


def wei_to_gwei(wei_val):
    """Convert Wei to Gwei."""
    if pd.isna(wei_val):
        return 0.0
    return float(wei_val) / 1e9


def convert_timestamp(ts):
    """Convert Unix timestamp to datetime object."""
    try:
        ts_int = int(ts)
        return pd.to_datetime(ts_int, unit='s')
    except (ValueError, TypeError):
        return pd.NaT


def transform_transactions(df):
    """Apply transformations to transaction DataFrame."""
    print(f"📊 Transforming {len(df):,} transactions...")
    if df.empty:
        return pd.DataFrame(columns=[
            'datetime', 'block_number', 'hash', 'from', 'to', 'value_eth',
            'gas_price_gwei', 'gas_used_int', 'nonce_int', 'is_error',
            'tx_status', 'methodId', 'functionName'
        ])
    
    # 0. Deduplicate (Remove extraction artifacts)
    # ---------------------------------------------------------
    initial_count = len(df)
    df = df.drop_duplicates(subset=['hash']).copy()
    if len(df) < initial_count:
        print(f"   • Removed {initial_count - len(df):,} duplicate transaction hashes")
    
    # 1. The "Big Three" Conversions
    # ---------------------------------------------------------
    
    # timestamp -> datetime
    print("   • Converting timestamps...")
    df['datetime'] = df['timeStamp'].apply(convert_timestamp)
    df = filter_date_range(df)
    
    # value (Wei -> ETH)
    print("   • Converting value (Wei -> ETH)...")
    df['value_hex'] = df['value'] # Keep original just in case
    # Handle cases where value might be hex or scientific notation string
    df['value_wei'] = df['value'].apply(hex_to_int)
    df['value_eth'] = df['value_wei'].apply(wei_to_eth)
    
    # gasPrice (Wei -> Gwei)
    print("   • Converting gasPrice (Wei -> Gwei)...")
    df['gas_price_wei'] = df['gasPrice'].apply(hex_to_int)
    df['gas_price_gwei'] = df['gas_price_wei'].apply(wei_to_gwei)


    # 2. Hex Numbers to Integers
    # ---------------------------------------------------------
    print("   • Converting hex/strings to integers...")
    
    # blockNumber
    df['block_number'] = df['blockNumber'].apply(hex_to_int)
    
    # nonce
    df['nonce_int'] = df['nonce'].apply(hex_to_int)
    
    # gasUsed
    df['gas_used_int'] = df['gasUsed'].apply(hex_to_int)

    # 3. Status Flags (Optional but good practice)
    # ---------------------------------------------------------
    if 'isError' in df.columns:
        df['is_error'] = df['isError'].apply(lambda x: bool(hex_to_int(x)))
    
    if 'txreceipt_status' in df.columns:
        df['tx_status'] = df['txreceipt_status'].apply(lambda x: bool(hex_to_int(x)))

    # Select and Reorder columns for clean output
    cols_to_keep = [
        'datetime', 'block_number', 'hash', 'from', 'to', 
        'value_eth', 'gas_price_gwei', 'gas_used_int', 'nonce_int',
        'is_error', 'tx_status', 'methodId', 'functionName'
    ]
    
    # Only keep columns that actually exist
    final_cols = [c for c in cols_to_keep if c in df.columns]
    
    return df[final_cols]


def save_processed(df, output_filename):
    """Save processed data to CSV."""
    output_path = Path(PROJECT_ROOT) / PROCESSED_DATA_DIR / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_path, index=False)
    print(f"💾 Saved {len(df):,} rows to {output_path}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("🚀 Linea Transaction Transformer")
    print("=" * 50)
    
    # Input Path
    input_path = Path(PROJECT_ROOT) / LINEA_TXS_FILE
    
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        print("   Make sure to run the extraction script first.")
        exit(1)
        
    print(f"📥 Reading {input_path}...")
    try:
        # load specific columns as string to avoid pandas inference errors on large ints
        df_raw = pd.read_csv(input_path, dtype=str)
        print(f"   Found {len(df_raw):,} raw transactions")
        
        df_processed = transform_transactions(df_raw)
        save_processed(df_processed, "transformed_transactions.csv")
        if not df_processed.empty:
            print(f"\n📄 Sample processed row:")
            print(df_processed.iloc[0])
            
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        sys.exit(1)
