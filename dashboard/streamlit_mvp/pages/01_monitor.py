from __future__ import annotations

"""交易统计监控页面（指标 #4、5、6）"""

import logging
import os
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dashboard.streamlit_mvp.db_reader import DbReader  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(_REPO_ROOT / "data" / "trading.db")
DB_PATH = os.environ.get("AIAGENTTS_DB", _DEFAULT_DB)

db = DbReader(DB_PATH)

# ---------------------------------------------------------------------------
# 页面标题
# ---------------------------------------------------------------------------
st.title("📊 交易统计监控")

# ---------------------------------------------------------------------------
# 四个计数卡片
# ---------------------------------------------------------------------------
counts = db.get_today_monitor_counts()

col1, col2, col3, col4 = st.columns(4)
col1.metric("📝 报单笔数", counts["order_count"])
col2.metric("❌ 撤单笔数", counts["cancel_count"])
col3.metric("✅ 成交笔数", counts["fill_count"])
col4.metric("⚠️ 重复报单次数", counts["duplicate_count"])

st.caption(f"最后更新时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")

st.divider()

# ---------------------------------------------------------------------------
# 阈値预警展示
# ---------------------------------------------------------------------------
alerts = db.get_today_monitor_alerts()
warnings = [a for a in alerts if a.get("level") == "WARNING"]
breaches = [a for a in alerts if a.get("level") == "BREACH"]

if breaches:
    latest_breach = breaches[0]
    field = latest_breach.get("field", "unknown")
    st.error(
        f"⚠️ 阈値超限 (BREACH): 字段={field}, 当前値={latest_breach.get('current_value')}, "
        f"限制={latest_breach.get('limit_value')}"
    )
    # 注入 JS 弹窗
    components.html(
        f'<script>window.alert("\u26a0\ufe0f \u9608\u5024\u8d85\u9650\uff1a{field}");</script>',
        height=0,
    )
elif warnings:
    latest_warning = warnings[0]
    field = latest_warning.get("field", "unknown")
    st.warning(
        f"🟡 阈値预警 (WARNING): 字段={field}, 当前値={latest_warning.get('current_value')}, "
        f"限制={latest_warning.get('limit_value')}"
    )
else:
    st.success("✅ 今日暂无阈値预警")

# ---------------------------------------------------------------------------
# 自动刷新（每 5 秒）
# ---------------------------------------------------------------------------
time.sleep(5)
st.rerun()
