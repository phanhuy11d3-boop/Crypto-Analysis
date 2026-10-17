-- Run in database linea_analytics. Refresh DBeaver schemas after dbt build.
SELECT * FROM analytics_marts.dim_users ORDER BY post_bridge_tx_count DESC;

-- Partial calendar months have NULL rates; observed counts remain visible.
SELECT cohort_month, user_segment, months_since_bridge, cohort_size,
       active_users, non_bridge_active_users, retention_rate,
       non_bridge_retention_rate, cumulative_retention_rate, is_month_complete
FROM analytics_marts.fct_cohort_retention
ORDER BY cohort_month, user_segment, months_since_bridge;

SELECT * FROM analytics_marts.mart_activity_buckets
ORDER BY activity_month, transaction_count DESC;

-- Historical name; these counts now refer to post-bridge Linea activity.
SELECT * FROM analytics_marts.mart_wallet_trading_sessions
ORDER BY total_tx_count DESC;
