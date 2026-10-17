"""
Load Transformed Data to PostgreSQL
====================================
Loads transformed etherscan logs and transactions CSV files into PostgreSQL raw schema.
This is the bronze layer - stores cleaned/transformed data before dbt modeling.
"""

import os
import json
from io import StringIO
from typing import Optional
from pathlib import Path
import psycopg2
from dotenv import load_dotenv
import pandas as pd
import sys

# Add the project root to sys.path to allow imports from src
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.append(str(project_root))

# We import config via the full package path `src.utils.config`
from src.utils.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from src.utils.date_range import filter_date_range

# Load environment variables from .env so local runs work without exporting.
load_dotenv()

# Project root directory (3 levels up from this script)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def get_db_connection(
    host: Optional[str] = None,
    port: Optional[str] = None,
    dbname: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
):
    """
    Open a Postgres connection using psycopg2.

    - Parameters override environment variables; if omitted, we read env vars.
    - Env vars: POSTGRES_HOST (default "localhost"), POSTGRES_PORT (default "5432"),
      POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD.
    - Autocommit stays OFF so callers control commit/rollback explicitly.
    """
    conn = psycopg2.connect(
        host=host or DB_HOST,
        port=port or DB_PORT,
        database=dbname or DB_NAME,
        user=user or DB_USER,
        password=password if password is not None else DB_PASSWORD,
    )

    conn.autocommit = False
    return conn


def create_etherscan_logs_table(conn) -> None:
    """
    Create the etherscan_logs table in raw schema.
    
    This table stores transformed bridge deposit events from Ethereum Mainnet.
    Columns match the output from transform_logs.py.
    """
    create_sql = """
    CREATE SCHEMA IF NOT EXISTS raw;
    
    CREATE TABLE IF NOT EXISTS raw.etherscan_logs (
        tx_hash VARCHAR(66) NOT NULL,
        block_number BIGINT NOT NULL,
        timestamp BIGINT NOT NULL,
        datetime TIMESTAMP WITH TIME ZONE NOT NULL,
        from_address VARCHAR(42) NOT NULL,
        to_address VARCHAR(42),
        message_hash VARCHAR(66),
        value_eth NUMERIC(78, 18) NOT NULL,
        fee_eth NUMERIC(78, 18),
        nonce BIGINT,
        gas_price BIGINT,
        gas_used BIGINT,
        log_index INTEGER,
        tx_index INTEGER,
        loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tx_hash, log_index)
    );
    
    -- Create indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_etherscan_logs_from_address ON raw.etherscan_logs(from_address);
    CREATE INDEX IF NOT EXISTS idx_etherscan_logs_datetime ON raw.etherscan_logs(datetime);
    CREATE INDEX IF NOT EXISTS idx_etherscan_logs_block_number ON raw.etherscan_logs(block_number);
    """
    
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("✓ Table raw.etherscan_logs created/verified")


def create_transactions_table(conn) -> None:
    """
    Create the linea_transactions table in raw schema.
    
    This table stores transformed Linea network transactions.
    Columns match the output from transform_transactions.py.
    """
    create_sql = """
    CREATE SCHEMA IF NOT EXISTS raw;
    
    CREATE TABLE IF NOT EXISTS raw.linea_transactions (
        datetime TIMESTAMP WITH TIME ZONE NOT NULL,
        block_number BIGINT NOT NULL,
        hash VARCHAR(66) NOT NULL PRIMARY KEY,
        from_address VARCHAR(42) NOT NULL,
        to_address VARCHAR(42),
        value_eth NUMERIC(78, 18),
        gas_price_gwei NUMERIC(20, 9),
        gas_used_int BIGINT,
        nonce_int INTEGER,
        is_error BOOLEAN,
        tx_status BOOLEAN,
        method_id VARCHAR(10),
        function_name TEXT,
        loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Create indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_linea_txs_from_address ON raw.linea_transactions(from_address);
    CREATE INDEX IF NOT EXISTS idx_linea_txs_datetime ON raw.linea_transactions(datetime);
    CREATE INDEX IF NOT EXISTS idx_linea_txs_block_number ON raw.linea_transactions(block_number);
    """
    
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("✓ Table raw.linea_transactions created/verified")


def truncate_table(conn, table_name: str) -> None:
    """
    Remove all rows from a raw table (keeps table structure).
    Use for full refresh strategy.
    
    Args:
        conn: PostgreSQL connection
        table_name: Name of table to truncate (without schema prefix)
    """
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE raw.{table_name};")
    conn.commit()
    print(f"✓ Truncated raw.{table_name}")


def load_etherscan_logs_csv(conn, csv_path: Path) -> int:
    """
    Load transformed etherscan logs CSV file into PostgreSQL.
    
    Uses COPY for fast bulk loading. Handles data type conversions and NULLs.
    
    Args:
        conn: PostgreSQL connection
        csv_path: Path to transformed_logs.csv file
        
    Returns:
        Number of rows inserted
    """
    print(f"📥 Reading {csv_path.name}...")
    df = pd.read_csv(csv_path)
    df = filter_date_range(df)
    
    if df.empty:
        print("   ⚠️  CSV file is empty, skipping.")
        return 0
    
    print(f"   Found {len(df):,} rows")
    
    # Ensure datetime column is properly typed
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
    
    # Replace NaN with None for PostgreSQL NULL handling
    df = df.where(pd.notnull(df), None)
    
    # Prepare columns in correct order matching table schema
    columns = [
        'tx_hash', 'block_number', 'timestamp', 'datetime',
        'from_address', 'to_address', 'message_hash',
        'value_eth', 'fee_eth', 'nonce',
        'gas_price', 'gas_used', 'log_index', 'tx_index'
    ]
    
    # Select only columns that exist in dataframe
    available_cols = [col for col in columns if col in df.columns]
    df_selected = df[available_cols].copy()
    
    # Stream DataFrame to CSV in-memory for COPY
    buffer = StringIO()
    df_selected.to_csv(buffer, index=False, header=False, na_rep='\\N')
    buffer.seek(0)
    
    # Use COPY for fast bulk insert
    copy_sql = f"""
        COPY incoming_logs ({", ".join(available_cols)})
        FROM STDIN WITH (FORMAT CSV, NULL '\\N')
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE incoming_logs (LIKE raw.etherscan_logs INCLUDING DEFAULTS) ON COMMIT DROP")
            cur.copy_expert(sql=copy_sql, file=buffer)
            cur.execute(f'INSERT INTO raw.etherscan_logs ({", ".join(available_cols)}) SELECT {", ".join(available_cols)} FROM incoming_logs ON CONFLICT (tx_hash, log_index) DO NOTHING')
            inserted = cur.rowcount
        conn.commit()
        
        print(f"   ✓ Loaded {inserted:,} rows into raw.etherscan_logs")
        return inserted
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error loading etherscan logs: {e}")
        raise


def load_transactions_csv(conn, csv_path: Path) -> int:
    """
    Load transformed transactions CSV file into PostgreSQL.
    
    Uses COPY for fast bulk loading. Handles data type conversions and NULLs.
    
    Args:
        conn: PostgreSQL connection
        csv_path: Path to transformed_transactions.csv file
        
    Returns:
        Number of rows inserted
    """
    print(f"📥 Reading {csv_path.name}...")
    df = pd.read_csv(csv_path)
    df = filter_date_range(df)
    
    if df.empty:
        print("   ⚠️  CSV file is empty, skipping.")
        return 0
    
    print(f"   Found {len(df):,} rows")
    
    # Ensure datetime column is properly typed
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
    
    # Replace NaN with None for PostgreSQL NULL handling
    df = df.where(pd.notnull(df), None)
    
    # Prepare columns in correct order matching table schema
    columns = [
        'datetime', 'block_number', 'hash', 'from', 'to',
        'value_eth', 'gas_price_gwei', 'gas_used_int', 'nonce_int',
        'is_error', 'tx_status', 'methodId', 'functionName'
    ]
    
    # Map column names (CSV uses 'from'/'to', table uses 'from_address'/'to_address')
    column_mapping = {
        'from': 'from_address',
        'to': 'to_address',
        'methodId': 'method_id',
        'functionName': 'function_name'
    }
    
    # Select only columns that exist in dataframe
    available_cols = [col for col in columns if col in df.columns]
    df_selected = df[available_cols].copy()
    
    # Rename columns to match table schema
    df_selected = df_selected.rename(columns=column_mapping)
    
    # Stream DataFrame to CSV in-memory for COPY
    buffer = StringIO()
    df_selected.to_csv(buffer, index=False, header=False, na_rep='\\N')
    buffer.seek(0)
    
    # Get final column names after renaming
    final_cols = [column_mapping.get(col, col) for col in available_cols]
    
    # Use COPY for fast bulk insert
    copy_sql = f"""
        COPY incoming_transactions ({", ".join(final_cols)})
        FROM STDIN WITH (FORMAT CSV, NULL '\\N')
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE incoming_transactions (LIKE raw.linea_transactions INCLUDING DEFAULTS) ON COMMIT DROP")
            cur.copy_expert(sql=copy_sql, file=buffer)
            cur.execute(f'INSERT INTO raw.linea_transactions ({", ".join(final_cols)}) SELECT {", ".join(final_cols)} FROM incoming_transactions ON CONFLICT (hash) DO NOTHING')
            inserted = cur.rowcount
        conn.commit()
        
        print(f"   ✓ Loaded {inserted:,} rows into raw.linea_transactions")
        return inserted
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Error loading transactions: {e}")
        raise


def check_table_status(conn, table_name: str) -> dict:
    """
    Check if table exists and return row count.
    
    Args:
        conn: psycopg2 connection
        table_name: Name of the table to check (without schema prefix)
    
    Returns:
        Dictionary with 'exists' (bool) and 'row_count' (int)
    """
    result = {
        "exists": False,
        "row_count": 0
    }
    
    with conn.cursor() as cur:
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'raw' 
                AND table_name = %s
            );
        """, (table_name,))
        table_exists = cur.fetchone()[0]
        result["exists"] = table_exists
        
        if not table_exists:
            return result
        
        # Count total rows
        cur.execute(f"SELECT COUNT(*) FROM raw.{table_name};")
        result["row_count"] = cur.fetchone()[0]
    
    return result



def load_all_transformed_data(
    transformed_dir: Optional[Path] = None,
    truncate_existing: bool = False
) -> dict:
    """
    Main function to load all transformed CSV files into PostgreSQL.
    
    Loads:
    - transformed_logs.csv → raw.bridge_logs
    - transformed_transactions.csv → raw.linea_transactions
    
    Args:
        transformed_dir: Directory containing transformed CSV files (default: data/transformed)
        truncate_existing: If True, truncate tables before loading (full refresh)
        
    Returns:
        Dictionary with 'bridge_logs' and 'transactions' row counts
    """
    if transformed_dir is None:
        transformed_dir = PROJECT_ROOT / "data/transformed"
    
    transformed_dir = Path(transformed_dir)

    if transformed_dir.resolve() == (PROJECT_ROOT / "data/transformed").resolve():
        status_path = PROJECT_ROOT / "data/raw/linea_transactions.status.json"
        if status_path.exists() and not json.loads(status_path.read_text(encoding="utf-8")).get("complete"):
            raise RuntimeError("Linea extraction is incomplete; resume it before loading the current pipeline output")
    
    if not transformed_dir.exists():
        print(f"❌ Directory not found: {transformed_dir}")
        raise FileNotFoundError(transformed_dir)
    
    # Define expected files
    bridge_logs_file = transformed_dir / "transformed_logs.csv"
    transactions_file = transformed_dir / "transformed_transactions.csv"
    
    # Open database connection
    conn = get_db_connection()
    
    results = {"etherscan_logs": 0, "transactions": 0}
    
    try:
        print("=" * 60)
        print("🚀 Loading Transformed Data to PostgreSQL")
        print("=" * 60)
        
        # =====================================================================
        # 1. CREATE TABLES
        # =====================================================================
        print("\n📋 Creating/verifying tables...")
        create_etherscan_logs_table(conn)
        create_transactions_table(conn)
        
        # =====================================================================
        # 2. LOAD BRIDGE LOGS
        # =====================================================================
        if bridge_logs_file.exists():
            print(f"\n📊 Loading Bridge Logs")
            print("-" * 60)
            
            if truncate_existing:
                truncate_table(conn, "etherscan_logs")
            
            try:
                rows = load_etherscan_logs_csv(conn, bridge_logs_file)
                results["etherscan_logs"] = rows
            except Exception as e:
                print(f"❌ Failed to load bridge logs: {e}")
                conn.rollback()
                raise
        else:
            print(f"\n⚠️  Bridge logs file not found: {bridge_logs_file}")
        
        # =====================================================================
        # 3. LOAD TRANSACTIONS
        # =====================================================================
        if transactions_file.exists():
            print(f"\n📊 Loading Linea Transactions")
            print("-" * 60)
            
            if truncate_existing:
                truncate_table(conn, "linea_transactions")
            
            try:
                rows = load_transactions_csv(conn, transactions_file)
                results["transactions"] = rows
            except Exception as e:
                print(f"❌ Failed to load transactions: {e}")
                conn.rollback()
                raise
        else:
            print(f"\n⚠️  Transactions file not found: {transactions_file}")
        
        # =====================================================================
        # 4. SUMMARY
        # =====================================================================
        print("\n" + "=" * 60)
        print("✅ Loading Complete!")
        print("=" * 60)
        
        # Check final row counts
        bridge_status = check_table_status(conn, "etherscan_logs")
        tx_status = check_table_status(conn, "linea_transactions")
        
        print(f"\n📈 Final Table Status:")
        print(f"   raw.etherscan_logs: {bridge_status['row_count']:,} rows")
        print(f"   raw.linea_transactions: {tx_status['row_count']:,} rows")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Load CSVs into raw; does not run dbt")
    parser.add_argument("--transformed-dir", type=Path)
    args = parser.parse_args()
    load_all_transformed_data(transformed_dir=args.transformed_dir)
