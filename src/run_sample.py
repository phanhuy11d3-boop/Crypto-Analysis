"""Run a bounded extraction sample: one UTC day and at most five wallets."""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from utils.config import ETHERSCAN_API_KEY, ETHERSCAN_URL, LINEA_BRIDGE_CONTRACT, MESSAGE_SENT_TOPIC, EXTRACTION_START_DATE
from transform.transform_logs import parse_logs
from transform.transform_transactions import transform_transactions
from transform.validate_transformed_logs import validate_logs
from transform.validate_transformed_transactions import validate_transactions

ROOT = Path(__file__).resolve().parent.parent
DAY = EXTRACTION_START_DATE
PAGE_SIZE = 100
session = requests.Session()


def request(chain, **params):
    time.sleep(0.6)
    response = session.get(ETHERSCAN_URL, params={
        'chainid': chain, 'apikey': ETHERSCAN_API_KEY, **params
    }, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f'HTTP {response.status_code} on chain {chain}')
    data = response.json()
    if data.get('status') == '1':
        return data['result']
    result = data.get('result')
    if result == [] and data.get('message') in ('No records found', 'No transactions found'):
        return []
    if str(result) in ('No records found', 'No transactions found'):
        return []
    raise RuntimeError(f'API rejected chain {chain}: {str(result).replace(ETHERSCAN_API_KEY, "[redacted]")}')


def pages(chain, **params):
    rows = []
    for page in range(1, 101):
        batch = request(chain, page=page, offset=PAGE_SIZE, **params)
        if not isinstance(batch, list):
            raise RuntimeError('Unexpected API response shape')
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
    raise RuntimeError('Sample exceeded its page budget; output would be incomplete')


def main():
    if not ETHERSCAN_API_KEY:
        raise RuntimeError('Set ETHERSCAN_API_KEY in .env first')
    start = datetime.fromisoformat(DAY).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    bounds = {}
    for chain in (1, 59144):
        first = int(request(chain, module='block', action='getblocknobytime',
                            timestamp=int(start.timestamp()), closest='after'))
        last = int(request(chain, module='block', action='getblocknobytime',
                           timestamp=int(end.timestamp()) - 1, closest='before'))
        bounds[chain] = (first, last)
        print(f'Chain {chain}: blocks {first} - {last}', flush=True)
    raw = pd.DataFrame(pages(1, module='logs', action='getLogs',
        address=LINEA_BRIDGE_CONTRACT, topic0=MESSAGE_SENT_TOPIC,
        fromBlock=bounds[1][0], toBlock=bounds[1][1]))
    if raw.empty:
        raise RuntimeError('No bridge logs found for the sample day')
    output = ROOT / 'data' / 'raw' / f'sample_{DAY}'
    output.mkdir(parents=True, exist_ok=True)
    raw.to_csv(output / 'etherscan_logs.csv', index=False)
    # The repository parser expects the CSV representation of topic lists.
    parser_input = raw.copy()
    parser_input['topics'] = parser_input['topics'].map(str)
    decoded = parse_logs(parser_input)
    decoded = decoded.loc[decoded["value_eth"] > 0].copy()
    if not validate_logs(raw, decoded):
        raise RuntimeError('Bridge log validation failed')
    decoded.to_csv(output / 'transformed_logs.csv', index=False)
    wallets = decoded['from_address'].dropna().drop_duplicates().head(5).tolist()
    transactions = []
    counts = {}
    for wallet in wallets:
        txs = pages(59144, module='account', action='txlist', address=wallet,
            startblock=bounds[59144][0], endblock=bounds[59144][1], sort='asc')
        counts[wallet] = len(txs)
        transactions.extend(txs)
        print(f'Wallet {len(counts)}/{len(wallets)}: {len(txs)} transactions', flush=True)
    raw_txs = pd.DataFrame(transactions)
    if not raw_txs.empty:
        raw_txs.to_csv(output / 'linea_transactions.csv', index=False)
        transformed = transform_transactions(raw_txs.copy())
        if not validate_transactions(raw_txs, transformed):
            raise RuntimeError('Transaction validation failed')
        transformed.to_csv(output / 'transformed_transactions.csv', index=False)
    summary = {'day_utc': DAY, 'bridge_logs': len(raw),
        'unique_bridging_wallets': decoded['from_address'].nunique(),
        'sampled_wallets': counts, 'linea_transactions_unique':
        raw_txs['hash'].nunique() if not raw_txs.empty else 0}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'Output: {output}')


if __name__ == '__main__':
    try:
        main()
    except requests.RequestException as exc:
        print(f'Network request failed: {type(exc).__name__}', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        message = str(exc)
        if ETHERSCAN_API_KEY:
            message = message.replace(ETHERSCAN_API_KEY, '[redacted]')
        print(message, file=sys.stderr)
        sys.exit(1)
