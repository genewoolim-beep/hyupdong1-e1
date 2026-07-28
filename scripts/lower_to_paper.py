#!/usr/bin/env python3
"""lower_to_paper.py — 키보드로 펜을 내려 '종이 표면 Z'를 직접 잡고,
그 높이로 (위치제어) SVG 를 그린다.  ※ 자세한 사용법: ../사용설명서.md

가장 안전한 방식: 사람이 눈으로 보며 키보드로 내려 종이에 '살짝 닿는 순간'을 직접 잡는다.
그 Z 를 표면으로 삼아, 표면보다 --press-mm 만큼 더 눌러(위치제어) 스크래치한다.

실행:
    source /opt/ros/humble/setup.bash
    source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
    python3 ~/ws_cobot_pjt/ws_dsr/src/svg_drawing/scripts/lower_to_paper.py --size 150
    # 패턴 바꾸기: --svg /path/to.svg   |  세기: --press-mm 0.3

키(글자를 친 뒤 반드시 Enter):
    Enter(빈 줄)   현재 step 만큼 하강 (기본 10mm)
    숫자 + Enter   step 크기 변경(예: 1 → 이후 Enter 는 1mm씩)
    z<값> + Enter  입력한 Base Z(mm)로 바로 이동 (예: z100)
    u + Enter      3mm 상승(너무 내렸을 때)
    done + Enter   지금 높이를 표면 Z 로 확정
    q + Enter      취소(안전 높이로 복귀 후 종료)

※ 실제 로봇을 종이 쪽으로 내리는 동작입니다. E-stop 손 위에 두고, 종이를
   '준비자세 홈 XY 바로 아래'에 놓은 뒤 진행하세요. 세게 누르지 말고 '살짝 닿으면' done.
※ 힘제어(--force)는 payload/TCP 캘리 후에만. 기본은 위치제어(안 박힘).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import rclpy
import DR_init

from svg_drawing.robot_controller import NoContactError
from tcp_check import verify_pen_tcp, TcpMismatchError

DEFAULT_SVG = os.path.expanduser(
    '/home/gene/ws_cobot_pjt/ws_dsr/src/svg_drawing/samples/merkaba.svg')


def rotate_polys(polys, cx: float, cy: float, deg: float):
    """용지mm 폴리라인들을 (cx,cy) 중심으로 deg(도)만큼 회전.
    deg 는 '위에서 내려다봤을 때 반시계방향'이 +다. 용지mm 좌표는 y가 아래로
    증가하므로(화면과 동일), 수식상으로는 -deg 를 표준 회전행렬에 넣어야
    맞다(y축이 뒤집힌 만큼 회전 방향이 수식에서는 반대로 나타남)."""
    if not deg:
        return polys
    import math
    th = math.radians(-deg)
    c, s = math.cos(th), math.sin(th)

    def rot_pt(p):
        x, y = p[0] - cx, p[1] - cy
        return (cx + x * c - y * s, cy + x * s + y * c)

    return [[rot_pt(p) for p in poly] for poly in polys]


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--svg', default=DEFAULT_SVG, help='그릴 SVG 경로')
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--model', default='m0609')
    ap.add_argument('--ready', default='0,0,90,0,90,0',
                    help='준비자세 관절각(deg), 콤마구분')
    ap.add_argument('--step', type=float, default=10.0,
                    help='초기 하강 스텝(mm). 기본 10(높은 데서 빨리). 표면 가까우면 1+Enter 로 줄이기')
    ap.add_argument('--start-z', type=float, default=340.0,
                    help='홈에서 이 Base Z(mm)까지 적당한 속도로 먼저 이동 후 키보드 미세조정. '
                         '기본 340mm(표면 74~100보다 훨씬 위라 안전). 블라인드 이동 끄려면 큰 값(예: 9999)')
    ap.add_argument('--surface-z', type=float, default=9.2,
                    help='표면 Z(mm). 기본 9.2mm(9.5→9.2). '
                         '대화형 하강(Enter/step/키보드) 전부 생략하고 '
                         '홈에서 바로 이 높이로 이동해 표면으로 확정, 곧장 그리기 시작. '
                         '⚠ 검증 없이 그대로 내려가니 값이 틀리면 위험(펜 박힘/뜸). '
                         '표면이 달라졌으면 --surface-z 로 새 값을, 대화형으로 다시 잡으려면 --no-auto-z')
    ap.add_argument('--no-auto-z', dest='auto_z', action='store_false', default=True,
                    help='--surface-z 자동이동을 끄고 예전처럼 키보드로 눈으로 하강(안전하게 재확인하고 싶을 때)')
    ap.add_argument('--start-vel', type=float, default=52.0,
                    help='start-z 까지 이동 속도(mm/s). 기본 52(40에서 +30%%). 낮추면 더 천천히')
    # 안전 리셋: 35→87.5→175→...→252까지 누적 상승시켰던 걸, 컨트롤러 재기동 후 클램핑
    # 없이 그대로 적용돼 위험해진 게 확인돼 최초 실기 검증값(35)으로 되돌림.
    ap.add_argument('--jump-vel', type=float, default=29.75,
                    help='z<값> 지정 점프 이동 속도(mm/s), --surface-z 자동하강에도 사용. '
                         '기본 29.75(35에서 -15%%). 점프 후에는 다시 15로 돌아가 미세조정은 그대로 느림')
    ap.add_argument('--min-z', type=float, default=70.0,
                    help='자동 하강 안전 바닥(mm). 접촉 없이 이 높이 도달하면 정지(그 아래로 안 내려감). '
                         '기본 70mm(표면74 근처). 표면이 더 낮으면 이 값을 낮추세요')
    ap.add_argument('--auto-contact', action='store_true',
                    help='자동 접촉정지 사용(payload/TCP 캘리된 경우만!). 기본 OFF — 사람이 키보드로 '
                         '눈으로 내려 done. 캘리 안 됐는데 켜면 힘을 못 읽어 표면 지나쳐 박힘')
    ap.add_argument('--contact-n', type=float, default=3.0,
                    help='(--auto-contact 시) 이 힘(N) 이상 감지되면 자동 정지·표면기록. 기본 3N')
    ap.add_argument('--size', type=float, default=100.75,
                    help='그림이 들어갈 정사각 작업영역 한 변(mm). 홈 XY 중심에 배치. 기본 100.75mm')
    ap.add_argument('--rotate-deg', type=float, default=90.0,
                    help='도안을 작업영역 중심 기준으로 이 각도(도)만큼 회전(위에서 봤을 때 '
                         '반시계방향이 +). 기본 90 — 도안의 6시 방향(아래쪽)이 로봇쪽을 향하게 '
                         '맞춘 값(회전 전엔 6시가 로봇 오른쪽을 향했음). 결과가 여전히 어긋나면 '
                         '180/−90/0 등으로 바꿔서 실측 확인')
    ap.add_argument('--pen-up', type=float, default=15.0,
                    help='획 사이 펜업 높이(표면 위 mm)')
    ap.add_argument('--off-x', type=float, default=0.0,
                    help='그림을 Base X 로 평행이동(mm). +는 홈 기준 앞/뒤(설치 자세에 따름)')
    ap.add_argument('--off-y', type=float, default=-10.0,
                    help='그림을 Base Y 로 평행이동(mm). +Y=왼쪽, -Y=오른쪽. 기본 -10(오른쪽30 +왼쪽20 = 홈기준 오른쪽 10mm)')
    # ── 힘제어(일정 힘으로 아크릴 긁기) ──────────────────────
    ap.add_argument('--force', action=argparse.BooleanOptionalAction, default=True,
                    help='Z축(위아래)만 힘제어(compliance), XY 는 항상 위치제어로 고정(강성 3000). '
                         'payload/TCP 캘리 완료 후 기본 ON. 문제 생기면 --no-force 로 위치제어(--press-mm)로')
    ap.add_argument('--press-mm', type=float, default=0.25,
                    help='(위치제어) 측정 표면보다 이만큼 더 눌러 긋는다(mm) = 일정 깊이=일정 압력 효과. '
                         '기본 0.25mm. 연하면 0.3~0.5 올리고, 과하면 0.15/0.1 로')
    ap.add_argument('--force-n', type=float, default=6.0,
                    help='아크릴을 누르는 목표 힘(N). 기본 6.0N(5.8→6.0). --force 로 켜면 이 힘으로 Fz 유지. '
                         '--force-split 이면 이 값 대신 --force-n-left/right 를 씀')
    ap.add_argument('--force-split', action=argparse.BooleanOptionalAction, default=True,
                    help='도안을 로봇이 바라보는 방향 기준 좌/우로 나눠 다른 힘을 준다(기본 켬). '
                         '끄려면 --no-force-split(이땐 --force-n 하나만 그대로 씀)')
    ap.add_argument('--force-n-left', type=float, default=7.0,
                    help='--force-split 켰을 때, 로봇 왼쪽(Base +Y 쪽) 영역에 쓰는 힘(N). 기본 7.0N(6.8→7.0)')
    ap.add_argument('--force-n-right', type=float, default=5.0,
                    help='--force-split 켰을 때, 로봇 오른쪽(Base -Y 쪽) 영역에 쓰는 힘(N). 기본 5.0N(4.5→5.0)')
    ap.add_argument('--force-sign', type=float, default=-1.0,
                    help='누르는 방향 부호. -1=Base -Z(아래로). 설치 자세에 맞춰 조정')
    ap.add_argument('--stiffness-z', type=float, default=10.0,
                    help='힘제어 Z 강성(N/m). 낮을수록 Z 위치제어가 약해지고 힘제어가 우선(=표면추종). '
                         '기본 10(20→10, 더 힘 우선). 5까지 낮췄을 땐 툴이 떠서 불안정했던 이력이 '
                         '있으니 실기에서 튀면 20~30 쪽으로 다시 올릴 것. XY·회전은 3000 고정')
    ap.add_argument('--draw-vel', type=float, default=None,
                    help='그리기 속도(mm/s). 미지정 시 힘제어=12.68, 위치제어=37.62. 표면 울퉁불퉁하면 '
                         '힘제어에서 더 낮추기(예: 5). 힘 루프가 요철 따라가려면 느려야 함')
    ap.add_argument('--draw-acc', type=float, default=None,
                    help='그리기 가속도(mm/s^2). 미지정 시 힘제어=78.54, 위치제어=150')
    ap.add_argument('--force-push-mm', type=float, default=0.0,
                    help='(힘제어) 획 본체 Z 목표를 표면보다 이만큼 아래로 둠. 기본 0(힘 우선). '
                         '0보다 크면 위치오차를 만들어 힘제어 우선을 해침. 힘 우선은 --stiffness-z 를 낮춰 구현')
    ap.add_argument('--force-ramp-wait', type=float, default=2.0,
                    help='(힘제어) 힘제어 ON 직후 목표힘까지 안정될 때까지 긋기 전에 대기하는 시간(초). '
                         '기본 2.0초. 짧으면(0 등) 각 획 초반이 힘이 덜 들어간 채로 흐리게 그어짐')
    ap.add_argument('--draw-extend', type=float, default=0.015,
                    help='각 획을 끝에서 이 비율만큼, 마지막 진행 방향으로 직선 연장해 그린다'
                         '(0=끔). 힘제어 지연/펜업 타이밍으로 획 끝이 덜 그려지는 것 보완. '
                         '기본 0.015(1.5%%)')
    ap.add_argument('--simplify-tol-mm', type=float, default=0.15,
                    help='RDP 단순화 허용오차(mm). 2mm 균일 샘플에서 이 오차 이내로 근사되는 '
                         '중간점을 없애 직선/완만한 곡선 구간의 세그먼트를 길게 만든다(→ 적응형 '
                         '블렌드가 그 구간에서 더 큰 반경/더 빠른 코너링을 쓸 수 있게 됨). '
                         '도형 꼭짓점은 오차를 벗어나 그대로 보존됨. 0=끔')
    ap.add_argument('--draw-passes', type=int, default=1,
                    help='같은 획을 이 횟수만큼 왕복하며 겹쳐 그린다(펜 든 채 되짚기). 1=한 번(기본), '
                         '2=왕복 1회 더, 3=세 번. 선을 더 진하게/끝까지 확실히. 시간은 대략 횟수배로 증가')
    ap.add_argument('--tcp', default=None,
                    help='펜던트에 등록된 TCP 이름으로 강제 선택(예: --tcp pen). 미지정 시 건드리지 않고 '
                         '현재 활성 TCP 이름만 출력. 실행마다 홈 Z/자세가 널뛰면(TCP 가 바뀐 것) 이걸로 고정하세요')
    ap.add_argument('--tool', default=None,
                    help='펜던트에 등록된 Tool(payload) 이름으로 강제 선택(예: --tool pen_gripper). '
                         '미지정 시 건드리지 않고 현재 활성 Tool 이름만 출력')
    return ap.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.svg):
        print(f"[에러] SVG 없음: {args.svg}")
        sys.exit(1)

    rclpy.init()
    # DSR_ROBOT2 는 DR_init 전역이 세팅된 뒤에만 import 가능(지연 import)
    dsr_node = rclpy.create_node('lower_to_paper', namespace=args.robot_id)
    DR_init.__dsr__id = args.robot_id
    DR_init.__dsr__model = args.model
    DR_init.__dsr__node = dsr_node

    try:
        from DSR_ROBOT2 import (
            movej, movel, get_current_posx, set_velx, set_accx,
            set_robot_mode, ROBOT_MODE_AUTONOMOUS,
            check_force_condition,
            set_tcp, get_tcp, set_tool, get_tool,
            DR_BASE, DR_MV_MOD_ABS, DR_MV_RA_DUPLICATE, DR_AXIS_Z,
        )
        from DR_common2 import posx, posj
    except ImportError as e:
        print(f"[에러] DSR_ROBOT2 import 실패: {e}\n"
              f"      → 로봇 bringup 이 떠 있고 install 을 source 했는지 확인하세요.")
        rclpy.shutdown()
        sys.exit(1)

    try:
        set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    except Exception as e:
        print(f"[경고] set_robot_mode 무시: {e}")

    # ── TCP/Tool 확인·고정 ────────────────────────────────────────────
    # 실행마다 홈 Z·자세가 달라지는 사고는 대부분 "활성 TCP 가 실행 사이에 바뀐 것"이 원인이다
    # (펜던트에서 수동 선택이라 안 남아있거나 다른 작업으로 바뀐 채 남는 경우가 있음). 매 실행
    # 시작 시 지금 활성 TCP/Tool 이름을 화면에 출력해 눈으로 바로 확인할 수 있게 하고,
    # --tcp/--tool 을 주면 그 이름으로 강제 선택해 항상 동일한 상태에서 시작하도록 한다.
    try:
        if args.tcp:
            r = set_tcp(args.tcp)
            print(f"[TCP] '{args.tcp}' 로 강제 선택 (결과 {r})")
        if args.tool:
            r = set_tool(args.tool)
            print(f"[Tool] '{args.tool}' 로 강제 선택 (결과 {r})")
        print(f"[확인] 현재 활성 TCP={get_tcp()!r} / Tool={get_tool()!r} "
              f"— 매 실행 이 값이 같은지 확인하세요(달라지면 홈 Z 도 널뜁니다)")
    except Exception as e:
        print(f"[경고] TCP/Tool 조회·설정 실패(무시하고 진행): {e}")

    ready = [float(v) for v in args.ready.split(',')]

    def cur_posx():
        p = get_current_posx(DR_BASE)
        return list(p[0])            # [x,y,z,rx,ry,rz]

    def move_to(x, y, z, rx, ry, rz):
        movel(posx(x, y, z, rx, ry, rz),
              ref=DR_BASE, mod=DR_MV_MOD_ABS, ra=DR_MV_RA_DUPLICATE)

    # ── 1) 준비자세로 이동(특이점 회피) ──────────────────────
    print(f"[1] 준비자세로 이동(movej) {ready} ...")
    set_velx(30.0, 30.0)
    set_accx(60.0, 60.0)
    # vel/acc 30→25.5deg/s(-15%, "모든 동작 15% 감소" 일괄 적용).
    movej(posj(*ready), vel=25.5, acc=25.5, ra=DR_MV_RA_DUPLICATE)

    home = cur_posx()
    x0, y0, z0 = home[0], home[1], home[2]
    rx, ry, rz = home[3], home[4], home[5]
    print(f"[2] 홈 TCP: X{x0:.1f} Y{y0:.1f} Z{z0:.1f}  R({rx:.1f},{ry:.1f},{rz:.1f})")
    print("    → 종이를 이 XY 바로 아래에 놓으세요. (XY 고정, Z 만 내립니다)")

    # ── 2) Z 하강: 홈→start_z 이동 후, 사람이 키보드로 '눈으로' 내려 표면을 잡는다 ──
    # 자동 접촉정지(--auto-contact)는 payload/TCP 캘리된 경우에만. 캘리 안 됐으면 힘을 못 읽어
    # 표면을 지나쳐 안전바닥까지 내려가 박힐 수 있으므로, 기본은 사람이 보며 멈추는 방식(검증됨).
    set_velx(20.0, 30.0)
    set_accx(60.0, 60.0)
    z = z0

    def read_contact():
        try:
            return bool(check_force_condition(
                DR_AXIS_Z, min=args.contact_n, ref=DR_BASE))
        except Exception:
            return None

    def auto_descend_to_contact(floor_z):
        """(--auto-contact 전용) 현재 z 에서 floor_z 까지 0.5mm 씩 자동 하강.
        접촉 감지 시 True(정지), 힘 못읽으면 None, 바닥 도달 시 False."""
        nonlocal z
        sub = 0.5
        while z - sub >= floor_z:
            z -= sub
            move_to(x0, y0, z, rx, ry, rz)
            hit = read_contact()
            if hit is None:
                return None
            if hit:
                return True
        return False

    surface_z = None

    if args.auto_z:
        # ── 자동 모드: 표면 Z를 이미 아니까 대화형 하강은 물론, 실제로 표면까지 내려갔다
        # 다시 올라오는 '확인용 접촉'도 생략한다. 이 접촉은 --surface-z 를 신뢰할 수 있게 된
        # 뒤로는 새 정보를 주지 않는 순수 중복 동작이었다(내려갔다 바로 올라오고, 곧이어
        # draw_svg_at_surface() 가 어차피 첫 획 시작점에서 다시 내려가 접촉함) — 없애서
        # pen_up→그리기 사이 시간을 ~1초 단축.
        print(f"\n[3] --surface-z {args.surface_z:.2f}mm 지정됨 → 대화형 하강 및 확인용 접촉 생략...")
        print("    ⚠ 검증 없이 이 값을 그대로 씁니다. 값이 틀리면 위험(펜 박힘/뜸). E-stop 손 위에.")
        z = args.surface_z
        surface_z = args.surface_z
        print(f"    ★ Z={surface_z:.2f}mm 표면으로 확정(실제 하강 없이 값만 사용).")
    else:
        # 1) 홈을 start_z(기본 100mm)로 '한 번에' 이동(빠르게 — 표면 위라 안전)
        if args.start_z < z0:
            print(f"\n[3] 홈 → Z={args.start_z:.1f}mm 로 이동(속도 {args.start_vel:.0f}mm/s)...")
            print("    ※ 종이가 홈 XY 아래에 있고 경로에 장애물 없는지 확인. E-stop 손 위에.")
            set_velx(args.start_vel, 40.0)
            set_accx(120.0, 120.0)
            move_to(x0, y0, args.start_z, rx, ry, rz)
            z = args.start_z
            print(f"    → Z={z:.1f}mm 도착. 여기서 키보드로 미세조정하며 표면까지 내려가세요.")
        else:
            print(f"\n[3] 홈 Z={z0:.1f}mm 에서 '키보드로 눈으로' 하강합니다(블라인드 이동 없음).")
            print(f"    표면 높이를 확실히 아는 경우에만 --start-z 로 그 위 높이까지 이동 가능.")

        set_velx(15.0, 30.0)                   # 이제부터 느리게
        set_accx(60.0, 60.0)

        # 2) (옵션) payload/TCP 캘리된 경우에만 자동 접촉정지. 기본은 건너뛰고 키보드.
        if args.auto_contact:
            print(f"    자동 하강(힘 {args.contact_n:.0f}N 감지 정지, 안전 바닥 {args.min_z:.0f}mm)...")
            res = auto_descend_to_contact(args.min_z)
            if res is True:
                surface_z = z
                print(f"    ★ 접촉 감지 → Z={surface_z:.2f}mm 표면 기록.")
            elif res is None:
                print("    [주의] 힘을 못 읽음 → 자동정지 불가. 아래 키보드로 눈으로 내리세요.")
            else:
                print(f"    [주의] 바닥({args.min_z:.0f}mm)까지 접촉 없음 → 키보드로 미세 진행.")
        else:
            print("    이제 키보드로 '눈으로 보며' 내리세요 — 종이에 살짝 닿으면 done.")
            print("    (자동정지 없음 = 힘센서 의존 X = 안 박힘. 처음엔 Enter로, 가까우면 1+Enter)")

        # 3) 키보드 하강: Enter=step 만큼 하강, u=상승, done=표면확정, q=취소
        step = args.step
        while surface_z is None:
            line = input(f"  [Z={z:.2f} step={step:.2f}] Enter=하강 / 숫자=step / "
                        f"z<값>=그Z로이동 / u=상승 / done / q > ").strip()
            print(f"  [입력받음: '{line}']")
            low = line.lower()
            if line == '':
                z -= step
                move_to(x0, y0, z, rx, ry, rz)
            elif low == 'u':
                z += 3.0
                move_to(x0, y0, z, rx, ry, rz)
            elif low.startswith('z') or low.startswith('g'):
                # z<값> / g<값> : 입력한 절대 Base Z(mm) 로 바로 이동
                try:
                    target = float(low[1:].strip())
                except ValueError:
                    print("  ? z 뒤에 숫자로 (예: z120 → Z=120mm 로 이동)")
                    continue
                print(f"  Z={target:.1f}mm 로 이동({args.jump_vel:.0f}mm/s)... "
                    f"{'⚠ 아래로 크게 내려갑니다' if z - target > 20 else ''}")
                set_velx(args.jump_vel, 30.0)      # 점프는 빠르게
                set_accx(90.0, 90.0)
                z = target
                move_to(x0, y0, z, rx, ry, rz)
                set_velx(15.0, 30.0)               # 점프 후엔 다시 느린 미세조정 속도로 복귀
                set_accx(60.0, 60.0)
            elif low == 'done':
                surface_z = z
            elif low == 'q':
                print("  취소 → 안전 높이로 복귀")
                move_to(x0, y0, z0, rx, ry, rz)
                _shutdown(dsr_node)
                return
            else:
                try:
                    step = float(line)
                    print(f"  step → {step:.2f}mm")
                except ValueError:
                    print("  ? 모르는 입력(Enter/숫자/z<값>/u/done/q)")

    # ── 3) 표면 Z 확정 ──────────────────────────────────────
    print(f"\n[4] 표면 Z = {surface_z:.2f} mm 로 확정.")
    print(f"    config 반영값 →  draw_height_mm: {surface_z:.2f}")
    if not args.auto_z:
        # 대화형 모드는 로봇이 지금 surface_z(표면 바로 위/접촉)에 있으니 살짝 들어 올려
        # 안전 확보. auto 모드는 애초에 안 내려갔으니(홈/준비자세 높이 그대로) 필요 없다 —
        # 여기서 또 내려가면, 곧이어 draw_svg_at_surface()->execute() 가 movej 로 준비자세로
        # '다시 올라갔다' 그리기 시작점으로 '또 내려가는' 왕복이 생겨 두 번 오르내리는
        # 것처럼 보이고 시간도 더 든다. 하강은 execute()+draw_stroke() 한 번으로 충분.
        move_to(x0, y0, surface_z + args.pen_up, rx, ry, rz)

    ans = input("\n[5] 이 높이로 지금 SVG 를 그릴까요? (y/N) > ").strip().lower()
    if ans != 'y':
        print("    그리기 생략. 안전 높이로 복귀 후 종료.")
        move_to(x0, y0, z0, rx, ry, rz)
        _shutdown(dsr_node)
        return

    draw_svg_at_surface(args, surface_z, home)
    print("\n[6] 완료. 안전 높이로 복귀.")
    move_to(x0, y0, z0, rx, ry, rz)
    _shutdown(dsr_node)


def draw_svg_at_surface(args, surface_z: float, home):
    """측정한 surface_z 를 draw_height 로, 홈 XY 중심에 SVG 를 그린다(위치제어)."""
    # 전체 파이프라인을 서비스와 동일하게 재사용
    from svg_drawing.svg_parser import SvgParser
    from svg_drawing.bezier_sampler import sample_paths, rdp_simplify_paths
    from svg_drawing.coordinate_mapper import CoordinateMapper, WorkArea
    from svg_drawing.trajectory_planner import optimize
    from svg_drawing.robot_controller import RobotConfig, RobotController

    x0, y0 = home[0], home[1]
    rx, ry, rz = home[3], home[4], home[5]
    size = args.size

    print(f"\n[파이프라인] SVG 파싱: {args.svg}")
    parsed = SvgParser().parse(args.svg)
    if not parsed.strokes:
        print("  [에러] SVG 에서 그릴 경로를 못 찾음"); return

    work = WorkArea(width_mm=size, height_mm=size, margin_mm=5.0, center=True)
    mapper = CoordinateMapper(parsed.viewbox, work)
    # 0.5→2.0mm: 구간이 짧으면(가속도 유한) 목표속도(draw_vel_mm_s)까지 도달을 못 해서
    # 아무리 속도를 올려도 체감이 안 됐다 — v_peak≈sqrt(accel*구간길이) 라 구간을 늘려야
    # 실제 도달속도가 오른다(대신 곡선이 살짝 덜 매끈해짐).
    res_mm = 2.0
    max_seg = res_mm / mapper.scale if mapper.scale > 0 else res_mm
    paper_polys = mapper.map_strokes(sample_paths(parsed.strokes, max_seg))
    # 곡선 구간이 너무 느린 문제 대응: 2mm 균일 샘플이라 직선/완만한 곡선에도 불필요한
    # 중간점이 촘촘히 남아있었다. RDP 로 --simplify-tol-mm(기본 0.15mm) 이내로 근사되는
    # 중간점을 제거 → 직선/완만한 구간 세그먼트가 길어져 robot_controller 의 각도 기반
    # 적응형 블렌드가 그 구간에서 더 큰 반경(더 빠른 코너링)을 쓸 여지가 생긴다.
    # 실제 도형 꼭짓점(꺾이는 지점)은 tolerance 를 벗어나 그대로 보존됨.
    if args.simplify_tol_mm > 0:
        before = sum(len(p) for p in paper_polys)
        paper_polys = rdp_simplify_paths(paper_polys, args.simplify_tol_mm)
        after = sum(len(p) for p in paper_polys)
        print(f"  단순화(RDP {args.simplify_tol_mm}mm): 점 {before} → {after}개")
    paper_polys = rotate_polys(paper_polys, size / 2.0, size / 2.0, args.rotate_deg)
    ordered = optimize(paper_polys, start=(0.0, 0.0))
    print(f"  획 {len(ordered)}개, 매핑 {mapper.describe()}")

    # 그림 중심(작업영역 중심 = size/2)이 '홈 XY' 에 오도록 용지 원점 설정
    px_sign, py_sign = 1.0, 1.0
    origin_x = x0 - (size / 2.0) * px_sign + args.off_x
    origin_y = y0 - (size / 2.0) * py_sign + args.off_y   # +Y=로봇 왼쪽

    cfg = RobotConfig(
        paper_origin_x_mm=origin_x,
        paper_origin_y_mm=origin_y,
        paper_x_sign=px_sign,
        paper_y_sign=py_sign,
        # 위치제어(force OFF)면 표면보다 press_mm 더 눌러 일정 깊이로 긁는다(일정 압력 효과).
        draw_height_mm=(surface_z if args.force else surface_z - args.press_mm),
        approach_height_mm=surface_z + 5.0,       # 시작점 위 접근
        travel_height_mm=surface_z + args.pen_up, # 획 사이 펜업(작게)
        tool_rx_deg=rx, tool_ry_deg=ry, tool_rz_deg=rz,   # 현재 자세 유지
        # 힘제어 16.51→13.21→10.57→12.68mm/s(다시 +20%, 저속구간 길이·속도 조정 후
        # 순항 속도는 좀 더 올려도 괜찮다는 피드백). 가속도는 한때 62.83→31.4(-50%,
        # 하드정지 지점 오버슈트 완화용)로 낮췄다가 원래대로 복귀(전역으로 낮추면 코너
        # 많은 곡선마다 재가속이 느려져 "곡선이 너무 느림"으로 나타났었음) → 이제 곡선
        # 구간은 적응형 블렌드(draw_blend_radius_max_mm)가 코너 감속을 따로 완화해주니,
        # 전역 가속도는 62.83→50.26(-20%)로 다시 살짝 낮춰도 곡선 체감 속도에 영향이 적다.
        draw_vel_mm_s=(args.draw_vel if args.draw_vel is not None
                       else (12.68 if args.force else 37.62)),
        draw_acc_mm_s2=(args.draw_acc if args.draw_acc is not None
                        else (50.26 if args.force else 120.0)),
        # 획 사이 이동(펜업 상태) 60/300→51/255(-15%)로 같이 낮춤.
        travel_vel_mm_s=51.0, travel_acc_mm_s2=255.0,
        # 각 점에서 완전정지("차큰차큰")하지 않도록 blend radius 부여 → 이어서 부드럽게 통과.
        # ★ 샘플 간격(2.0mm)의 '절반 미만'(<1.0)이어야 인접 블렌드가 안 겹쳐 코너가 안 삐져나옴.
        # 1.5(간격 절반 초과)로 뒀더니 코너가 부풀어 삐져나오던 문제 → 0.8로 복귀.
        draw_blend_radius_mm=0.8,
        draw_extend_frac=args.draw_extend,   # 획을 끝에서 이만큼 더 연장(끝이 덜 그려지는 것 보완)
        draw_passes=args.draw_passes,        # 같은 획 왕복 겹쳐그리기 횟수
        # 힘제어: --force 면 설정 높이(surface_z)로 정확히 내려간 뒤 그 지점에서
        # 일정 힘으로 눌러 아크릴을 긁는다. XY 는 위치제어(형태 유지), Z 만 힘추종.
        use_force_control=args.force,
        draw_force_n=args.force_n,
        # 좌우 힘 분리(도안을 로봇이 바라보는 방향 기준). 중심선은 용지 중심(= 홈 XY)의
        # Base Y 값 그대로 — origin_y 계산식(y0 - size/2*py_sign + off_y)에서 py=size/2를
        # 대입하면 py_sign 항이 정확히 상쇄돼 항상 y0+off_y 가 된다.
        draw_force_n_left=args.force_n_left,
        draw_force_n_right=args.force_n_right,
        force_split_center_by_mm=(y0 + args.off_y) if args.force_split else None,
        # 딱 자르지 않고 도안 폭(size) 전체에 걸쳐 오른쪽→왼쪽 힘으로 부드럽게 보간.
        force_gradient_span_mm=size,
        force_z_sign=args.force_sign,
        force_push_mm=args.force_push_mm,
        force_ramp_wait_s=args.force_ramp_wait,
        # XY 병진 딱딱(3000, 형태 유지), Z 병진만 --stiffness-z 로 물렁(힘제어).
        # 회전(Rx·Ry·Rz) 200→1000→3000: 긴 펜(289mm)이 끌림 토크에 기울면 펜 팁 XY가 크게
        # 흔들려(지렛대 증폭) 시작/끝 위치가 어긋남 → 회전을 XY와 같은 3000으로 완전히 딱딱하게
        # 잡아 툴 기울기(→팁 흔들림)를 최대한 억제. Z만 물렁하게 두어 힘제어는 그대로.
        compliance_stiffness=[3000.0, 3000.0, args.stiffness_z, 3000.0, 3000.0, 3000.0],
        # 준비자세(원위치) 관절각. 그리기 시작 전 특이점 회피용이자, 아크릴 미접촉으로
        # 중단(NoContactError)될 때 "원위치로 복귀"하는 목표 자세로도 쓰인다. pen_up 이
        # 이미 이 자세로 끝나 시작 movej 는 사실상 제자리(빠름)라 둬도 부담 없다.
        ready_joints_deg=[0.0, 0.0, 90.0, 0.0, 90.0, 0.0],
        dry_run=False,
    )

    # 안전: 실제로 보낼 Base 좌표 범위를 먼저 보여주고 카운트다운
    xs = [origin_x + px * px_sign for poly in ordered for (px, _) in poly]
    ys = [origin_y + py * py_sign for poly in ordered for (_, py) in poly]
    print(f"\n[확인] 로봇에 보낼 Base 좌표 범위:")
    print(f"   X {min(xs):.1f} ~ {max(xs):.1f} mm")
    print(f"   Y {min(ys):.1f} ~ {max(ys):.1f} mm")
    if args.force:
        print(f"   [힘제어] 표면 {surface_z:.1f}mm 로 내려가 {args.force_n:.0f}N 으로 누름 "
              f"(강성Z={args.stiffness_z:.0f})")
    else:
        _dz = surface_z - args.press_mm
        print(f"   [위치제어] Z 긋기 {_dz:.2f}mm (표면 {surface_z:.1f} − 눌림 {args.press_mm:.2f}) "
              f"/ 펜업 {surface_z + args.pen_up:.1f} mm")
    if args.force:
        print(f"   힘제어 ON → 표면({surface_z:.1f}mm)으로 내려간 뒤 "
              f"{args.force_n:.1f}N 으로 누르며 긁기 (부호 {args.force_sign:+.0f})")
    else:
        print(f"   힘제어 OFF(위치제어) → {surface_z:.1f}mm 높이 고정으로 긋기")
    print("   범위가 이상하면(작업영역 밖 등) 지금 Ctrl+C 로 취소하세요.")
    for s in range(5, 0, -1):
        print(f"   {s}...", end=' ', flush=True)
        time.sleep(1.0)
    print("시작!\n")

    # 그리기 시작 전 TCP 오프셋 검증 — pen(~289mm)이 아니면(리셋 의심) 움직이기 전에 중단.
    ok, msg = verify_pen_tcp(DR_init.__dsr__node)
    print(msg)
    if not ok:
        raise TcpMismatchError(msg)

    rc = RobotController(cfg)
    stats = rc.execute(ordered)
    print(f"[파이프라인] 완료: 획 {stats.strokes}, 점 {stats.points}, "
          f"긋기 {stats.draw_len_mm:.0f}mm")


def _shutdown(node):
    try:
        node.destroy_node()
    except Exception:
        pass
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단] Ctrl+C — 로봇을 그대로 두고 종료합니다. "
              "필요시 티치펜던트로 안전 위치로 옮기세요.")
        if rclpy.ok():
            rclpy.shutdown()
    except NoContactError as e:
        # robot_controller.py 가 이미 안전 위치로 복귀시킨 뒤 이 예외를 던진다 —
        # 여기서는 트레이스백 대신 원인이 분명한 한 줄 메시지로 깔끔하게 종료.
        print(f"\n[중단] {e}")
        if rclpy.ok():
            rclpy.shutdown()
        sys.exit(1)
    except TcpMismatchError as e:
        # TCP 리셋(오프셋 불일치) 감지 — 로봇을 전혀 움직이지 않고 중단.
        print(f"\n[중단] {e}")
        if rclpy.ok():
            rclpy.shutdown()
        sys.exit(1)
