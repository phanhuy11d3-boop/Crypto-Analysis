select transaction_hash
from {{ ref('int_user_transactions') }}
where block_timestamp <= first_bridge_timestamp
   or (is_non_bridge_activity and not is_successful)
   or (is_non_bridge_activity and activity_bucket in ('Bridging', 'Unknown', 'Unclassified'))
