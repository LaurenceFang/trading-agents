"""CTP error code mapping table.

Maps CTP ErrorID integers to human-readable Chinese descriptions
for display in Streamlit UI and logs.
"""
from __future__ import annotations

# CTP error code → (short_label, description)
CTP_ERROR_MAP: dict[int, tuple[str, str]] = {
    0:    ("成功", "操作成功"),
    1:    ("数据不一致", "柜台系统内部数据不一致"),
    2:    ("不支持操作", "当前不支持此操作"),
    3:    ("非交易时间", "现在不是交易时间，请在交易时间内操作"),
    4:    ("未知品种", "合约代码不存在或已下架"),
    5:    ("价格超范围", "委托价格超出涨跌停板限制"),
    6:    ("资金不足", "账户可用资金不足，无法下单"),
    7:    ("持仓不足", "持仓数量不足，无法平仓"),
    8:    ("重复报单", "该委托已提交，不能重复报单"),
    9:    ("委托不存在", "撤单失败，找不到对应委托"),
    10:   ("撤单失败", "委托已成交或已撤销，无法再撤单"),
    11:   ("超出最大手数", "单笔委托超出最大允许手数"),
    12:   ("超出持仓限额", "持仓已达上限，不允许继续开仓"),
    13:   ("价格精度错误", "委托价格精度不符合最小变动单位要求"),
    14:   ("合约暂停交易", "合约处于暂停交易状态"),
    15:   ("开平标志错误", "开平仓标志与持仓方向不匹配"),
    16:   ("投机套保标志错误", "投机/套保标志填写有误"),
    17:   ("手数为零", "委托手数不能为零"),
    18:   ("价格为零", "限价单价格不能为零"),
    19:   ("没有报价权限", "当前账户没有报价权限"),
    20:   ("登录失败", "用户名或密码错误，登录失败"),
    21:   ("未登录", "尚未登录，请先完成登录"),
    22:   ("用户不存在", "用户不存在"),
    23:   ("经纪商不存在", "经纪商编号不存在"),
    24:   ("内存不足", "服务器内存不足，请稍后重试"),
    25:   ("权限不足", "当前账户权限不足，无法执行此操作"),
    26:   ("强平委托", "该委托为强制平仓委托，不允许撤单"),
    27:   ("超出撤单笔数限制", "当日撤单笔数已达上限"),
    28:   ("超出报单笔数限制", "当日报单笔数已达上限"),
    29:   ("不允许使用市价单", "该合约不支持市价委托"),
    30:   ("涨停板", "委托价格触及涨停板，无法成交"),
    31:   ("跌停板", "委托价格触及跌停板，无法成交"),
    32:   ("平今手数不足", "今日持仓不足，无法平今"),
    33:   ("平昨手数不足", "昨日持仓不足，无法平昨"),
    34:   ("上期所不支持平今", "上期所此合约不支持单独平今操作"),
    35:   ("穿透认证失败", "AppID 或 AuthCode 验证失败，请检查穿透式认证信息"),
    36:   ("认证已过期", "穿透式认证已过期，请重新认证"),
    37:   ("IP 不在白名单", "客户端 IP 不在允许范围内"),
    38:   ("MAC 地址不匹配", "客户端 MAC 地址与注册信息不匹配"),
    39:   ("产品不在交易时间", "该产品当前不在交易时段内"),
    40:   ("查询频率超限", "查询过于频繁，请稍后重试"),
    41:   ("系统忙", "服务器繁忙，请稍后重试"),
    42:   ("网络超时", "网络请求超时，请检查网络连接"),
    43:   ("柜台维护", "柜台系统正在维护，暂时不可用"),
    44:   ("结算确认未完成", "请先完成上一交易日的结算确认"),
    45:   ("账户已冻结", "账户已被冻结，请联系期货公司"),
    46:   ("合约交割日", "合约已进入交割期，不允许开仓"),
    47:   ("报单数超限", "当前挂单数量超出系统允许上限"),
    48:   ("期权行权失败", "期权行权操作失败"),
    49:   ("期权放弃行权失败", "期权放弃行权操作失败"),
    50:   ("资金账户不存在", "资金账户不存在或未开通"),
    99:   ("未知错误", "柜台返回未知错误，请联系期货公司技术支持"),
}

_UNKNOWN = ("未知错误", "柜台返回未知错误码 {code}，请联系期货公司技术支持")


def get_error_label(error_id: int) -> str:
    """Return a short Chinese label for a CTP ErrorID.

    Args:
        error_id: CTP numeric error code.

    Returns:
        Short label string, e.g. "资金不足".
    """
    entry = CTP_ERROR_MAP.get(error_id)
    if entry:
        return entry[0]
    return _UNKNOWN[0]


def get_error_description(error_id: int) -> str:
    """Return a human-readable Chinese description for a CTP ErrorID.

    Args:
        error_id: CTP numeric error code.

    Returns:
        Full description string suitable for UI display.
    """
    entry = CTP_ERROR_MAP.get(error_id)
    if entry:
        return entry[1]
    return _UNKNOWN[1].format(code=error_id)


def format_ctp_error(error_id: int, raw_msg: str = "") -> str:
    """Format a complete error string for UI display.

    Combines the human-readable description with the raw CTP message
    so operators can cross-reference with official CTP documentation.

    Args:
        error_id: CTP numeric error code.
        raw_msg: Raw error message string from CTP (may be empty or GBK-decoded).

    Returns:
        Formatted string like "[资金不足] 账户可用资金不足，无法下单 (CTP: 资金不足)"
    """
    label = get_error_label(error_id)
    description = get_error_description(error_id)
    parts = [f"[{label}] {description}"]
    if raw_msg and raw_msg.strip():
        parts.append(f"(CTP原文: {raw_msg.strip()})")
    return " ".join(parts)
