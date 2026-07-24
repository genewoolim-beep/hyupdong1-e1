#!/usr/bin/env python3
"""run_drl_motion.py

~/Downloads/ 의 DRL 4개(m0609_grab/pen_down/pen_up/brush.drl)를 옮긴 drl_motions.py 를
DSR_ROBOT2 로 실제 실행한다. 실기뿐 아니라 Doosan 가상모드(mode:=virtual) + RViz2 로도
그대로 동작 — 코드 분기 없음, virtual 컨트롤러가 실기와 같은 ROS2 서비스/액션을 흉내낸다.

사용 순서(RViz 시뮬레이터로 검증):
    [터미널 1] 워크스페이스 source 후 가상 컨트롤러 + RViz 기동
        source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
        ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py \\
            mode:=virtual model:=m0609 name:=dsr01 gui:=true

    [터미널 2] 이 스크립트 실행(RViz 창에서 움직임 확인)
        source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
        python3 scripts/run_drl_motion.py --motion grab
        python3 scripts/run_drl_motion.py --motion pen_down
        python3 scripts/run_drl_motion.py --motion pen_up
        python3 scripts/run_drl_motion.py --motion brush
        python3 scripts/run_drl_motion.py --motion grab --loop 3   # 여러 번 반복

실기에서 실행할 땐 --robot-id/--model 을 실제 값에 맞추고(가상모드와 동일 인자 구조),
dsr_bringup2 를 mode:=real 로 띄운 상태에서 그대로 실행하면 된다.
"""

from __future__ import annotations

import argparse
import sys

import rclpy
import DR_init

from drl_motions import DrlMotions, MOTIONS


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--motion', required=True, choices=sorted(MOTIONS.keys()),
                    help='실행할 동작(원본 DRL 파일명 기준)')
    ap.add_argument('--loop', type=int, default=1,
                    help='반복 횟수. 기본 1(DRL의 while ... < 1: 과 동일)')
    ap.add_argument('--speed-scale', type=float, default=0.1,
                    help='DRL 원본 속도(velj/accj/velx/accx) 대비 배율. 기본 0.1(10%% 속도) — '
                         '시뮬레이터 첫 테스트라 느리게. 원본 속도 그대로 쓰려면 1.0')
    ap.add_argument('--skip-ready-movej', action='store_true',
                    help='grab 전용: 시작 준비자세 movej 생략(brush 가 바로 직전에 정확히 같은 '
                         '자세로 끝나서 이어서 실행할 때만 안전 — 단독 테스트 시엔 절대 쓰지 말 것)')
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--model', default='m0609')
    ap.add_argument('--tcp', default='pen',
                    help='펜던트에 등록된 TCP 이름으로 강제 선택. 기본값 "pen" — 이 DRL 4개를 '
                         '펜던트에서 movel 로 교시할 때 활성 TCP가 pen 이었음을 확인함(2026-07-24). '
                         'DRL 원본엔 set_tcp 호출이 없어서, 재생 시점에 pen 이 아닌 다른 TCP가 '
                         '활성화돼 있으면 같은 숫자라도 실제 높이가 달라져 바닥을 박을 수 있음. '
                         '강제 선택을 끄려면 --tcp "" (빈 문자열)')
    ap.add_argument('--tool', default='pen',
                    help='펜던트에 등록된 Tool(payload) 이름으로 강제 선택. 기본값 "pen" — '
                         '무게 1.290kg, CoG(21.290, 13.410, 17.730mm) 확인됨(2026-07-24). '
                         '강제 선택을 끄려면 --tool "" (빈 문자열)')
    ap.add_argument('--yes', action='store_true',
                    help='아래 Z 미리보기 확인 프롬프트 생략하고 바로 실행(스크립트/자동화용)')
    return ap.parse_args()


def main():
    args = parse_args()

    rclpy.init()
    dsr_node = rclpy.create_node('run_drl_motion', namespace=args.robot_id)
    DR_init.__dsr__id = args.robot_id
    DR_init.__dsr__model = args.model
    DR_init.__dsr__node = dsr_node

    try:
        from DSR_ROBOT2 import (
            movej, movel, wait,
            set_velj, set_accj, set_velx, set_accx,
            set_digital_output, set_singular_handling,
            set_robot_mode, ROBOT_MODE_AUTONOMOUS,
            set_tcp, get_tcp, set_tool, get_tool, add_tcp, add_tool,
            DR_AVOID, DR_MV_MOD_ABS, DR_MV_RA_DUPLICATE,
        )
        from DR_common2 import posj, posx
    except ImportError as e:
        print(f"[에러] DSR_ROBOT2 import 실패: {e}\n"
              f"      → dsr_bringup2 가 떠 있고(가상 또는 실기) install 을 source 했는지 확인하세요.")
        rclpy.shutdown()
        sys.exit(1)

    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    except Exception as e:
        print(f"[경고] set_robot_mode 무시: {e}")

    # ── TCP/Tool: DRL 원본에 set_tcp/set_tool 이 없어서, 가르칠 때와 다른 툴이 지금
    #    활성화돼 있으면 같은 좌표라도 실제 높이가 달라진다(바닥 충돌 원인). 가시성 확보 +
    #    필요시 강제 선택. pen 오프셋은 2026-07-24 펜던트 TCP 화면에서 직접 확인한 값
    #    (X=0.383 Y=-0.318 Z=289.416mm, 각도 전부 0) — Z가 289mm 나 되므로 TCP 가 안
    #    맞으면 그만큼 그대로 위치오차가 나서 바닥을 박는다.
    PEN_TCP_OFFSET = [0.383, -0.318, 289.416, 0.0, 0.0, 0.0]
    PEN_TOOL_WEIGHT = 1.290
    PEN_TOOL_COG = [21.290, 13.410, 17.730]
    PEN_TOOL_INERTIA = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # 펜던트에 값 없어 근사(0)
    try:
        if args.tcp:
            ret = set_tcp(args.tcp)
            if ret != 0 and args.tcp == 'pen':
                print(f"[안내] TCP '{args.tcp}' 이(가) 이 컨트롤러에 없는 것 같습니다 "
                      f"(가상 시뮬레이터는 프로젝트 데이터가 비어있을 수 있음) → "
                      f"확인된 오프셋({PEN_TCP_OFFSET})으로 자동 등록 시도...")
                add_tcp(args.tcp, PEN_TCP_OFFSET)
                ret = set_tcp(args.tcp)
            if ret != 0:
                print(f"[경고] TCP '{args.tcp}' 선택 실패(ret={ret}) — "
                      f"펜던트에서 이름을 다시 확인하세요.")
        if args.tool:
            ret = set_tool(args.tool)
            if ret != 0 and args.tool == 'pen':
                print(f"[안내] Tool '{args.tool}' 이(가) 이 컨트롤러에 없는 것 같습니다 → "
                      f"확인된 무게/CoG(weight={PEN_TOOL_WEIGHT}kg, cog={PEN_TOOL_COG})로 "
                      f"자동 등록 시도(inertia는 값이 없어 0으로 근사)...")
                add_tool(args.tool, PEN_TOOL_WEIGHT, PEN_TOOL_COG, PEN_TOOL_INERTIA)
                ret = set_tool(args.tool)
            if ret != 0:
                print(f"[경고] Tool '{args.tool}' 선택 실패(ret={ret}) — "
                      f"펜던트에서 이름을 다시 확인하세요.")
        print(f"[TCP/Tool] 현재 활성 TCP={get_tcp()!r} Tool={get_tool()!r}")
        if not args.tcp and not args.tool:
            print("           (--tcp/--tool 미지정 → 위 값 그대로 사용. "
                  "DRL 가르칠 때와 다른 툴이면 바닥 충돌 위험 있으니 펜던트에서 확인하세요)")
    except Exception as e:
        print(f"[경고] TCP/Tool 조회·설정 실패: {e}")

    motions = DrlMotions(
        movej=movej, movel=movel, wait=wait,
        set_velj=set_velj, set_accj=set_accj,
        set_velx=set_velx, set_accx=set_accx,
        set_digital_output=set_digital_output,
        set_singular_handling=set_singular_handling,
        posj=posj, posx=posx,
        DR_AVOID=DR_AVOID, DR_MV_MOD_ABS=DR_MV_MOD_ABS,
        DR_MV_RA_DUPLICATE=DR_MV_RA_DUPLICATE,
        speed_scale=args.speed_scale,
    )
    run = getattr(motions, MOTIONS[args.motion].__name__)

    # ── 실행 전 미리보기: 실제 API 호출 없이 movel 목표 Z 값만 훑어서 보여준다.
    #    현재 활성 TCP 기준 절대 Base Z 이므로, 여기서 이상하게 낮은 값(음수 등)이
    #    보이면 --tcp/--tool 부터 다시 확인.
    preview_targets = []
    dummy = DrlMotions(
        movej=lambda *a, **k: None,
        movel=lambda pose, **k: preview_targets.append(pose),
        wait=lambda *a, **k: None,
        set_velj=lambda *a, **k: None, set_accj=lambda *a, **k: None,
        set_velx=lambda *a, **k: None, set_accx=lambda *a, **k: None,
        set_digital_output=lambda *a, **k: None,
        set_singular_handling=lambda *a, **k: None,
        posj=lambda *a: a, posx=lambda *a: a,
        DR_AVOID=DR_AVOID, DR_MV_MOD_ABS=DR_MV_MOD_ABS,
        DR_MV_RA_DUPLICATE=DR_MV_RA_DUPLICATE,
    )
    getattr(dummy, MOTIONS[args.motion].__name__)()
    z_values = [pose[2] for pose in preview_targets]
    print(f"[미리보기] {args.motion} movel Z 목표 {len(z_values)}개: "
          f"min={min(z_values):.1f}mm max={max(z_values):.1f}mm")
    print(f"           {[round(z, 1) for z in z_values]}")
    if min(z_values) < 0:
        print("[경고] 목표 Z 에 음수(테이블 아래로 해석될 수 있음)가 있습니다 — "
              "현재 활성 TCP가 이 좌표를 가르칠 때와 같은지 반드시 확인하세요.")
    if not args.yes:
        ans = input("위 Z 값들이 지금 설치된 툴 기준으로 안전해 보이면 Enter, 아니면 q+Enter로 취소 > ").strip().lower()
        if ans == 'q':
            print("[취소]")
            dsr_node.destroy_node()
            rclpy.shutdown()
            return

    print(f"[시작] motion={args.motion} loop={args.loop} speed_scale={args.speed_scale} "
          f"robot_id={args.robot_id} model={args.model}")
    for i in range(args.loop):
        print(f"  [{i + 1}/{args.loop}] {args.motion} 실행...")
        if args.motion == 'grab' and args.skip_ready_movej:
            run(skip_ready=True)
        else:
            run()
    print("[완료]")

    dsr_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
