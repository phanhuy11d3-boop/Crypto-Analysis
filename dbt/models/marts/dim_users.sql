-- One row per bridge sender. All activity summaries are POST-bridge and
-- limited to the extraction window; no metric claims lifetime coverage.
with activity as (
    select
        user_address,
        count(*) filter (where successful_tx_count > 0) as active_months,
        count(*) filter (where non_bridge_tx_count > 0) as non_bridge_active_months,
        sum(transaction_count) as post_bridge_tx_count,
        sum(successful_tx_count) as successful_tx_count,
        sum(failed_tx_count) as failed_tx_count,
        sum(non_bridge_tx_count) as non_bridge_tx_count,
        sum(total_eth_transacted) as post_bridge_eth_transacted,
        min(activity_month) filter (where successful_tx_count > 0) as first_active_month,
        max(activity_month) filter (where successful_tx_count > 0) as last_active_month,
        max(last_tx_of_month) as last_active_timestamp
    from {{ ref('int_monthly_activity') }}
    group by user_address
)
select
    s.*,
    c.first_bridge_timestamp,
    coalesce(a.active_months, 0) as active_months,
    coalesce(a.non_bridge_active_months, 0) as non_bridge_active_months,
    coalesce(a.post_bridge_tx_count, 0) as post_bridge_tx_count,
    coalesce(a.successful_tx_count, 0) as successful_tx_count,
    coalesce(a.failed_tx_count, 0) as failed_tx_count,
    coalesce(a.non_bridge_tx_count, 0) as non_bridge_tx_count,
    coalesce(a.post_bridge_eth_transacted, 0) as post_bridge_eth_transacted,
    a.first_active_month,
    a.last_active_month,
    a.last_active_timestamp,
    -- No churn conclusion before a full two-month observation period.
    -- This remains based on OBSERVED data; incomplete extraction can bias it.
    case
        when c.first_bridge_timestamp + interval '2 months'
             > ({{ extraction_end_exclusive_utc() }} at time zone 'UTC') then null
        else coalesce(a.last_active_timestamp, c.first_bridge_timestamp)
             + interval '2 months' <= ({{ extraction_end_exclusive_utc() }} at time zone 'UTC')
    end as is_churned,
    case
        when a.active_months >= 3 and s.user_segment = 'Whale' then 'High Value Retained (3+ months, Whale)'
        when a.active_months >= 3 then 'Retained (3+ months)'
        when a.active_months >= 1 then 'Engaged (1-2 months)'
        else 'No observed successful activity'
    end as engagement_status
from {{ ref('int_user_segments') }} s
inner join {{ ref('int_user_cohorts') }} c using (user_address)
left join activity a using (user_address)
