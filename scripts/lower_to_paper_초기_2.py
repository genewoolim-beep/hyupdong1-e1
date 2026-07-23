#!/usr/bin/env python3
"""lower_to_paper.py — 키보드로 펜을 조금씩 내려 '종이 표면 Z'를 직접 찾고,
그 높이로 (위치제어·힘제어 OFF) SVG 를 바로 그린다.

가장 안전한 방식: 로봇이 자동으로 훅 내려가지 않고, 사람이 눈으로 보며 키보드로
1mm~5mm씩 내려 종이에 '살짝 닿는 순간'을 직접 잡는다. 그 Z 를 draw_height 로 삼아
아까 고친 draw_stroke(설정 높이로 정확히 내려와 긋기) 로 그린다.

실행:
    source /opt/ros/humble/setup.bash
    source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
    python3 ~/ws_cobot_pjt/ws_dsr/src/svg_drawing/scripts/lower_to_paper.py
    # SVG 지정 / 그림 크기(mm) 지정:
    python3 .../lower_to_paper.py --svg /path/to.svg --size 100

키(글자를 친 뒤 반드시 Enter):
    Enter(빈 줄)  현재 step 만큼 하강 (기본 5mm)
    숫자 + Enter  step 크기 변경(예: 1 → 이후 Enter 는 1mm씩)
    u  + Enter    3mm 상승(너무 내렸을 때)
    done+ Enter   지금 높이를 표면 Z 로 확정
    q  + Enter    취소(안전 높이로 복귀 후 종료)

※ 실제 로봇을 종이 쪽으로 내리는 동작입니다. E-stop 손 위에 두고, 종이를
   '준비자세 홈 XY 바로 아래'에 놓은 뒤 진행하세요. 세게 누르지 말고 '살짝 닿으면' done.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import rclpy
import DR_init

DEFAULT_SVG = os.path.expanduser(
    '~/ws_cobot_pjt/ws_dsr/src/svg_drawing/samples/entj_star.svg')


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
    ap.add_argument('--start-vel', type=float, default=40.0,
                    help='start-z 까지 이동 속도(mm/s). 기본 40(적당). 낮추면 더 천천히')
    ap.add_argument('--min-z', type=float, default=70.0,
                    help='자동 하강 안전 바닥(mm). 접촉 없이 이 높이 도달하면 정지(그 아래로 안 내려감). '
                         '기본 70mm(표면74 근처). 표면이 더 낮으면 이 값을 낮추세요')
    ap.add_argument('--auto-contact', action='store_true',
                    help='자동 접촉정지 사용(payload/TCP 캘리된 경우만!). 기본 OFF — 사람이 키보드로 '
                         '눈으로 내려 done. 캘리 안 됐는데 켜면 힘을 못 읽어 표면 지나쳐 박힘')
    ap.add_argument('--contact-n', type=float, default=3.0,
                    help='(--auto-contact 시) 이 힘(N) 이상 감지되면 자동 정지·표면기록. 기본 3N')
    ap.add_argument('--size', type=float, default=100.0,
                    help='그림이 들어갈 정사각 작업영역 한 변(mm). 홈 XY 중심에 배치')
    ap.add_argument('--pen-up', type=float, default=15.0,
                    help='획 사이 펜업 높이(표면 위 mm)')
    # ── 힘제어(일정 힘으로 아크릴 긁기) ──────────────────────
    ap.add_argument('--force', action=argparse.BooleanOptionalAction, default=False,
                    help='Z축 힘제어(compliance). 기본 OFF — 이 로봇은 payload/TCP 캘리 없이는 '
                         '힘제어 시 펜이 안 움직이거나 박힘. 일정 압력은 --press-mm(위치제어) 권장')
    ap.add_argument('--press-mm', type=float, default=0.2,
                    help='(위치제어) 측정 표면보다 이만큼 더 눌러 긋는다(mm) = 일정 깊이=일정 압력 효과. '
                         '기본 0.2mm(가벼운 스크래치). 연하면 0.3~0.5 올리고, 과하면 0.1/0 로')
    ap.add_argument('--force-n', type=float, default=2.0,
                    help='아크릴을 누르는 목표 힘(N). 기본 2N(가볍게). 스크래치 연하면 3~4N로 조금씩 올려 튜닝')
    ap.add_argument('--force-sign', type=float, default=-1.0,
                    help='누르는 방향 부호. -1=Base -Z(아래로). 설치 자세에 맞춰 조정')
    ap.add_argument('--stiffness-z', type=float, default=2000.0,
                    help='힘제어 Z 강성(N/m). 높을수록 표면 위치를 단단히 유지=덜 파고듦. '
                         '기본 2000(박힘 방지 안전측). 더 물렁하게=표면추종 원하면 낮추기(예: 500)')
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
    movej(posj(*ready), vel=30.0, acc=30.0, ra=DR_MV_RA_DUPLICATE)

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
        line = input(f"  [Z={z:.1f} step={step:.1f}] Enter=하강 / 숫자=step / "
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
            print(f"  Z={target:.1f}mm 로 이동(느리게)... "
                  f"{'⚠ 아래로 크게 내려갑니다' if z - target > 20 else ''}")
            z = target
            move_to(x0, y0, z, rx, ry, rz)
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
                print(f"  step → {step:.1f}mm")
            except ValueError:
                print("  ? 모르는 입력(Enter/숫자/z<값>/u/done/q)")

    # ── 3) 표면 Z 확정 ──────────────────────────────────────
    print(f"\n[4] 표면 Z = {surface_z:.2f} mm 로 확정.")
    print(f"    config 반영값 →  draw_height_mm: {surface_z:.2f}")
    # 살짝 들어 올려 안전 확보
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
    from svg_drawing.bezier_sampler import sample_paths
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
    res_mm = 0.5
    max_seg = res_mm / mapper.scale if mapper.scale > 0 else res_mm
    paper_polys = mapper.map_strokes(sample_paths(parsed.strokes, max_seg))
    ordered = optimize(paper_polys, start=(0.0, 0.0))
    print(f"  획 {len(ordered)}개, 매핑 {mapper.describe()}")

    # 그림 중심(작업영역 중심 = size/2)이 '홈 XY' 에 오도록 용지 원점 설정
    px_sign, py_sign = 1.0, 1.0
    origin_x = x0 - (size / 2.0) * px_sign
    origin_y = y0 - (size / 2.0) * py_sign

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
        draw_vel_mm_s=30.0, draw_acc_mm_s2=150.0,
        travel_vel_mm_s=60.0, travel_acc_mm_s2=300.0,
        # 힘제어: --force 면 설정 높이(surface_z)로 정확히 내려간 뒤 그 지점에서
        # 일정 힘으로 눌러 아크릴을 긁는다. XY 는 위치제어(형태 유지), Z 만 힘추종.
        use_force_control=args.force,
        draw_force_n=args.force_n,
        force_z_sign=args.force_sign,
        # XY 는 딱딱(3000)하게 형태 유지, Z 는 --stiffness-z 로 조절(높을수록 덜 파고듦)
        compliance_stiffness=[3000.0, 3000.0, args.stiffness_z, 200.0, 200.0, 200.0],
        ready_joints_deg=None,                    # 이미 준비자세 → 재이동 생략
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
