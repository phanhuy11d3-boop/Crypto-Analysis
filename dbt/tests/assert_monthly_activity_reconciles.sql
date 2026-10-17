select user_address, activity_month
from {{ ref('int_monthly_activity') }}
where transaction_count != successful_tx_count + failed_tx_count + unknown_status_tx_count
   or successful_tx_count != non_bridge_tx_count + bridge_tx_count + unclassified_tx_count
