"""Boundary checks for the UTC window shared by Python and dbt."""
import sys
import unittest
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.config import EXTRACTION_START_DATE, EXTRACTION_END_DATE, EXTRACTION_END_EXCLUSIVE
from utils.date_range import filter_date_range


class DateWindowTests(unittest.TestCase):
    def test_python_reads_dbt_dates(self):
        values = yaml.safe_load((ROOT / "dbt/dbt_project.yml").read_text())["vars"]
        self.assertEqual(EXTRACTION_START_DATE, values["extraction_start_date"])
        self.assertEqual(EXTRACTION_END_DATE, values["extraction_end_date"])

    def test_start_inclusive_end_day_inclusive_next_midnight_excluded(self):
        start = pd.Timestamp(EXTRACTION_START_DATE, tz="UTC")
        end = pd.Timestamp(EXTRACTION_END_EXCLUSIVE, tz="UTC")
        frame = pd.DataFrame({"datetime": [start - pd.Timedelta(seconds=1), start,
            end - pd.Timedelta(microseconds=1), end]})
        self.assertEqual(filter_date_range(frame).index.tolist(), [1, 2])

    def test_timezone_offsets_are_compared_as_utc(self):
        start = pd.Timestamp(EXTRACTION_START_DATE, tz="UTC")
        frame = pd.DataFrame({"datetime": [start.tz_convert("Asia/Ho_Chi_Minh").isoformat(),
            (start - pd.Timedelta(seconds=1)).tz_convert("Asia/Ho_Chi_Minh").isoformat()]})
        self.assertEqual(filter_date_range(frame).index.tolist(), [0])


if __name__ == "__main__":
    unittest.main()
