-- Compatibility name: this now measures successful POST-bridge LINEA
-- activity, not Ethereum sends and not necessarily trading. Hours are UTC.
with tagged as (
    select *, case
        when extract(hour from block_timestamp) < 8 then 'asian'
        when extract(hour from block_timestamp) < 16 then 'european'
        when extract(hour from block_timestamp) < 22 then 'american'
        else 'off_hours'
    end as session
    from {{ ref('int_user_transactions') }}
    where is_successful
),
stats as (
    select user_address,
        count(*) filter (where session = 'asian') as asian_tx_count,
        count(*) filter (where session = 'european') as european_tx_count,
        count(*) filter (where session = 'american') as american_tx_count,
        count(*) filter (where session = 'off_hours') as off_hours_tx_count,
        count(*) as total_tx_count,
        count(*) filter (where is_non_bridge_activity) as non_bridge_tx_count,
        coalesce(sum(value_eth) filter (where session = 'asian'), 0) as asian_eth_volume,
        coalesce(sum(value_eth) filter (where session = 'european'), 0) as european_eth_volume,
        coalesce(sum(value_eth) filter (where session = 'american'), 0) as american_eth_volume,
        coalesce(sum(value_eth) filter (where session = 'off_hours'), 0) as off_hours_eth_volume,
        coalesce(sum(value_eth), 0) as total_eth_volume
    from tagged group by user_address
)
select *,
    -- Stable tie break: asian, european, american, off_hours.
    case
        when greatest(asian_tx_count, european_tx_count, american_tx_count, off_hours_tx_count) = asian_tx_count then 'asian'
        when greatest(asian_tx_count, european_tx_count, american_tx_count, off_hours_tx_count) = european_tx_count then 'european'
        when greatest(asian_tx_count, european_tx_count, american_tx_count, off_hours_tx_count) = american_tx_count then 'american'
        else 'off_hours'
    end as dominant_session,
    round(100.0 * asian_tx_count / nullif(total_tx_count, 0), 2) as asian_tx_pct,
    round(100.0 * european_tx_count / nullif(total_tx_count, 0), 2) as european_tx_pct,
    round(100.0 * american_tx_count / nullif(total_tx_count, 0), 2) as american_tx_pct,
    round(100.0 * off_hours_tx_count / nullif(total_tx_count, 0), 2) as off_hours_tx_pct
from stats
