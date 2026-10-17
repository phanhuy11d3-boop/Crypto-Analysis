with expected as (
    select user_address, count(*) as transactions
    from {{ ref('int_user_transactions') }}
    where is_successful
    group by user_address
)
select coalesce(e.user_address, s.user_address) as user_address
from expected e
full join {{ ref('mart_wallet_trading_sessions') }} s using (user_address)
where e.transactions is distinct from s.total_tx_count
   or s.total_tx_count != s.asian_tx_count + s.european_tx_count + s.american_tx_count + s.off_hours_tx_count
