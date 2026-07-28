#!/usr/bin/env python3
"""calibrate_pen_grasp.py — 어느 Modbus 레지스터가 '실제로 벌어진 그리퍼 폭'을
보여주는지 실측으로 찾아낸다.

문제: 지금 쓰던 reg[263]은 '명령한 목표 폭'일 가능성이 있다. 펜(25mm)을 잡으려고
"0mm로 닫아" 명령을 보내면 펜이 막아 실제로는 25mm에서 멈추는데, 목표-폭 레지스터는
명령값(0)을 그대로 보여줘서 항상 '펜 없음'으로 읽힌다.

이 스크립트는 두 상태를 같은 위치에서 측정해 비교한다:
  A) 펜을 문 상태(그리퍼 닫기 명령 → 실제로는 펜 두께 25mm 에서 멈춤)
  B) 펜을 놓고 40mm 로 벌린 상태(비교 기준)
'실제 폭' 레지스터라면 A 에서 ~25mm, B 에서 ~40mm 에 해당하는 값이 나오고,
'목표 폭' 레지스터라면 A 에서 0(닫기 명령값)이 나온다 → A 값이 0 근처인 레지스터는
탈락, A 에서 유의미하게 큰 값이 나오는 레지스터가 정답.

사용법(펜을 펜홀더에 꽂아둔 상태로):
    source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
    python3 scripts/calibrate_pen_grasp.py
"""
from __future__ import annotations

import sys

import rclpy
import DR_init

# 후보 레지스터(이전 probe 에서 폭에 따라 변한 것들)와, 그때 측정한 빈-상태 참고값
# (96mm / 40mm / 0mm 명령 시). 펜을 문 상태 값과 비교하는 용도.
CANDIDATES = [263, 264, 265, 267, 275]
EMPTY_REF = {
    #        96mm   40mm   0mm
    263:  (  332,    42,     0),
    264:  (  332, 65246, 65494),
    265:  ( 1165,   397,    42),
    267:  ( 1061,   475,    97),
    275:  (  969,   383,     5),
}


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
    dsr_node = rclpy.create_node('calibrate_pen_grasp', namespace='dsr01')
    DR_init.__dsr__id = 'dsr01'
    DR_init.__dsr__model = 'm0609'
    DR_init.__dsr__node = dsr_node

    try:
        from DSR_ROBOT2 import (
            movej, movel, wait,
            set_velj, set_accj, set_velx, set_accx,
            set_digital_output, set_singular_handling,
            set_robot_mode, ROBOT_MODE_AUTONOMOUS,
            DR_AVOID, DR_MV_MOD_ABS, DR_MV_RA_DUPLICATE,
        )
        from DR_common2 import posj, posx
    except ImportError as e:
        print(f"[에러] DSR_ROBOT2 import 실패: {e}")
        rclpy.shutdown()
        sys.exit(1)

    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    except Exception as e:
        print(f"[경고] set_robot_mode 무시: {e}")

    from drl_motions import DrlMotions

    m = DrlMotions(
        movej=movej, movel=movel, wait=wait,
        set_velj=set_velj, set_accj=set_accj,
        set_velx=set_velx, set_accx=set_accx,
        set_digital_output=set_digital_output,
        set_singular_handling=set_singular_handling,
        posj=posj, posx=posx,
        DR_AVOID=DR_AVOID, DR_MV_MOD_ABS=DR_MV_MOD_ABS,
        DR_MV_RA_DUPLICATE=DR_MV_RA_DUPLICATE,
        speed_scale=0.506,
        verify_pen_grasp=False,   # 자동판정 끔(여기선 우리가 직접 잼)
    )
    ready = (-0.02, -0.05, 90.15, 0.01, 89.22, 0.04)

    print("[1] 준비자세 → 펜 위치 접근...")
    m._apply_common_profile()
    m._movej_p(*ready)
    m._pen_release()
    m._movel_p(313.84, -283.52, 72.12, 89.87, -136.08, 91.85)
    m._wait(1.0)

    print("[2] 펜 집기(닫기) — 완전히 닫힐 시간까지 2.5초 대기...")
    m._pen_grasp()
    m._wait(2.5)
    with_pen = read_regs(CANDIDATES)
    print(f"    펜 문 상태: {with_pen}")

    print("[3] 펜 놓고 40mm 로 벌려 기준값 측정...")
    m._pen_release()
    m._wait(1.5)
    # DO3 = 40mm
    m._do(1, 0); m._do(2, 0); m._do(4, 0); m._do(3, 1)
    m._wait(2.0)
    at40 = read_regs(CANDIDATES)
    print(f"    40mm 벌린 상태: {at40}")

    print("[4] 안전하게 펜 다시 잡고(원위치 복귀 위해) 준비자세로...")
    # 주의: 여기서 펜을 다시 잡아두지 않으면 펜이 홀더에 남고 팔만 올라간다.
    # calibrate 는 값만 재는 용도라 그냥 준비자세로 복귀(펜은 홀더에 둔 채).
    m._pen_release()
    m._wait(1.0)
    m._movej_p(*ready)

    dsr_node.destroy_node()
    rclpy.shutdown()

    print("\n" + "=" * 64)
    print(" 레지스터별 비교 (펜25mm 문상태 / 방금40mm / 이전참고 96·40·0mm)")
    print("=" * 64)
    best = None
    for a in CANDIDATES:
        p = with_pen.get(a)
        f = at40.get(a)
        ref = EMPTY_REF.get(a)
        print(f"  reg[{a}]: 펜문={p}  40mm={f}  (참고 96/40/0 = {ref})")
        # '실제 폭' 후보: 펜 문 상태 값이 0 근처가 아니고, 40mm 기준값보다 작아야 자연스러움
        if p is not None and f is not None and p > 5 and p < f:
            if best is None:
                best = a
    print("=" * 64)
    if best is not None:
        p = with_pen[best]; f = at40[best]
        # 25mm(펜) → p, 40mm → f 를 잇는 직선으로 20mm 문턱의 레지스터값 추정
        # (0mm 근처는 참고값의 0mm 열을 씀)
        r0 = EMPTY_REF[best][2]
        # 20mm 는 0mm(r0)과 40mm(f) 사이 선형보간
        thr20 = r0 + (f - r0) * (20.0 / 40.0)
        print(f"[추천] gripper_modbus.py 를 다음으로 수정:")
        print(f"    WIDTH_PROXY_REGISTER = {best}")
        print(f"    PEN_GRASP_MIN_REG    = {int(round(thr20))}   "
              f"# 20mm 문턱(펜25mm={p}, 40mm={f}, 0mm={r0} 보간)")
    else:
        print("[안내] '펜 문 상태에서 0 이 아니면서 40mm 보다 작은' 레지스터를 못 찾음.")
        print("       위 표를 그대로 알려주면 어느 레지스터를 쓸지 같이 정하자.")


if __name__ == '__main__':
    main()
