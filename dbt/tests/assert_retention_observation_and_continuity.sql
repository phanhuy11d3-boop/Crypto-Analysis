with checked as (
    select *, lag(cumulative_users) over (
        partition by cohort_month, user_segment order by months_since_bridge
    ) as previous_cumulative
    from {{ ref('fct_cohort_retention') }}
)
select cohort_month, user_segment, months_since_bridge
from checked
where cumulative_users > active_users
   or cumulative_users > previous_cumulative
   or non_bridge_cumulative_users > non_bridge_active_users
   or non_bridge_active_users > active_users
   or (not is_month_complete and (retention_rate is not null or non_bridge_retention_rate is not null))
   or (is_month_complete and (retention_rate is null or non_bridge_retention_rate is null))
