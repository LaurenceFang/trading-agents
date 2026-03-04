from __future__ import annotations

"""系统日志查看页面（指标 #11）"""

import logging
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dashboard.streamlit_mvp.db_reader import DbReader  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(_REPO_ROOT / "data" / "trading.db")
DB_PATH = os.environ.get("AIAGENTTS_DB", _DEFAULT_DB)

db = DbReader(DB_PATH)

st.title("📋 系统日志")

# 数量滑块
_LIMITS = [50, 100, 200, 500]
limit = st.select_slider("显示条数", options=_LIMITS, value=100)

tab_orders, tab_system, tab_monitor, tab_error = st.tabs(
    ["📝 交易日志", "🖥️ 系统日志", "📊 监测日志", "🚨 错误日志"]
)

# ---------------------------------------------------------------------------
# 交易日志 (orders)
# ---------------------------------------------------------------------------
with tab_orders:
    rows_orders = db.get_orders(limit=limit)
    if rows_orders:
        df = pd.DataFrame(rows_orders)
        # 第一列重命名
        col_map = {
            "created_at": "时间",
            "order_id": "委托号",
            "symbol": "品种",
            "side": "方向",
            "price": "价格",
            "status": "状态",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        # 过滤器
        if "状态" in df.columns:
            statuses = ["全部"] + df["状态"].dropna().unique().tolist()
            sel = st.selectbox("状态过滤", statuses, key="order_status_filter")
            if sel != "全部":
                df = df[df["状态"] == sel]
        st.dataframe(df, use_container_width=True)
        # 导出 CSV
        st.download_button(
            "📥 导出 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="orders.csv",
            mime="text/csv",
        )
    else:
        st.info("暂无交易记录")

# ---------------------------------------------------------------------------
# 系统日志 (system_log)
# ---------------------------------------------------------------------------
with tab_system:
    rows_sys = db.get_system_log(limit=limit)
    if rows_sys:
        df = pd.DataFrame(rows_sys)
        col_map = {"ts": "时间", "event_type": "事件类型", "detail": "详情"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "事件类型" in df.columns:
            types = ["全部"] + df["事件类型"].dropna().unique().tolist()
            sel = st.selectbox("事件类型过滤", types, key="sys_type_filter")
            if sel != "全部":
                df = df[df["事件类型"] == sel]
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "📥 导出 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="system_log.csv",
            mime="text/csv",
        )
    else:
        st.info("暂无系统日志记录")

# ---------------------------------------------------------------------------
# 监测日志 (monitor_log)
# ---------------------------------------------------------------------------
with tab_monitor:
    rows_mon = db.get_monitor_log(limit=limit)
    if rows_mon:
        df = pd.DataFrame(rows_mon)
        col_map = {
            "ts": "时间",
            "field": "指标",
            "current_value": "当前値",
            "limit_value": "上限",
            "level": "级别",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "级别" in df.columns:
            levels = ["全部"] + df["级别"].dropna().unique().tolist()
            sel = st.selectbox("级别过滤", levels, key="mon_level_filter")
            if sel != "全部":
                df = df[df["级别"] == sel]
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "📥 导出 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="monitor_log.csv",
            mime="text/csv",
        )
    else:
        st.info("暂无监测日志记录")

# ---------------------------------------------------------------------------
# 错误日志 (error_log)
# ---------------------------------------------------------------------------
with tab_error:
    rows_err = db.get_error_log(limit=limit)
    if rows_err:
        df = pd.DataFrame(rows_err)
        col_map = {
            "ts": "时间",
            "error_id": "错误码",
            "error_msg": "错误描述",
            "context": "上下文",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "错误码" in df.columns:
            err_ids = ["全部"] + [str(x) for x in df["错误码"].dropna().unique().tolist()]
            sel = st.selectbox("错误码过滤", err_ids, key="err_code_filter")
            if sel != "全部":
                df = df[df["错误码"].astype(str) == sel]
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "📥 导出 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="error_log.csv",
            mime="text/csv",
        )
    else:
        st.info("暂无错误日志记录")
