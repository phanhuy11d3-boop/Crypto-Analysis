"""Load filtered bridge data and cached Linea transactions into local SQLite.

The original API CSVs are retained. Linea rows are selected by the queried
wallet, so incoming transactions are retained just as in the API response.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from transform.transform_transactions import transform_transactions
from transform.validate_transformed_transactions import validate_transactions
from utils.config import EXTRACTION_START_DATE, EXTRACTION_END_DATE
from utils.date_range import filter_date_range


def main():
    status_path = ROOT / "data/raw/linea_transactions.status.json"
    if status_path.exists() and not json.loads(status_path.read_text(encoding="utf-8")).get("complete"):
        raise RuntimeError("Linea extraction is incomplete; resume before loading")
    bridges = pd.read_csv(ROOT / "data/transformed/transformed_logs.csv")
    bridges = filter_date_range(bridges)
    if bridges.empty or not bridges.value_eth.gt(0).all():
        raise ValueError("Run transform_logs.py first; only positive ETH logs are allowed")
    wallets = set(bridges.from_address.str.lower())
    cached = pd.read_csv(ROOT / "data/raw/linea_transactions.csv", dtype=str)
    selected = cached.loc[cached.wallet.str.lower().isin(wallets)].copy()
    transactions = transform_transactions(selected.copy())
    if not validate_transactions(selected, transactions):
        raise ValueError("Transaction validation failed")
    transactions.to_csv(ROOT / "data/transformed/transformed_transactions.csv", index=False)
    transactions = transactions.rename(columns={
        "from": "from_address", "to": "to_address",
        "methodId": "method_id", "functionName": "function_name",
    })
    transactions["datetime"] = pd.to_datetime(transactions["datetime"], utc=True).astype(str)
    db_path = ROOT / "data/linea_analytics.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS etherscan_logs (
                tx_hash TEXT NOT NULL, block_number INTEGER NOT NULL,
                timestamp INTEGER NOT NULL, datetime TEXT NOT NULL,
                from_address TEXT NOT NULL, to_address TEXT, message_hash TEXT,
                value_eth REAL NOT NULL CHECK (value_eth > 0), fee_eth REAL,
                nonce INTEGER, gas_price INTEGER, gas_used INTEGER,
                log_index INTEGER NOT NULL, tx_index INTEGER,
                loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tx_hash, log_index)
            );
            CREATE TABLE IF NOT EXISTS linea_transactions (
                datetime TEXT NOT NULL, block_number INTEGER NOT NULL,
                hash TEXT NOT NULL PRIMARY KEY, from_address TEXT NOT NULL,
                to_address TEXT, value_eth REAL, gas_price_gwei REAL,
                gas_used_int INTEGER, nonce_int INTEGER, is_error INTEGER,
                tx_status INTEGER, method_id TEXT, function_name TEXT,
                loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_bridge_from ON etherscan_logs(from_address);
            CREATE INDEX IF NOT EXISTS idx_linea_from ON linea_transactions(from_address);
            CREATE VIEW IF NOT EXISTS bridge_wallets AS
                SELECT from_address, COUNT(*) AS bridge_log_count,
                    MIN(datetime) AS first_observed_bridge_utc,
                    SUM(value_eth) AS total_eth_sent
                FROM etherscan_logs GROUP BY from_address;
        """)
        # Refresh the two local snapshots atomically; retain other tables.
        with conn:
            for name, frame in (("etherscan_logs", bridges), ("linea_transactions", transactions)):
                conn.execute(f'DELETE FROM "{name}"')
                columns = ','.join(f'"{c}"' for c in frame.columns)
                placeholders = ','.join('?' for _ in frame.columns)
                clean = frame.astype(object).where(pd.notna(frame), None)
                conn.executemany(f'INSERT INTO "{name}" ({columns}) VALUES ({placeholders})',
                                 clean.itertuples(index=False, name=None))
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT COUNT(*) FROM etherscan_logs').fetchone()[0] == len(bridges)
        assert conn.execute('SELECT COUNT(*) FROM linea_transactions').fetchone()[0] == len(transactions)
    report = {
        "sqlite_file": str(db_path), "bridge_logs": len(bridges),
        "unique_bridge_senders": len(wallets),
        "linea_source": f"Existing API cache for {EXTRACTION_START_DATE} through {EXTRACTION_END_DATE} UTC",
        "queried_wallets_with_returned_transactions": selected.wallet.nunique(),
        "linea_transactions_unique": len(transactions),
        "excluded_cached_rows": len(cached) - len(selected),
    }
    (ROOT / "data/sqlite_load_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
