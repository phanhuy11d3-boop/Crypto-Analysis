"""
Unit Tests for transform_logs.py
================================
Tests pure transformation functions (no API calls, no file I/O).
"""

import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from transform.transform_logs import (
    hex_to_int,
    hex_to_address,
    wei_to_eth,
    decode_data,
    parse_topics
)


# =============================================================================
# TESTS
# =============================================================================

def test_hex_to_int():
    """Test hex string to integer conversion."""
    assert hex_to_int("0x1f4") == 500
    assert hex_to_int("0x0") == 0
    assert hex_to_int("0x") == 0
    assert hex_to_int(None) == 0


def test_hex_to_address():
    """Test address extraction from padded hex."""
    # 32-byte padded hex (64 chars after 0x)
    padded = "0x000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa96045"
    assert hex_to_address(padded) == "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
    assert hex_to_address(None) is None


def test_wei_to_eth():
    """Test wei to ETH conversion."""
    assert wei_to_eth(1_000_000_000_000_000_000) == 1.0  # 1 ETH
    assert wei_to_eth(500_000_000_000_000_000) == 0.5    # 0.5 ETH
    assert wei_to_eth(0) == 0.0
    assert wei_to_eth(None) is None


def test_decode_data():
    """Test MessageSent event data decoding."""
    # Sample data: fee=100, value=1 ETH (1e18 wei), nonce=42
    # Each value is 32 bytes (64 hex chars)
    fee_hex = format(100, '064x')
    value_hex = format(10**18, '064x')
    nonce_hex = format(42, '064x')
    data = "0x" + fee_hex + value_hex + nonce_hex + ("0" * 128)  # + padding
    
    fee, value, nonce = decode_data(data)
    assert fee == 100
    assert value == 10**18
    assert nonce == 42
    
    # Edge case: short data
    assert decode_data("0x") == (None, None, None)
    assert decode_data(None) == (None, None, None)


def test_parse_topics():
    """Test topics string parsing."""
    topics_str = "['0xabc', '0xdef', '0x123']"
    result = parse_topics(topics_str)
    assert result == ['0xabc', '0xdef', '0x123']
    assert parse_topics(None) == []


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    # Simple test runner
    tests = [
        test_hex_to_int,
        test_hex_to_address,
        test_wei_to_eth,
        test_decode_data,
        test_parse_topics
    ]
    
    passed = 0
    for test in tests:
        try:
            test()
            print(f"✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
    
    print(f"\n{'='*40}")
    print(f"Passed: {passed}/{len(tests)}")
