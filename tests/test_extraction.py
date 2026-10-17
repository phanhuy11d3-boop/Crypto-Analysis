"""Failure/empty/pagination tests; these never call a live API."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from extract import extract_transactions_from_lineascan as api
from extract import extract_logs_from_etherscan as bridge_api


def response(payload):
    result = Mock(status_code=200)
    result.json.return_value = payload
    return result


class ExtractionTests(unittest.TestCase):
    def test_rate_limit_is_retried_not_treated_as_empty(self):
        client = Mock()
        client.get.side_effect = [response({"status": "0", "result": "Max rate limit reached"}),
                                  response({"status": "1", "result": []})]
        with patch.object(api, "_get_session", return_value=client), patch.object(api, "_throttle"), patch.object(api.time, "sleep"):
            self.assertEqual(api.get_transactions("wallet", 1, 2), [])
        self.assertEqual(client.get.call_count, 2)

    def test_real_empty_wallet_is_allowed(self):
        client = Mock()
        client.get.return_value = response({"status": "0", "message": "No transactions found", "result": []})
        with patch.object(api, "_get_session", return_value=client), patch.object(api, "_throttle"):
            self.assertEqual(api.get_transactions("wallet", 1, 2), [])

    def test_error_after_first_page_does_not_return_partial_wallet(self):
        first = [{"hash": "tx1", "blockNumber": "1", "from": "wallet", "to": "other"}]
        with patch.object(api, "PAGE_SIZE", 1), patch.object(api, "_request_page", side_effect=[first, api.ExtractionError("timeout")]):
            with self.assertRaises(api.ExtractionError):
                api.get_transactions("wallet", 1, 2)

    def test_failed_run_preserves_published_csv_and_can_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "txs.csv"
            output.write_text("previous complete snapshot")
            def fetch(wallet, *_):
                if wallet == "b":
                    raise api.ExtractionError("rate limited")
                return [{"hash": "tx-a", "wallet": wallet}]
            with patch.object(api, "get_transactions", side_effect=fetch):
                with self.assertRaises(api.ExtractionError):
                    api.extract_all_wallet_transactions(["a", "b"], output, 1, 2, max_workers=1)
            self.assertEqual(output.read_text(), "previous complete snapshot")
            self.assertFalse(json.loads(output.with_suffix(".status.json").read_text())["complete"])
            with patch.object(api, "get_transactions", return_value=[]) as retry:
                api.extract_all_wallet_transactions(["a", "b"], output, 1, 2, max_workers=1)
                retry.assert_called_once_with("b", 1, 2)
            self.assertTrue(json.loads(output.with_suffix(".status.json").read_text())["complete"])

    def test_capped_window_is_split_without_losing_boundary_blocks(self):
        txs = [{"hash": "tx1", "blockNumber": "1", "from": "wallet"},
               {"hash": "tx2", "blockNumber": "2", "from": "wallet"}]
        def page(address, first, last, page_no, retries):
            return [dict(tx) for tx in txs if first <= int(tx["blockNumber"]) <= last]
        with patch.object(api, "PAGE_SIZE", 2), patch.object(api, "MAX_PAGES", 1), patch.object(api, "_request_page", side_effect=page):
            result = api.get_transactions("wallet", 1, 2)
            self.assertEqual([tx["hash"] for tx in result], ["tx1", "tx2"])

    def test_bridge_api_error_is_not_an_empty_range(self):
        with patch.object(bridge_api.session, "get", return_value=response({"status": "0", "result": "Max rate limit reached"})):
            with self.assertRaises(RuntimeError):
                bridge_api.get_logs_for_range("contract", "topic", 1, 2)

    def test_bridge_empty_range_is_allowed(self):
        with patch.object(bridge_api.session, "get", return_value=response({"status": "0", "message": "No records found", "result": []})):
            self.assertEqual(bridge_api.get_logs_for_range("contract", "topic", 1, 2), [])

    def test_query_timeout_splits_the_window(self):
        def page(address, first, last, page_no, retries):
            if first != last:
                raise api.WindowLimitError("Query Timeout")
            return [{"hash": f"tx{first}", "blockNumber": str(first), "from": "wallet"}]
        with patch.object(api, "_request_page", side_effect=page):
            rows = api.get_transactions("wallet", 1, 2)
            self.assertEqual([row["hash"] for row in rows], ["tx1", "tx2"])

    def test_exhausted_api_errors_raise_instead_of_returning_empty(self):
        client = Mock()
        client.get.return_value = response({"status": "0", "result": "Max rate limit reached"})
        with patch.object(api, "_get_session", return_value=client), patch.object(api, "_throttle"), patch.object(api.time, "sleep"):
            with self.assertRaises(api.ExtractionError):
                api.get_transactions("wallet", 1, 2, max_retries=2)
        self.assertEqual(client.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
