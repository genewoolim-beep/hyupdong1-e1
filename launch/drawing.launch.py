"""svg_drawing 서비스 서버 실행 launch.

사용:
    ros2 launch svg_drawing drawing.launch.py
    ros2 launch svg_drawing drawing.launch.py dry_run:=true       # 로봇 미동작(경로만)
    ros2 launch svg_drawing drawing.launch.py config:=/path/to/params.yaml

호출:
    ros2 service call /svg_drawing/draw_svg svg_drawing_interfaces/srv/DrawSvg \
        "{svg_path: '/absolute/path/mandala.svg'}"

주의) 실제 로봇 제어는 Doosan bringup(dsr_bringup2 등)이 먼저 실행되어
      /dsr01/... 서비스가 떠 있어야 동작합니다.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('svg_drawing')
    default_config = os.path.join(pkg_share, 'config', 'drawing_params.yaml')

    config_arg = DeclareLaunchArgument(
        'config', default_value=default_config,
        description='드로잉 파라미터 YAML 경로')
    dry_run_arg = DeclareLaunchArgument(
        'dry_run', default_value='false',
        description='true면 로봇을 움직이지 않고 경로만 계산/로그')
    robot_id_arg = DeclareLaunchArgument(
        'robot_id', default_value='dsr01', description='Doosan 로봇 네임스페이스/ID')

    drawing_server = Node(
        package='svg_drawing',
        executable='drawing_server',
        name='svg_drawing_server',
        namespace=LaunchConfiguration('robot_id'),
        output='screen',
        parameters=[
            LaunchConfiguration('config'),
            {'dry_run': LaunchConfiguration('dry_run'),
             'robot_id': LaunchConfiguration('robot_id')},
        ],
    )

    return LaunchDescription([
        config_arg, dry_run_arg, robot_id_arg, drawing_server,
    ])
