"""
CTP 连接诊断脚本 v2
运行： python test_ctp_debug.py
"""
import asyncio
import os
import socket
import sys
import threading

USER_ID    = "256354"
BROKER_ID  = "9999"
PASSWORD   = os.getenv("CTP_PASSWORD", "")
AUTH_CODE  = "0000000000000000"
APP_ID     = "client_aiagentts_1.0.0"
FRONT_ADDR = "tcp://180.168.146.187:10130"
MD_ADDR    = "tcp://180.168.146.187:10111"


def test_tcp(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=5.0):
            return True
    except Exception as e:
        print(f"  ✖ {host}:{port} —— {e}")
        return False


def run_ctp_test():
    """CTP 登录测试（同步，在普通线程中运行）"""
    from vnpy.event import EventEngine, Event
    from vnpy_ctp.gateway import CtpGateway

    done    = threading.Event()   # 线程安全，无需 asyncio
    received: list[str] = []

    def on_general(event: Event):
        """register_general 捕获所有事件类型"""
        try:
            data = event.data
            msg  = getattr(data, "msg", None) or str(data)
        except Exception:
            msg  = str(event.data)

        line = f"  [EVENT type={event.type!r}] {msg}"
        print(line, flush=True)
        received.append(msg)

        # 登录成功关键字
        if any(k in msg for k in ["登录成功", "交易服务器", "login", "Login"]):
            done.set()
        # 登录失败关键字
        if any(k in msg for k in ["失败", "错误", "Error", "error", "FAIL"]):
            done.set()

    def on_account(event: Event):
        print(f"  [ACCOUNT] {event.data}  → 登录成功!", flush=True)
        done.set()

    ee = EventEngine()
    # register_general 捕获所有类型事件（不需要指定类型字符串）
    ee.register_general(on_general)
    ee.register("eAccount.", on_account)
    ee.start()
    print(f"  EventEngine 已启动: {ee._active}", flush=True)

    gw = CtpGateway(ee, "CTP")
    print("  CtpGateway 创建成功", flush=True)

    gw.connect({
        "用户名":    USER_ID,
        "密码":      PASSWORD,
        "经纪商代码":  BROKER_ID,
        "交易服务器":  FRONT_ADDR,
        "行情服务器":  MD_ADDR,
        "产品名称":  APP_ID,
        "授权编码":  AUTH_CODE,
        "产品信息":  "",
    })
    print("  gateway.connect() 调用完成，等待回调...", flush=True)

    ok = done.wait(timeout=30.0)

    try:
        gw.close()
        ee.stop()
    except Exception:
        pass

    if ok:
        print("\n[结果] 收到登录相关事件 ✔")
    else:
        print("\n[结果] 30秒内未收到任何事件 ✖")
        print("建议：")
        print("  1. 检查防火墙是否允许 TCP 10130、10111 出站")
        print("  2. 尝试关闭杀毒软件/安全软件后重试")
        print("  3. 尝试备用前置: tcp://180.168.146.187:10131")

    if received:
        print("\n收到的事件列表:")
        for m in received:
            print(f"  {m}")
    else:
        print("\n[无任何事件收到]")


def main():
    print("="*55)
    print(f"  user_id   : {USER_ID}")
    print(f"  password  : {'[set]' if PASSWORD else '[EMPTY]'}")
    print(f"  front TD  : {FRONT_ADDR}")
    print(f"  front MD  : {MD_ADDR}")
    print("="*55)

    if not PASSWORD:
        print("[ERROR] 请先设置: $env:CTP_PASSWORD = \"Abc6610195@\"")
        sys.exit(1)

    print("\n[Step 1] TCP 端口测试...")
    ok_td = test_tcp("180.168.146.187", 10130)
    ok_md = test_tcp("180.168.146.187", 10111)
    print(f"  TD 10130: {'OK' if ok_td else 'FAIL'}")
    print(f"  MD 10111: {'OK' if ok_md else 'FAIL'}")

    if not ok_td:
        print("[ERROR] TD 前置不可达，无法继续")
        sys.exit(1)

    print("\n[Step 2] CTP 登录测试...")
    run_ctp_test()


if __name__ == "__main__":
    main()
