"""gripper_modbus.py — OnRobot RG2 Compute Box(192.168.1.1:502, Modbus TCP,
device_id=65)의 홀딩 레지스터를 읽어 "그리퍼가 실제로 무언가를 물고 있는지"를 판단한다.

[2026-07-28 실측 확정] 처음엔 reg[263]을 썼는데, 이건 "명령한 목표 폭"이라 못 쓴다는 걸
확인했다 — 닫기(0mm) 명령을 보내면 실제로 펜을 물어서 막혔든 아니든 명령값(0 근처)을
그대로 보여준다. 실제 GUI 로 pen_up/brush 가 펜·브러쉬를 잡는 순간을 로그로 남겨 비교한
결과, **reg[275]**가 훨씬 확실한 신호였다:
    아무것도 안 잡음(그리퍼 완전히 오므라짐) : 5
    펜(25mm) 잡음                            : 200
    브러쉬 잡음                              : 254
빈 상태 대비 40배 가까이 차이 나서(263은 겨우 0→12~19) 훨씬 안정적으로 구분된다.
공식 mm 환산식은 OnRobot 문서 없이 확정 못 했지만, "뭔가 물렸는지 아닌지" 판단에는
이 정도 차이면 충분하다.
"""
from __future__ import annotations

from typing import Optional

GRIPPER_HOST = "192.168.1.1"
GRIPPER_PORT = 502
GRIPPER_DEVICE_ID = 65

# [2026-07-28 실측 확정] reg[263]은 "명령한 목표 폭"이라 못 씀(닫기 명령을 보내면 실제로
# 뭘 물었든 0 근처로 나옴). reg[275]가 훨씬 확실한 신호였다 — 실제 GUI 그리기 실행 중
# pen_up/brush 가 펜·브러쉬를 잡는 순간을 로그로 남겨 비교:
#     아무것도 안 잡음(0mm)  : 5
#     펜(25mm) 잡음          : 200
#     브러쉬 잡음            : 254
# 빈 상태 대비 40배 가까이 차이 나서(263은 겨우 0→12~19) 훨씬 안정적인 신호.
WIDTH_PROXY_REGISTER = 275

# 빈 상태(5)와 실측 최소값(펜 200) 사이에서 충분한 안전마진을 둔 문턱값.
PEN_GRASP_MIN_REG = 80

# [진단 모드] True 면 확인 시 후보 레지스터를 전부 로그로 찍고, 판정 실패여도 막지 않고
# 그냥 통과시킨다. reg[275] 확정으로 이제 꺼서 실제 예외처리를 켠다.
DIAGNOSTIC_LOG_ONLY = False
CANDIDATE_REGISTERS = [259, 260, 263, 264, 265, 266, 267, 268, 269, 273, 275]


def read_registers(addrs, timeout: float = 2.0) -> dict:
    """여러 레지스터를 한 번에 읽어 {주소: 값}(실패한 건 None) 반환."""
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        try:
            from pymodbus.client.sync import ModbusTcpClient
        except ImportError:
            return {a: None for a in addrs}
    client = ModbusTcpClient(GRIPPER_HOST, port=GRIPPER_PORT, timeout=timeout, retries=1)
    out = {}
    try:
        if not client.connect():
            return {a: None for a in addrs}
        for a in addrs:
            r = client.read_holding_registers(a, count=1, device_id=GRIPPER_DEVICE_ID)
            out[a] = None if r.isError() else r.registers[0]
    except Exception:
        return {a: None for a in addrs}
    finally:
        client.close()
    return out


def read_width_proxy(timeout: float = 2.0) -> Optional[int]:
    """WIDTH_PROXY_REGISTER(reg[275]) 값을 1회 읽어 반환. 연결/읽기 실패 시 None
    (판단 불가 — 호출부에서 안전 쪽으로 처리할 것)."""
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        try:
            from pymodbus.client.sync import ModbusTcpClient  # pymodbus 2.x
        except ImportError:
            return None

    client = ModbusTcpClient(GRIPPER_HOST, port=GRIPPER_PORT, timeout=timeout, retries=1)
    try:
        if not client.connect():
            return None
        result = client.read_holding_registers(
            WIDTH_PROXY_REGISTER, count=1, device_id=GRIPPER_DEVICE_ID)
        if result.isError():
            return None
        return result.registers[0]
    except Exception:
        return None
    finally:
        client.close()


def pen_is_grasped(min_reg: int = PEN_GRASP_MIN_REG) -> Optional[bool]:
    """WIDTH_PROXY_REGISTER 값이 min_reg 이상이면 뭔가 물려서(펜/브러쉬) 있는 것으로 보고
    True. 5 근처(빈 상태 기준값)면 아무것도 안 물린 것으로 False.
    읽기 자체가 실패하면 None(판단 불가) — 호출부에서 '판단 불가 시 계속 진행할지'
    결정해야 한다(그리퍼 이상으로 매번 멈추면 오히려 더 문제가 될 수 있음)."""
    val = read_width_proxy()
    if val is None:
        return None
    return val >= min_reg
