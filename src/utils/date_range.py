"""Shared UTC boundaries: start inclusive, midnight after end date exclusive."""
import pandas as pd
from .config import EXTRACTION_START_DATE, EXTRACTION_END_EXCLUSIVE


def filter_date_range(frame, column="datetime"):
    timestamps = pd.to_datetime(frame[column], utc=True, errors="raise")
    start = pd.Timestamp(EXTRACTION_START_DATE, tz="UTC")
    end = pd.Timestamp(EXTRACTION_END_EXCLUSIVE, tz="UTC")
    return frame.loc[timestamps.ge(start) & timestamps.lt(end)].copy()
