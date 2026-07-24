"""robot_controller.py

Doosan Robotics Python API(DSR_ROBOT2) 로 실제 드로잉 모션을 생성/실행한다.

설계 원칙:
    - 용지 mm 좌표(좌상단 원점, x→오른쪽, y→아래) → 로봇 Base Cartesian 좌표로 변환.
    - 자세(Rx,Ry,Rz)는 작업 내내 고정 → XY 평면에서만 이동(스크래치 평면).
    - Z 는 draw/travel/approach 세 높이를 config 로 분리 → 추후 캘리브레이션이 쉬움.
    - 펜 집기/놓기(pick&place)는 구현 대상 제외(스펙).
    - DSR_ROBOT2 는 DR_init 노드 설정 이후에만 import 가능하므로 connect()에서 지연 import.

한 획(stroke) 그리기 순서:
    travel_height 로 시작점 위 이동 → approach_height 로 하강 → draw_height 로 접촉
    → 획의 모든 점을 draw_height 로 이동 → travel_height 로 상승(펜업)

dry_run=True 면 로봇을 움직이지 않고 계산/로그만 수행(빌드·경로 검증용).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

Point = Tuple[float, float]
Polyline = List[Point]


@dataclass
class RobotConfig:
    # 용지 원점의 Base 좌표 및 축 부호
    paper_origin_x_mm: float = 350.0
    paper_origin_y_mm: float = -100.0
    paper_x_sign: float = 1.0
    paper_y_sign: float = 1.0

    # Z 높이 (Base Z, mm)
    draw_height_mm: float = 5.0
    travel_height_mm: float = 25.0
    approach_height_mm: float = 10.0

    # 고정 자세 (deg)
    tool_rx_deg: float = 180.0
    tool_ry_deg: float = 0.0
    tool_rz_deg: float = 0.0

    # 속도/가속
    draw_vel_mm_s: float = 40.0
    draw_acc_mm_s2: float = 200.0
    travel_vel_mm_s: float = 150.0
    travel_acc_mm_s2: float = 600.0
    move_rot_vel_deg_s: float = 60.0
    move_rot_acc_deg_s2: float = 180.0

    # 그리기 방식
    stroke_mode: str = "movel"          # "movel" | "movesx"
    movesx_chunk: int = 50
    draw_blend_radius_mm: float = 0.0
    # 획 사이 이동(상승→수평이동→접근→접촉)이 전부 radius=0 이라 각 구간마다 완전정지
    # 했다가 재출발해서 "여러 번 뜨고 멈췄다 내려가는" 것처럼 보이던 문제 방지용 블렌드.
    # 5.0→2.0: 수직→수평처럼 방향이 크게 꺾이는 코너에서 블렌드가 크면 실제 travel_height
    # 보다 살짝 더 위로 부풀어 보일 수 있어(코너 블렌딩 특성) 줄임.
    travel_blend_radius_mm: float = 2.0

    # 그리기 시작 전 이동할 안전 준비자세(joint, deg). None 이면 생략.
    # 전원 직후 로봇은 수직으로 쭉 뻗은 '특이점' 자세일 수 있는데, 특이점에서 출발하는
    # movel(직선)은 거부되므로, 먼저 movej(관절이동)로 특이점을 벗어난 자세로 보낸다.
    ready_joints_deg: Optional[List[float]] = None

    # ── Z축 힘 제어(compliance) ────────────────────────────────────────────
    # True 면 획을 그을 때 순수 위치제어 대신, XY 는 위치제어(정확한 형태)로 두고
    # Z 는 '일정한 힘으로 누르는' 힘제어로 그린다. 표면이 조금 울퉁불퉁하거나
    # draw_height 가 미세하게 안 맞아도 펜이 일정 압력으로 눌려 접촉이 유지된다.
    # (스크래치 품질·안전에 가장 큰 영향. 실장비에서 draw_force_n·부호는 튜닝 필요)
    use_force_control: bool = False
    draw_force_n: float = 5.0                    # 표면을 누르는 목표 힘(N)
    # compliance 강성 [x,y,z,rx,ry,rz]. XY 는 딱딱하게(형태 유지), Z 는 물렁하게(힘추종).
    compliance_stiffness: List[float] = field(
        default_factory=lambda: [3000.0, 3000.0, 200.0, 200.0, 200.0, 200.0])
    # 힘 방향 부호: +1 이면 Base +Z 로, -1 이면 Base -Z 로 누른다(설치·자세에 맞춰 조정).
    force_z_sign: float = -1.0
    # 힘제어 그리기 시, 획 본체 Z 목표를 표면보다 이만큼 '아래'로 둔다(mm).
    # ⚠ 0 이 기본이다. 0보다 크면 실제 힘 = 목표힘 + 강성×(이 값)이 되어 과압(예: 2mm×강성)이
    #    발생한다(딱딱한 아크릴은 못 내려가 위치오차가 그대로 힘으로 더해짐). 힘을 목표값으로
    #    정확히 유지하려면 표면 높이에서 힘만 인가(=0)하고, 힘 부족 시엔 강성을 낮춰 대응한다.
    force_push_mm: float = 0.0

    # ── 터치오프(표면 Z 자동 측정) 안전 파라미터 ─────────────────────────
    probe_start_offset_mm: float = 30.0          # 예상 표면보다 이만큼 위에서 하강 시작
    probe_force_n: float = 5.0                   # 하강 시 누르는 탐침 힘(N)
    probe_contact_force_n: float = 7.0           # 이 힘 이상 감지되면 '접촉'으로 판단(N)
    probe_max_travel_mm: float = 80.0            # [안전] 이 이상 내려가도 접촉 없으면 중단
    probe_timeout_s: float = 20.0               # [안전] 시간 초과 시 중단
    probe_vel_mm_s: float = 10.0                 # 탐침 하강 속도(느리게)
    # [오탐 방지] 툴 무게로 인한 정적 Z힘이 접촉 임계값을 넘겨 '하강 전 접촉'으로 오판할 수
    # 있다. 시작 높이에서 최소 이만큼 실제로 내려간 뒤에만 접촉으로 인정한다.
    probe_min_descent_mm: float = 25.0

    dry_run: bool = False


@dataclass
class DrawStats:
    strokes: int = 0
    points: int = 0
    draw_len_mm: float = 0.0
    travel_len_mm: float = 0.0


class RobotController:
    """용지 mm 폴리라인들을 받아 Doosan 로봇으로 그린다."""

    def __init__(self, config: RobotConfig, logger=None):
        self.cfg = config
        self._log = logger
        self._connected = False
        # 지연 import 로 채워지는 DSR 심볼들
        self._movej: Optional[Callable] = None
        self._movel: Optional[Callable] = None
        self._movesx: Optional[Callable] = None
        self._set_velx: Optional[Callable] = None
        self._set_accx: Optional[Callable] = None
        self._posx: Optional[Callable] = None
        self._posj: Optional[Callable] = None
        self._DR_BASE = 0
        self._DR_MV_MOD_ABS = 0
        self._DR_MV_RA_DUPLICATE = 0
        # 힘제어/터치오프용 (connect 에서 채움)
        self._set_ref_coord: Optional[Callable] = None
        self._task_compliance_ctrl: Optional[Callable] = None
        self._release_compliance_ctrl: Optional[Callable] = None
        self._set_stiffnessx: Optional[Callable] = None
        self._set_desired_force: Optional[Callable] = None
        self._release_force: Optional[Callable] = None
        self._check_force_condition: Optional[Callable] = None
        self._get_current_posx: Optional[Callable] = None
        self._wait: Optional[Callable] = None
        self._DR_AXIS_Z = 2
        self._DR_FC_MOD_ABS = 0

    # ── 로깅 헬퍼 ────────────────────────────────────────────
    def _info(self, msg: str):
        if self._log is not None:
            self._log.info(msg)
        else:
            print(msg)

    # ── DSR API 연결(지연 import) ────────────────────────────
    def connect(self):
        """DR_init 노드가 설정된 뒤 호출. dry_run 이면 import 생략."""
        if self._connected:
            return
        if self.cfg.dry_run:
            self._info("[robot] dry_run=True → DSR API import 생략(모션 미실행)")
            self._connected = True
            return
        try:
            from DSR_ROBOT2 import (
                movej, movel, movesx, set_velx, set_accx,
                set_robot_mode, ROBOT_MODE_AUTONOMOUS,
                task_compliance_ctrl, release_compliance_ctrl,
                set_stiffnessx, set_desired_force, release_force,
                check_force_condition, get_current_posx, wait, set_ref_coord,
                DR_BASE, DR_MV_MOD_ABS, DR_MV_RA_DUPLICATE,
                DR_AXIS_Z, DR_FC_MOD_ABS,
            )
            from DR_common2 import posx, posj
        except ImportError as e:
            raise ImportError(
                f"DSR_ROBOT2 import 실패: {e}. Doosan 드라이버(bringup)와 "
                f"DR_init 노드 설정이 되어 있는지 확인하세요."
            ) from e
        self._movej, self._movel, self._movesx = movej, movel, movesx
        self._set_velx, self._set_accx, self._posx = set_velx, set_accx, posx
        self._posj = posj
        self._task_compliance_ctrl = task_compliance_ctrl
        self._release_compliance_ctrl = release_compliance_ctrl
        self._set_stiffnessx = set_stiffnessx
        self._set_desired_force = set_desired_force
        self._release_force = release_force
        self._check_force_condition = check_force_condition
        self._get_current_posx = get_current_posx
        self._wait = wait
        self._set_ref_coord = set_ref_coord
        self._DR_BASE = DR_BASE
        self._DR_MV_MOD_ABS = DR_MV_MOD_ABS
        self._DR_MV_RA_DUPLICATE = DR_MV_RA_DUPLICATE
        self._DR_AXIS_Z = DR_AXIS_Z
        self._DR_FC_MOD_ABS = DR_FC_MOD_ABS

        # 모션 명령을 받으려면 로봇이 자율(AUTONOMOUS) 모드여야 한다.
        try:
            set_robot_mode(ROBOT_MODE_AUTONOMOUS)
        except Exception as e:
            self._info(f"[robot] set_robot_mode 경고(무시): {e}")

        self._connected = True
        self._info("[robot] DSR API 연결 완료")

    # ── 좌표 변환: 용지 mm → Base posx ──────────────────────
    def paper_to_base(self, px: float, py: float, z: float):
        """용지(px,py) mm + Z(mm) → Base Cartesian posx (자세 고정)."""
        c = self.cfg
        bx = c.paper_origin_x_mm + px * c.paper_x_sign
        by = c.paper_origin_y_mm + py * c.paper_y_sign
        coords = [bx, by, z, c.tool_rx_deg, c.tool_ry_deg, c.tool_rz_deg]
        if self.cfg.dry_run or self._posx is None:
            return coords          # dry_run 에선 순수 리스트로 반환(검증용)
        return self._posx(*coords)

    # ── 속도 프로파일 전환 ──────────────────────────────────
    def _use_travel_speed(self):
        if self.cfg.dry_run:
            return
        self._set_velx(self.cfg.travel_vel_mm_s, self.cfg.move_rot_vel_deg_s)
        self._set_accx(self.cfg.travel_acc_mm_s2, self.cfg.move_rot_acc_deg_s2)

    def _use_draw_speed(self):
        if self.cfg.dry_run:
            return
        self._set_velx(self.cfg.draw_vel_mm_s, self.cfg.move_rot_vel_deg_s)
        self._set_accx(self.cfg.draw_acc_mm_s2, self.cfg.move_rot_acc_deg_s2)

    # ── 단일 movel 래퍼 ─────────────────────────────────────
    def _movel_to(self, px: float, py: float, z: float, radius: float = 0.0):
        if self.cfg.dry_run:
            return
        pos = self.paper_to_base(px, py, z)
        self._movel(pos, radius=radius, ref=self._DR_BASE,
                    mod=self._DR_MV_MOD_ABS, ra=self._DR_MV_RA_DUPLICATE)

    # ── 힘제어(compliance) 켜기/끄기 ─────────────────────────
    def _enable_z_force(self, force_n: float):
        """Base 기준 Z축에 일정한 힘을 인가(누름). XY 는 딱딱, Z 는 물렁(강성 설정)."""
        if self.cfg.dry_run:
            return
        self._set_ref_coord(self._DR_BASE)               # 힘 기준좌표 = Base
        self._task_compliance_ctrl()                     # 컴플라이언스 ON
        self._set_stiffnessx(self.cfg.compliance_stiffness, time=0.0)
        fz = self.cfg.force_z_sign * force_n             # 부호로 누르는 방향 결정
        # 램프업 시간(0.3초): draw_stroke() 의 _draw_body_movel(slow_first=True) 가 시작
        # 몇 점을 절반 속도로 그어서 이 시간만큼을 대기 없이 자연스럽게 확보한다.
        self._set_desired_force([0.0, 0.0, fz, 0.0, 0.0, 0.0],
                                [0, 0, 1, 0, 0, 0], time=0.3, mod=self._DR_FC_MOD_ABS)

    def _disable_z_force(self):
        if self.cfg.dry_run:
            return
        self._release_force(time=0.0)
        self._release_compliance_ctrl()

    # ── 한 획 그리기 ────────────────────────────────────────
    def draw_stroke(self, poly: Polyline):
        if len(poly) < 2:
            return
        c = self.cfg
        sx, sy = poly[0]

        # 1) 시작점 위(travel) → 접근(approach)  : 펜업 속도(위치제어)
        #    여기도 blend radius 를 줘서 travel→approach 사이에 완전정지 없이 흐르게 한다.
        #    (전엔 travel_height 도착 후 멈췄다가 다시 approach_height 로 내려가며 또 멈췄음
        #    → "멈추고 다시 내려가"로 보이던 원인)
        self._use_travel_speed()
        self._movel_to(sx, sy, c.travel_height_mm, radius=c.travel_blend_radius_mm)
        self._movel_to(sx, sy, c.approach_height_mm, radius=c.travel_blend_radius_mm)

        # 2) 획 본체
        self._use_draw_speed()
        if c.use_force_control and not c.dry_run:
            # ── 하이브리드 위치/힘 제어 ──────────────────────────────────
            #   XY = 위치제어(강성 3000, 형태 정확)   Z = 힘제어(강성 낮게, 표면 추종 4N)
            # 1) 먼저 위치제어로 표면(surface_z)까지 정확히 내려가 접촉(공중서 힘 켜면 안 됨)
            self._movel_to(sx, sy, c.draw_height_mm)
            # 2) 그 지점부터 Z 힘제어 ON — Z강성이 낮아(예:20) 위치 영향 최소, 힘이 지배해야 함
            self._enable_z_force(c.draw_force_n)
            # [삭제] 예전엔 여기서 time.sleep(0.3) 으로 힘 램프업을 기다렸는데, 획이 많은
            # 도안에서 순수 대기시간이 누적돼 너무 느려짐. 완전히 기다리지 않는 대신, 아래
            # _draw_body_movel(slow_first=True) 가 시작 몇 점만 절반 속도로 그어서 "어차피
            # 움직여야 하는 시간"을 램프업에 자연스럽게 써먹는다(순수 대기보다 훨씬 저렴).
            # 3) 본체는 point-by-point movel 로 긋는다.
            #    [되돌림] 한때 movesx(스플라인)로 바꿨었다 — per-point movel 의 가감속이 힘 추정에
            #    노이즈를 준다는 이유였는데, movesx 는 task_compliance_ctrl/set_desired_force 와
            #    상호작용하도록 검증된 명령이 아니라서(Doosan 컴플라이언스는 movel 계열 기준으로
            #    문서화됨) 오히려 "안 닿아도 안 내려간다"— 즉 힘제어 자체가 씹히는 훨씬 심각한
            #    문제가 생겼다(실기 확인됨). 노이즈보다 무반응이 더 나쁘므로 movel 로 되돌린다.
            # try/finally: _draw_body_movel 중 예외가 나도 컴플라이언스를 반드시 끈다.
            # (전엔 여기서 죽으면 힘제어가 로봇에 켜진 채로 남아, 다음 실행이 그 위에서
            # 시작돼 갈수록 이상해지는/느려지는 문제가 있었다)
            try:
                self._draw_body_movel(poly, slow_first=True)
            finally:
                self._disable_z_force()
        else:
            # 순수 위치제어: draw_height 로 접촉 후 본체
            self._movel_to(sx, sy, c.draw_height_mm)
            if c.stroke_mode == "movesx":
                self._draw_body_movesx(poly)
            else:
                self._draw_body_movel(poly)

        # 3) 펜업(travel_height 상승) : 마지막 점 위로. blend radius 를 줘서 다음 획
        #    시작부의 travel_height 수평이동과 완전정지 없이 이어지게 한다("두 번 뜨는" 현상 방지).
        lx, ly = poly[-1]
        self._use_travel_speed()
        self._movel_to(lx, ly, c.travel_height_mm, radius=c.travel_blend_radius_mm)

    def _draw_body_movel(self, poly: Polyline, include_first: bool = False,
                         z_override: Optional[float] = None, slow_first: bool = False):
        # 두 모드 모두 draw_stroke 에서 첫 점을 draw_height 로 이미 접촉시켰으므로
        # 기본은 poly[1:] 만 긋는다. include_first=True 는 첫 점부터 다시 긋고 싶을 때만.
        # z_override 를 주면(힘제어) 그 Z 를 목표로 긋는다(표면보다 살짝 아래 → 힘이 4N 유지).
        r = self.cfg.draw_blend_radius_mm
        z = self.cfg.draw_height_mm if z_override is None else z_override
        pts = poly if include_first else poly[1:]

        if slow_first and pts and not self.cfg.dry_run:
            # 힘 램프업을 별도 대기 없이 "벌기" 위해, 시작 몇 점만 절반 속도로 긋는다.
            # 샘플 간격이 0.5mm라 점 1개만으론 시간이 너무 적으니(대기 대체 효과 없음)
            # 여러 점(N_SLOW_FIRST)을 묶어서 확보한다.
            N_SLOW_FIRST = 6
            slow_pts, pts = pts[:N_SLOW_FIRST], pts[N_SLOW_FIRST:]
            self._set_velx(self.cfg.draw_vel_mm_s * 0.5, self.cfg.move_rot_vel_deg_s)
            self._set_accx(self.cfg.draw_acc_mm_s2, self.cfg.move_rot_acc_deg_s2)
            for (px, py) in slow_pts:
                self._movel_to(px, py, z, radius=r)
            self._use_draw_speed()   # 나머지는 정상 속도로 복귀

        for (px, py) in pts:
            self._movel_to(px, py, z, radius=r)

    def _draw_body_movesx(self, poly: Polyline):
        """스트로크를 movesx(스플라인)로 chunk 단위로 그린다(빠름)."""
        z = self.cfg.draw_height_mm
        chunk = max(2, self.cfg.movesx_chunk)
        pts = poly[1:]                          # 시작점은 이미 draw_height 로 접촉함
        i = 0
        while i < len(pts):
            seg = pts[i:i + chunk]
            if len(seg) == 1:                   # 마지막 한 점이면 movel 로 마무리
                self._movel_to(seg[0][0], seg[0][1], z)
                break
            pos_list = [self.paper_to_base(x, y, z) for (x, y) in seg]
            self._movesx(pos_list, ref=self._DR_BASE, mod=self._DR_MV_MOD_ABS)
            i += chunk

    # ── 터치오프: 표면 Z(Base) 자동 측정 ────────────────────
    def touch_off(self, x_mm: float, y_mm: float) -> Optional[float]:
        """용지(x,y)mm 지점에서 펜을 천천히 내려 표면 접촉을 감지하고 Base Z(mm)를 반환.
        접촉을 못 찾으면(안전 한계 도달) None.

        안전장치:
          - 예상 표면(draw_height)보다 probe_start_offset_mm 위에서만 하강 시작
          - probe_max_travel_mm 이상 내려가도 접촉 없으면 즉시 중단
          - probe_timeout_s 초과 시 중단
        시뮬(에뮬레이터)은 접촉 물리가 없어 힘이 감지되지 않으므로, 항상 '안전 중단'으로
        끝난다(코드 경로 검증용). 실장비에서만 실제 표면 Z 를 잡는다.
        """
        self.connect()
        c = self.cfg
        if c.dry_run:
            self._info("[touch] dry_run — 측정 생략, 현재 draw_height 반환")
            return c.draw_height_mm

        import time
        # 준비자세(특이점 회피) 후 탐침 지점 위로
        if c.ready_joints_deg:
            self._movej(self._posj(*c.ready_joints_deg),
                        vel=30.0, acc=30.0, ra=self._DR_MV_RA_DUPLICATE)
        start_z = c.draw_height_mm + c.probe_start_offset_mm
        floor_z = start_z - c.probe_max_travel_mm         # 이 아래로는 안 내려감(안전)

        self._use_travel_speed()
        self._movel_to(x_mm, y_mm, c.travel_height_mm)    # 안전하게 위에서 접근
        self._set_velx(c.probe_vel_mm_s, c.move_rot_vel_deg_s)  # 느린 탐침 속도
        self._set_accx(c.draw_acc_mm_s2, c.move_rot_acc_deg_s2)
        self._movel_to(x_mm, y_mm, start_z)

        self._info(f"[touch] 탐침 시작 @용지({x_mm:.1f},{y_mm:.1f}) "
                   f"start_z={start_z:.1f} floor_z={floor_z:.1f}")
        self._enable_z_force(c.probe_force_n)             # 아래로 살짝 누르며 하강

        contacted = False
        t0 = time.time()
        while time.time() - t0 < c.probe_timeout_s:
            cur = self._get_current_posx(self._DR_BASE)
            z = cur[0][2] if cur else start_z
            descended = start_z - z                 # 시작 높이 대비 실제 하강량

            # 접촉 = 힘 임계 초과 AND 최소 하강량 이상 실제로 내려감(정적힘 오탐 방지)
            force_hit = False
            try:
                force_hit = bool(self._check_force_condition(
                    self._DR_AXIS_Z, min=c.probe_contact_force_n, ref=self._DR_BASE))
            except Exception:
                force_hit = False
            if force_hit and descended >= c.probe_min_descent_mm:
                contacted = True
                break

            # 안전: 너무 많이 내려갔으면 중단
            if z <= floor_z:
                self._info(f"[touch] 안전 한계 도달(z={z:.1f}≤{floor_z:.1f}) → 중단")
                break
            self._wait(0.1)

        cur = self._get_current_posx(self._DR_BASE)
        surface_z = cur[0][2] if cur else None

        self._disable_z_force()
        self._use_travel_speed()
        self._movel_to(x_mm, y_mm, c.travel_height_mm)    # 다시 안전 높이로

        if contacted and surface_z is not None:
            self._info(f"[touch] 표면 접촉 감지 → 표면 Z = {surface_z:.2f} mm")
            return surface_z
        self._info("[touch] 접촉 감지 실패(안전 중단). 표면을 찾지 못함.")
        return None

    # ── 전체 실행 ───────────────────────────────────────────
    def execute(self, strokes: List[Polyline]) -> DrawStats:
        self.connect()
        stats = self._compute_stats(strokes)

        self._info(
            f"[robot] 실행 시작: 획 {stats.strokes}개, 점 {stats.points}개, "
            f"긋는 길이 {stats.draw_len_mm:.0f}mm, 공중 이동 {stats.travel_len_mm:.0f}mm, "
            f"mode={self.cfg.stroke_mode}, dry_run={self.cfg.dry_run}"
        )

        # 0) 특이점 회피: 그리기(movel) 전에 안전 준비자세로 movej(관절이동).
        #    전원 직후 수직 특이점 자세에서 바로 movel 하면 거부되어 로봇이 안 움직인다.
        if self.cfg.ready_joints_deg and not self.cfg.dry_run:
            self._info(f"[robot] 준비자세로 이동(movej) {self.cfg.ready_joints_deg}")
            self._movej(self._posj(*self.cfg.ready_joints_deg),
                        vel=30.0, acc=30.0, ra=self._DR_MV_RA_DUPLICATE)

        # 시작 전 안전하게 travel 높이로 올려둔다(첫 획 위에서 하강하도록)
        if strokes and not self.cfg.dry_run:
            self._use_travel_speed()
            fx, fy = strokes[0][0]
            self._movel_to(fx, fy, self.cfg.travel_height_mm)

        for idx, poly in enumerate(strokes):
            self.draw_stroke(poly)
            if (idx + 1) % 20 == 0:
                self._info(f"[robot] 진행 {idx + 1}/{stats.strokes} 획")

        # 종료 시 travel 높이로 상승
        if strokes and not self.cfg.dry_run:
            lx, ly = strokes[-1][-1]
            self._movel_to(lx, ly, self.cfg.travel_height_mm)

        self._info("[robot] 실행 완료")
        return stats

    # ── 통계(거리) 계산 ─────────────────────────────────────
    @staticmethod
    def _compute_stats(strokes: List[Polyline]) -> DrawStats:
        st = DrawStats()
        cur: Optional[Point] = None
        for poly in strokes:
            if len(poly) < 2:
                continue
            st.strokes += 1
            st.points += len(poly)
            if cur is not None:
                st.travel_len_mm += math.hypot(poly[0][0] - cur[0], poly[0][1] - cur[1])
            for a, b in zip(poly, poly[1:]):
                st.draw_len_mm += math.hypot(b[0] - a[0], b[1] - a[1])
            cur = poly[-1]
        return st


# ── 단독 테스트 (dry_run: 로봇/DSR 없이 좌표변환·통계 검증) ───────────────────
if __name__ == '__main__':
    cfg = RobotConfig(dry_run=True, paper_origin_x_mm=350.0, paper_origin_y_mm=-100.0)
    rc = RobotController(cfg)
    # 사각형 한 획
    square = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]
    base0 = rc.paper_to_base(0, 0, cfg.draw_height_mm)
    base1 = rc.paper_to_base(100, 0, cfg.draw_height_mm)
    print("용지(0,0)  -> Base", [round(v, 2) for v in base0])
    print("용지(100,0)-> Base", [round(v, 2) for v in base1])
    assert abs(base0[0] - 350.0) < 1e-6 and abs(base1[0] - 450.0) < 1e-6
    assert abs(base0[2] - cfg.draw_height_mm) < 1e-6           # Z = draw height
    assert base0[3] == cfg.tool_rx_deg                         # 자세 고정
    stats = rc.execute([square])
    print(f"stats: strokes={stats.strokes} points={stats.points} "
          f"draw={stats.draw_len_mm:.1f}mm travel={stats.travel_len_mm:.1f}mm")
    assert abs(stats.draw_len_mm - 400.0) < 1e-6               # 둘레 400mm
    print("OK")
