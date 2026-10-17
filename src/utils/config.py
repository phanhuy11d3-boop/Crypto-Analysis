"""
Config - All project settings in one place
===========================================
"""

import os
from datetime import date, timedelta
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# =============================================================================
# API KEYS (from .env file)
# =============================================================================

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
LINEASCAN_API_KEY = os.getenv("LINEASCAN_API_KEY") or ETHERSCAN_API_KEY
INFURA_API_KEY = os.getenv("INFURA_API_KEY")

# =============================================================================
# API URLS
# =============================================================================

# Block explorers (for fetching logs)
# Etherscan v2 API is unified - use chainid param to select network
ETHERSCAN_URL = "https://api.etherscan.io/v2/api"
LINEASCAN_URL = "https://api.etherscan.io/v2/api"  # Same v2 endpoint, use chainid=59144

# Chain IDs (required for v2 API)
ETHEREUM_CHAIN_ID = 1
LINEA_CHAIN_ID = 59144

# RPC endpoints (for direct blockchain queries)
ETHEREUM_RPC = f"https://mainnet.infura.io/v3/{INFURA_API_KEY}"
LINEA_RPC = f"https://linea-mainnet.infura.io/v3/{INFURA_API_KEY}"

# =============================================================================
# CONTRACT ADDRESSES
# =============================================================================

# Linea Canonical Bridge on Ethereum Mainnet
LINEA_BRIDGE_CONTRACT = "0xd19d4B5d358258f05D7B411E21A1460D11B0876F"

# =============================================================================
# EVENT SIGNATURES (Topic0)
# =============================================================================

# MessageSent event - fires when someone bridges ETH to Linea
# This is the keccak256 hash of: MessageSent(address,address,uint256,uint256,uint256,bytes,bytes32)
MESSAGE_SENT_TOPIC = "0xe856c2b8bd4eb0027ce32eeaf595c21b0b6b4644b326e5b7bd80a1cf8db72e6c"

# =============================================================================
# EXTRACTION DATE RANGE (edit these to change extraction period)
# =============================================================================

# Read the same vars used by dbt; edit dates only in dbt/dbt_project.yml.
_project_config = Path(__file__).resolve().parents[2] / "dbt" / "dbt_project.yml"
_date_vars = yaml.safe_load(_project_config.read_text(encoding="utf-8"))["vars"]
EXTRACTION_START_DATE = str(_date_vars["extraction_start_date"])
EXTRACTION_END_DATE = str(_date_vars["extraction_end_date"])
if date.fromisoformat(EXTRACTION_START_DATE) > date.fromisoformat(EXTRACTION_END_DATE):
    raise ValueError("Extraction start date must not exceed end date")
EXTRACTION_END_EXCLUSIVE = (date.fromisoformat(EXTRACTION_END_DATE) + timedelta(days=1)).isoformat()

# =============================================================================
# USER SEGMENTATION
# =============================================================================

# Users who bridge more than this are "whales"
WHALE_THRESHOLD_USD = 10000

# =============================================================================
# DATA PATHS
# =============================================================================

# Where raw data gets saved
RAW_DATA_DIR = "data/raw"
PROCESSED_DATA_DIR = "data/transformed"

# Output file names
BRIDGE_LOGS_FILE = f"{RAW_DATA_DIR}/etherscan_logs.csv"
LINEA_TXS_FILE = f"{RAW_DATA_DIR}/linea_transactions.csv"

# =============================================================================
# API SETTINGS
# =============================================================================

# Etherscan rate limits
REQUESTS_PER_SECOND = 4 # max 5 in API
REQUEST_DELAY = 0.15  # seconds between requests

# =============================================================================
# DATABASE SETTINGS
# =============================================================================

# Postgres Database connection settings
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "linea_analytics")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
