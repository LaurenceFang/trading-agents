from __future__ import annotations
"""主入口 - Streamlit MVP 付表盘（指标 #9）"""
import logging
import os
import sys
import time
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# 路径设置：确保能 import 项目包
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dashboard.streamlit_mvp.db_reader import DbReader  # noqa: E402
from dashboard.backend.command_router import handle as _cmd_handle  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="aiagentts 交易控制台",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# 数据库路径
# ---------------------------------------------------------------------------
_DEFAULT_DB = str(_REPO_ROOT / "data" / "trading.db")
DB_PATH = os.environ.get("AIAGENTTS_DB", _DEFAULT_DB)

db = DbReader(DB_PATH)

# ---------------------------------------------------------------------------
# 读取最新风控状态
# ---------------------------------------------------------------------------
risk_state = db.get_latest_risk_state()

# ---------------------------------------------------------------------------
# 顶部横栏——状态灯 + 操作按鈕
# ---------------------------------------------------------------------------
STATUS_ICONS = {
    "NORMAL": "🟢 NORMAL",
    "DEGRADED": "🟡 DEGRADED",
    "VENUE_HALT": "🔴 HALTED",
    "CIRCUIT": "🟡 CIRCUIT",
    "RECONCILING": "🟡 RECONCILING",
    "OFFLINE": "⚪ OFFLINE",
}

col_status, col_halt, col_flatten, col_resume = st.columns([3, 1, 1, 1])
with col_status:
    label = STATUS_ICONS.get(risk_state, f"❓ {risk_state}")
    st.markdown(f"## 系统状态：{label}")
with col_halt:
    if st.button("🔴 冻结交易", use_container_width=True):
        result = _cmd_handle("HALT", reason="manual")
        logger.info("HALT result: %s", result)
        st.rerun()
with col_flatten:
    if st.button("🚨 一键平仓", use_container_width=True, type="primary"):
        result = _cmd_handle("FLATTEN_ALL")
        logger.info("FLATTEN_ALL result: %s", result)
        st.rerun()
with col_resume:
    if st.button("🟢 恢复交易", use_container_width=True):
        result = _cmd_handle("RESUME")
        logger.info("RESUME result: %s", result)
        st.rerun()

# ---------------------------------------------------------------------------
# HALTED 横幅警告
# ---------------------------------------------------------------------------
if risk_state == "VENUE_HALT":
    st.error("⚠️ 交易已冻结，所有新单将被拒绝")

# 已撤销委托汇总
canceled = db.get_orders_by_status("CANCELED", limit=200)
st.caption(f"今日已撤销委托：{len(canceled)} 笔")

st.divider()

# ---------------------------------------------------------------------------
# 主页面简介
# ---------------------------------------------------------------------------
st.markdown("""
### 导航
- 🔌 **登录连接** → 左侧边栏选择 `00_login_connection`
- 📊 **交易统计监控** → 左侧边栏选择 `01_monitor`
- ⚠️ **风控管理** → 左侧边栏选择 `02_risk_control`
- 📄 **系统日志** → 左侧边栏选择 `03_log_viewer`
- 📂 **持仓资金** → 左侧边栏选择 `04_positions`
""")

# ---------------------------------------------------------------------------
# 自动刷新（每 2 秒）
# ---------------------------------------------------------------------------
time.sleep(2)
st.rerun()
