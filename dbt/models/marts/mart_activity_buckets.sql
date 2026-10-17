-- Successful outgoing Linea transactions after the sender's first observed
-- bridge. Retain Bridging and Unknown as separate buckets, not as non-bridge.
with monthly as (
    select
        t.activity_month,
        t.activity_bucket,
        u.user_segment,
        u.user_tier,
        count(*) as transaction_count,
        count(distinct t.user_address) as unique_users,
        count(*) filter (where t.is_non_bridge_activity) as non_bridge_tx_count
    from {{ ref('int_user_transactions') }} t
    inner join {{ ref('dim_users') }} u using (user_address)
    where t.is_successful
    group by 1, 2, 3, 4
)
select *, round(100.0 * transaction_count /
    nullif(sum(transaction_count) over (partition by activity_month), 0), 2) as pct_of_month_txns
from monthly
