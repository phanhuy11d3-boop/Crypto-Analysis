-- Shared activity scope: outgoing transactions strictly AFTER the first
-- observed positive-ETH send. This does not prove bridge delivery on Linea.
-- Keep failed/unknown transactions for diagnostics, but don't count as success.
select
    t.*,
    c.first_bridge_timestamp,
    c.cohort_month,
    (t.if_transaction_failed is false and t.tx_status is true) as is_successful,
    (t.if_transaction_failed is false and t.tx_status is true
        and t.is_classified_non_bridge) as is_non_bridge_activity
from {{ ref('stg_function_categories') }} t
inner join {{ ref('int_user_cohorts') }} c
    on t.user_address = c.user_address
where t.block_timestamp > c.first_bridge_timestamp
