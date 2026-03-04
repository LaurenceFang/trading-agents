from __future__ import annotations

"""单元测试 - PriceLimitChecker（指标 #7）"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# 依赖 PriceLimitChecker 时需要一个有效的 config，用 mock 读取
# ---------------------------------------------------------------------------

_MOCK_CONFIG = """
futures_monitor:
  max_orders_per_day: 500
  max_cancels_per_day: 200
  max_duplicate_orders: 5
  max_lots_per_order: 10
  warning_pct: 0.8
  price_limit_pct: 0.1
"""


def _make_checker():
    """Create a PriceLimitChecker with mocked config file."""
    import io
    from core.price_limit_checker import PriceLimitChecker

    mock_path = Path("/fake/risk_params.yaml")
    with patch.object(Path, "open", return_value=io.StringIO(_MOCK_CONFIG)):
        checker = PriceLimitChecker(config_path=mock_path)
    return checker


# ---------------------------------------------------------------------------
# 价格测试
# ---------------------------------------------------------------------------

def test_price_within_limit_passes():
    """price 在 ref_price ± 10% 范围内 → passed=True"""
    checker = _make_checker()
    result = checker.check_price(Decimal("100"), Decimal("100"))
    assert result.passed is True
    assert result.reason == ""


def test_price_within_limit_edge_passes():
    """price == ref_price * 1.1 (exactly at limit boundary) → passed=True"""
    checker = _make_checker()
    result = checker.check_price(Decimal("110"), Decimal("100"))
    assert result.passed is True


def test_price_above_limit_fails():
    """price > ref_price * 1.1 → passed=False， reason 非空"""
    checker = _make_checker()
    result = checker.check_price(Decimal("111"), Decimal("100"))
    assert result.passed is False
    assert result.reason != ""


def test_price_below_limit_fails():
    """price < ref_price * 0.9 → passed=False"""
    checker = _make_checker()
    result = checker.check_price(Decimal("89"), Decimal("100"))
    assert result.passed is False
    assert result.reason != ""


# ---------------------------------------------------------------------------
# 手数测试
# ---------------------------------------------------------------------------

def test_lots_within_limit_passes():
    """lots ≤ max_lots_per_order (10) → passed=True"""
    checker = _make_checker()
    result = checker.check_lots(10)
    assert result.passed is True
    assert result.reason == ""


def test_lots_exceed_limit_fails():
    """lots > max_lots_per_order (10) → passed=False"""
    checker = _make_checker()
    result = checker.check_lots(11)
    assert result.passed is False
    assert result.reason != ""


# ---------------------------------------------------------------------------
# 组合检查
# ---------------------------------------------------------------------------

def test_check_order_fails_on_price():
    """价格失败时 check_order 先返回价格失败结果"""
    checker = _make_checker()
    result = checker.check_order(
        order_price=Decimal("200"),  # 远超上限
        ref_price=Decimal("100"),
        lots=5,  # lots OK
    )
    assert result.passed is False
    assert "涨停" in result.reason or "price" in result.reason.lower() or "limit" in result.reason.lower() or "价格" in result.reason


def test_check_order_fails_on_lots():
    """价格通过但手数失败"""
    checker = _make_checker()
    result = checker.check_order(
        order_price=Decimal("100"),  # price OK
        ref_price=Decimal("100"),
        lots=999,  # 远超上限
    )
    assert result.passed is False
    assert "手数" in result.reason or "lots" in result.reason.lower()


def test_check_order_passes():
    """价格和手数均在限制内 → passed=True"""
    checker = _make_checker()
    result = checker.check_order(
        order_price=Decimal("105"),
        ref_price=Decimal("100"),
        lots=5,
    )
    assert result.passed is True
    assert result.reason == ""
