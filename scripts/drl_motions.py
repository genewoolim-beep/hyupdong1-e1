"""drl_motions.py

~/Downloads/ 의 DRL(Doosan Robot Language) 4개를 DSR_ROBOT2 파이썬 API로 그대로 옮긴 것.
    m0609_grab.drl     -> grab_motion()
    m0609_pen_down.drl -> pen_down_motion()
    m0609_pen_up.drl   -> pen_up_motion()
    m0609_brush.drl    -> brush_motion()

각 함수는 원본 DRL의 movej/movel 좌표·순서·grasp/release 디지털출력 패턴을 그대로 재현한다.
DRL의 set_velx(v, w, DR_OFF) 세 번째 인자(ref)는 이 워크스페이스에 설치된 DSR_ROBOT2.set_velx가
(vel, acc) 2-인자만 받으므로 생략했다(그 상태로도 값 자체는 동일하게 적용됨).

가상/시뮬레이터 모드로 띄우면(mode:=virtual, 하드웨어 없이) 이 스크립트가 실제 로봇과 완전히
동일한 DSR_ROBOT2 호출을 그대로 사용하므로, RViz 로 움직임을 확인만 하고 싶을 때도 실기용 코드와
분기 없이 같은 파일로 검증 가능하다.
"""

from __future__ import annotations

from typing import Callable

import gripper_modbus


class PenGraspError(Exception):
    """pen_up/brush 가 펜을 집으려 했는데 실제로는 못 집은 것으로 판단될 때(그리퍼가
    펜 두께만큼 벌어지지 않고 거의 완전히 오므라짐). 이 예외가 나올 때쯤엔 이미
    그리퍼를 열고 준비자세로 복귀까지 마친 상태다 — 호출부는 잡고 재시작 여부만
    사용자에게 물으면 된다."""


class DrlMotions:
    """connect() 이후 확보한 DSR_ROBOT2 함수들을 들고 각 모션을 실행."""

    def __init__(self, movej: Callable, movel: Callable, wait: Callable,
                 set_velj: Callable, set_accj: Callable,
                 set_velx: Callable, set_accx: Callable,
                 set_digital_output: Callable, set_singular_handling: Callable,
                 posj, posx, DR_AVOID, DR_MV_MOD_ABS, DR_MV_RA_DUPLICATE,
                 speed_scale: float = 1.0, verify_pen_grasp: bool = True):
        self._movej = movej
        self._movel = movel
        self._wait = wait
        self._set_velj = set_velj
        self._set_accj = set_accj
        self._set_velx = set_velx
        self._set_accx = set_accx
        self._set_digital_output = set_digital_output
        self._set_singular_handling = set_singular_handling
        self._posj = posj
        self._posx = posx
        self._DR_AVOID = DR_AVOID
        self._MOD_ABS = DR_MV_MOD_ABS
        self._RA_DUP = DR_MV_RA_DUPLICATE
        self._speed_scale = speed_scale  # DRL 원본 속도 대비 배율(예: 0.1 = 10% 속도)
        # False면 _verify_pen_grasped_or_recover 가 아무 것도 안 하고 넘어간다 — Z값
        # 미리보기용 더미 인스턴스(movel/set_digital_output 등이 전부 no-op)에서 이 값을
        # 꺼야 한다. 안 그러면 더미는 실제로 그리퍼를 안 움직였는데도 Modbus로 "현재
        # 실제 그리퍼 상태"를 읽어버려, 미리보기 단계에서 엉뚱하게 PenGraspError 가 나며
        # 죽는다(실제 로봇 동작을 하나도 안 했는데 실패로 뜨는 버그였음).
        self._verify_pen_grasp = verify_pen_grasp

    # ── 공통: DRL 상단부의 set_singular_handling/set_velj/accj/velx/accx ──
    #    (DRL 원본 값 * speed_scale)
    def _apply_common_profile(self):
        self._set_speed(1.0)
        self._set_singular_handling(self._DR_AVOID)

    def _set_speed(self, mult: float):
        """speed_scale * mult 로 velj/accj/velx/accx 재설정. 모션 중간에 구간별
        속도를 바꾸고 싶을 때 사용(예: grab 에서 파지 전/후 속도를 다르게)."""
        s = self._speed_scale * mult
        self._set_velj(60.0 * s)
        self._set_accj(100.0 * s)
        self._set_velx(250.0 * s, 80.625 * s)
        self._set_accx(1000.0 * s, 322.5 * s)

    def _movej_p(self, *j):
        self._movej(self._posj(*j), radius=0.0, ra=self._RA_DUP)

    def _movel_p(self, *x, radius: float = 0.0):
        self._movel(self._posx(*x), radius=radius, ref=0, mod=self._MOD_ABS, ra=self._RA_DUP)

    def _do(self, index: int, val: int, retries: int = 2):
        """set_digital_output 은 서비스 호출 실패 시 -1 을 반환하는데, 지금까지 그 반환값을
        아무데서도 확인하지 않아 실패해도 조용히 넘어가고 팔은 계획대로 계속 움직였다
        (그리퍼만 무반응인 채로 grab 이 끝까지 진행되는 사고의 원인). 여기서 반환값을 확인해
        실패 시 경고를 찍고 짧게 재시도한다."""
        for attempt in range(1 + retries):
            ret = self._set_digital_output(index, val)
            if ret is None or ret == 0:
                return
            if attempt < retries:
                print(f"[경고] set_digital_output(index={index}, val={val}) 실패(ret={ret})"
                      f" — 재시도 {attempt + 1}/{retries}")
                self._wait(0.1)
            else:
                print(f"[경고] set_digital_output(index={index}, val={val}) 실패(ret={ret})"
                      f" — 재시도 소진, 그리퍼가 이 신호를 못 받았을 수 있음")

    # ── m0609_grab.drl 의 grasp/release (핀 1/2 조합) ──
    def _grab_grasp(self):
        # 신호 전환 순서 주의: 파지 직전 상태는 _grab_release() 라 DO1=1(96mm 열림)이다.
        # 여기서 DO2 를 먼저 켜면 순간적으로 DO1=1·DO2=1(=WebLogic rule#4=1100=5mm)이 잡혀
        # 그리퍼가 5mm 로 갔다가 다시 닫히는 '천천히 닫힘/다른 동작'이 간헐적으로 발생한다.
        # → 충돌 신호(DO1/3/4)를 먼저 0 으로 내리고 마지막에 DO2 만 1 로 올려 0mm 파지 룰만
        #    깔끔히 트리거한다(_pen_grasp 과 동일한 순서).
        self._do(1, 0)
        self._do(3, 0)
        self._do(4, 0)
        self._do(2, 1)
        self._wait(2.5)  # RG2 가 96mm→0mm 완전히 닫혀 아크릴을 물 때까지(들어올리기 전) 넉넉히.
                         # 1.5→2.5: 그리퍼가 가끔 느리게 닫혀 들어올리기 전에 다 안 물린 채로
                         # 넘어가는 경우가 있어 1초 더 여유를 줌.

    def _grab_release(self):
        self._do(1, 1)
        self._do(2, 0)
        self._do(3, 0)
        self._do(4, 0)
        self._wait(1.0)

    def _grab_release_5mm(self):
        # grab 마지막 '놓기' 전용 — 폭 ~5mm 로 놓는다.
        # [2026-07-27] DO4·DO5 신호선은 그리퍼에 미배선(1~3번만 동작)이라 단일 채널로는 못 씀.
        # 대신 WebLogic 에 rule #4 를 입력조합 IN1=1 AND IN2=1(1 1 0 0…) → Width 5mm 로 등록하고,
        # 여기서 DO1·DO2 를 동시에 1로 켜서 그 룰을 트리거한다(작동하는 라인만 조합 → 배선 불필요).
        # ※ 실제 폭 5mm 는 WebLogic rule #4 의 Width 값으로 결정됨(코드가 아니라).
        self._do(1, 1)
        self._do(2, 1)
        self._do(3, 0)
        self._do(4, 0)
        self._do(5, 0)
        # 내부 대기 없음 — 놓은 후 대기는 grab_motion 에서 명시적으로 준다(정확한 시간 제어).

    # ── m0609_pen_down/pen_up/brush.drl 공용 grasp/release (핀 2/3 조합) ──
    def _pen_grasp(self):
        self._do(4, 0)
        self._do(1, 0)
        self._do(3, 0)
        self._do(2, 1)

    def _pen_release(self):
        self._do(3, 1)
        self._do(2, 0)
        self._do(4, 0)
        self._do(1, 0)

    def _verify_pen_grasped_or_recover(self, ready_pose: tuple, item: str = "펜"):
        """_pen_grasp() 직후 호출. 그리퍼가 대상(펜/브러쉬 약 2.5cm)만큼 안 벌어지고 거의
        완전히 오므라들었으면(Modbus 폭이 임계 미만) 못 집은 것으로 보고, 그리퍼를 열고
        ready_pose 로 복귀한 뒤 PenGraspError 를 던진다. 호출부(오케스트레이터/GUI)가 이걸
        잡아 사용자에게 재시작 여부를 물으면 된다.
        Modbus 로 판단이 안 될 때(None, 네트워크/장비 문제)는 그리퍼 이상만으로 매번
        멈추면 더 나쁠 수 있어 경고만 찍고 그냥 진행한다."""
        if not self._verify_pen_grasp:
            return
        # [진단] 대상을 잡은 이 순간의 후보 레지스터 값을 전부 로그로 남긴다 — 어느
        # 레지스터가 '실제 폭(대상 25mm)'을 보여주는지 확정하는 용도. pen/brush 구분해서 찍음.
        dump = gripper_modbus.read_registers(gripper_modbus.CANDIDATE_REGISTERS)
        print(f"[진단:{item}] 잡은 순간 그리퍼 레지스터: {dump}")
        if gripper_modbus.DIAGNOSTIC_LOG_ONLY:
            print("[진단] DIAGNOSTIC_LOG_ONLY=True — 실패 판정 안 하고 그대로 진행합니다.")
            return
        grasped = gripper_modbus.pen_is_grasped()
        if grasped is None:
            print("[경고] 그리퍼 폭 확인 실패(Modbus 응답 없음) — 판단 못 하고 계속 진행")
            return
        if grasped:
            return
        print(f"[에러] {item}을(를) 못 집은 것으로 판단됨(그리퍼가 거의 완전히 오므라듦) — "
              "그리퍼를 열고 준비자세로 복귀합니다.")
        self._pen_release()
        self._wait(1.0)
        self._movej_p(*ready_pose)
        raise PenGraspError(
            f"{item}을(를) 집지 못했습니다. 제자리에 있는지 확인하고 재시작하세요.")

    # ── m0609_grab.drl ──
    def grab_motion(self, skip_ready: bool = False):
        # skip_ready=True: brush 바로 다음에 이어서 실행할 때만 사용. brush 가 정확히
        # 같은 자세(0,0,90,0,90,0)로 끝나서, 여기서 다시 movej 하면 완전한 중복(제자리
        # movej)이 되어 시간만 버림. grab 을 단독 테스트할 땐 반드시 False(기본값)로
        # 둬서 현재 자세가 뭐든 안전하게 준비자세로 이동하게 한다.
        self._apply_common_profile()
        # 첫 파지 전(접근/정렬) 구간은 기본 속도의 절반으로 — 아크릴판을 정확히 잡아야
        # 하는 구간이라 신중하게. 파지 후(전달 구간)는 아래에서 다시 1.0(기본 속도)로 복귀.
        self._set_speed(0.5)
        if not skip_ready:
            self._movej_p(0.00, 0.00, 90.00, 0.00, 90.00, 0.00)
        self._grab_release()
        # 접근/정렬 구간도 블렌드(5mm, 최소 점간거리 ~12.7mm의 절반 미만이라 안전)로 부드럽게.
        # 마지막 점(294.39...)은 파지 직전이라 정확히 멈춰야 해서 radius=0 유지.
        R_APPROACH = 5.0
        self._movel_p(521.16, -8.38, 37.96, 7.12, -174.30, 13.33, radius=R_APPROACH)
        self._movel_p(394.49, 2.39, 1.79, 175.35, 132.77, -177.32, radius=R_APPROACH)
        self._movel_p(351.15, 7.85, -10.35, 174.81, 127.97, -177.80, radius=R_APPROACH)
        self._movel_p(343.48, 3.72, -19.75, 178.70, 131.96, -175.11, radius=R_APPROACH)
        self._movel_p(335.61, 3.82, 11.51, 178.71, 128.96, -175.13, radius=R_APPROACH)
        self._movel_p(318.32, 3.65, 58.39, 178.80, 123.53, -175.09, radius=R_APPROACH)
        self._movel_p(272.53, 4.42, 131.73, 179.02, 127.59, -174.99, radius=R_APPROACH)
        self._movel_p(294.39, -2.28, 96.20, 7.13, -143.17, 6.02)
        self._grab_grasp()
        # 파지 후(전달 구간) 속도가 너무 빠르다는 피드백 → 기본 속도의 절반으로.
        self._set_speed(0.5)
        # blend radius(15mm)로 점마다 완전정지 없이 부드럽게 이어지도록. 마지막 점(718.34...)
        # 은 곧바로 wait+release 가 이어지니 정확히 멈춰야 해서 radius=0 유지.
        R = 15.0
        self._movel_p(330.53, -3.72, 183.46, 2.86, -152.23, 8.86, radius=R)
        self._movel_p(450.53, -7.25, 251.06, 85.55, -178.70, 92.04, radius=R)
        self._movel_p(671.79, -9.29, 289.04, 176.94, -149.03, -177.02, radius=R)
        self._movel_p(646.01, -5.50, 317.03, 178.27, -128.91, -176.37, radius=R)
        self._movel_p(718.34, -23.29, 253.96, 177.99, -100.50, -175.89)
        self._wait(1.0)   # 놓기 전 대기 1초(그 자리에 멈춰 대기)
        self._grab_release_5mm()   # 마지막 놓기: 폭 ~5mm(DO1+DO2=1100 조합, WebLogic rule #4)로 놓음
        self._wait(5.0)   # 놓은 후 자세 유지하며 대기 5초(그 자리에 멈춰 대기)
        self._movej_p(0.00, 0.00, 90.00, 0.00, 90.00, 0.00)

    # ── m0609_pen_down.drl ──
    def pen_down_motion(self):
        self._apply_common_profile()
        self._movej_p(-0.02, -0.05, 90.15, 0.01, 89.22, 0.04)
        # 점간 거리 100mm 이상이라 20mm 블렌드는 안전(절반 미만). release/grasp 직전 점은
        # 정확히 멈춰야 하므로 radius=0 유지.
        self._movel_p(313.84, -283.52, 172.12, 89.87, -136.08, 91.85, radius=20.0)
        self._movel_p(313.84, -283.52, 72.12, 89.87, -136.08, 91.85)
        self._pen_release()
        self._wait(1.0)  # 원본 DRL엔 없음: release 직후 바로 movel 이 시작돼 그리퍼가
                          # 물리적으로 열리기 전에 팔이 먼저 움직이는 문제 방지(좌표는 그대로)
        self._movel_p(313.84, -283.52, 172.12, 89.87, -136.08, 91.85, radius=20.0)
        self._movel_p(314.19, -105.41, 256.82, 89.55, -136.00, 91.49)
        self._movej_p(-0.02, -0.05, 90.15, 0.01, 89.22, 0.04)

    # ── m0609_pen_up.drl ──
    def pen_up_motion(self):
        self._apply_common_profile()
        self._movej_p(-0.02, -0.05, 90.15, 0.01, 89.22, 0.04)
        self._pen_release()
        self._movel_p(313.84, -283.52, 72.12, 89.87, -136.08, 91.85)
        self._wait(1.0)  # 집기 전 자세 안정 대기 2→1초로 단축
        self._pen_grasp()
        self._wait(1.0)  # 원본 DRL엔 없음: grasp 직후 바로 movel 이 시작돼 그리퍼가
                          # 물리적으로 닫히기 전에 팔이 먼저 올라가는 문제 방지(좌표는 그대로)
        self._verify_pen_grasped_or_recover((-0.02, -0.05, 90.15, 0.01, 89.22, 0.04))
        self._movel_p(313.84, -283.52, 172.12, 89.87, -136.08, 91.85, radius=20.0)
        self._movel_p(314.19, -105.41, 256.82, 89.55, -136.00, 91.49)
        self._movej_p(-0.02, -0.05, 90.15, 0.01, 89.22, 0.04)

    # ── m0609_brush.drl ──
    def brush_motion(self):
        self._apply_common_profile()
        self._movej_p(0.00, 0.00, 90.00, 0.00, 90.00, 0.00)
        self._pen_release()
        # 첫 점은 grasp 직전이라 정확히 멈춰야 함(radius=0). 나머지는 실측 최소 점간거리
        # (~41mm, 중복점 제외)의 절반 미만인 15mm 블렌드로 부드럽게 이어붙임.
        self._movel_p(381.13, -246.91, 54.29, 85.11, -177.96, 85.92)
        self._pen_grasp()
        self._wait(1.0)  # pen_up 과 동일: grasp 직후 바로 움직이면 그리퍼가 물리적으로
                          # 닫히기 전에 팔이 먼저 움직여 붓을 놓칠 수 있어 대기(좌표는 그대로)
        self._verify_pen_grasped_or_recover((0.00, 0.00, 90.00, 0.00, 90.00, 0.00), item="브러쉬")
        R = 15.0
        self._movel_p(381.50, -239.95, 240.43, 88.49, -178.01, 89.36, radius=R)
        self._movel_p(296.13, -45.54, 231.87, 93.85, -178.08, 94.60, radius=R)
        self._movel_p(305.88, 2.12, 63.44, 69.12, -177.93, 69.21, radius=R)
        self._movel_p(302.40, 210.02, 57.27, 69.35, -177.91, 69.32, radius=R)
        self._movel_p(302.40, 210.02, 110.27, 69.35, -177.91, 69.32, radius=R)
        self._movel_p(343.33, 5.28, 102.02, 90.94, -176.85, 91.15, radius=R)
        self._movel_p(342.37, 11.00, 57.46, 85.94, -176.72, 86.38, radius=R)
        self._movel_p(341.66, 205.55, 45.42, 87.89, -176.72, 88.20, radius=R)
        self._movel_p(341.66, 205.55, 145.42, 87.89, -176.72, 88.20, radius=R)
        self._movel_p(390.06, 15.52, 92.44, 88.90, -176.62, 89.22, radius=R)
        self._movel_p(388.46, 14.55, 51.10, 86.98, -176.65, 87.15, radius=R)
        # [2026-07-27] 원본 DRL에 위쪽 점(390.19,214.41,132.73)이 두 번 중복돼 있어(거리 0)
        # 블렌드를 못 걸고 radius=0(완전정지)+거리0 이동을 하느라 3번째 브러시만 멈칫했다.
        # → 중복 한 줄 제거하고 다른 브러시처럼 블렌드(radius=R)로 통일해 부드럽게 넘어가게 함.
        self._movel_p(390.19, 214.41, 32.73, 87.52, -176.78, 87.47, radius=R)
        self._movel_p(390.19, 214.41, 132.73, 87.52, -176.78, 87.47, radius=R)
        self._movel_p(421.21, 33.31, 85.66, 93.36, -176.62, 93.75, radius=R)
        self._movel_p(420.66, 32.68, 35.98, 91.43, -176.70, 91.69, radius=R)
        self._movel_p(392.53, 210.21, 47.15, 94.72, -176.64, 94.04, radius=R)
        self._movel_p(392.53, 210.21, 147.15, 94.72, -176.64, 94.04, radius=R)
        self._movel_p(370.14, -79.80, 189.18, 94.35, -176.24, 94.14, radius=R)
        self._movel_p(383.59, -206.24, 123.45, 95.07, -175.83, 96.43, radius=R)
        # 마지막 점은 release 직전이라 정확히 멈춰야 함(radius=0).
        self._movel_p(382.07, -245.18, 56.32, 90.01, -175.57, 91.51)
        self._pen_release()
        self._wait(1.0)  # grab 의 release 와 동일: 그리퍼가 물리적으로 다 열리기 전에
                          # 팔이 먼저 움직여 붓을 놓치는 문제 방지(좌표는 그대로)
        self._movej_p(0.00, 0.00, 90.00, 0.00, 90.00, 0.00)


MOTIONS = {
    'grab': DrlMotions.grab_motion,
    'pen_down': DrlMotions.pen_down_motion,
    'pen_up': DrlMotions.pen_up_motion,
    'brush': DrlMotions.brush_motion,
}
