"""
FUTURES ONLY - DO NOT IMPORT CRYPTO MODULES

期货独立启动入口
AppID: client_aiagentts_1.0.0
开发人: 方馒涵

启动顺序：DB建表 → StateWriter → EventBus → OutboxDispatcher → CtpAdapter → Streamlit Dashboard

使用方式：
    cd <repo_root>
    python -m futures.run_futures
"""

import asyncio
import subprocess
import sys
from pathlib import Path

import aiosqlite
import yaml
from loguru import logger

# ── 共用核心层（core/ 与 venue/ 是共享模块，允许导入）────────────────────────
from core.event_bus import EventBus
from core.state_writer import StateWriter
from core.outbox_dispatcher import OutboxDispatcher
from venue.ctp_adapter import CtpAdapter

# ── 路径常量 ─────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent.parent
CONFIG_PATH = Path(__file__).parent / "config" / "risk_params_futures.yaml"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"


def load_config() -> dict:
    """加载期货专用配置文件"""
    if not CONFIG_PATH.exists():
        logger.error(f"配置文件不存在: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def init_database(db_path: str) -> None:
    """创建 data/ 目录并执行 schema.sql 建表（IF NOT EXISTS，安全重入）"""
    # 自动创建数据库目录
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if not SCHEMA_PATH.exists():
        logger.error(f"Schema 文件不存在: {SCHEMA_PATH}")
        sys.exit(1)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(schema_sql)
        await db.commit()

    logger.info(f"[Futures] 数据库建表完成: {db_path}")


# ── 主启动逻辑 ────────────────────────────────────────────────────────────────
async def main() -> None:
    logger.info("[Futures] 启动期货交易系统...")
    logger.info("[Futures] AppID: client_aiagentts_1.0.0")

    config = load_config()
    db_path = config.get("db_path", "./data/futures.db")

    # 0. 数据库初始化（建表）
    logger.info("[Futures] 初始化数据库...")
    await init_database(db_path)

    # 1. StateWriter——注意: 方法名是 start() 而非 initialize()
    logger.info("[Futures] 初始化 StateWriter...")
    state_writer = StateWriter(db_path=db_path)
    await state_writer.start()          # ✅ 正确方法名

    # 2. EventBus
    logger.info("[Futures] 初始化 EventBus...")
    event_bus = EventBus(state_writer=state_writer)

    # 3. OutboxDispatcher
    logger.info("[Futures] 初始化 OutboxDispatcher...")
    dispatcher = OutboxDispatcher(
        event_bus=event_bus,
        state_writer=state_writer,
        max_retries=config.get("reconnect_max_retries", 5),
    )

    # 4. CtpAdapter
    logger.info("[Futures] 初始化 CtpAdapter...")
    ctp_config = {
        "broker_id":  config.get("broker_id", ""),
        "user_id":    config.get("user_id", ""),
        "app_id":     config.get("app_id", "client_aiagentts_1.0.0"),
        "front_addr": config.get("ctp_front_addr", ""),
        "password":   config.get("password", ""),
        "auth_code":  config.get("auth_code", ""),
    }
    ctp_adapter = CtpAdapter(config=ctp_config, state_writer=state_writer)
    logger.info("[Futures] 连接 CTP 前置机...")
    await ctp_adapter.connect()
    logger.info("[Futures] CTP 连接成功。")

    # 5. 启动 Streamlit Dashboard（#15 实现）
    dashboard_path = REPO_ROOT / "dashboard" / "app_futures.py"
    if dashboard_path.exists():
        logger.info("[Futures] 启动 Streamlit Dashboard...")
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(dashboard_path),
             "--server.port", "8501"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        logger.warning(f"[Futures] Dashboard 未找到: {dashboard_path}（#15 完成后生效）")

    # 6. 启动事件循环
    logger.info("[Futures] 系统启动完成，进入事件循环...")
    try:
        await dispatcher.run()
    except KeyboardInterrupt:
        logger.info("[Futures] 收到停止信号，正在关闭...")
    finally:
        await ctp_adapter.disconnect()
        await state_writer.stop()       # ✅ 正确方法名
        logger.info("[Futures] 已安全关闭。")


if __name__ == "__main__":
    asyncio.run(main())
