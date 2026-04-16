#!/usr/bin/env python3
"""Seminar Part 1 — intro launch.

하나의 명령으로 ROS 2 + Gazebo 체험을 위한 모든 것을 켭니다:

  - Gazebo Harmonic (gco_test.world)
  - 3D LiDAR 포인트클라우드 누적 맵 (RViz 에서 관찰)
  - 카메라 브리지 (/nasa_satellite3/camera, /nasa_satellite/camera)
  - web_video_server (브라우저에서 영상 확인, http://localhost:8080)
  - 멀티 위성 CSV 궤적 컨트롤러 (nasa_satellite3 LiDAR 탑재)
  - SetEntityPose 서비스 브리지
  - (옵션) RViz2 자동 실행

Usage:
    ros2 launch orbit_sim seminar_intro.launch.py           # RViz 안 켬
    ros2 launch orbit_sim seminar_intro.launch.py rviz:=true
"""

import os
from os import environ

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg = get_package_share_directory('orbit_sim')
    world_file = os.path.join(pkg, 'worlds', 'gco_test.world')
    model_path = os.path.join(pkg, 'models')
    csv_dir    = os.path.join(pkg, 'data')

    env = {
        'GZ_SIM_RESOURCE_PATH': ':'.join(filter(None, [
            environ.get('GZ_SIM_RESOURCE_PATH', ''),
            model_path,
        ])),
        'GZ_SIM_SYSTEM_PLUGIN_PATH': environ.get(
            'GZ_SIM_SYSTEM_PLUGIN_PATH', ''),
    }

    # --- Launch arguments -------------------------------------------------
    csv1 = DeclareLaunchArgument(
        'csv_file1', default_value=os.path.join(csv_dir, 'sat1_state.csv'))
    csv2 = DeclareLaunchArgument(
        'csv_file2', default_value=os.path.join(csv_dir, 'sat3_state.csv'))
    csv3 = DeclareLaunchArgument(
        'csv_file3', default_value=os.path.join(csv_dir, 'sat4_state.csv'))
    time_scale = DeclareLaunchArgument('time_scale', default_value='1.0')
    rviz_arg   = DeclareLaunchArgument('rviz',       default_value='false')

    # --- 1. Gazebo world --------------------------------------------------
    gz = ExecuteProcess(
        cmd=['gz', 'sim', world_file, '-r'],
        output='screen',
        additional_env=env,
    )

    # --- 2. LiDAR PointCloud2 bridge --------------------------------------
    lidar_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='lidar_bridge',
        arguments=[
            '/lidar/points_raw/points@sensor_msgs/msg/PointCloud2['
            'gz.msgs.PointCloudPacked',
        ],
        output='screen',
    )

    # --- 3. Camera bridges (전체 4 모델) ---------------------------------
    # gco_test.world 모델: nasa_satellite(1), 2, 3, 4
    camera_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='camera_bridge',
        arguments=[
            '/nasa_satellite/camera@sensor_msgs/msg/Image@gz.msgs.Image',
            '/nasa_satellite2/camera@sensor_msgs/msg/Image@gz.msgs.Image',
            '/nasa_satellite3/camera@sensor_msgs/msg/Image@gz.msgs.Image',
            '/stereo/left/image_raw@sensor_msgs/msg/Image@gz.msgs.Image',
            '/stereo/right/image_raw@sensor_msgs/msg/Image@gz.msgs.Image',
        ],
        output='screen',
    )

    # --- 4. IMU bridges (전체 4 모델) + LiDAR Odometry -------------------
    imu_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='imu_bridge',
        arguments=[
            '/nasa_satellite/imu@sensor_msgs/msg/Imu@gz.msgs.IMU',
            '/nasa_satellite2/imu@sensor_msgs/msg/Imu@gz.msgs.IMU',
            '/nasa_satellite3/imu@sensor_msgs/msg/Imu@gz.msgs.IMU',
            '/nasa_satellite4/imu@sensor_msgs/msg/Imu@gz.msgs.IMU',
        ],
        output='screen',
    )

    # --- 5. SetEntityPose service bridge ----------------------------------
    set_pose_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='set_pose_bridge',
        arguments=[
            '/world/space_world/set_pose@ros_gz_interfaces/srv/SetEntityPose',
        ],
        output='screen',
    )

    # --- 6. Web video server (http://localhost:8080) ----------------------
    web = Node(
        package='web_video_server',
        executable='web_video_server',
        name='web_video_server',
        output='screen',
    )

    # --- 6b. rosbridge (ws://localhost:9090) — 노트북 roslibpy 용 --------
    rosbridge = Node(
        package='rosbridge_server',
        executable='rosbridge_websocket',
        name='rosbridge_websocket',
        output='screen',
    )

    # --- 7. Multi-satellite CSV trajectory controller ---------------------
    # (Gazebo 시작 후 5s 지연)
    controller = Node(
        package='orbit_sim',
        executable='multi_satellite_controller_service',
        name='multi_satellite_controller_service',
        output='screen',
        parameters=[{
            'csv_file1':       LaunchConfiguration('csv_file1'),
            'csv_file2':       LaunchConfiguration('csv_file2'),
            'csv_file3':       LaunchConfiguration('csv_file3'),
            'update_rate':     50.0,
            'csv_data_rate':   50.0,
            'loop_data':       True,
            'time_scale':      LaunchConfiguration('time_scale'),
            'tf_entity':       'nasa_satellite3',
            'tf_lidar_frame':  'nasa_satellite3/nasa_satellite_link/lidar_3d',
        }],
    )
    delayed_controller = TimerAction(period=5.0, actions=[controller])

    # --- 8. PointCloud mapper (누적 맵 생성, 10s 지연) ---------------------
    pc_mapper = Node(
        package='orbit_sim',
        executable='pointcloud_mapper',
        name='pointcloud_mapper',
        parameters=[{
            'input_topic':  '/lidar/points_raw/points',
            'voxel_size':   0.05,
            'max_points':   500000,
            'publish_rate': 2.0,
        }],
        output='screen',
    )
    delayed_mapper = TimerAction(period=10.0,
                                 actions=[lidar_bridge, pc_mapper])

    # --- 9. RViz2 (옵션) --------------------------------------------------
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=[
            '-d',
            os.path.join(pkg, 'config', 'lidar_mapping.rviz'),
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    return LaunchDescription([
        csv1, csv2, csv3, time_scale, rviz_arg,
        gz,
        camera_bridge,
        imu_bridge,
        set_pose_bridge,
        web,
        rosbridge,
        delayed_controller,
        delayed_mapper,
        rviz,
    ])
