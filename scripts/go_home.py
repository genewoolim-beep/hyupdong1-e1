#!/usr/bin/env python3
"""go_home.py

로봇을 안전 준비자세(관절각, 기본 0,0,90,0,90,0)로 되돌린다.
긴급정지(emergency_stop.py) 이후 팔이 애매한 자세로 멈춰있을 때, 다음 작업 전에
알려진 안전한 자세로 복귀시키는 용도.

movej(관절이동)만 사용 — 힘제어/컴플라이언스 없이 순수 위치제어로 이동하므로
어떤 상태에서 멈췄든(힘제어 ON 상태로 죽었어도) 안전하게 복귀 가능.

사용:
    python3 go_home.py
    python3 go_home.py --ready 0,0,90,0,90,0 --vel 30 --acc 30
"""

from __future__ import annotations

import argparse
import sys

import rclpy
import DR_init


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--model', default='m0609')
    ap.add_argument('--ready', default='0,0,90,0,90,0',
                    help='복귀할 준비자세 관절각(deg), 콤마구분. 기본 0,0,90,0,90,0')
    ap.add_argument('--vel', type=float, default=30.0, help='관절 속도(deg/s). 기본 30(안전)')
    ap.add_argument('--acc', type=float, default=30.0, help='관절 가속도(deg/s^2). 기본 30(안전)')
    return ap.parse_args()


def main():
    args = parse_args()
    ready = [float(v) for v in args.ready.split(',')]

    rclpy.init()
    node = rclpy.create_node('go_home', namespace=args.robot_id)
    DR_init.__dsr__id = args.robot_id
    DR_init.__dsr__model = args.model
    DR_init.__dsr__node = node

    try:
        from DSR_ROBOT2 import (
            movej, set_robot_mode, ROBOT_MODE_AUTONOMOUS,
            release_compliance_ctrl, release_force,
            DR_MV_RA_DUPLICATE,
        )
        from DR_common2 import posj
    except ImportError as e:
        print(f"[에러] DSR_ROBOT2 import 실패: {e}")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    except Exception as e:
        print(f"[경고] set_robot_mode 무시: {e}")

    # 긴급정지 등으로 힘제어(compliance)가 켜진 채 멈췄을 수 있으니, 위치이동 전에 먼저
    # 꺼둔다(꺼져있으면 에러 나도 무시 — 이미 꺼진 상태일 수 있음).
    try:
        release_force(time=0.0)
        release_compliance_ctrl()
    except Exception:
        pass

    print(f"[원위치] {ready} 로 이동(vel={args.vel}, acc={args.acc})...")
    movej(posj(*ready), vel=args.vel, acc=args.acc, ra=DR_MV_RA_DUPLICATE)
    print("[완료] 원위치 복귀")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
