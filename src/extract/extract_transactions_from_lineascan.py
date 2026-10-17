"""
Lineascan Address Info Extractor
================================
Fetches all transactions for bridged wallets from Lineascan.
"""

import sys
import time
import json
import threading
from datetime import datetime, timezone
import requests
import pandas as pd
from pathlib import Path

# Add project root to path so we can import config
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.config import (
    LINEASCAN_API_KEY,
    LINEASCAN_URL,
    LINEA_CHAIN_ID,
    ETHERSCAN_API_KEY,
    EXTRACTION_START_DATE,
    EXTRACTION_END_DATE,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    REQUEST_DELAY,
    REQUESTS_PER_SECOND
)
from utils.block_utils import get_linea_block_by_date
from utils.date_range import filter_date_range


# =============================================================================
# SESSION (reuse connection)
# =============================================================================

_local = threading.local()
_rate_lock = threading.Lock()
_last_request = 0.0
PAGE_SIZE = 1000
MAX_PAGES = 10  # Split block windows before exceeding the explorer result window.


class ExtractionError(RuntimeError):
    """The wallet result is incomplete; it must never be treated as empty."""


class WindowLimitError(ExtractionError):
    """Retry the wallet using smaller, disjoint block windows."""


def _get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _throttle():
    global _last_request
    with _rate_lock:
        delay = max(REQUEST_DELAY, 1.0 / REQUESTS_PER_SECOND)
        wait = delay - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def load_unique_wallets(logs_path):
    """Load unique wallet addresses from logs (filtered by date).
    
    Supports both raw logs (etherscan_logs.csv with timeStamp) 
    and processed logs (transformed_logs.csv with datetime).
    """
    df = pd.read_csv(logs_path)
    
    # Filter by date - handle both raw (timeStamp) and processed (datetime) formats
    if "timeStamp" in df.columns:
        # Raw logs: convert Unix timestamp to datetime
        seconds = df["timeStamp"].map(lambda value: int(str(value), 16) if str(value).startswith("0x") else int(value))
        df["datetime"] = pd.to_datetime(seconds, unit="s", utc=True)
    elif "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    else:
        raise ValueError("Logs must contain timeStamp or datetime to enforce the date window")
    df = filter_date_range(df)
    print(f"📅 UTC window: {EXTRACTION_START_DATE} through {EXTRACTION_END_DATE} (inclusive)")
    print(f"   Transactions in range: {len(df):,}")
    
    # The column name varies: _from (raw), from_address (processed), from
    if "_from" in df.columns:
        wallets = df["_from"].unique()
    elif "from_address" in df.columns:
        wallets = df["from_address"].unique()
    elif "from" in df.columns:
        wallets = df["from"].unique()
    else:
        print(f"Available columns: {df.columns.tolist()}")
        raise ValueError("Could not find wallet address column")
    
    return list(wallets)


def _request_page(address, start_block, end_block, page, max_retries):
    params = {"chainid": LINEA_CHAIN_ID, "module": "account", "action": "txlist",
              "address": address, "startblock": start_block, "endblock": end_block,
              "page": page, "offset": PAGE_SIZE, "sort": "asc", "apikey": LINEASCAN_API_KEY}
    reason = "unknown API failure"
    for attempt in range(max_retries):
        try:
            _throttle()
            response = _get_session().get(LINEASCAN_URL, params=params, timeout=30)
            if response.status_code != 200:
                reason = f"HTTP {response.status_code}"
            else:
                data = response.json()
                result = data.get("result")
                if data.get("status") == "1" and isinstance(result, list):
                    return result
                if data.get("status") == "0" and (
                    result == "No transactions found" or
                    (result == [] and data.get("message") == "No transactions found")
                ):
                    return []
                reason = str(result or data.get("message", "Invalid API response"))
                if LINEASCAN_API_KEY:
                    reason = reason.replace(LINEASCAN_API_KEY, "[redacted]")
                reason = reason[:200]
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            # Do not log request URLs: they contain the API key.
            reason = type(exc).__name__
        if attempt + 1 < max_retries:
            time.sleep(min(2 ** attempt, 16))
    error_type = WindowLimitError if any(term in reason.lower() for term in
        ("query timeout", "readtimeout", "result window", "response size")) else ExtractionError
    raise error_type(f"Wallet {address}, blocks {start_block}-{end_block}, page {page}: {reason}")


def get_transactions(address, start_block, end_block, max_retries=5):
    """Return a complete wallet result or raise; recursively split capped windows."""
    address = address.lower()

    def fetch_range(first, last):
        rows = []
        seen = set()
        for page in range(1, MAX_PAGES + 1):
            try:
                batch = _request_page(address, first, last, page, max_retries)
            except WindowLimitError:
                if first == last:
                    raise
                middle = (first + last) // 2
                return fetch_range(first, middle) + fetch_range(middle + 1, last)
            for tx in batch:
                if not isinstance(tx, dict) or not tx.get("hash") or "blockNumber" not in tx:
                    raise ExtractionError(f"Malformed transaction for {address}")
                block = int(tx["blockNumber"])
                if not first <= block <= last:
                    raise ExtractionError(f"API returned an out-of-range transaction for {address}")
                if address not in (str(tx.get("from", "")).lower(), str(tx.get("to", "")).lower()):
                    raise ExtractionError(f"API returned an unrelated transaction for {address}")
            hashes = {tx["hash"] for tx in batch}
            if seen.intersection(hashes) or len(hashes) != len(batch):
                raise ExtractionError(f"API repeated transaction hashes while paging {address}")
            seen.update(hashes)
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                return rows
        if first == last:
            raise ExtractionError(f"Single block {first} exceeds API result window for {address}")
        middle = (first + last) // 2
        return fetch_range(first, middle) + fetch_range(middle + 1, last)

    txs = fetch_range(start_block, end_block)
    for tx in txs:
        tx["wallet"] = address
    return txs


def _save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def extract_all_wallet_transactions(wallets, output_path, start_block, end_block,
                                    checkpoint_every=500, max_workers=4):
    """Resume completed wallets; publish the CSV only when every wallet succeeded.

    Failed/in-progress runs have a status manifest and partial CSV. The previous
    published CSV is left intact. Each completed wallet has an independent cache.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    output_path = Path(PROJECT_ROOT) / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wallets = sorted({str(w).lower() for w in wallets})
    cache = output_path.parent / f"{output_path.stem}_checkpoints" / f"{start_block}_{end_block}"
    cache.mkdir(parents=True, exist_ok=True)
    status_path = output_path.with_suffix(".status.json")
    partial_path = output_path.with_suffix(".partial.csv")
    manifest = {"complete": False, "start_block": start_block, "end_block": end_block,
                "chain_id": LINEA_CHAIN_ID, "wallets": {}, "updated_at_utc": None}
    all_transactions = []

    def save_status():
        manifest["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _save_json(status_path, manifest)

    save_status()

    def fetch(wallet):
        cached_path = cache / f"{wallet}.json"
        if cached_path.exists():
            txs = json.loads(cached_path.read_text(encoding="utf-8"))
            if isinstance(txs, list) and all(tx.get("wallet") == wallet for tx in txs):
                return txs
            raise ExtractionError(f"Invalid wallet checkpoint: {wallet}")
        txs = get_transactions(wallet, start_block, end_block)
        _save_json(cached_path, txs)
        return txs

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch, wallet): wallet for wallet in wallets}
        for future in as_completed(futures):
            wallet = futures[future]
            try:
                txs = future.result()
                all_transactions.extend(txs)
                manifest["wallets"][wallet] = {"status": "complete", "rows": len(txs)}
            except Exception as exc:
                message = str(exc)
                if LINEASCAN_API_KEY:
                    message = message.replace(LINEASCAN_API_KEY, "[redacted]")
                manifest["wallets"][wallet] = {"status": "failed", "error": message[:500]}
            save_status()
            processed = len(manifest["wallets"])
            if processed % 100 == 0 or processed == len(wallets):
                print(f"[{processed}/{len(wallets)}] {len(all_transactions):,} rows", flush=True)
            if processed % checkpoint_every == 0 and all_transactions:
                pd.DataFrame(all_transactions).to_csv(partial_path, index=False)

    failures = [w for w, result in manifest["wallets"].items() if result["status"] != "complete"]
    if failures:
        if all_transactions:
            pd.DataFrame(all_transactions).to_csv(partial_path, index=False)
        save_status()
        raise ExtractionError(f"Incomplete extraction: {len(failures)}/{len(wallets)} wallets failed. "
                              f"See {status_path}; rerun to resume. Published CSV was not replaced.")
    df = pd.DataFrame(all_transactions)
    if df.empty:
        df = pd.DataFrame(columns=["hash", "wallet", "timeStamp", "blockNumber", "from", "to"])
    temporary = output_path.with_suffix(".tmp.csv")
    df.to_csv(temporary, index=False)
    temporary.replace(output_path)
    manifest["complete"] = True
    save_status()
    print(f"Complete: {len(wallets)} wallets checked, {len(df):,} API rows saved", flush=True)
    return df


# =============================================================================
# MAIN - Run extraction
# =============================================================================

if __name__ == "__main__":
    
    if not LINEASCAN_API_KEY:
        print("❌ No ETHERSCAN_API_KEY (or LINEASCAN_API_KEY) in .env file!")
        exit(1)
    
    print("🚀 Linea Wallet Transaction Extraction")
    print("=" * 60)

    # Fetch block numbers for the date range
    print(f"📅 Date range: {EXTRACTION_START_DATE} → {EXTRACTION_END_DATE}")
    print("   Looking up block numbers...")
    start_block = get_linea_block_by_date(EXTRACTION_START_DATE, ETHERSCAN_API_KEY, closest="after")
    end_block = get_linea_block_by_date(EXTRACTION_END_DATE, ETHERSCAN_API_KEY, end_of_day=True)
    print(f"   Blocks: {start_block:,} → {end_block:,}")
    
    # Load unique wallets from processed logs (has decoded wallet addresses)
    processed_logs = Path(PROJECT_ROOT) / PROCESSED_DATA_DIR / "transformed_logs.csv"
    
    if not processed_logs.exists():
        print(f"❌ Processed logs not found: {processed_logs}")
        exit(1)
    
    wallets = load_unique_wallets(processed_logs)
    print(f"📋 Found {len(wallets):,} unique wallets to process")
    
    # Extract all transactions
    output_file = f"{RAW_DATA_DIR}/linea_transactions.csv"
    df = extract_all_wallet_transactions(
        wallets, 
        output_file,
        start_block=start_block,
        end_block=end_block
    )
    
    if not df.empty:
        print(f"\n📄 Sample row:")
        print(df.iloc[0].to_dict())
