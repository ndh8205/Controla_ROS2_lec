# orbit_sim — ROS2 우주 시뮬레이션 실습 패키지

ROS 2 Jazzy + Gazebo Harmonic 기반 궤도 시뮬레이션 실습 패키지.
연구실 세미나(4교시) 실습용으로, 다중 위성 궤도 시뮬레이션과 GCO 근접운전을 다룹니다.

**환경:** WSL2 Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic (DART), NVIDIA GPU (D3D12)

---

## 세미나 구성

| 교시 | 주제 | 핵심 내용 |
|------|------|----------|
| **준비** | 환경 이해 | WSL2, 터미널, source/export, colcon build |
| **1교시** | ROS2 기초 | Node, Topic, Pub/Sub, CLI 명령어, Launch 파일 |
| **2교시** | Gazebo 우주 환경 | SDF, World/Model, ros_gz_bridge, 패키지 구조 |
| **3교시** | 궤도 시뮬레이션 | 궤도역학, CSV 궤적, multi_satellite_controller |
| **4교시** | GCO 근접운전 | CW 방정식, PID 제어, gco_controller, ros2 bag |

---

## 빠른 시작

### 1. 워크스페이스 구축

```bash
mkdir -p ~/space_ros_ws/src && cd ~/space_ros_ws/src
git clone https://github.com/ndh8205/Controla_ROS2_lec.git orbit_sim
cd ~/space_ros_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

### 2. 환경 변수 (~/.bashrc)

```bash
source ~/space_ros_ws/install/setup.bash
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/space_ros_ws/install/orbit_sim/share/orbit_sim/models
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:$GZ_SIM_SYSTEM_PLUGIN_PATH
```

WSL2 GPU 렌더링:
```bash
export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH
export MESA_D3D12_DEFAULT_ADAPTER_NAME="NVIDIA"
export GALLIUM_DRIVER=d3d12
```

---

## 실습 실행

### GCO 근접운전 (3~4교시)

```bash
# 시뮬레이션 실행
ros2 launch orbit_sim gco_test.launch.py

# 별도 터미널에서 데이터 확인
ros2 topic echo /model/nasa_satellite5/odometry
ros2 topic hz /model/nasa_satellite5/odometry
ros2 topic list
```

### 데이터 녹화 (ros2 bag)

```bash
ros2 bag record /model/nasa_satellite5/odometry /nasa_satellite5/imu
ros2 bag play <bag_directory>
```

### 노드 연결 확인

```bash
ros2 node list
ros2 topic info /model/nasa_satellite5/odometry
rqt_graph
```

---

## 패키지 구조

```
orbit_sim/
├── orbit_sim/                          # Python 노드
│   ├── multi_satellite_controller.py   #   다중 위성 CSV 궤적 제어
│   ├── gco_controller.py              #   GCO PID 상대궤도 제어
│   └── orbit_LVLH_gco.py             #   LVLH GCO 시뮬레이터
│
├── launch/
│   └── gco_test.launch.py            #   GCO 시뮬레이션 런치
│
├── worlds/                            # Gazebo World
│   ├── orbit.sdf                      #   기본 궤도 환경
│   ├── orbit_LVLH_GCO.world          #   LVLH GCO 물리엔진 설정
│   └── gco_test.world                 #   GCO 테스트 환경
│
├── models/                            # Gazebo 모델 (8개)
│   ├── nasa_satellite ~ nasa_satellite6/  # NASA 위성 시리즈
│   ├── intel_sat_dummy/               #   IntelSat 더미 위성
│   └── earth/                         #   지구
│
├── data/                              # 궤적 데이터
│   ├── sat1_state.csv                 #   위성 1 궤적
│   └── orbit_data_1hz.csv            #   궤도 데이터 (1Hz)
│
├── package.xml
├── setup.py
└── setup.cfg
```

---

## 주요 ROS 2 토픽

| 토픽 | 타입 | 용도 |
|------|------|------|
| `/model/<sat>/odometry` | `nav_msgs/Odometry` | 위성 위치/속도 |
| `/<sat>/imu` | `sensor_msgs/Imu` | IMU 데이터 |
| `/<sat>/camera` | `sensor_msgs/Image` | 카메라 영상 |
| `/model/<sat>/apply_world_wrench` | `gz.msgs.EntityWrench` | 제어 입력 (힘) |

---

## 의존성

### 시스템
- Ubuntu 24.04 (WSL2)
- ROS 2 Jazzy Desktop
- Gazebo Harmonic
- NVIDIA GPU + D3D12 렌더링

### ROS 패키지
```
ros-jazzy-ros-gz
```

### Python
```
numpy
```

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| GPU 소프트웨어 렌더링 | `GALLIUM_DRIVER=d3d12` 확인 |
| 모델 로딩 실패 | `GZ_SIM_RESOURCE_PATH` 확인 |
| `colcon build` 실패 | `source /opt/ros/jazzy/setup.bash` 후 재빌드 |
| 프로세스 정리 안 됨 | `pkill -f gz && pkill -f ros2` |

---

*ROS2 우주 시뮬레이션 세미나 실습용*
