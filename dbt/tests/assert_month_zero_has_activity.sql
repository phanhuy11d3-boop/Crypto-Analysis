-- Bridge itself is not Linea activity. A zero-activity month 0 is valid.
-- Instead, every cohort/segment must have a month-0 row, including zero users.

select distinct u.cohort_month, u.user_segment
from {{ ref('dim_users') }} u
left join {{ ref('fct_cohort_retention') }} r
    on u.cohort_month = r.cohort_month
    and u.user_segment = r.user_segment
    and r.months_since_bridge = 0
where r.cohort_month is null
