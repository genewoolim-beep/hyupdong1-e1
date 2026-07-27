#!/usr/bin/env python3
"""tcp_info.py — 현재 활성 TCP의 '오프셋 길이(mm)'를 JSON 한 줄로 출력한다.

왜 이름이 아니라 길이인가: 컨트롤러의 활성 TCP는 재부팅/안전정지/bringup 재기동 사이에
조용히 리셋되는데(예: 'pen'(Z 289mm) → 플랜지(0mm)), 이름만 봐서는 눈치채기 어렵다.
반면 '오프셋 길이'는 리셋되면 289 → 0 으로 확 떨어져 한눈에 드러난다.

계산: 오프셋 길이 = ‖(현재 TCP 위치) − (현재 플랜지 위치)‖  (Base 좌표, mm)
  - get_current_posx           : 활성 TCP 기준 위치(오프셋 반영됨)
  - get_current_tool_flange_posx: 플랜지 위치(TCP=0 기준)
  둘의 XYZ 거리 = 활성 TCP 오프셋 벡터의 크기.

DSR_ROBOT2 의 get_tcp()/get_current_posx() 래퍼가 이 환경에서 블로킹되는 일이 있어,
emergency_stop.py 처럼 ROS2 서비스를 '직접' 호출한다(create_client).

출력(성공): {"ok": true, "name": "pen", "len_mm": 289.4, "dz_mm": 289.4, "tcp_z": 133.4}
출력(실패): {"ok": false, "error": "..."}
"""
from __future__ import annotations
import argparse
import json
import math
import sys

import rclpy


def _call(node, cli_type, name, timeout, **reqkw):
    cli = node.create_client(cli_type, name)
    if not cli.wait_for_service(timeout_sec=timeout):
        raise RuntimeError(f"서비스 응답 없음: {name} (bringup 확인)")
    req = cli_type.Request()
    for k, v in reqkw.items():
        setattr(req, k, v)
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
    if not fut.done():
        raise RuntimeError(f"서비스 타임아웃: {name}")
    return fut.result()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--timeout-s', type=float, default=3.0)
    args = ap.parse_args()

    rclpy.init()
    node = rclpy.create_node('tcp_info', namespace=args.robot_id)
    try:
        from dsr_msgs2.srv import (
            GetCurrentTcp, GetCurrentPosx, GetCurrentToolFlangePosx)
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"dsr_msgs2 import 실패: {e}"}))
        rclpy.shutdown()
        sys.exit(1)

    try:
        tcp = _call(node, GetCurrentTcp, 'tcp/get_current_tcp', args.timeout_s)
        posx = _call(node, GetCurrentPosx, 'aux_control/get_current_posx',
                     args.timeout_s, ref=0)
        flange = _call(node, GetCurrentToolFlangePosx,
                       'aux_control/get_current_tool_flange_posx', args.timeout_s, ref=0)

        name = tcp.info if tcp else ""
        tcp_xyz = [float(v) for v in posx.task_pos_info[0].data[:3]]
        fl_xyz = [float(v) for v in flange.pos[:3]]
        d = [tcp_xyz[i] - fl_xyz[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in d))
        out = {
            "ok": True,
            "name": name,
            "len_mm": round(length, 1),
            "dx_mm": round(d[0], 1),
            "dy_mm": round(d[1], 1),
            "dz_mm": round(d[2], 1),
            "tcp_z": round(tcp_xyz[2], 1),
        }
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        rclpy.shutdown()
        sys.exit(1)

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
