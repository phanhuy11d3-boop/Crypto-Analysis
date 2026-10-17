-- Run against database linea_analytics. No staging/dbt required.
SET TIME ZONE 'UTC';

SELECT 'bridge_logs' AS dataset, COUNT(*) AS rows FROM raw.etherscan_logs
UNION ALL
SELECT 'linea_transactions', COUNT(*) FROM raw.linea_transactions;

SELECT datetime, from_address, to_address, value_eth, fee_eth, tx_hash
FROM raw.etherscan_logs ORDER BY datetime LIMIT 20;

SELECT datetime, from_address, to_address, value_eth, function_name, is_error, hash
FROM raw.linea_transactions ORDER BY datetime LIMIT 20;

SELECT from_address, COUNT(*) AS transactions,
       COUNT(*) FILTER (WHERE is_error) AS failed_transactions
FROM raw.linea_transactions
GROUP BY from_address ORDER BY transactions DESC;

-- Bridge logs cover 45 wallets; Linea transactions cover only the five
-- sampled wallets. Missing activity for other wallets is not evidence of churn.
