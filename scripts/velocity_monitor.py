#!/usr/bin/env python3
"""velocity_monitor.py

get_current_velx() 를 짧은 주기로 폴링해서 실제 TCP 속도(mm/s)의 최댓값을 출력한다.
다른 터미널에서 동작(run_drl_motion.py 등)을 실행하는 동안 이걸 같이 띄워두면,
컨트롤러가 요청 속도를 클램핑하고 있는지 실측으로 확인할 수 있다.

사용:
    python3 velocity_monitor.py --duration 8
"""

from __future__ import annotations

import argparse
import time

import rclpy
import DR_init


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--model', default='m0609')
    ap.add_argument('--duration', type=float, default=8.0, help='측정 시간(초)')
    ap.add_argument('--interval', type=float, default=0.1, help='폴링 주기(초)')
    return ap.parse_args()


def main():
    args = parse_args()

    rclpy.init()
    node = rclpy.create_node('velocity_monitor', namespace=args.robot_id)
    DR_init.__dsr__id = args.robot_id
    DR_init.__dsr__model = args.model
    DR_init.__dsr__node = node

    from DSR_ROBOT2 import get_current_velx, DR_BASE

    max_trans = 0.0
    max_rot = 0.0
    samples = []
    t0 = time.time()
    print(f"[velocity_monitor] {args.duration}s 동안 {args.interval}s 간격으로 실측 시작...")
    while time.time() - t0 < args.duration:
        try:
            v = get_current_velx(DR_BASE)
            trans, rot = float(v[0]), float(v[1])
            samples.append(trans)
            if trans > max_trans:
                max_trans = trans
            if rot > max_rot:
                max_rot = rot
        except Exception as e:
            print(f"[경고] 조회 실패: {e}")
        time.sleep(args.interval)

    print(f"[결과] 최대 이동속도(trans) = {max_trans:.1f} mm/s, 최대 회전속도(rot) = {max_rot:.1f} deg/s")
    if samples:
        nonzero = [s for s in samples if s > 1.0]
        if nonzero:
            print(f"       0이 아닌 샘플 {len(nonzero)}개, 평균 = {sum(nonzero)/len(nonzero):.1f} mm/s")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
