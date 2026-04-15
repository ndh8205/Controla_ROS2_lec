# WSL2 Ubuntu 24.04에서 ROS2 우주 시뮬레이션 구축 가이드

**환경:** Windows 10/11 (WSL2), Ubuntu 24.04
**목표:** ROS 2 Jazzy + Gazebo Harmonic 환경에서 인공위성 GCO 근접운전 시뮬레이션 구축
**대상:** 연구실 세미나 실습 (4교시)

---

## 목차
1. [WSL2 환경 설정](#1-wsl2-환경-설정)
2. [ROS 2 Jazzy 설치](#2-ros-2-jazzy-설치)
3. [Gazebo Harmonic 설치](#3-gazebo-harmonic-설치)
4. [GPU 렌더링 설정 (NVIDIA)](#4-gpu-렌더링-설정-nvidia)
5. [워크스페이스 구축 및 빌드](#5-워크스페이스-구축-및-빌드)
6. [환경 변수 설정](#6-환경-변수-설정)
7. [시뮬레이션 실행](#7-시뮬레이션-실행)
8. [트러블슈팅](#8-트러블슈팅)

---

## 1. WSL2 환경 설정

### 1.1 Ubuntu 24.04 설치

PowerShell (관리자):
```powershell
wsl --install -d Ubuntu-24.04
```

### 1.2 WSL2 자원 제한 (권장)

`C:\Users\<사용자명>\.wslconfig` 파일 생성:
```ini
[wsl2]
memory=8GB
processors=4
swap=2GB
```

변경 후 반영:
```cmd
wsl --shutdown
```

---

## 2. ROS 2 Jazzy 설치

### 2.1 Locale 설정
```bash
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```

### 2.2 ROS 2 저장소 추가
```bash
sudo apt install -y curl gnupg2 lsb-release
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

### 2.3 설치
```bash
sudo apt update
sudo apt install -y ros-jazzy-desktop python3-colcon-common-extensions python3-rosdep python3-vcstool
```

### 2.4 rosdep 초기화
```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
sudo rosdep init || true
rosdep update
```

### 2.5 설치 확인
```bash
printenv ROS_DISTRO   # "jazzy" 출력 확인
ros2 topic list
```

---

## 3. Gazebo Harmonic 설치

### 3.1 OSRF 저장소 추가
```bash
sudo apt install -y wget
sudo wget https://packages.osrfoundation.org/gazebo.gpg \
  -O /usr/share/keyrings/gazebo-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gazebo-archive-keyring.gpg] \
http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | \
sudo tee /etc/apt/sources.list.d/gazebo-stable.list

sudo apt update
```

### 3.2 설치
```bash
sudo apt install -y gz-harmonic ros-jazzy-ros-gz \
  ros-jazzy-image-transport ros-jazzy-web-video-server
```

### 3.3 확인
```bash
gz sim --version
```

---

## 4. GPU 렌더링 설정 (NVIDIA)

WSL2에서 NVIDIA GPU로 Gazebo를 렌더링하려면:

```bash
# ~/.bashrc에 추가
export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH
export MESA_D3D12_DEFAULT_ADAPTER_NAME="NVIDIA"
export GALLIUM_DRIVER=d3d12
```

```bash
source ~/.bashrc
```

GPU 사용자 그룹 추가 (재부팅 후 적용):
```bash
sudo usermod -aG render $USER
```

GPU 렌더링 확인:
```bash
glxinfo | grep "OpenGL renderer"
# NVIDIA GPU 모델이 출력되면 정상
```

> **참고:** WSLg가 기본 GUI를 지원하므로 VcXsrv는 보통 불필요합니다.
> GPU가 없거나 문제가 있으면 `export LIBGL_ALWAYS_SOFTWARE=1`로 소프트웨어 렌더링 사용.

---

## 5. 워크스페이스 구축 및 빌드

### 5.1 소스 클론

```bash
mkdir -p ~/space_ros_ws/src && cd ~/space_ros_ws/src
git clone https://github.com/ndh8205/Controla_ROS2_lec.git orbit_sim
```

### 5.2 의존성 설치 및 빌드

```bash
cd ~/space_ros_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

### 5.3 Zone.Identifier 제거 (Windows에서 복사한 경우)

Windows에서 WSL로 파일을 복사하면 `Zone.Identifier` 메타파일이 생길 수 있습니다:
```bash
find ~/space_ros_ws/src -name "*:Zone.Identifier*" -delete
```

---

## 6. 환경 변수 설정

`~/.bashrc`에 다음을 추가:

```bash
# ROS 2
source /opt/ros/jazzy/setup.bash
source ~/space_ros_ws/install/setup.bash

# Gazebo 모델 경로
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/space_ros_ws/install/orbit_sim/share/orbit_sim/models

# Gazebo 플러그인 경로
export GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ros/jazzy/lib:$GZ_SIM_SYSTEM_PLUGIN_PATH

# GPU 렌더링 (NVIDIA)
export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH
export MESA_D3D12_DEFAULT_ADAPTER_NAME="NVIDIA"
export GALLIUM_DRIVER=d3d12
```

```bash
source ~/.bashrc
```

---

## 7. 시뮬레이션 실행

### 7.1 GCO 근접운전 시뮬레이션

```bash
ros2 launch orbit_sim gco_test.launch.py
```

Gazebo Harmonic 창이 열리면서 위성 모델이 표시됩니다.

### 7.2 토픽 확인 (별도 터미널)

```bash
# 토픽 목록
ros2 topic list

# 위성 위치/속도 데이터
ros2 topic echo /model/nasa_satellite5/odometry

# 발행 빈도 확인
ros2 topic hz /model/nasa_satellite5/odometry

# IMU 데이터
ros2 topic echo /nasa_satellite5/imu

# 노드 목록
ros2 node list
```

### 7.3 카메라 영상 확인

launch 파일이 카메라 브리지와 web_video_server를 자동 실행합니다.

**방법 1: rqt_image_view (GUI)**
```bash
ros2 run rqt_image_view rqt_image_view
# 드롭다운에서 /nasa_satellite5/camera 선택
```

**방법 2: web_video_server (브라우저)**

launch 실행 시 web_video_server가 자동으로 포트 8080에서 시작됩니다.
브라우저에서 접속:
```
http://localhost:8080/stream?topic=/nasa_satellite5/camera
```

스트림 가능 토픽 목록 확인:
```
http://localhost:8080/
```

**방법 3: Gazebo GUI 내장 카메라 뷰**

Gazebo 창 상단 메뉴에서 카메라 센서 영상을 직접 확인할 수 있습니다:
1. Gazebo 우측 패널 > Plugins > Image Display
2. Topic에 `nasa_satellite5/camera` 입력

**카메라 브리지 토픽 목록:**
| 토픽 | 설명 |
|------|------|
| `/nasa_satellite5/camera` | Deputy 위성 카메라 |
| `/nasa_satellite5/imu` | Deputy IMU |
| `/mev/vss_nfov/left/image_raw` | NFOV 스테레오 좌 |
| `/mev/vss_nfov/right/image_raw` | NFOV 스테레오 우 |
| `/mev/vss_wfov/left/image_raw` | WFOV 스테레오 좌 |
| `/mev/vss_wfov/right/image_raw` | WFOV 스테레오 우 |
| `/mev/vss_docking/left/image_raw` | 도킹 카메라 좌 |
| `/mev/vss_docking/right/image_raw` | 도킹 카메라 우 |

### 7.4 노드 연결 시각화

```bash
rqt_graph
```

### 7.5 데이터 녹화/재생 (ros2 bag)

```bash
# 녹화
ros2 bag record /model/nasa_satellite5/odometry /nasa_satellite5/imu

# 재생
ros2 bag play <bag_directory>
```

### 7.6 프로세스 정리

```bash
pkill -f gz && pkill -f ros2
```

---

## 8. 트러블슈팅

| 증상 | 해결 |
|------|------|
| `gz sim --version` 실패 | `sudo apt install -y gz-harmonic` 재설치 |
| GPU 소프트웨어 렌더링 | `GALLIUM_DRIVER=d3d12` 확인, `sudo usermod -aG render $USER` 후 재부팅 |
| 모델 로딩 실패 | `echo $GZ_SIM_RESOURCE_PATH`로 경로 확인 |
| `colcon build` 실패 | `source /opt/ros/jazzy/setup.bash` 확인 후 재빌드 |
| 토픽이 안 보임 | `ros2 topic list`로 확인, bridge 노드 실행 여부 체크 |
| Gazebo 검은 화면 | GPU 드라이버 확인, `LIBGL_ALWAYS_SOFTWARE=1`로 임시 우회 |
| 빌드 후 노드 못 찾음 | `source ~/space_ros_ws/install/setup.bash` 재실행 |
| Zone.Identifier 오류 | `find . -name "*:Zone.Identifier*" -delete` |
| 카메라 토픽 안 보임 | `ros2 topic list \| grep camera`로 bridge 확인, Gazebo 센서 활성화 확인 |
| web_video_server 접속 안 됨 | `ros2 node list`에서 web_video_server 실행 확인, 포트 8080 충돌 체크 |
| rqt_image_view 검은 화면 | 토픽 선택 후 몇 초 대기, Gazebo가 먼저 실행 완료되었는지 확인 |

### 클린 빌드 (빌드 오류 시)
```bash
cd ~/space_ros_ws
rm -rf build/ install/ log/
colcon build --symlink-install
source install/setup.bash
```

---

## 패키지 구조

```
~/space_ros_ws/src/orbit_sim/
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
│   ├── orbit_LVLH_GCO.world          #   LVLH GCO 환경
│   └── gco_test.world                 #   GCO 테스트 환경
│
├── models/                            # Gazebo 모델
│   ├── nasa_satellite ~ nasa_satellite6/
│   ├── intel_sat_dummy/
│   └── earth/
│
├── data/                              # 궤적 데이터 (CSV)
│   ├── sat1_state.csv
│   └── orbit_data_1hz.csv
│
├── package.xml
├── setup.py
└── setup.cfg
```

---

## 참고 자료

- [ROS 2 Jazzy 공식 문서](https://docs.ros.org/en/jazzy/)
- [Gazebo Harmonic 공식 문서](https://gazebosim.org/docs/harmonic)
- [ros_gz 브리지 가이드](https://github.com/gazebosim/ros_gz)
- [WSL2 GPU 가속 설정](https://learn.microsoft.com/windows/wsl/tutorials/gpu-compute)
