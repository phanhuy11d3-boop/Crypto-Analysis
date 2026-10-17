"""
Bridge Log Validator
====================
Reconciliation checks between raw and processed logs.
"""

import sys
import pandas as pd
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.config import BRIDGE_LOGS_FILE, PROCESSED_DATA_DIR
from transform.transform_logs import decode_data
from utils.date_range import filter_date_range


# =============================================================================
# VALIDATION CHECKS
# =============================================================================

def validate_logs(df_raw, df_parsed):
    """Run reconciliation checks between raw and processed data."""
    print("🔍 Validation Checks:")
    print("-" * 40)
    
    errors = []
    
    # Reconcile against ETH-bearing messages, not data-only messages.
    expected = df_raw.loc[df_raw["data"].apply(lambda value: (decode_data(value)[1] or 0) > 0)]
    expected = expected.copy()
    expected["datetime"] = pd.to_datetime(expected["timeStamp"].map(lambda value: int(str(value), 16) if str(value).startswith("0x") else int(value)), unit="s", utc=True)
    expected = filter_date_range(expected)
    expected_keys = set(zip(expected["transactionHash"], expected["logIndex"].apply(lambda value: int(value, 16))))
    actual_keys = set(zip(df_parsed["tx_hash"], df_parsed["log_index"]))
    if len(expected) == len(df_parsed) and expected_keys == actual_keys:
        print(f"✅ ETH-bearing logs in UTC window reconciled: {len(df_parsed):,}; excluded {len(df_raw) - len(expected):,} other logs")
    else:
        errors.append("ETH-bearing log count or identities mismatch")
        print(f"❌ Expected {len(expected):,} ETH-bearing logs; got {len(df_parsed):,}")
    
    # 2. No duplicate transactions
    dupes = df_parsed.duplicated(subset=["tx_hash", "log_index"]).sum()
    if dupes == 0:
        print(f"✅ No duplicate (tx_hash, log_index) pairs")
    else:
        errors.append(f"Found {dupes} duplicate rows")
        print(f"❌ Found {dupes} duplicate rows")
    
    # 3. Critical fields not null
    critical_cols = ["tx_hash", "block_number", "from_address", "value_eth"]
    for col in critical_cols:
        nulls = df_parsed[col].isnull().sum()
        if nulls == 0:
            print(f"✅ No nulls in {col}")
        else:
            errors.append(f"{col} has {nulls} nulls")
            print(f"❌ {col} has {nulls} nulls")
    
    # 4. Value sanity checks
    negative_values = (df_parsed["value_eth"] <= 0).sum()
    if negative_values == 0:
        print(f"✅ All ETH values are greater than zero")
    else:
        errors.append(f"Found {negative_values} negative values")
        print(f"❌ Found {negative_values} negative ETH values")
    
    # 5. Block numbers in expected range
    min_block = df_parsed["block_number"].min()
    max_block = df_parsed["block_number"].max()
    if min_block >= 17000000 and max_block <= 30000000:
        print(f"✅ Block range looks valid: {min_block:,} → {max_block:,}")
    else:
        print(f"⚠️ Block range: {min_block:,} → {max_block:,} (verify if expected)")
    
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
    
    print("🚀 Linea Bridge Log Validator")
    print("=" * 50)
    
    # Load raw logs
    raw_path = Path(PROJECT_ROOT) / BRIDGE_LOGS_FILE
    if not raw_path.exists():
        print(f"❌ Raw file not found: {raw_path}")
        exit(1)
    
    print(f"📥 Reading raw logs...")
    df_raw = pd.read_csv(raw_path)
    print(f"   Found {len(df_raw):,} raw rows")
    
    # Load processed logs
    parsed_path = Path(PROJECT_ROOT) / f"{PROCESSED_DATA_DIR}/transformed_logs.csv"
    if not parsed_path.exists():
        print(f"❌ Processed file not found: {parsed_path}")
        exit(1)
    
    print(f"📥 Reading processed logs...")
    df_parsed = pd.read_csv(parsed_path)
    print(f"   Found {len(df_parsed):,} processed rows\n")
    
    # Run validation
    success = validate_logs(df_raw, df_parsed)
    exit(0 if success else 1)
