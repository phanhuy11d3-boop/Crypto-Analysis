-- Whales must have bridged more than 10 ETH (business rule)
-- Returns whale classifications that don't meet the threshold

select *
from {{ ref('int_user_segments') }}
where user_segment = 'Whale' 
  and total_bridged_eth <= 10
