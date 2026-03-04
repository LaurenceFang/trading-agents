from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "risk_params.yaml"


@dataclass
class CheckResult:
    passed: bool
    reason: str  # 通过时为 ""，拒绝时说明原因


class PriceLimitChecker:
    """检查单笔委托价格和手数是否在风控限制内。"""

    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH) -> None:
        """从 risk_params.yaml 读取 max_lots_per_order 和 price_limit_pct。"""
        self._max_lots_per_order: int = 100
        self._price_limit_pct: Decimal = Decimal("0.1")
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            fm = data.get("futures_monitor", {})
            self._max_lots_per_order = int(fm.get("max_lots_per_order", 100))
            # price_limit_pct 不在现有 yaml 里，默认 10%
            pct = fm.get("price_limit_pct", data.get("price_limit_pct", "0.1"))
            self._price_limit_pct = Decimal(str(pct))
        except Exception as exc:
            logger.error("PriceLimitChecker: failed to load config: %s", exc)

    def check_price(
        self,
        order_price: Decimal,
        ref_price: Decimal,
    ) -> CheckResult:
        """检查 order_price 是否在 ref_price ± price_limit_pct 范围内。"""
        if ref_price == Decimal("0"):
            return CheckResult(passed=True, reason="")
        upper = ref_price * (Decimal("1") + self._price_limit_pct)
        lower = ref_price * (Decimal("1") - self._price_limit_pct)
        if order_price > upper:
            return CheckResult(
                passed=False,
                reason=(
                    f"价格超出涨停限制: order_price={order_price} > upper_limit={upper} "
                    f"(ref={ref_price}, pct={self._price_limit_pct})"
                ),
            )
        if order_price < lower:
            return CheckResult(
                passed=False,
                reason=(
                    f"价格低于跌停限制: order_price={order_price} < lower_limit={lower} "
                    f"(ref={ref_price}, pct={self._price_limit_pct})"
                ),
            )
        return CheckResult(passed=True, reason="")

    def check_lots(self, lots: int) -> CheckResult:
        """检查手数是否超过 max_lots_per_order。"""
        if lots > self._max_lots_per_order:
            return CheckResult(
                passed=False,
                reason=(
                    f"手数超限: lots={lots} > max_lots_per_order={self._max_lots_per_order}"
                ),
            )
        return CheckResult(passed=True, reason="")

    def check_order(
        self,
        order_price: Decimal,
        ref_price: Decimal,
        lots: int,
    ) -> CheckResult:
        """组合检查价格和手数，任一失败立即返回。"""
        price_result = self.check_price(order_price, ref_price)
        if not price_result.passed:
            return price_result
        lots_result = self.check_lots(lots)
        if not lots_result.passed:
            return lots_result
        return CheckResult(passed=True, reason="")
