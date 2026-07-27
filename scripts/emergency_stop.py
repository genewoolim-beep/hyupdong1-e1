#!/usr/bin/env python3
"""emergency_stop.py

지금 로봇이 뭘 하고 있든(다른 프로세스가 movel/movej 로 블로킹 중이어도) 상관없이,
컨트롤러의 motion/move_stop 서비스를 '독립된' rclpy 노드로 직접 호출해 즉시 정지시킨다.

DSR_ROBOT2.py 에는 이 서비스의 편의 래퍼 함수가 없어서(dsr_msgs2/srv/motion/MoveStop.srv
자체는 존재), ROS2 서비스를 직접 호출한다. 서비스 이름: motion/move_stop (네임스페이스는
노드의 namespace=robot_id 로 자동 해석됨) — Doosan 공식 테스트(dsr_tests/test_cli_dsr_system.py)
의 사용법을 그대로 따름.

정지 모드(stop_mode):
    0 = DR_QSTOP_STO : Quick stop, Category 1 (없이 STO) — 가장 급격
    1 = DR_QSTOP     : Quick stop, Category 2 — 급정지, 서보 제어 유지
    2 = DR_SSTOP     : Soft stop — 부드럽게 감속 후 정지 (Doosan 공식 예제 기본값)
    3 = DR_HOLD      : Hold stop
기본값 1(Quick stop, Category 2)로 뒀다 — 긴급중지 버튼용이라 "빨리 서는 것"이 최우선.
서보 제어는 유지한 채 급감속한다(Soft stop=2 는 부드럽지만 느려서 긴급중지엔 부적합했음).
더 급하게(토크 차단까지) 세우고 싶으면 --stop-mode 0, 부드럽게 원하면 --stop-mode 2.

사용:
    python3 emergency_stop.py                    # stop_mode=2(Soft stop)
    python3 emergency_stop.py --stop-mode 1       # Quick stop Category 2
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
    ap.add_argument('--stop-mode', type=int, default=1, choices=[0, 1, 2, 3],
                    help='0=QSTOP_STO 1=QSTOP(Cat2, 기본·급정지) 2=SSTOP(소프트) 3=HOLD')
    ap.add_argument('--timeout-s', type=float, default=3.0,
                    help='서비스 응답 대기 시간(초). 기본 3 — 급하니까 짧게')
    return ap.parse_args()


def main():
    args = parse_args()

    rclpy.init()
    node = rclpy.create_node('emergency_stop', namespace=args.robot_id)
    DR_init.__dsr__id = args.robot_id
    DR_init.__dsr__model = args.model
    DR_init.__dsr__node = node

    try:
        from dsr_msgs2.srv import MoveStop
    except ImportError as e:
        print(f"[에러] dsr_msgs2 import 실패: {e}")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    cli = node.create_client(MoveStop, 'motion/move_stop')
    if not cli.wait_for_service(timeout_sec=args.timeout_s):
        print(f"[에러] motion/move_stop 서비스 응답 없음({args.timeout_s}s 대기) — "
              f"bringup 이 떠 있는지 확인하세요.")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    req = MoveStop.Request()
    req.stop_mode = args.stop_mode
    future = cli.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=args.timeout_s)

    if not future.done():
        print("[에러] move_stop 응답 타임아웃")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    resp = future.result()
    if resp is not None and resp.success:
        print(f"[완료] 정지 명령 전송 성공(stop_mode={args.stop_mode})")
    else:
        print(f"[경고] 정지 서비스가 실패 응답을 반환함: {resp}")
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
