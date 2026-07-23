"""drawing_server.py

ROS2 서비스 서버 노드. SVG 파일 경로를 받아 전체 파이프라인을 실행한다.

파이프라인:
    Service 호출(DrawSvg)
      → SVG 로드/파싱(svg_parser)
      → 곡선 샘플링(bezier_sampler, 실측 0.5mm 간격)
      → 작업영역 스케일링/정렬(coordinate_mapper, A5·비율유지·중앙정렬)
      → 경로 최적화(trajectory_planner, Nearest-Neighbor)
      → 로봇 모션 생성/실행(robot_controller, Doosan API)
      → 성공 여부/메시지 반환

Doosan API(DSR_ROBOT2)의 모션 함수는 내부에서 rclpy.spin_until_future_complete(g_node)
로 g_node(=DR_init.__dsr__node)를 직접 spin 한다. 만약 이 g_node 를 '서비스 서버 노드'와
동일하게 두면, 이미 실행기(executor)에 물린 노드를 또 spin 하려다 충돌/행이 난다.
→ 해결: DR_init 용 노드(dsr_node)를 서비스 노드와 분리한다. dsr_node 는 어떤 executor 에도
   추가하지 않고, DSR 이 필요할 때만 전역 executor 로 on-demand spin 하게 둔다.
→ 또한 동시에 두 번 그리면 로봇/‪dsr_node‬가 충돌하므로 Lock 으로 직렬화한다.

서비스:
    /<robot_id>/draw_svg   (svg_drawing_interfaces/srv/DrawSvg)
호출 예:
    ros2 service call /dsr01/draw_svg svg_drawing_interfaces/srv/DrawSvg \
        "{svg_path: '/absolute/path/mandala.svg'}"
"""

from __future__ import annotations

import os
import threading
import traceback

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

import DR_init

from svg_drawing_interfaces.srv import DrawSvg, TouchOff

from svg_drawing.svg_parser import SvgParser
from svg_drawing.bezier_sampler import sample_paths
from svg_drawing.coordinate_mapper import CoordinateMapper, WorkArea
from svg_drawing.trajectory_planner import optimize, travel_distance
from svg_drawing.robot_controller import RobotConfig, RobotController


class DrawingServer(Node):
    def __init__(self):
        super().__init__('svg_drawing_server')

        # ── 파라미터 선언(기본값 = config/drawing_params.yaml 과 일치) ──
        self._declare_params()

        self.robot_id = self.get_parameter('robot_id').value
        self.robot_model = self.get_parameter('robot_model').value

        # 파이프라인 구성요소
        self.parser = SvgParser()
        self.robot = RobotController(self._build_robot_config(), logger=self.get_logger())

        # 동시에 두 번 그리지 않도록 직렬화(로봇/dsr_node 충돌 방지)
        self._draw_lock = threading.Lock()

        # 서비스: 로봇 모션이 블로킹이므로 Reentrant 그룹으로 등록
        self.cb_group = ReentrantCallbackGroup()
        self.srv = self.create_service(
            DrawSvg, 'draw_svg', self.on_draw_request, callback_group=self.cb_group)
        # 터치오프 서비스(표면 Z 측정 → draw_height 자동 갱신)
        self.touch_srv = self.create_service(
            TouchOff, 'touch_off', self.on_touch_request, callback_group=self.cb_group)

        self.get_logger().info(
            f"SVG 드로잉 서버 준비 완료. 서비스: /{self.robot_id}/draw_svg, "
            f"/{self.robot_id}/touch_off "
            f"(dry_run={self.get_parameter('dry_run').value}, "
            f"force_control={self.get_parameter('use_force_control').value})")

    # ── 파라미터 ────────────────────────────────────────────
    def _declare_params(self):
        defaults = {
            'robot_id': 'dsr01',
            'robot_model': 'm0609',
            'work_area_width_mm': 148.0,
            'work_area_height_mm': 210.0,
            'work_area_margin_mm': 5.0,
            'center_drawing': True,
            'sample_resolution_mm': 0.5,
            'draw_height_mm': 5.0,
            'travel_height_mm': 25.0,
            'approach_height_mm': 10.0,
            'paper_origin_x_mm': 350.0,
            'paper_origin_y_mm': -100.0,
            'paper_x_sign': 1.0,
            'paper_y_sign': 1.0,
            'tool_rx_deg': 180.0,
            'tool_ry_deg': 0.0,
            'tool_rz_deg': 0.0,
            'draw_vel_mm_s': 40.0,
            'draw_acc_mm_s2': 200.0,
            'travel_vel_mm_s': 150.0,
            'travel_acc_mm_s2': 600.0,
            'move_rot_vel_deg_s': 60.0,
            'move_rot_acc_deg_s2': 180.0,
            'stroke_mode': 'movel',
            'movesx_chunk': 50,
            'draw_blend_radius_mm': 0.0,
            'ready_joints_deg': [0.0, 0.0, 90.0, 0.0, 90.0, 0.0],
            # ── Z축 힘 제어 ──
            'use_force_control': False,
            'draw_force_n': 5.0,
            'compliance_stiffness': [3000.0, 3000.0, 200.0, 200.0, 200.0, 200.0],
            'force_z_sign': -1.0,
            # ── 터치오프 ──
            'probe_start_offset_mm': 30.0,
            'probe_force_n': 5.0,
            'probe_contact_force_n': 3.0,
            'probe_max_travel_mm': 80.0,
            'probe_timeout_s': 20.0,
            'probe_vel_mm_s': 10.0,
            'probe_min_descent_mm': 2.0,
            'dry_run': False,
        }
        for k, v in defaults.items():
            self.declare_parameter(k, v)

    def _p(self, name):
        return self.get_parameter(name).value

    def _build_robot_config(self) -> RobotConfig:
        return RobotConfig(
            paper_origin_x_mm=float(self._p('paper_origin_x_mm')),
            paper_origin_y_mm=float(self._p('paper_origin_y_mm')),
            paper_x_sign=float(self._p('paper_x_sign')),
            paper_y_sign=float(self._p('paper_y_sign')),
            draw_height_mm=float(self._p('draw_height_mm')),
            travel_height_mm=float(self._p('travel_height_mm')),
            approach_height_mm=float(self._p('approach_height_mm')),
            tool_rx_deg=float(self._p('tool_rx_deg')),
            tool_ry_deg=float(self._p('tool_ry_deg')),
            tool_rz_deg=float(self._p('tool_rz_deg')),
            draw_vel_mm_s=float(self._p('draw_vel_mm_s')),
            draw_acc_mm_s2=float(self._p('draw_acc_mm_s2')),
            travel_vel_mm_s=float(self._p('travel_vel_mm_s')),
            travel_acc_mm_s2=float(self._p('travel_acc_mm_s2')),
            move_rot_vel_deg_s=float(self._p('move_rot_vel_deg_s')),
            move_rot_acc_deg_s2=float(self._p('move_rot_acc_deg_s2')),
            stroke_mode=str(self._p('stroke_mode')),
            movesx_chunk=int(self._p('movesx_chunk')),
            draw_blend_radius_mm=float(self._p('draw_blend_radius_mm')),
            ready_joints_deg=[float(v) for v in self._p('ready_joints_deg')],
            use_force_control=bool(self._p('use_force_control')),
            draw_force_n=float(self._p('draw_force_n')),
            compliance_stiffness=[float(v) for v in self._p('compliance_stiffness')],
            force_z_sign=float(self._p('force_z_sign')),
            probe_start_offset_mm=float(self._p('probe_start_offset_mm')),
            probe_force_n=float(self._p('probe_force_n')),
            probe_contact_force_n=float(self._p('probe_contact_force_n')),
            probe_max_travel_mm=float(self._p('probe_max_travel_mm')),
            probe_timeout_s=float(self._p('probe_timeout_s')),
            probe_vel_mm_s=float(self._p('probe_vel_mm_s')),
            probe_min_descent_mm=float(self._p('probe_min_descent_mm')),
            dry_run=bool(self._p('dry_run')),
        )

    def _build_work_area(self) -> WorkArea:
        return WorkArea(
            width_mm=float(self._p('work_area_width_mm')),
            height_mm=float(self._p('work_area_height_mm')),
            margin_mm=float(self._p('work_area_margin_mm')),
            center=bool(self._p('center_drawing')),
        )

    # ── 서비스 콜백 : 전체 파이프라인 ───────────────────────
    def on_draw_request(self, request: DrawSvg.Request, response: DrawSvg.Response):
        svg_path = request.svg_path
        log = self.get_logger()
        log.info(f"[draw_svg] 요청 수신: {svg_path}")

        # 이미 그리는 중이면 즉시 거절(로봇/dsr_node 동시 사용 방지)
        if not self._draw_lock.acquire(blocking=False):
            response.success = False
            response.message = "실패: 이미 다른 드로잉이 진행 중입니다."
            log.warn(response.message)
            return response

        try:
            if not svg_path or not os.path.isfile(svg_path):
                raise FileNotFoundError(f"SVG 파일을 찾을 수 없습니다: {svg_path}")

            # 1) 파싱
            parsed = self.parser.parse(svg_path)
            if not parsed.strokes:
                raise ValueError("SVG 에서 그릴 경로(path/도형)를 찾지 못했습니다.")
            log.info(f"[1/5] 파싱: 획 {len(parsed.strokes)}개, "
                     f"viewBox {parsed.viewbox.width:.1f}x{parsed.viewbox.height:.1f}")

            # 2) 좌표 매퍼(스케일) 먼저 만들어 실측 0.5mm → SVG단위 샘플 간격 계산
            mapper = CoordinateMapper(parsed.viewbox, self._build_work_area())
            res_mm = float(self._p('sample_resolution_mm'))
            max_seg_len_svg = res_mm / mapper.scale if mapper.scale > 0 else res_mm
            log.info(f"[2/5] 매핑 준비: {mapper.describe()}")

            # 3) 곡선 샘플링(SVG 좌표계) → 4) 용지 mm 로 변환
            svg_polys = sample_paths(parsed.strokes, max_seg_len_svg)
            paper_polys = mapper.map_strokes(svg_polys)
            log.info(f"[3/5] 샘플링: 폴리라인 {len(paper_polys)}개 "
                     f"(간격 {res_mm}mm ≈ {max_seg_len_svg:.3f} SVG unit)")

            # 5) 경로 최적화(Nearest-Neighbor)
            before = travel_distance(paper_polys)
            ordered = optimize(paper_polys, start=(0.0, 0.0))
            after = travel_distance(ordered)
            log.info(f"[4/5] 경로 최적화: 공중 이동 {before:.0f} → {after:.0f} mm")

            # 6) 로봇 실행 (설정 재적용: 파라미터가 런타임에 바뀌었을 수 있음)
            self.robot.cfg = self._build_robot_config()
            self.robot._connected = False           # 설정 갱신 반영 위해 재연결
            stats = self.robot.execute(ordered)
            log.info(f"[5/5] 실행 완료: 획 {stats.strokes}, 점 {stats.points}, "
                     f"긋기 {stats.draw_len_mm:.0f}mm")

            response.success = True
            response.message = (
                f"완료: 획 {stats.strokes}개, 점 {stats.points}개, "
                f"긋는 길이 {stats.draw_len_mm:.0f}mm, 공중 이동 {after:.0f}mm"
                + (" (dry_run)" if self._p('dry_run') else "")
            )
            log.info(response.message)

        except Exception as e:
            response.success = False
            response.message = f"실패: {e}"
            log.error(response.message)
            log.debug(traceback.format_exc())
        finally:
            self._draw_lock.release()

        return response

    # ── 터치오프 서비스 : 표면 Z 측정 → draw_height 자동 갱신 ─────────
    def on_touch_request(self, request: TouchOff.Request, response: TouchOff.Response):
        log = self.get_logger()
        log.info(f"[touch_off] 요청: 용지({request.x_mm:.1f},{request.y_mm:.1f})")

        # 드로잉과 로봇/‪dsr_node‬를 공유하므로 동시에 못 쓴다 → 같은 락으로 직렬화
        if not self._draw_lock.acquire(blocking=False):
            response.success = False
            response.surface_z_mm = 0.0
            response.message = "실패: 다른 작업(드로잉/터치오프)이 진행 중입니다."
            log.warn(response.message)
            return response
        try:
            # 최신 파라미터 반영해 재설정
            self.robot.cfg = self._build_robot_config()
            self.robot._connected = False
            surface_z = self.robot.touch_off(float(request.x_mm), float(request.y_mm))

            if surface_z is None:
                response.success = False
                response.surface_z_mm = 0.0
                response.message = ("표면 접촉 감지 실패(안전 중단). probe_start_offset/힘/"
                                    "부호(force_z_sign) 설정을 확인하세요. "
                                    "시뮬(에뮬레이터)은 접촉 물리가 없어 항상 실패합니다.")
                log.warn(response.message)
            else:
                # 측정값으로 draw_height_mm 파라미터 갱신 → 이후 드로잉에 반영
                self.set_parameters([Parameter(
                    'draw_height_mm', Parameter.Type.DOUBLE, float(surface_z))])
                response.success = True
                response.surface_z_mm = float(surface_z)
                response.message = (f"표면 Z = {surface_z:.2f} mm 측정 완료. "
                                    f"draw_height_mm 를 이 값으로 갱신했습니다.")
                log.info(response.message)
        except Exception as e:
            response.success = False
            response.surface_z_mm = 0.0
            response.message = f"실패: {e}"
            log.error(response.message)
            log.debug(traceback.format_exc())
        finally:
            self._draw_lock.release()
        return response


def main(args=None):
    rclpy.init(args=args)

    # 1) 서비스 서버 노드(파라미터/서비스 담당) — executor 로 spin 한다.
    node = DrawingServer()

    # 2) DR_init 전용 노드(dsr_node) — DSR 이 내부에서 직접 spin 하므로
    #    executor 에는 절대 추가하지 않는다(그래야 충돌이 없다).
    dsr_node = rclpy.create_node('svg_drawing_dsr', namespace=node.robot_id)
    DR_init.__dsr__id = node.robot_id
    DR_init.__dsr__model = node.robot_model
    DR_init.__dsr__node = dsr_node

    executor = MultiThreadedExecutor()
    executor.add_node(node)          # dsr_node 는 추가하지 않음(중요)
    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info("종료 요청(Ctrl+C)")
    finally:
        for n in (node, dsr_node):
            try:
                n.destroy_node()
            except Exception:
                pass
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
