"""Count unique bridge wallets in the configured UTC window."""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from utils.config import EXTRACTION_START_DATE, EXTRACTION_END_DATE, PROCESSED_DATA_DIR
from utils.date_range import filter_date_range

df = filter_date_range(pd.read_csv(ROOT / PROCESSED_DATA_DIR / "transformed_logs.csv"))


unique_wallets = df["from_address"].nunique()
total_txs = len(df)


df["datetime"] = pd.to_datetime(df["datetime"])

# Get date range info
start_date = df["datetime"].min()
end_date = df["datetime"].max()
six_months_after_start = start_date + pd.DateOffset(months=6)
six_months_before_end = end_date - pd.DateOffset(months=6)

# First 6 months (from start)
first_6m_df = df[df["datetime"] <= six_months_after_start]
first_6m_wallets = first_6m_df["from_address"].nunique()
first_6m_txs = len(first_6m_df)

# Last 6 months (before end)
last_6m_df = df[df["datetime"] >= six_months_before_end]
last_6m_wallets = last_6m_df["from_address"].nunique()
last_6m_txs = len(last_6m_df)

print(f"\n--- Date Range ---")
print(f"Configured UTC window: {EXTRACTION_START_DATE} through {EXTRACTION_END_DATE} inclusive")
print(f"Data starts: {start_date}")
print(f"Data ends: {end_date}")

print(f"\n--- Full Dataset ---")
print(f"Total transactions: {total_txs:,}")
print(f"Unique wallets: {unique_wallets:,}")

print(f"\n--- First 6 Months (until {six_months_after_start.date()}) ---")
print(f"Transactions: {first_6m_txs:,}")
print(f"Unique wallets: {first_6m_wallets:,}")

print(f"\n--- Last 6 Months (from {six_months_before_end.date()}) ---")
print(f"Transactions: {last_6m_txs:,}")
print(f"Unique wallets: {last_6m_wallets:,}")
