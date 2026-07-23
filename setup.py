import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'svg_drawing'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # launch / config 파일 설치
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'svgelements', 'numpy'],
    zip_safe=True,
    maintainer='gene',
    maintainer_email='genewoolim@gmail.com',
    description='Doosan M0609 SVG scratch-drawing system (ROS2 Humble)',
    license='Apache-2.0',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            # ROS2 서비스 서버 노드
            'drawing_server = svg_drawing.drawing_server:main',
        ],
    },
)
