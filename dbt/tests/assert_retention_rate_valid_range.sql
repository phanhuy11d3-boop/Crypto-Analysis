-- Retention rate must be between 0% and 100%
-- Returns rows that violate this rule (should return 0 rows)

select *
from {{ ref('fct_cohort_retention') }}
where retention_rate < 0 or retention_rate > 100
