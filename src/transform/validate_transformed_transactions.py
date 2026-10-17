"""
Transaction Validator
=====================
Reconciliation checks between raw and processed transactions.
"""

import sys
import pandas as pd
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.config import LINEA_TXS_FILE, PROCESSED_DATA_DIR
from utils.date_range import filter_date_range


# =============================================================================
# VALIDATION CHECKS
# =============================================================================

def validate_transactions(df_raw, df_parsed):
    """Run reconciliation checks between raw and processed data."""
    df_raw = df_raw.copy()
    df_raw["datetime"] = pd.to_datetime(df_raw["timeStamp"].astype("int64"), unit="s", utc=True)
    df_raw = filter_date_range(df_raw)
    if len(filter_date_range(df_parsed)) != len(df_parsed):
        print("Transactions outside the configured UTC window")
        return False
    print("🔍 Validation Checks:")
    print("-" * 40)
    
    errors = []
    
    # 1. Row count match
    if len(df_raw) == len(df_parsed):
        print(f"✅ Row count: {len(df_raw):,} == {len(df_parsed):,}")
    else:
        # Check if the difference matches the number of duplicates in raw data
        raw_dupes = df_raw.duplicated(subset=["hash"]).sum()
        if len(df_raw) - raw_dupes == len(df_parsed):
            print(f"⚠️ Row count mismatch (expected): {len(df_raw):,} → {len(df_parsed):,} ({raw_dupes} hashes deduplicated)")
        else:
            errors.append(f"Row count mismatch: {len(df_raw)} vs {len(df_parsed)}")
            print(f"❌ Row count: {len(df_raw):,} != {len(df_parsed):,} (Unexpected difference)")
    
    # 2. No duplicate transactions
    # In raw data, hash should be unique for transactions (unlike logs where tx_hash repeats)
    dupes = df_parsed.duplicated(subset=["hash"]).sum()
    if dupes == 0:
        print(f"✅ No duplicate hashes")
    else:
        print(f"❌ Found {dupes} duplicate hashes")
        #print(df_parsed[df_parsed.duplicated(subset=["hash"], keep=False)].sort_values("hash"))
    
    # 3. Critical fields not null
    critical_cols = ["hash", "block_number", "from", "value_eth"]
    for col in critical_cols:
        if col not in df_parsed.columns:
            errors.append(f"Missing column: {col}")
            print(f"❌ Missing column: {col}")
            continue
            
        nulls = df_parsed[col].isnull().sum()
        if nulls == 0:
            print(f"✅ No nulls in {col}")
        else:
            errors.append(f"{col} has {nulls} nulls")
            print(f"❌ {col} has {nulls} nulls")
    
    # 4. Value sanity checks
    if "value_eth" in df_parsed.columns:
        negative_values = (df_parsed["value_eth"] < 0).sum()
        if negative_values == 0:
            print(f"✅ No negative ETH values")
        else:
            errors.append(f"Found {negative_values} negative values")
            print(f"❌ Found {negative_values} negative ETH values")
            
    if "gas_price_gwei" in df_parsed.columns:
        negative_gas = (df_parsed["gas_price_gwei"] < 0).sum()
        if negative_gas == 0:
            print(f"✅ No negative gas prices")
        else:
            errors.append(f"Found {negative_gas} negative gas prices")
            print(f"❌ Found {negative_gas} negative gas prices")
    
    # 5. Block numbers in expected range (Linea Mainnet started around block 0, but mainly active later)
    # We'll just check for non-negative and reasonable max (e.g. < 100M for now)
    if "block_number" in df_parsed.columns:
        min_block = df_parsed["block_number"].min()
        max_block = df_parsed["block_number"].max()
        if min_block >= 0 and max_block <= 100000000:
            print(f"✅ Block range looks valid: {min_block:,} → {max_block:,}")
        else:
            print(f"⚠️ Block range: {min_block:} → {max_block:} (verify if expected)")
    
    # Summary
    print("-" * 40)
    if not errors:
        print("✅ All validation checks passed!")
        return True
    else:
        print(f"❌ {len(errors)} validation issue(s) found")
        return False


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    
    print("🚀 Linea Transaction Validator")
    print("=" * 50)
    
    # Load raw transactions
    raw_path = Path(PROJECT_ROOT) / LINEA_TXS_FILE
    if not raw_path.exists():
        print(f"❌ Raw file not found: {raw_path}")
        exit(1)
    
    print(f"📥 Reading raw transactions...")
    # Load raw with dtype=str to avoid inference issues, consistent with transformer
    df_raw = pd.read_csv(raw_path, dtype=str)
    print(f"   Found {len(df_raw):,} raw rows")
    
    # Load processed transactions
    parsed_path = Path(PROJECT_ROOT) / f"{PROCESSED_DATA_DIR}/transformed_transactions.csv"
    if not parsed_path.exists():
        print(f"❌ Processed file not found: {parsed_path}")
        exit(1)
    
    print(f"📥 Reading processed transactions...")
    df_parsed = pd.read_csv(parsed_path)
    print(f"   Found {len(df_parsed):,} processed rows\n")
    
    # Run validation
    success = validate_transactions(df_raw, df_parsed)
    exit(0 if success else 1)
