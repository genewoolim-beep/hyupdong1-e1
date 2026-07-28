#!/usr/bin/env python3
"""calibrate_grip_inplace.py — 팔은 전혀 안 움직이고, 그리퍼만 여닫으며 어느 Modbus
레지스터가 '실제 벌어진 폭'을 보여주는지 찾는다(가장 안전·빠름).

사람이 할 일:
  이 스크립트가 "지금 펜을 그리퍼 사이에 물려주세요" 하고 멈추면, 펜(25mm)을 손으로
  그리퍼 손가락 사이에 끼운 뒤 Enter. 스크립트가 닫기 명령을 보내면 펜이 25mm 에서
  막고, 그때 각 레지스터 값을 읽는다.

판정: '실제 폭' 레지스터라면 펜을 물었을 때(25mm) 값이 0 이 아니고, 빈 채로 닫았을
때(0mm)와 확연히 다르다. '목표 폭' 레지스터라면 둘 다 0(닫기 명령값)이라 못 쓴다.

사용법:
    source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
    python3 scripts/calibrate_grip_inplace.py
"""
from __future__ import annotations

import sys

import rclpy
import DR_init

CANDIDATES = [263, 264, 265, 267, 275]


def read_regs(addrs):
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        from pymodbus.client.sync import ModbusTcpClient
    c = ModbusTcpClient("192.168.1.1", port=502, timeout=2, retries=1)
    out = {}
    try:
        if not c.connect():
            return {a: None for a in addrs}
        for a in addrs:
            r = c.read_holding_registers(a, count=1, device_id=65)
            out[a] = None if r.isError() else r.registers[0]
    finally:
        c.close()
    return out


def main():
    rclpy.init()
    node = rclpy.create_node('calibrate_grip_inplace', namespace='dsr01')
    DR_init.__dsr__id = 'dsr01'
    DR_init.__dsr__model = 'm0609'
    DR_init.__dsr__node = node

    try:
        from DSR_ROBOT2 import set_digital_output, wait, set_robot_mode, ROBOT_MODE_AUTONOMOUS
    except ImportError as e:
        print(f"[에러] DSR_ROBOT2 import 실패: {e}")
        rclpy.shutdown(); sys.exit(1)
    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    except Exception:
        pass

    def close_grip():   # DO2=1 → 0mm 로 닫기(펜 있으면 펜 두께에서 멈춤)
        set_digital_output(1, 0); set_digital_output(3, 0); set_digital_output(4, 0)
        set_digital_output(2, 1)
    def open_grip():    # DO1=1 → 96mm 열기
        set_digital_output(2, 0); set_digital_output(3, 0); set_digital_output(4, 0)
        set_digital_output(1, 1)

    print("\n[준비] 그리퍼를 엽니다.")
    open_grip(); wait(2.0)

    input(">>> 펜(25mm)을 그리퍼 손가락 사이에 물려주고 Enter <<< ")
    print("[측정] 닫는 중... (완전히 닫힐 때까지 2.5초)")
    close_grip(); wait(2.5)
    with_pen = read_regs(CANDIDATES)
    print(f"  펜 문 상태: {with_pen}")

    print("\n[준비] 그리퍼를 엽니다 — 펜을 빼주세요.")
    open_grip(); wait(2.0)
    input(">>> 펜을 완전히 뺐으면 Enter (빈 채로 닫아 0mm 기준 측정) <<< ")
    print("[측정] 빈 채로 닫는 중... 2.5초")
    close_grip(); wait(2.5)
    empty = read_regs(CANDIDATES)
    print(f"  빈 상태(0mm): {empty}")

    print("[정리] 그리퍼 엽니다.")
    open_grip(); wait(1.0)

    node.destroy_node(); rclpy.shutdown()

    print("\n" + "=" * 60)
    print(" 레지스터  |  펜25mm  |  빈0mm  |  판정")
    print("=" * 60)
    best = None
    for a in CANDIDATES:
        p, e = with_pen.get(a), empty.get(a)
        verdict = ""
        if p is not None and e is not None:
            if p > 5 and abs(p - e) > 5:
                verdict = "★ 실제폭 후보(펜에서 값이 살아있고 빈것과 다름)"
                if best is None:
                    best = a
            elif p <= 5:
                verdict = "탈락(펜 물어도 0 근처 = 목표폭/명령값)"
        print(f"  reg[{a:>4}] | {str(p):>7} | {str(e):>6} | {verdict}")
    print("=" * 60)
    if best is not None:
        p, e = with_pen[best], empty[best]
        # 펜25mm=p, 0mm=e 를 잇는 직선으로 20mm 문턱값 추정
        thr20 = e + (p - e) * (20.0 / 25.0)
        print(f"[추천] gripper_modbus.py:")
        print(f"    WIDTH_PROXY_REGISTER = {best}")
        print(f"    PEN_GRASP_MIN_REG    = {int(round(thr20))}   "
              f"# 20mm 문턱(펜25mm={p}, 0mm={e} 선형보간)")
        print("  → 이 값 두 개만 알려주면 내가 코드에 반영할게.")
    else:
        print("[안내] 확실한 '실제 폭' 레지스터를 못 찾음. 위 표를 그대로 알려줘.")


if __name__ == '__main__':
    main()
