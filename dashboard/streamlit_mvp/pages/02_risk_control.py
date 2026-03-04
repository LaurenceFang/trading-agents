from __future__ import annotations

"""风控管理页面（指标 #6、7、10）"""

import logging
import os
import sys
from pathlib import Path

import streamlit as st
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dashboard.streamlit_mvp.db_reader import DbReader  # noqa: E402
from dashboard.backend.command_router import handle as _cmd_handle  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(_REPO_ROOT / "data" / "trading.db")
DB_PATH = os.environ.get("AIAGENTTS_DB", _DEFAULT_DB)
_RISK_PARAMS_PATH = _REPO_ROOT / "config" / "risk_params.yaml"

db = DbReader(DB_PATH)

st.title("⚠️ 风控管理")

# ===========================================================================
# 指标 #6 — 阈値配置
# ===========================================================================
st.header("🔧 阈値参数配置")

try:
    with _RISK_PARAMS_PATH.open("r", encoding="utf-8") as f:
        risk_data = yaml.safe_load(f)
except Exception as e:
    logger.error("Failed to load risk_params.yaml: %s", e)
    risk_data = {}

fm = risk_data.get("futures_monitor", {})

with st.form("risk_params_form"):
    max_orders = st.number_input(
        "max_orders_per_day",
        value=int(fm.get("max_orders_per_day", 500)),
        min_value=0,
        step=1,
    )
    max_cancels = st.number_input(
        "max_cancels_per_day",
        value=int(fm.get("max_cancels_per_day", 200)),
        min_value=0,
        step=1,
    )
    max_duplicates = st.number_input(
        "max_duplicate_orders",
        value=int(fm.get("max_duplicate_orders", 5)),
        min_value=0,
        step=1,
    )
    max_lots = st.number_input(
        "max_lots_per_order",
        value=int(fm.get("max_lots_per_order", 100)),
        min_value=1,
        step=1,
    )
    warning_pct = st.number_input(
        "warning_pct",
        value=float(fm.get("warning_pct", 0.8)),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        format="%.2f",
    )
    price_limit_pct = st.number_input(
        "price_limit_pct",
        value=float(fm.get("price_limit_pct", 0.1)),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        format="%.2f",
    )
    submitted = st.form_submit_button("💾 保存配置")

if submitted:
    try:
        if "futures_monitor" not in risk_data:
            risk_data["futures_monitor"] = {}
        risk_data["futures_monitor"]["max_orders_per_day"] = int(max_orders)
        risk_data["futures_monitor"]["max_cancels_per_day"] = int(max_cancels)
        risk_data["futures_monitor"]["max_duplicate_orders"] = int(max_duplicates)
        risk_data["futures_monitor"]["max_lots_per_order"] = int(max_lots)
        risk_data["futures_monitor"]["warning_pct"] = float(warning_pct)
        risk_data["futures_monitor"]["price_limit_pct"] = float(price_limit_pct)
        with _RISK_PARAMS_PATH.open("w", encoding="utf-8") as f:
            yaml.dump(risk_data, f, allow_unicode=True, default_flow_style=False)
        st.success("配置已保存，下次 FuturesMonitor 初始化时生效")
    except Exception as exc:
        st.error(f"保存失败: {exc}")

st.divider()

# ===========================================================================
# 指标 #8 — 错误指令展示
# ===========================================================================
st.header("🚨 CTP 错误指令（最近 20 条）")

error_rows = db.get_error_log(limit=20)
total_errors = len(error_rows)
st.caption(f"错误总条数（本次读取）：{total_errors}")

if error_rows:
    import pandas as pd
    df_err = pd.DataFrame(error_rows)
    # 重命名列
    col_rename = {"ts": "时间", "error_id": "CTP错误码", "error_msg": "错误描述", "context": "上下文"}
    df_err = df_err.rename(columns={k: v for k, v in col_rename.items() if k in df_err.columns})
    st.dataframe(df_err, use_container_width=True)
else:
    st.info("暂无错误记录")

st.divider()

# ===========================================================================
# 指标 #10 — 一键撤单
# ===========================================================================
st.header("⚡ 一键撤单")

if st.button("⚡ 一键撤销所有未成交委托", type="primary"):
    result = _cmd_handle("CANCEL_ALL")
    logger.info("CANCEL_ALL result: %s", result)
    st.info("撤单指令已发送，封建结果展示如下：")

# 展示最近已撤销委托
canceled_orders = db.get_orders_by_status("CANCELED", limit=50)
if canceled_orders:
    import pandas as pd
    df_canceled = pd.DataFrame(canceled_orders)
    st.dataframe(df_canceled, use_container_width=True)
    st.caption(f"已撤销 {len(canceled_orders)} 笔委托")
else:
    st.info("暂无已撤销委托")
