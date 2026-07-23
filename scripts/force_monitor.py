#!/usr/bin/env python3
"""force_monitor.py — 로봇 TCP 외력(Fx,Fy,Fz,Tx,Ty,Tz)을 실시간으로 출력한다.

lower_to_paper.py 로 그리는 중에 '별도 터미널'에서 띄워 힘을 눈으로 감시할 수 있다.
읽기 전용(get_tool_force)이라 로봇 동작을 방해하지 않는다.

실행:
    source /opt/ros/humble/setup.bash
    source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
    python3 ~/ws_cobot_pjt/ws_dsr/src/svg_drawing/scripts/force_monitor.py
    # 옵션: --hz 20 (갱신 주기)  --ref tool (기준좌표: base|tool)

※ 주의: 이 로봇은 payload/TCP 캘리가 안 돼 있으면 값이 '절대적으로 정확'하진 않다
   (그리기용 힘제어가 안 됐던 이유). 그래도 '변화/상대값'은 실시간으로 보인다.
"""

from __future__ import annotations
import argparse
import sys
import threading
import time

import rclpy
from rclpy.executors import MultiThreadedExecutor
import DR_init


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--model', default='m0609')
    ap.add_argument('--hz', type=float, default=10.0, help='출력 주기(Hz), 기본 10')
    ap.add_argument('--ref', choices=['base', 'tool'], default='base',
                    help='힘 기준좌표계 (기본 base)')
    ap.add_argument('--fz-warn', type=float, default=5.0,
                    help='|Fz| 가 이 값(N) 넘으면 ⚠ 표시 (기본 5N)')
    args = ap.parse_args()

    rclpy.init()
    node = rclpy.create_node('force_monitor', namespace=args.robot_id)
    DR_init.__dsr__id = args.robot_id
    DR_init.__dsr__model = args.model
    DR_init.__dsr__node = node

    try:
        from DSR_ROBOT2 import get_tool_force, get_external_torque, DR_BASE, DR_TOOL
    except ImportError as e:
        print(f"[에러] DSR_ROBOT2 import 실패: {e}\n"
              f"      → 로봇 bringup 이 떠 있고 install 을 source 했는지 확인하세요.")
        rclpy.shutdown()
        sys.exit(1)

    # ★ 노드를 백그라운드로 spin 해야 get_tool_force 서비스 응답이 계속 들어온다.
    #   (spin 안 하면 한 번 읽고 멈추거나 아예 블록됨)
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()

    ref = DR_TOOL if args.ref == 'tool' else DR_BASE
    period = 1.0 / max(0.5, args.hz)
    print(f"[force_monitor] ref={args.ref} · {args.hz:.0f}Hz · Ctrl-C 로 종료")
    print("  (지금은 힘제어 중이 아니면 Fz≈0 이 정상. 4N 은 --force 로 그릴 때만)")
    print(f"{'Fx':>8}{'Fy':>8}{'Fz':>8}{'Tx':>8}{'Ty':>8}{'Tz':>8}   (N, Nm)")

    try:
        while rclpy.ok():
            try:
                f = get_tool_force(ref)          # [Fx,Fy,Fz,Tx,Ty,Tz]
            except Exception as e:
                print(f"  [읽기 실패] {e}")
                time.sleep(period)
                continue
            if not f or len(f) < 6:
                print("  [값 없음] — bringup/네임스페이스 확인")
                time.sleep(period)
                continue
            warn = " ⚠Fz" if abs(f[2]) >= args.fz_warn else ""
            # \r 로 같은 줄 갱신
            sys.stdout.write(
                f"\r{f[0]:8.2f}{f[1]:8.2f}{f[2]:8.2f}"
                f"{f[3]:8.2f}{f[4]:8.2f}{f[5]:8.2f}{warn}   ")
            sys.stdout.flush()
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n[종료]")
    finally:
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
