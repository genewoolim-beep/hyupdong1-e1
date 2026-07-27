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


class NoContactError(RuntimeError):
    """힘제어로 긋는 중인데 표면 접촉이 감지되지 않을 때(아크릴판 미배치, 표면 Z 오차 등).
    허공에 그리다가 계속 진행하는 것보다, 여기서 멈추고 안전 위치로 돌아가는 게 낫다."""
    pass


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
    # 획을 끝에서 이 비율만큼 더 연장해 그린다(마지막 진행 방향으로). 힘제어 지연·펜업 타이밍
    # 때문에 획 끝이 살짝 덜 그려지는 걸 보완. 0.10 = 전체 길이의 10% 더. 0 이면 연장 안 함.
    # 너무 크면 끝이 삐져나오거나 닫힌 도형이 과하게 겹치니 0.05~0.15 범위에서 조정.
    draw_extend_frac: float = 0.03
    # 같은 획을 이 횟수만큼 왕복하며 겹쳐 그린다(펜 든 채 되짚기). 1=한 번(기본), 2=왕복 1회
    # 더 덧그림, 3=세 번 등. 선을 더 진하게/끝까지 확실히 그리고 싶을 때. 시간은 대략 횟수배.
    draw_passes: int = 1
    # 획 시작 이 개수만큼의 점을 느리게 긋는다(draw_vel × draw_start_slow_frac 속도).
    # 정지→이동 전환 시 Z 힘 루프가 지연돼 초반이 뜬 채(가늘게) 그어지는 걸 완화 — 천천히
    # 움직이면 힘제어가 접촉을 유지할 시간이 생겨 초반부터 힘이 제대로 들어간다. 0이면 끔.
    draw_start_slow_pts: int = 6
    draw_start_slow_frac: float = 0.4
    # 획 끝~시작점 거리가 이 값(mm) 이하면 '닫힌 획'으로 보고, 연장 시 직선 외삽 대신
    # 시작 경로를 따라 이어 그려(랩어라운드) 시작 부분에 겹치게 한다(닫힘 연결).
    close_tol_mm: float = 5.0

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
    # 힘제어 ON 직후 실제 목표힘까지 램프업되는 데 시간이 걸리는데, 그 전에 긋기 시작하면
    # 초반 구간이 힘이 덜 들어간 채로 그어져 흐리게/안 그어진다. 획마다 이 시간만큼 그냥
    # 대기한 뒤 본체를 긋는다(예전엔 순수 대기 대신 시작 몇 점을 절반속도로 긋는 식으로
    # "대기 없이" 시간을 벌어봤는데, 실기에서 그것만으론 부족해서 결국 대기를 다시 넣음).
    force_ramp_wait_s: float = 3.0
    # 램프업 대기 후, 실제로 표면에 힘이 걸렸는지 확인하는 접촉 판정 임계값(N). 아크릴판을
    # 안 놓았거나 표면 Z 가 크게 틀어지면 펜이 허공에서 목표힘에 못 미친 채(≈0N) 계속
    # 긋게 되는데, 이 값보다 낮으면 "접촉 없음"으로 보고 그 획에서 즉시 중단·복귀한다.
    # draw_force_n 보다 충분히 낮게(노이즈 여유) 잡아야 오탐이 안 남.
    no_contact_force_n: float = 4.8
    # 접촉 판정을 '한 순간'이 아니라 짧은 시간 동안 |Fz| 를 여러 번 샘플링해 중앙값으로
    # 내린다(순간 노이즈로 힘이 잠깐 임계 밑으로 내려가도 오판 안 하도록). 아크릴이 있는데도
    # 없다고 나오던 오탐을 줄이는 핵심. samples×interval 이 분석 시간(기본 10×0.1s=1.0초).
    contact_check_samples: int = 10
    contact_check_interval_s: float = 0.1
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
        self._get_tool_force: Optional[Callable] = None
        self._wait: Optional[Callable] = None
        self._DR_AXIS_Z = 2
        self._DR_FC_MOD_ABS = 0
        # 아크릴 접촉 검사를 그리기당 '첫 획에서만' 한 번 하기 위한 플래그(execute 시작 시 리셋)
        self._contact_verified = False

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
                get_tool_force,
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
        self._get_tool_force = get_tool_force
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
        # time=0.3: DRL 커맨드 자체의 힘 램프업 시간(이 시간에 걸쳐 목표힘까지 부드럽게 올림).
        # 다만 실기에서는 이 0.3초가 지나도 실제로 완전히 안정(정착)되기까지 더 걸려서,
        # draw_stroke() 에서 cfg.force_ramp_wait_s(기본 2초) 만큼 별도로 더 대기한다.
        self._set_desired_force([0.0, 0.0, fz, 0.0, 0.0, 0.0],
                                [0, 0, 1, 0, 0, 0], time=0.3, mod=self._DR_FC_MOD_ABS)

    def _disable_z_force(self):
        if self.cfg.dry_run:
            return
        self._release_force(time=0.0)
        self._release_compliance_ctrl()

    def _has_contact(self) -> bool:
        """힘제어 램프업 후, 표면에 실제로 접촉해 힘이 걸렸는지 확인한다.
        한 순간이 아니라 짧은 시간 동안 |Fz| 를 여러 번(get_tool_force) 읽어 중앙값으로
        판정한다 — 순간 노이즈로 힘이 잠깐 임계 밑으로 내려가도 오판(아크릴 있는데 없다고
        하는 것)하지 않도록. 측정값은 로그로 남겨 임계값 튜닝에 참고한다.
        판단 불가(힘 읽기 실패/예외)면 오탐 방지를 위해 접촉으로 간주하고 계속 진행한다."""
        if self.cfg.dry_run:
            return True
        try:
            n = max(1, self.cfg.contact_check_samples)
            fz_samples = []
            for _ in range(n):
                f = self._get_tool_force(self._DR_BASE)   # [Fx,Fy,Fz,Tx,Ty,Tz]
                if f and len(f) >= 3:
                    fz_samples.append(abs(float(f[2])))
                time.sleep(self.cfg.contact_check_interval_s)
            if not fz_samples:
                self._info("[robot] 힘(Fz) 읽기 실패 — 접촉으로 간주하고 계속 진행")
                return True
            fz_samples.sort()
            median = fz_samples[len(fz_samples) // 2]
            peak = fz_samples[-1]
            contact = median >= self.cfg.no_contact_force_n
            self._info(
                f"[robot] 접촉 분석: |Fz| 중앙값 {median:.1f}N (최대 {peak:.1f}N, "
                f"표본 {len(fz_samples)}개, 임계 {self.cfg.no_contact_force_n}N) "
                f"→ {'접촉' if contact else '미접촉'}"
            )
            return contact
        except Exception as e:
            self._info(f"[robot] 접촉 판정 실패(무시하고 계속 진행): {e}")
            return True

    # ── 한 획 그리기 ────────────────────────────────────────
    def _extend_stroke(self, poly: Polyline) -> Polyline:
        """획 끝을 draw_extend_frac(전체 길이 기준)만큼 더 그어 끝이 덜 그려지거나 폐곡선이
        안 닫히는 걸 보완한다.
        - 닫힌 획: '도안 자체의 시작 곡선(poly[1], poly[2]…)'을 이어 그려 시작 부분에 겹친다.
          직선 외삽/합성 곡선이 아니라 원래 도안 경로를 그대로 연장한 거라 자연스럽게 이어지고,
          로봇의 ~1mm 경로 오차로 생기는 시작/끝 틈을 겹쳐서 덮는다.
        - 열린 획: 마지막 진행 방향으로 직선 외삽."""
        frac = self.cfg.draw_extend_frac
        if frac <= 0 or len(poly) < 3:
            return poly
        total = 0.0
        for (ax, ay), (bx, by) in zip(poly, poly[1:]):
            total += math.hypot(bx - ax, by - ay)
        if total <= 0:
            return poly
        ext = total * frac

        (p0x, p0y), (pnx, pny) = poly[0], poly[-1]
        gap = math.hypot(pnx - p0x, pny - p0y)
        # 닫힘 판정: 끝~시작 거리가 절대 기준(close_tol_mm) 또는 획 길이의 20% 이하면 닫힘.
        closed = gap <= max(self.cfg.close_tol_mm, 0.20 * total)
        if closed:
            # 도안의 시작 경로를 ext 길이만큼 이어 그림 → 시작 부분에 자연스럽게 겹침.
            out = list(poly)
            acc = 0.0
            prev = poly[-1]
            for pt in poly[1:]:
                acc += math.hypot(pt[0] - prev[0], pt[1] - prev[1])
                out.append(pt)
                prev = pt
                if acc >= ext:
                    break
            return out
        # 열린 획: 마지막 진행 방향으로 직선 외삽
        (px, py), (qx, qy) = poly[-2], poly[-1]
        dx, dy = qx - px, qy - py
        d = math.hypot(dx, dy)
        if d < 1e-9:
            return poly
        return list(poly) + [(qx + dx / d * ext, qy + dy / d * ext)]

    def draw_stroke(self, poly: Polyline):
        if len(poly) < 2:
            return
        c = self.cfg
        poly = self._extend_stroke(poly)   # 끝에서 draw_extend_frac 만큼 더 그리도록 연장
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
            # [한때 삭제했다가 복원] 시작 몇 점을 절반속도로 그어 "대기 없이" 램프업 시간을
            # 버는 방식을 써봤는데, 실기에서 그것만으론 힘이 덜 들어간 채로 초반 구간이
            # 흐리게/안 그어지는 문제가 있었다 → 결국 힘이 완전히 들어갈 때까지 그냥 대기.
            time.sleep(c.force_ramp_wait_s)
            # 2.5) 접촉 확인 — 아크릴 유무는 그리기 시작 전에 정해지는 조건이라 '첫 획에서만'
            # 한 번 검사한다(매 획 검사하면 획당 ~3초씩 붙어 너무 느림). 아크릴판을 안 놓았거나
            # 표면 Z 가 크게 틀어지면 램프업 후에도 목표힘에 못 미친 채(≈0N, 허공) 남는데, 그때
            # 그리기를 중단하고 원위치로 복귀한다. (도중에 판이 빠지는 경우는 감지 못 함 — 트레이드오프)
            if not self._contact_verified:
                if not self._has_contact():
                    self._info(
                        f"[에러] 표면 접촉 미감지(목표 {c.draw_force_n}N, 임계 {c.no_contact_force_n}N "
                        f"미만) — 아크릴판이 없거나 표면 높이가 잘못됐을 수 있습니다. "
                        f"그리기를 중단하고 원위치로 복귀합니다."
                    )
                    self._disable_z_force()
                    self._use_travel_speed()
                    self._movel_to(sx, sy, c.travel_height_mm, radius=c.travel_blend_radius_mm)
                    if c.ready_joints_deg:
                        self._movej(self._posj(*c.ready_joints_deg),
                                   vel=30.0, acc=30.0, ra=self._DR_MV_RA_DUPLICATE)
                    self._info("[안내] 원위치 복귀 완료. 아크릴판을 제자리에 놓고 "
                               "'로봇으로 그리기'를 다시 눌러주세요.")
                    raise NoContactError(
                        "아크릴판이 감지되지 않았습니다. 판을 제자리에 놓고 '로봇으로 그리기'를 "
                        "다시 눌러주세요."
                    )
                self._contact_verified = True   # 첫 획 접촉 확인됨 → 이후 획은 검사 생략
            # 3) 본체는 point-by-point movel 로 긋는다.
            #    [되돌림] 한때 movesx(스플라인)로 바꿨었다 — per-point movel 의 가감속이 힘 추정에
            #    노이즈를 준다는 이유였는데, movesx 는 task_compliance_ctrl/set_desired_force 와
            #    상호작용하도록 검증된 명령이 아니라서(Doosan 컴플라이언스는 movel 계열 기준으로
            #    문서화됨) 오히려 "안 닿아도 안 내려간다"— 즉 힘제어 자체가 씹히는 훨씬 심각한
            #    문제가 생겼다(실기 확인됨). 노이즈보다 무반응이 더 나쁘므로 movel 로 되돌린다.
            # try/finally: _draw_body_movel 중 예외가 나도 컴플라이언스를 반드시 끈다.
            # (전엔 여기서 죽으면 힘제어가 로봇에 켜진 채로 남아, 다음 실행이 그 위에서
            # 시작돼 갈수록 이상해지는/느려지는 문제가 있었다)
            lx, ly = poly[-1]
            try:
                lx, ly = self._draw_body_passes(poly)   # draw_passes 회 왕복 덧그림
            finally:
                self._disable_z_force()
        else:
            # 순수 위치제어: draw_height 로 접촉 후 본체
            self._movel_to(sx, sy, c.draw_height_mm)
            if c.stroke_mode == "movesx":
                self._draw_body_movesx(poly)
                lx, ly = poly[-1]
            else:
                lx, ly = self._draw_body_passes(poly)

        # 3) 펜업(travel_height 상승) : 펜이 실제로 끝난 지점 위로(왕복 횟수가 짝수면 시작점,
        #    홀수면 끝점). blend radius 를 줘서 다음 획 시작부 수평이동과 완전정지 없이 이어진다.
        self._use_travel_speed()
        self._movel_to(lx, ly, c.travel_height_mm, radius=c.travel_blend_radius_mm)

    def _draw_body_passes(self, poly: Polyline) -> Point:
        """같은 획을 draw_passes 회 '왕복'하며 겹쳐 긋는다(펜 든 채 되짚기).
        한 번 긋고, 펜을 안 떼고 역방향으로 되짚고, 다시 정방향… 반복.
        같은 선을 여러 번 덧그어 더 진하고 끝까지 확실히 그려진다.
        반환: 마지막 패스가 끝난 지점(펜 현재 위치) — 짝수 패스면 시작점, 홀수면 끝점."""
        passes = max(1, self.cfg.draw_passes)
        cur = poly
        for k in range(passes):
            self._draw_body_movel(cur)     # cur[1:] 를 그림(첫 점은 현재 펜 위치라 생략)
            if k < passes - 1:
                cur = cur[::-1]            # 다음 패스는 역방향으로 되짚기
        return cur[-1]

    def _draw_body_movel(self, poly: Polyline, include_first: bool = False,
                         z_override: Optional[float] = None):
        # 두 모드 모두 draw_stroke 에서 첫 점을 draw_height 로 이미 접촉시켰으므로
        # 기본은 poly[1:] 만 긋는다. include_first=True 는 첫 점부터 다시 긋고 싶을 때만.
        # z_override 를 주면(힘제어) 그 Z 를 목표로 긋는다(표면보다 살짝 아래 → 힘이 4N 유지).
        r = self.cfg.draw_blend_radius_mm
        z = self.cfg.draw_height_mm if z_override is None else z_override
        pts = poly if include_first else poly[1:]

        n = len(pts)
        # 시작 몇 점은 느리게 — 정지→이동 전환 시 힘 루프 지연으로 초반이 뜬 채(가늘게)
        # 그어지는 것 완화. 그 구간이 끝나면 정상 속도로 복귀.
        slow_n = 0 if self.cfg.dry_run else min(self.cfg.draw_start_slow_pts, n)
        if slow_n > 0:
            self._set_velx(self.cfg.draw_vel_mm_s * self.cfg.draw_start_slow_frac,
                           self.cfg.move_rot_vel_deg_s)
            self._set_accx(self.cfg.draw_acc_mm_s2, self.cfg.move_rot_acc_deg_s2)
        for i, (px, py) in enumerate(pts):
            if slow_n and i == slow_n:
                self._use_draw_speed()   # 느린 시작 구간 끝 → 정상 속도
            # 마지막 점은 radius=0 으로 '정확히' 찍는다. blend radius 를 마지막 점까지 주면
            # 코너를 잘라 끝점 ~1.5mm 앞에서 펜업이 시작돼 획이 짧아지고(닫힌 도형이 안 닫혀
            # 시작점과 ~2mm 벌어짐). 중간 점은 그대로 blend 유지(부드러움·속도).
            radius = 0.0 if i == n - 1 else r
            self._movel_to(px, py, z, radius=radius)

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
        self._contact_verified = False   # 이번 그리기의 첫 획에서 접촉 1회 검사하도록 리셋
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
            # 획마다 매번 찍는다(예전엔 20획마다였는데, 성향 시그니처는 보통 7~25획이라
            # 20 문턱을 넘는 경우가 거의 없어 진행률이 사실상 안 보였다). gui_bridge_server가
            # 이 줄을 파싱해 GUI에 진행률(%)로 보여준다 — 형식 바꾸면 그쪽 정규식도 같이 수정.
            pct = round((idx + 1) / stats.strokes * 100) if stats.strokes else 100
            self._info(f"[진행] {idx + 1}/{stats.strokes}획 ({pct}%)")

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
