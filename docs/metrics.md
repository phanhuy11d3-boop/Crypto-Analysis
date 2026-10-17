# Current metric definitions

The extraction window is configured in `dbt/dbt_project.yml`. All model timestamps
are UTC. A wallet means an address, not an identified person. Cohorts use the
sender of a positive-ETH MessageSent event from the configured Ethereum-to-Linea
contract. This is the first observed send in the dataset, not necessarily the
first historical send, and does not prove delivery on Linea.

## Activity scope

`int_user_transactions` is the shared scope for every activity mart:

- The sender is in `int_user_cohorts`.
- The Linea transaction timestamp is strictly after its first observed send.
- Failed/unknown-status attempts are retained for diagnostics.
- Successful activity requires `if_transaction_failed = false` and `tx_status = true`.
- Any successful outgoing transaction counts as activity, including a later bridge.
- Non-bridge activity additionally requires a recognized non-bridge bucket.
- Incoming-only transactions do not count as active use.

Classification still uses function-name heuristics, not execution traces or a
verified protocol registry. Approval is a separate bucket; multicall and generic
execute are not assumed to be swaps. Unknown/unclassified transactions count as
general successful activity but not as classified non-bridge activity. A non-bridge
metric is therefore conservative and subject to classification coverage.

## Monthly activity and user summary

`int_monthly_activity.transaction_count` counts post-bridge outgoing attempts.
`successful_tx_count`, `failed_tx_count`, and `unknown_status_tx_count` reconcile
to that total. Intensity, active days and ETH sent use successful transactions.
`unique_destinations_interacted` includes both wallet and contract destinations.
ETH value is native ETH attached to transactions, not total token trading volume.

`dim_users` has one row per cohort address, including those with no observed
activity. `post_bridge_tx_count` and `post_bridge_eth_transacted` replace the old
`lifetime_*` names; they cover only the available extraction window. An active
month contains at least one successful outgoing transaction. Engagement labels
summarize the number of active months; they do not require consecutive months.
`is_churned` is NULL until a two-month observation period is available, then tests
whether two calendar months have passed since the last observed successful
activity (or first bridge if never active). This is observed inactivity, not proof
that a person has abandoned Linea.

## Retention

One row per cohort month, segment and relative calendar month (0 through 12,
bounded by the extraction end). The denominator is ALL addresses in that cohort
and segment, including addresses with no month-0 activity.

- `retention_rate`: successful active addresses / cohort size, multiplied by 100.
- `non_bridge_retention_rate`: classified non-bridge active addresses / cohort size.
- `cumulative_retention_rate`: addresses active in EVERY month 0 through N / cohort size.
- `non_bridge_cumulative_retention_rate`: the same, requiring non-bridge activity each month.
- `activation_rate`: general activity rate in month 0, not a 7/30-day activation window.
- `non_bridge_activation_rate`: non-bridge activity rate in month 0.

Inactive complete months have zero counts/rates. Incomplete calendar months retain
their observed counts but all rates are NULL (`is_month_complete = false`).
For an end date of 2026-10-01, October is incomplete. Calendar completeness does
NOT certify API completeness. Late starters count in the months they are active.

## Other marts

`mart_activity_buckets` counts successful post-bridge Linea transactions and
unique senders by month, bucket, segment and tier. It retains Bridging and Unknown
buckets. Percentages use all successful post-bridge transactions in that month.

`mart_wallet_trading_sessions` retains its old table name for compatibility, but
now counts successful post-bridge Linea activity, not Ethereum bridge logs. UTC
intervals are [00,08), [08,16), [16,22), [22,24). These are time buckets, not proof
of a user's geographic location. Ties favor asian, european, american, off_hours.

## Extraction completeness

The repaired Linea extractor retries API/HTTP failures, splits capped block
windows, records every wallet's status, and caches only complete wallet results.
The published raw CSV is replaced only after ALL wallets succeed. Failed runs
produce `.status.json` and `.partial.csv`; rerun to resume completed wallets.
Do not load the partial CSV as a complete dataset.

Previously collected data remains incomplete until re-extracted with this code.
A successful dbt build validates transformations, not missing API history. Native
normal transactions are covered; internal transactions/token-transfer histories
and bridge-delivery matching are outside this dataset's scope.
