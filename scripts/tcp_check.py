"""tcp_check.py — 그리기/모션 시작 전 현재 활성 TCP 오프셋을 실측해, pen(~289mm)과
크게 다르면(리셋 의심) '움직이기 전에' 막기 위한 검증 헬퍼.

왜 필요한가: 컨트롤러의 활성 TCP 가 bringup 재기동/안전정지 사이에 조용히 리셋되면
(pen 289mm → 플랜지 0mm), 하드코딩 절대좌표 모션이 289mm 어긋나 충돌한다(실제 사고 발생).
set_tcp 성공/실패와 무관하게 '실제 오프셋 값'만 보고 판단하므로, set_tcp 가 안 먹는 이
컨트롤러에서도 안전하다.

오프셋 = ‖현재 TCP 위치 − 현재 플랜지 위치‖ (Base 좌표, mm).
DSR_ROBOT2 래퍼(get_tcp 등)가 이 환경에서 블로킹되는 일이 있어, emergency_stop.py 처럼
ROS2 서비스를 직접 호출한다(create_client).
"""
from __future__ import annotations

import math


class TcpMismatchError(RuntimeError):
    """활성 TCP 오프셋이 pen(~289mm)과 크게 달라(리셋 의심) 움직이기 전에 중단할 때."""
    pass


def measure_tcp_offset(node, timeout_s: float = 3.0):
    """(offset_mm, tcp_name) 반환. 조회 실패 시 (None, None)."""
    import rclpy
    from dsr_msgs2.srv import (
        GetCurrentTcp, GetCurrentPosx, GetCurrentToolFlangePosx)

    def call(srv_type, srv_name, **reqkw):
        cli = node.create_client(srv_type, srv_name)
        if not cli.wait_for_service(timeout_sec=timeout_s):
            return None
        req = srv_type.Request()
        for k, v in reqkw.items():
            setattr(req, k, v)
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout_s)
        return fut.result() if fut.done() else None

    tcp = call(GetCurrentTcp, 'tcp/get_current_tcp')
    posx = call(GetCurrentPosx, 'aux_control/get_current_posx', ref=0)
    flange = call(GetCurrentToolFlangePosx,
                  'aux_control/get_current_tool_flange_posx', ref=0)
    if posx is None or flange is None:
        return None, None
    if not posx.task_pos_info or len(flange.pos) < 3:
        return None, None
    t3 = [float(v) for v in posx.task_pos_info[0].data[:3]]
    f3 = [float(v) for v in flange.pos[:3]]
    offset = math.sqrt(sum((t3[i] - f3[i]) ** 2 for i in range(3)))
    name = tcp.info if tcp else ""
    return offset, name


def verify_pen_tcp(node, expected_mm: float = 289.0, tol_mm: float = 20.0,
                   timeout_s: float = 3.0):
    """(ok: bool, msg: str) 반환. ok=False 면 호출부가 '움직이기 전에' 중단해야 함.
    조회 실패는 ok=True(경고만) — 일시적 조회 오류로 전체를 막지 않기 위함."""
    offset, name = measure_tcp_offset(node, timeout_s)
    if offset is None:
        return True, "[경고] TCP 오프셋 조회 실패 — 검증 생략하고 진행합니다."
    if abs(offset - expected_mm) <= tol_mm:
        return True, f"[TCP검증] 오프셋 {offset:.1f}mm — pen 정상(이름={name!r})."
    return False, (
        f"[에러] TCP 오프셋 {offset:.1f}mm 가 pen({expected_mm:.0f}mm, 허용 ±{tol_mm:.0f})와 "
        f"다릅니다 → 절대좌표가 어긋나 충돌 위험이라 중단합니다. "
        f"펜던트에서 TCP 를 pen 으로 맞춘 뒤 다시 실행하세요.")
