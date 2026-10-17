-- One row per sender/month with post-bridge attempts. Successful activity
-- includes further bridges; non-bridge activity is reported separately.
with monthly_activity as (
    select
        user_address,
        activity_month,
        count(*) as transaction_count,
        count(*) filter (where is_successful) as successful_tx_count,
        count(*) filter (where if_transaction_failed is true) as failed_tx_count,
        count(*) filter (where not is_successful and if_transaction_failed is not true) as unknown_status_tx_count,
        count(*) filter (where is_non_bridge_activity) as non_bridge_tx_count,
        count(*) filter (where is_successful and activity_bucket = 'Bridging') as bridge_tx_count,
        count(*) filter (where is_successful and activity_bucket in ('Unknown', 'Unclassified')) as unclassified_tx_count,
        count(distinct date(block_timestamp)) filter (where is_successful) as active_days,
        count(distinct to_address) filter (where is_successful) as unique_destinations_interacted,
        coalesce(sum(value_eth) filter (where is_successful), 0) as total_eth_transacted,
        min(block_timestamp) filter (where is_successful) as first_tx_of_month,
        max(block_timestamp) filter (where is_successful) as last_tx_of_month
    from {{ ref('int_user_transactions') }}
    group by user_address, activity_month
)
select *,
    case
        when successful_tx_count >= 50 then 'Power User'
        when successful_tx_count >= 10 then 'Active'
        when successful_tx_count >= 3 then 'Casual'
        when successful_tx_count >= 1 then 'Minimal'
        else 'No successful activity'
    end as activity_level
from monthly_activity
