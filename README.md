# Crypto Analysis — Linea User Analytics

An end-to-end blockchain analytics pipeline built with Python, PostgreSQL, and dbt to study what wallets do on Linea after sending ETH through the canonical bridge from Ethereum.

The project addresses a practical question: **Do bridging wallets continue using Linea, and how does engagement differ across cohorts and wallet segments?**

## What the project does

- Extracts Ethereum bridge events and normal Linea transactions through the Etherscan V2 API.
- Decodes bridge logs, validates transformed records, and loads them into PostgreSQL.
- Builds monthly cohorts and segments wallets by observed ETH bridge volume.
- Measures activation, monthly retention, continuous retention, and observed inactivity.
- Classifies activity into bridging, swapping, approvals, NFTs, DeFi, governance/campaigns, transfers, claims, and unknown activity.
- Produces analytics tables for BI dashboards, with SQL examples for exploring the results.
- Supports a bounded extraction sample and an optional SQLite snapshot for local inspection.

## Architecture

```text
Etherscan V2 API
  ├── Ethereum: canonical bridge MessageSent events
  └── Linea: wallet normal transactions
                  |
          Python extraction
                  |
       CSV transformation + validation
                  |
       PostgreSQL: raw source tables
                  |
       dbt staging → intermediate → marts
                  |
         SQL analysis / external BI
```

The core stack is Python, pandas, requests, PostgreSQL, and dbt-postgres. Docker Compose provides an optional PostgreSQL 16 service. BI tools connect to the generated tables separately; this repository does not include a dashboard application or an Airflow deployment.

## Analytics models

| Model | Purpose |
| --- | --- |
| `int_user_cohorts` | First observed positive-ETH bridge send and cohort assignment |
| `int_user_segments` | Whale/Retail segmentation and bridge-volume tiers |
| `int_user_transactions` | Shared post-bridge transaction scope |
| `int_monthly_activity` | Monthly attempts, successful activity, failures, and non-bridge activity |
| `dim_users` | Wallet-level engagement and observed inactivity summary |
| `fct_cohort_retention` | Activation, monthly retention, and continuous retention |
| `mart_activity_buckets` | Activity distribution by month, segment, and tier |
| `mart_wallet_trading_sessions` | Successful Linea activity grouped by UTC time intervals |

Whales have more than 10 ETH in observed bridge volume; other wallets are Retail. These thresholds are currently defined in `dbt/models/intermediate/int_user_segments.sql`.

## Metric scope

A user represents a wallet address. Cohorts use the first observed positive-ETH `MessageSent` event within the configured dataset, rather than a wallet's first-ever bridge or confirmed delivery on Linea.

Activity requires a successful outgoing Linea transaction strictly after that first observed bridge send. Later bridges count toward general activity; recognized non-bridge activity is measured separately. Incoming transfers alone do not count as active use.

Retention uses the entire cohort as its denominator, including wallets without month-0 activity. Continuous retention requires activity in every month from month 0 through the reported month. Complete inactive months have zero rates; incomplete calendar months have NULL rates.

Function-name classification is heuristic. ETH values measure native ETH attached to transactions, not total token trading volume. UTC activity buckets do not identify a user's location.

See [metric definitions and limitations](docs/metrics.md) for the full specification.

## Getting started

### 1. Install dependencies

Use Python 3.10 or 3.11. Run the following from the repository root:

```powershell
git clone https://github.com/phanhuy11d3-boop/Crypto-Analysis.git
cd Crypto-Analysis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure credentials

Create a local `.env` file:

```dotenv
ETHERSCAN_API_KEY=your_etherscan_api_key
LINEASCAN_API_KEY=your_etherscan_api_key
INFURA_API_KEY=your_infura_api_key
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=linea_analytics
POSTGRES_USER=postgres
POSTGRES_PASSWORD=replace_with_your_local_password
```

Both networks use the Etherscan V2 endpoint, with chain IDs `1` and `59144`. `LINEASCAN_API_KEY` falls back to `ETHERSCAN_API_KEY`. API access and plan coverage must support the requested networks and endpoints.

### 3. Set the analysis window

Edit the shared configuration in `dbt/dbt_project.yml`:

```yaml
vars:
  extraction_start_date: '2026-01-01'
  extraction_end_date: '2026-10-01'
```

Python and dbt read these dates. Both boundary dates are inclusive in UTC. Changing them requires re-extracting and reloading the relevant data; avoid overriding only dbt's date variables with `--vars`.

### 4. Start PostgreSQL and configure dbt

Use an existing PostgreSQL instance or start the included service:

```powershell
docker compose up -d warehouse
```

Create `dbt/profiles.yml` locally:

```yaml
linea_analytics:
  target: dev
  outputs:
    dev:
      type: postgres
      host: "{{ env_var('POSTGRES_HOST', 'localhost') }}"
      port: "{{ env_var('POSTGRES_PORT', '5432') | int }}"
      user: "{{ env_var('POSTGRES_USER', 'postgres') }}"
      password: "{{ env_var('POSTGRES_PASSWORD') }}"
      dbname: "{{ env_var('POSTGRES_DB', 'linea_analytics') }}"
      schema: public
      threads: 4
```

The dbt source declaration currently names database `linea_analytics`. If you choose another database name, update `dbt/models/staging/sources.yml` to match. With this profile, dbt creates `public_staging`, `public_intermediate`, and `public_marts` schemas using its default schema naming behavior.

### 5. Run the pipeline

```powershell
python src/extract/extract_logs_from_etherscan.py
python src/transform/transform_logs.py
python src/extract/extract_transactions_from_lineascan.py
python src/transform/transform_transactions.py
python src/load/load_to_database.py
python src/run_dbt.py build
```

The loader populates raw tables; the dbt command builds and tests the analytics models. Start exploring with [mart queries](sql/mart_queries.sql) and [raw data queries](sql/raw_queries.sql).

### Optional: bounded API sample

```powershell
python src/run_sample.py
```

This extracts the first UTC day of the configured window and inspects at most five bridge senders. Output is written to `data/raw/sample_<date>/`; it does not replace the main pipeline dataset or automatically load PostgreSQL.

### Optional: SQLite snapshot

After preparing transformed bridge logs and the main Linea transaction cache:

```powershell
python src/load/load_to_sqlite.py
```

This creates `data/linea_analytics.sqlite` for local inspection. The dbt analytics pipeline still uses PostgreSQL.

## Extraction completeness

The Linea extractor retries failed requests, splits capped block windows, and caches complete wallet results for resuming a run. It publishes the main CSV only after all queried wallets succeed. Failed runs leave a status manifest and a partial CSV; rerun extraction to resume, and do not treat partial output as complete data.

Previously collected API data is known to be incomplete until re-extracted. Successful dbt builds validate model behavior and do not establish API completeness. Coverage excludes internal transactions, full token-transfer history, and bridge-delivery matching.

## Verification

```powershell
python -m unittest discover -s tests -v
```

To additionally run PostgreSQL fixture tests against a configured, running database:

```powershell
$env:RUN_DB_INTEGRATION='1'
python -m unittest discover -s tests -p test_metric_scenarios.py -v
python src/run_dbt.py build
```

The fixture tests execute model SQL through read-only PostgreSQL CTEs. They cover late activation, activity gaps, failed attempts, pre-bridge activity, passive receipts, classification, empty months, and partial-month rates.

## Repository structure

```text
├── compose.yml          # Optional PostgreSQL service
├── dbt/
│   ├── macros/          # Shared extraction-window SQL
│   ├── models/          # Staging, intermediate, and mart models
│   ├── seeds/           # Reference data
│   └── tests/           # dbt data assertions
├── docs/metrics.md      # Metric definitions and limitations
├── sql/                 # Exploration queries
├── src/
│   ├── extract/         # API extraction
│   ├── transform/       # Decoding, cleaning, and validation
│   ├── load/            # PostgreSQL and SQLite loaders
│   ├── utils/           # Configuration and shared helpers
│   ├── run_dbt.py       # dbt wrapper using local environment
│   └── run_sample.py    # Bounded extraction sample
├── tests/               # Python and SQL fixture tests
└── requirements.txt
```

Credentials, local dbt profiles, virtual environments, generated dbt artifacts, and local datasets are excluded from version control.
