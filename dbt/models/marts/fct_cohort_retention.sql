-- One row per cohort/segment/calendar month since first observed bridge.
-- All cohort users are eligible, including users who first act after month 0.
-- Complete calendar months with no activity have zeros. Partial months retain
-- observed counts but their rates are NULL. Calendar completeness does NOT
-- certify that the upstream API extraction is complete.
with users as (
    select user_address, cohort_month, user_segment from {{ ref('dim_users') }}
),
user_month_grid as (
    select u.*, m.month_num as months_since_bridge,
        (to_date(u.cohort_month, 'YYYY-MM') + m.month_num * interval '1 month')::date as activity_month_date
    from users u
    cross join generate_series(0, 12) as m(month_num)
    where to_date(u.cohort_month, 'YYYY-MM') + m.month_num * interval '1 month'
        < ({{ extraction_end_exclusive_utc() }} at time zone 'UTC')
),
observed as (
    select g.*,
        coalesce(a.successful_tx_count, 0) > 0 as is_active,
        coalesce(a.non_bridge_tx_count, 0) > 0 as is_non_bridge_active,
        g.activity_month_date + interval '1 month'
            <= ({{ extraction_end_exclusive_utc() }} at time zone 'UTC') as is_month_complete
    from user_month_grid g
    left join {{ ref('int_monthly_activity') }} a
        on g.user_address = a.user_address
        and to_char(g.activity_month_date, 'YYYY-MM') = a.activity_month
),
prefix_activity as (
    select *,
        sum(is_active::integer) over (
            partition by user_address order by months_since_bridge
            rows between unbounded preceding and current row
        ) as active_months_so_far,
        sum(is_non_bridge_active::integer) over (
            partition by user_address order by months_since_bridge
            rows between unbounded preceding and current row
        ) as non_bridge_months_so_far
    from observed
),
counts as (
    select cohort_month, user_segment, months_since_bridge, activity_month_date,
        is_month_complete,
        count(*) as cohort_size,
        count(*) filter (where is_active) as active_users,
        count(*) filter (where is_non_bridge_active) as non_bridge_active_users,
        count(*) filter (where active_months_so_far = months_since_bridge + 1) as cumulative_users,
        count(*) filter (where non_bridge_months_so_far = months_since_bridge + 1) as non_bridge_cumulative_users
    from prefix_activity
    group by 1, 2, 3, 4, 5
)
select *,
    to_char(activity_month_date, 'YYYY-MM') as activity_month,
    case when is_month_complete then round(100.0 * active_users / nullif(cohort_size, 0), 2) end as retention_rate,
    case when is_month_complete then round(100.0 * non_bridge_active_users / nullif(cohort_size, 0), 2) end as non_bridge_retention_rate,
    case when is_month_complete then round(100.0 * cumulative_users / nullif(cohort_size, 0), 2) end as cumulative_retention_rate,
    case when is_month_complete then round(100.0 * non_bridge_cumulative_users / nullif(cohort_size, 0), 2) end as non_bridge_cumulative_retention_rate,
    -- Month-0 activation is a calendar-month metric, not a 7/30-day window.
    case when months_since_bridge = 0 and is_month_complete
        then round(100.0 * active_users / nullif(cohort_size, 0), 2) end as activation_rate,
    case when months_since_bridge = 0 and is_month_complete
        then round(100.0 * non_bridge_active_users / nullif(cohort_size, 0), 2) end as non_bridge_activation_rate,
    'Month ' || months_since_bridge as month_label
from counts
