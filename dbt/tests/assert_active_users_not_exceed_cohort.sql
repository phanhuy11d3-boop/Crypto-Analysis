-- Active users count cannot exceed cohort size
-- Returns rows where math is wrong

select *
from {{ ref('fct_cohort_retention') }}
where active_users > cohort_size
