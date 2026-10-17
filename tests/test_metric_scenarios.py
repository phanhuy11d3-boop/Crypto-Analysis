"""Run the actual dbt model SQL against small fixtures using read-only Postgres.

Enable with RUN_DB_INTEGRATION=1. No fixture tables or production data are written.
"""
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined
from psycopg2.extensions import adapt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.load.load_to_database import get_db_connection


def values_sql(columns, rows):
    def literal(value):
        return adapt(value).getquoted().decode("utf8")
    values = ','.join('(' + ','.join(literal(v) for v in row) + ')' for row in rows)
    return 'select * from (values ' + values + ') as fixture(' + ','.join(columns) + ')'


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "Set RUN_DB_INTEGRATION=1 for Postgres fixture tests")
class MetricScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = get_db_connection()
        cls.connection.set_session(readonly=True, autocommit=True)
        cohort = ['late', 'gap', 'bridge', 'failed', 'pre', 'unknown', 'receiver']
        bridge_rows = [(w, datetime(2026, 1, 10, 12), 1) for w in cohort]
        bridge_rows.append(('partial', datetime(2026, 9, 30, 12), 1))
        transactions = []
        def tx(key, sender, when, function, failed=False, recipient='contract'):
            transactions.append((key, sender, recipient, datetime.fromisoformat(when), 0.1,
                                 failed, not failed, '0x12345678', function))
        tx('late-feb', 'late', '2026-02-03T10:00:00', 'swap(...)')
        tx('gap-jan', 'gap', '2026-01-11T10:00:00', 'swap(...)')
        tx('gap-approve', 'gap', '2026-01-12T10:00:00', 'approve(...)')
        tx('gap-mar', 'gap', '2026-03-03T10:00:00', 'swap(...)')
        tx('bridge-jan', 'bridge', '2026-01-11T10:00:00', 'sendMessage(...)')
        tx('failed-jan', 'failed', '2026-01-11T10:00:00', 'swap(...)', failed=True)
        tx('pre-before', 'pre', '2026-01-10T11:00:00', 'swap(...)')
        tx('unknown-jan', 'unknown', '2026-01-11T10:00:00', None)
        tx('only-received', 'outsider', '2026-01-11T10:00:00', 'transfer(...)', recipient='receiver')
        tx('partial-oct', 'partial', '2026-10-01T10:00:00', 'swap(...)')
        tx('unresolved-multicall', 'unknown', '2026-01-12T10:00:00', 'multicall(...)')
        env = Environment(undefined=StrictUndefined)
        dates = yaml.safe_load((ROOT / 'dbt/dbt_project.yml').read_text())["vars"]
        # Fixed fixture window, independent from future production date changes.
        dates.update(extraction_start_date='2026-01-01', extraction_end_date='2026-10-01')
        env.globals.update(ref=lambda name: name, var=lambda name: dates[name])
        macros = env.from_string((ROOT / 'dbt/macros/extraction_window.sql').read_text()).module
        env.globals.update(extraction_start_utc=macros.extraction_start_utc,
                           extraction_end_exclusive_utc=macros.extraction_end_exclusive_utc)
        ctes = [
            'stg_etherscan_logs as (' + values_sql(['from_address','block_timestamp','value_eth'],bridge_rows) + ')',
            'stg_linea_transactions as (' + values_sql(['transaction_hash','from_address','to_address',
                'block_timestamp','value_eth','if_transaction_failed','tx_status','method_id','function_name'], transactions) + ')',
        ]
        files = {p.stem: p for p in (ROOT/'dbt/models').rglob('*.sql')}
        for name in ['stg_function_categories','int_user_cohorts','int_user_segments',
                     'int_user_transactions','int_monthly_activity','dim_users',
                     'fct_cohort_retention','mart_activity_buckets','mart_wallet_trading_sessions']:
            ctes.append(name + ' as (' + env.from_string(files[name].read_text(encoding='utf8')).render() + ')')
        cls.prefix = 'WITH ' + ','.join(ctes)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def query(self, query):
        with self.connection.cursor() as cur:
            cur.execute(self.prefix + ' ' + query)
            return cur.fetchall()

    def test_pre_bridge_and_incoming_are_excluded(self):
        rows = self.query("select transaction_hash from int_user_transactions where user_address in ('pre','receiver')")
        self.assertEqual(rows, [])

    def test_bridge_is_activity_but_not_non_bridge_activity(self):
        self.assertEqual(self.query("select is_successful,is_non_bridge_activity from int_user_transactions where user_address='bridge'"), [(True,False)])

    def test_failed_transactions_do_not_make_a_user_active(self):
        self.assertEqual(self.query("select active_months,successful_tx_count,failed_tx_count from dim_users where user_address='failed'"), [(0,0,1)])

    def test_late_activation_counts_in_retention_with_full_cohort_denominator(self):
        self.assertEqual(self.query("select cohort_size,active_users from fct_cohort_retention where cohort_month='2026-01' and months_since_bridge=1"), [(7,1)])

    def test_gap_breaks_continuous_retention(self):
        self.assertEqual(self.query("select active_users,cumulative_users from fct_cohort_retention where cohort_month='2026-01' and months_since_bridge=2"), [(1,0)])

    def test_empty_months_are_zero_and_partial_rates_are_null(self):
        self.assertEqual(self.query("select active_users,retention_rate from fct_cohort_retention where cohort_month='2026-01' and months_since_bridge=3"), [(0,0)])
        self.assertEqual(self.query("select is_month_complete,active_users,retention_rate from fct_cohort_retention where cohort_month='2026-09' and months_since_bridge=1"), [(False,1,None)])

    def test_approval_and_unknown_classification(self):
        rows = dict(self.query("select transaction_hash,activity_bucket from stg_function_categories where transaction_hash in ('gap-approve','unresolved-multicall')"))
        self.assertEqual(rows, {'gap-approve':'Approval','unresolved-multicall':'Unclassified'})
        self.assertEqual(self.query("select bool_or(is_non_bridge_activity) from int_user_transactions where user_address='unknown'"), [(False,)])

    def test_sessions_use_post_bridge_linea_not_bridge_counts(self):
        self.assertEqual(self.query("select total_tx_count,european_tx_count from mart_wallet_trading_sessions where user_address='gap'"), [(3,3)])


if __name__ == '__main__':
    unittest.main()
