# WSL2 Ubuntu 24.04에서 ROS2 우주 시뮬레이션 구축 가이드

**환경:** Windows 10/11 (WSL2), Ubuntu 24.04
**목표:** ROS 2 Jazzy + Gazebo Harmonic 환경에서 인공위성 GCO 근접운전 시뮬레이션 구축
**대상:** 연구실 세미나 실습 (4교시)

---

## 목차
1. [WSL2 환경 설정](#1-wsl2-환경-설정)
2. [Linux 터미널 기초](#2-linux-터미널-기초)
3. [ROS 2 Jazzy 설치](#3-ros-2-jazzy-설치)
4. [Gazebo Harmonic 설치](#4-gazebo-harmonic-설치)
5. [GPU 렌더링 설정 (NVIDIA)](#5-gpu-렌더링-설정-nvidia)
6. [워크스페이스 구축 및 빌드](#6-워크스페이스-구축-및-빌드)
7. [환경 변수 설정](#7-환경-변수-설정)
8. [시뮬레이션 실행](#8-시뮬레이션-실행)
9. [트러블슈팅](#9-트러블슈팅)

---

## 1. WSL2 환경 설정

### 1.1 Ubuntu 24.04 설치

CMD 또는 PowerShell (관리자):
```cmd
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

### 1.3 빠른 초기화 (문제 발생 시)

환경이 꼬였을 때 WSL을 완전히 초기화하고 재설치:
```cmd
wsl --terminate Ubuntu-24.04
wsl --unregister Ubuntu-24.04
wsl --install -d Ubuntu-24.04
```
> **주의:** `--unregister`는 해당 배포판의 모든 데이터를 삭제합니다. 필요한 파일은 먼저 백업하세요.

---

## 2. Linux 터미널 기초

WSL2 Ubuntu를 설치하면 Linux 터미널을 사용합니다. Windows 명령 프롬프트와 유사하지만 Linux 명령어를 사용합니다.

### 2.1 터미널 여는 법
- Windows 시작메뉴에서 "Ubuntu" 검색 → 클릭
- Windows Terminal 앱 → Ubuntu 탭
- ROS2 실습에서는 터미널 3~4개를 동시에 사용합니다

### 2.2 파일/폴더 명령어

현재 위치 확인:
```bash
pwd
```

폴더 생성:
```bash
mkdir my_folder
```

중간 경로까지 한번에 생성 (`-p`):
```bash
mkdir -p ~/space_ros_ws/src
```

파일/폴더 목록 보기 (만든 폴더 확인):
```bash
ls
```

폴더 이동:
```bash
cd ~/space_ros_ws
```

상위 폴더로 이동:
```bash
cd ..
```

홈 폴더로 이동:
```bash
cd ~
```

폴더 생성 + 이동 (한번에):
```bash
mkdir -p ~/space_ros_ws/src && cd ~/space_ros_ws/src
```

파일 내용 보기:
```bash
cat ~/.bashrc
```

파일 복사:
```bash
cp 원본 대상
```

파일/폴더 이름 변경 또는 이동:
```bash
mv 원본 대상
```

파일 삭제:
```bash
rm 파일명
```

폴더 삭제 (내부 포함):
```bash
rm -rf 폴더명
```

### 2.3 경로 표기

| 표기 | 의미 |
|------|------|
| `~` | 홈 폴더 (= `/home/사용자명/`) |
| `~/space_ros_ws` | 홈 안의 space_ros_ws 폴더 |
| `/opt/ros/jazzy/` | ROS2 설치 경로 |
| `./` | 현재 폴더 |
| `..` | 상위 폴더 |

### 2.4 source와 export

`source` = 설정 파일을 현재 터미널에 적용:
```bash
source /opt/ros/jazzy/setup.bash
```

`export` = 환경 변수 설정:
```bash
export ROS_DOMAIN_ID=42
```

설정한 변수 확인:
```bash
echo $ROS_DOMAIN_ID
```

> **주의:** 터미널을 닫으면 source/export 설정이 사라집니다.
> 매번 치기 귀찮으면 `~/.bashrc` 파일 끝에 추가하면 터미널 열 때 자동 실행됩니다.

### 2.5 자주 쓰는 단축키

| 단축키 | 기능 |
|--------|------|
| `Ctrl+C` | **실행 중인 프로그램 종료** (가장 중요!) |
| `Ctrl+L` | 화면 정리 (clear) |
| `Tab` | 명령어/경로 자동 완성 |
| `↑` / `↓` | 이전/다음 명령어 기록 |
| `Ctrl+R` | 명령어 기록 검색 |

### 2.6 패키지 설치 (apt)

Ubuntu에서 프로그램을 설치하는 명령어:
```bash
sudo apt update
```
```bash
sudo apt install -y 패키지이름
```

> `sudo` = 관리자 권한으로 실행 (비밀번호 물어봄)
> `-y` = 설치 확인 질문에 자동으로 "예"

---

## 3. ROS 2 Jazzy 설치

### 3.1 Locale 설정
```bash
sudo apt update && sudo apt install -y locales
```
```bash
sudo locale-gen en_US en_US.UTF-8
```
```bash
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
```
```bash
export LANG=en_US.UTF-8
```

### 3.2 ROS 2 저장소 추가
```bash
sudo apt install -y curl gnupg2 lsb-release
```
```bash
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
```
```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

### 3.3 설치
```bash
sudo apt update
```
```bash
sudo apt install -y ros-jazzy-desktop
```
```bash
sudo apt install -y python3-colcon-common-extensions
```
```bash
sudo apt install -y python3-rosdep
```
```bash
sudo apt install -y python3-vcstool
```

### 3.4 rosdep 초기화
```bash
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
```
```bash
source ~/.bashrc
```
```bash
sudo rosdep init || true
```
```bash
rosdep update
```

### 3.5 설치 확인
```bash
printenv ROS_DISTRO   # "jazzy" 출력 확인
ros2 topic list
```

---

## 4. Gazebo Harmonic 설치

### 4.1 OSRF 저장소 추가
```bash
sudo apt install -y wget
```
```bash
sudo wget https://packages.osrfoundation.org/gazebo.gpg \
  -O /usr/share/keyrings/gazebo-archive-keyring.gpg
```
```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gazebo-archive-keyring.gpg] \
http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | \
sudo tee /etc/apt/sources.list.d/gazebo-stable.list
```
```bash
sudo apt update
```

### 4.2 설치
```bash
sudo apt install -y gz-harmonic
```
```bash
sudo apt install -y ros-jazzy-ros-gz
```
```bash
sudo apt install -y ros-jazzy-image-transport
```
```bash
sudo apt install -y ros-jazzy-web-video-server
```

### 4.3 확인
```bash
gz sim --version
```

---

## 5. GPU 렌더링 설정 (NVIDIA) - 추후 PC에서 작업하는 사람들 권장

이 작업은 추후 PC에서 작업하는 사람들을 대상으로 하므로 이번 실습에서는 넘어가도 무방

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

## 6. 워크스페이스 구축 및 빌드

### 6.1 소스 클론

```bash
mkdir -p ~/space_ros_ws/src && cd ~/space_ros_ws/src
```
```bash
git clone https://github.com/ndh8205/Controla_ROS2_lec.git orbit_sim
```

### 6.2 `gz_cw_dynamics` 클론 (세미나 Part 2 용)

이 패키지가 CW 동역학, 추력기, 반작용휠, 궤도 IMU, 별센서, GPS, SGP4 chief 전파기를 제공합니다.

```bash
cd ~/space_ros_ws/src
```
```bash
git clone https://github.com/ndh8205/gz_cw_dynamics.git
```

### 6.3 추가 의존성 (sgp4 + gz python)

```bash
sudo apt install -y \
    python3-sgp4 \
    python3-gz-transport13 \
    python3-gz-msgs10 \
    ros-jazzy-ros-gz-image \
    ros-jazzy-ros-gz-bridge
```

### 6.4 의존성 설치 및 빌드

```bash
cd ~/space_ros_ws
```
```bash
rosdep install --from-paths src --ignore-src -r -y
```
```bash
colcon build --symlink-install --packages-select orbit_sim gz_cw_dynamics
```
```bash
source install/setup.bash
```

### 6.5 Zone.Identifier 제거 (Windows에서 복사한 경우에만 진행)

Windows에서 WSL로 파일을 복사하면 `Zone.Identifier` 메타파일이 생기게 되고 ROS 빌드과정에서 오류가 발생함:
```bash
find ~/space_ros_ws/src -name "*:Zone.Identifier*" -delete
```

---

## 7. 환경 변수 설정

`~/.bashrc`에 다음을 추가:

```bash
# ROS 2
source /opt/ros/jazzy/setup.bash
source ~/space_ros_ws/install/setup.bash

# Gazebo 모델 경로
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/space_ros_ws/install/orbit_sim/share/orbit_sim/models

# Gazebo 플러그인 경로 (orbit_sim + gz_cw_dynamics)
export GZ_SIM_SYSTEM_PLUGIN_PATH=~/space_ros_ws/install/gz_cw_dynamics/lib:/opt/ros/jazzy/lib:$GZ_SIM_SYSTEM_PLUGIN_PATH

# ROS 2 DDS 도메인 (동일 서브넷 DDS 경유 시 필요; rosbridge 사용 시 생략 가능)
export ROS_DOMAIN_ID=7

# GPU 렌더링 (NVIDIA)
export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH
export MESA_D3D12_DEFAULT_ADAPTER_NAME="NVIDIA"
export GALLIUM_DRIVER=d3d12
```

```bash
source ~/.bashrc
```

---

## 7b. 네트워크 설정 (GAIMSat FlatSat — rosbridge 방식)

### 세미나 운영 모델

> **플랫샛 (192.168.0.54)** 에서 Gazebo 가 돌고, **학생 노트북** 들은 자기 자리에서 WebSocket 으로 **그 시뮬레이션을 제어** 합니다.
>
> 학생이 노트북에서 `thruster` 토픽을 publish → rosbridge → 플랫샛 Gazebo 의 Deputy 가 실제로 움직임. 센서 데이터 (IMU/GPS/ST/카메라) 는 그 반대 방향으로 노트북에 흘러옵니다.

```
[플랫샛 192.168.0.54]                         [학생 노트북 × 7]

  Gazebo (mission.sdf)
  ├─ deputy_formation (팀 1, 4명)
  └─ deputy_docking   (팀 2, 3명)
       │ ROS 2 플러그인 (DDS 로컬)
       ▼
  rosbridge_server :9090 ◄────── WebSocket ─────── roslibpy (Python)
  web_video_server :8080 ◄────── HTTP ───────────── 브라우저

노트북 → pub /deputy_*/thruster/*/cmd  → 플랫샛 Gazebo 적용 (위성 움직임)
노트북 ← sub /deputy_*/imu/data        ← 플랫샛 센서 출력
노트북 ← HTTP stream 카메라            ← 플랫샛 web_video_server
```

DDS 디스커버리 대신 **rosbridge** 를 써서 서브넷/방화벽 제약과 무관하게 동작합니다.

### 구조

```
플랫샛 (.54) WSL2 → rosbridge_server (ws://192.168.0.54:9090)
                         ↑ TCP / WebSocket (NAT·방화벽 무관)
노트북들 (.22, .52 등) ──┘  (roslibpy / roslibjs 클라이언트)
```

### 7b.1 플랫샛 (서버) 설정

```bash
# WSL Ubuntu 터미널
sudo apt install -y ros-jazzy-rosbridge-suite
```

서버 실행 (시뮬 launch 전 먼저 띄우거나 별도 터미널):
```bash
source /opt/ros/jazzy/setup.bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

**Windows 관리자 CMD** 에서 방화벽 허용 (1회만):
```cmd
netsh advfirewall firewall add rule name="ROS2 rosbridge" dir=in action=allow protocol=TCP localport=9090
```

### 7b.2 모든 노트북 (클라이언트) 설정

```bash
# WSL Ubuntu 터미널
sudo apt install -y ros-jazzy-rosbridge-suite python3-roslibpy
```

**Python 에서 토픽 구독 예시**:
```python
import roslibpy
client = roslibpy.Ros(host='192.168.0.54', port=9090)
client.run()
listener = roslibpy.Topic(client, '/deputy_formation/imu/data', 'sensor_msgs/Imu')
listener.subscribe(lambda msg: print(msg))
```

**토픽 발행 예시** (추력기 명령):
```python
import roslibpy
client = roslibpy.Ros(host='192.168.0.54', port=9090)
client.run()
pub = roslibpy.Topic(client, '/deputy_docking/thruster/fy_plus/cmd',
                     'std_msgs/Float32')
pub.publish(roslibpy.Message({'data': 0.5}))
```

### 7b.3 연결 확인

플랫샛 측:
```bash
ros2 topic pub /test std_msgs/String "data: hello"
```

노트북 측 Python:
```python
import roslibpy
c = roslibpy.Ros('192.168.0.54', 9090); c.run()
t = roslibpy.Topic(c, '/test', 'std_msgs/String')
t.subscribe(lambda m: print(m))   # "hello" 수신되면 성공
```

### 7b.4 주의사항

- 학생 노트북의 **`ros2 topic echo` 같은 CLI 명령은 rosbridge 를 경유하지 않습니다**. DDS 기반이므로 같은 서브넷에서만 동작. 개인 노트북에서 플랫샛 토픽을 직접 `ros2 topic echo` 로 볼 수 없는 게 일반적. roslibpy 사용 필수.
- 우리 스타터 스크립트 (`thruster_commander.py`, `sensor_monitor.py` 등) 는 rclpy 기반이라 **같은 머신에서만 동작**. 노트북에서 플랫샛 시뮬레이션 제어하려면 roslibpy 로 포팅하거나, 학생 코드를 플랫샛에서 실행.
- **gz 토픽 (카메라 `/nasa_satellite/camera` 등)** 은 rosbridge 경유가 아니라 `ros_gz_bridge` 로 ROS 2 토픽화된 후에만 외부 공유됨. 브리지된 토픽 이름으로 roslibpy 구독.

### 7b.5 전체 토픽 접근 방법 (Part 1 + Part 2)

**세미나에서는 3가지 방식이 병존합니다**. 기존 로컬 방식도 그대로 유효, rosbridge/web 은 노트북용 추가 경로:

| 방식 | 실행 위치 | 접근 | 장점 |
|---|---|---|---|
| **A. 로컬 rclpy** (기존) | **플랫샛** 자체 쉘 | `ros2 run gz_cw_dynamics thruster_commander.py ...` | 빠른 프로토타이핑, CLI 전체 |
| **B. 원격 roslibpy** (신규) | **학생 노트북** Python | `client = roslibpy.Ros(host='192.168.0.54', ...)` | 자기 자리에서 시뮬 제어 |
| **C. 브라우저** (신규) | **학생 노트북** 브라우저 | `http://192.168.0.54:8080/...` | 코드 없이 영상/상태 관찰 |

- 이미지/비디오: **C (web_video_server)** 가 가장 빠름 (HTTP stream)
- 나머지 토픽 (IMU, GPS, ST, Odometry, PointCloud2, 명령): **B (rosbridge)** 가 노트북에서 유일한 경로
- 플랫샛 앞에 앉아 있다면 **A (로컬 rclpy)** 가 가장 단순

참고 — 로컬 rclpy 방식 정리:
```bash
# 플랫샛 자체 쉘에서 (기존)
ros2 run gz_cw_dynamics thruster_commander.py  --deputy deputy_docking --axis fy_plus --throttle 0.5 --duration 2
ros2 run gz_cw_dynamics rw_commander.py        --deputy deputy_docking --axis z --torque 0.001 --duration 3
ros2 run gz_cw_dynamics sensor_monitor.py      --deputy deputy_formation
ros2 run gz_cw_dynamics camera_saver.py        --deputy deputy_formation --out /tmp/team1
```

#### 카메라 (web_video_server, 브라우저)

| 토픽 | URL (브라우저에서 접속) |
|---|---|
| `/nasa_satellite5/camera` | `http://192.168.0.54:8080/stream?topic=/nasa_satellite5/camera` |
| `/nasa_satellite3/camera` | `http://192.168.0.54:8080/stream?topic=/nasa_satellite3/camera` |
| `/nasa_satellite/camera`  | `http://192.168.0.54:8080/stream?topic=/nasa_satellite/camera` |
| `/nasa_satellite2/camera` (Part 2) | `http://192.168.0.54:8080/stream?topic=/nasa_satellite2/camera` |

전체 가용 토픽 목록: `http://192.168.0.54:8080/`

#### 데이터 토픽 (roslibpy, Python)

공통 서버 연결:
```python
import roslibpy
client = roslibpy.Ros(host='192.168.0.54', port=9090)
client.run()
```

**Part 1 — LiDAR 포인트클라우드**
```python
pc = roslibpy.Topic(client, '/lidar/points_raw/points',
                    'sensor_msgs/PointCloud2')
pc.subscribe(lambda m: print(f'points: width={m["width"]}'))
```

**Part 1 — 누적 맵**
```python
m = roslibpy.Topic(client, '/map_cloud', 'sensor_msgs/PointCloud2')
m.subscribe(lambda msg: print(f'map width={msg["width"]}'))
```

**Part 1 — 위성 Odometry (nasa_satellite5)**
```python
odo = roslibpy.Topic(client, '/model/nasa_satellite5/odometry',
                     'nav_msgs/Odometry')
odo.subscribe(lambda m: print(
    f"pos=({m['pose']['pose']['position']['x']:.2f}, "
    f"{m['pose']['pose']['position']['y']:.2f}, "
    f"{m['pose']['pose']['position']['z']:.2f})"))
```

**Part 1 — IMU (nasa_satellite5)**
```python
imu = roslibpy.Topic(client, '/nasa_satellite5/imu', 'sensor_msgs/Imu')
imu.subscribe(lambda m: print(
    f"gyro_z={m['angular_velocity']['z']:+.4e}"))
```

**Part 2 — Deputy IMU (궤도-aware)**
```python
imu = roslibpy.Topic(client, '/deputy_docking/imu/data',
                     'sensor_msgs/Imu')
imu.subscribe(lambda m: print(
    f"gyro z={m['angular_velocity']['z']:+.4e} rad/s"))
```

**Part 2 — Deputy Star Tracker**
```python
st = roslibpy.Topic(client, '/deputy_docking/star_tracker/attitude',
                    'geometry_msgs/QuaternionStamped')
st.subscribe(lambda m: print(
    f"q=({m['quaternion']['x']:+.4f}, {m['quaternion']['y']:+.4f}, "
    f"{m['quaternion']['z']:+.4f}, {m['quaternion']['w']:+.4f})"))
```

**Part 2 — Deputy GPS (ECI)**
```python
gps = roslibpy.Topic(client, '/deputy_docking/gps/odometry',
                     'nav_msgs/Odometry')
gps.subscribe(lambda m: print(
    f"r_ECI=({m['pose']['pose']['position']['x']:.1f}, "
    f"{m['pose']['pose']['position']['y']:.1f}, "
    f"{m['pose']['pose']['position']['z']:.1f}) m"))
```

**Part 2 — Chief TLE 추정**
```python
tle = roslibpy.Topic(client, '/chief/eci_state', 'nav_msgs/Odometry')
tle.subscribe(lambda m: print(
    f"chief r_ECI_TLE=({m['pose']['pose']['position']['x']:.1f}, ...)"))
```

**Part 2 — Sun 벡터 (LVLH)**
```python
sun = roslibpy.Topic(client, '/chief/sun_vector_lvlh',
                     'geometry_msgs/Vector3Stamped')
sun.subscribe(lambda m: print(
    f"sun_lvlh=({m['vector']['x']:+.4f}, {m['vector']['y']:+.4f}, "
    f"{m['vector']['z']:+.4f})"))
```

#### 제어 발행 (roslibpy)

**추력기 0.5 throttle**:
```python
pub = roslibpy.Topic(client, '/deputy_docking/thruster/fy_plus/cmd',
                     'std_msgs/Float32')
pub.publish(roslibpy.Message({'data': 0.5}))
```

**반작용휠 +z 방향 1 mN·m 토크**:
```python
pub = roslibpy.Topic(client, '/deputy_docking/rw/z/cmd',
                     'std_msgs/Float32')
pub.publish(roslibpy.Message({'data': 0.001}))
```

(정지: `pub.publish(roslibpy.Message({'data': 0.0}))`)

### 7b.6 노트북에서 바로 실행하는 roslibpy 스크립트 예시

아래 세 파일을 학생 노트북에 저장 후 `python3 <파일>.py` 로 실행. **플랫샛 Gazebo 에 직접 영향을 줍니다** (추력기 점화, 휠 토크, 센서 관측).

#### (1) `laptop_thruster.py` — 노트북에서 플랫샛 deputy 추력기 점화

```python
#!/usr/bin/env python3
"""노트북 → 플랫샛 Gazebo deputy 추력기 명령 (rosbridge 경유)."""
import argparse, time, roslibpy

AXES = ('fx_plus','fx_minus','fy_plus','fy_minus','fz_plus','fz_minus')

ap = argparse.ArgumentParser()
ap.add_argument('--host',     default='192.168.0.54')
ap.add_argument('--deputy',   default='deputy_docking')
ap.add_argument('--axis',     choices=AXES, default='fy_plus')
ap.add_argument('--throttle', type=float,   default=0.5)
ap.add_argument('--duration', type=float,   default=2.0)
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090); client.run()
topic  = f'/{args.deputy}/thruster/{args.axis}/cmd'
pub    = roslibpy.Topic(client, topic, 'std_msgs/Float32')

print(f'[fire] {topic} throttle={args.throttle} for {args.duration}s')
t_end = time.time() + args.duration
while time.time() < t_end:
    pub.publish(roslibpy.Message({'data': float(args.throttle)}))
    time.sleep(0.05)
pub.publish(roslibpy.Message({'data': 0.0}))
print('[fire] stopped'); client.terminate()
```

실행:
```bash
python3 laptop_thruster.py --deputy deputy_docking --axis fy_plus --throttle 0.5 --duration 2
```

#### (2) `laptop_rw.py` — 노트북에서 플랫샛 deputy 반작용휠 토크

```python
#!/usr/bin/env python3
"""노트북 → 플랫샛 deputy RW 토크 명령."""
import argparse, time, roslibpy

ap = argparse.ArgumentParser()
ap.add_argument('--host',     default='192.168.0.54')
ap.add_argument('--deputy',   default='deputy_docking')
ap.add_argument('--axis',     choices=('x','y','z'), default='z')
ap.add_argument('--torque',   type=float, default=0.001)  # N·m
ap.add_argument('--duration', type=float, default=3.0)
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090); client.run()
topic  = f'/{args.deputy}/rw/{args.axis}/cmd'
pub    = roslibpy.Topic(client, topic, 'std_msgs/Float32')

print(f'[rw] {topic} tau={args.torque} Nm for {args.duration}s')
t_end = time.time() + args.duration
while time.time() < t_end:
    pub.publish(roslibpy.Message({'data': float(args.torque)}))
    time.sleep(0.05)
pub.publish(roslibpy.Message({'data': 0.0}))
print('[rw] stopped'); client.terminate()
```

#### (3) `laptop_monitor.py` — 노트북에서 플랫샛 deputy 센서 통합 모니터

```python
#!/usr/bin/env python3
"""노트북 → 플랫샛 deputy 센서 통합 모니터 (IMU, ST, GPS, TLE chief, sun)."""
import argparse, time, roslibpy
from threading import Lock

ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='192.168.0.54')
ap.add_argument('--deputy', default='deputy_formation')
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090); client.run()
state, lock = {}, Lock()
def put(k, v):
    with lock: state[k] = v

roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(lambda m: put('imu', m))
roslibpy.Topic(client, f'/{args.deputy}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(
                   lambda m: put('st', m))
roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(lambda m: put('gps', m))
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(lambda m: put('tle', m))
roslibpy.Topic(client, '/chief/sun_vector_lvlh',
               'geometry_msgs/Vector3Stamped').subscribe(
                   lambda m: put('sun', m))

print(f'[monitor] {args.deputy} @ {args.host}:9090 (Ctrl+C to quit)')
try:
    while True:
        time.sleep(0.5)
        with lock:
            if 'imu' in state:
                g = state['imu']['angular_velocity']
                print(f"  gyro=({g['x']:+.2e},{g['y']:+.2e},{g['z']:+.2e})",
                      end='')
            if 'gps' in state:
                p = state['gps']['pose']['pose']['position']
                print(f"  r_ECI=({p['x']:.0f},{p['y']:.0f},{p['z']:.0f})",
                      end='')
            if 'sun' in state:
                s = state['sun']['vector']
                print(f"  sun=({s['x']:+.3f},{s['y']:+.3f},{s['z']:+.3f})",
                      end='')
            print()
except KeyboardInterrupt:
    pass
client.terminate()
```

실행:
```bash
python3 laptop_monitor.py --deputy deputy_formation
```

#### 전체 쓸 수 있는 토픽 체크리스트

**Part 1** (`seminar_intro.launch.py` 실행 후):

| 토픽 | 타입 | 접근 |
|---|---|---|
| `/lidar/points_raw/points` | PointCloud2 | rosbridge |
| `/map_cloud` | PointCloud2 | rosbridge |
| `/nasa_satellite/camera` | Image | web (8080) |
| `/nasa_satellite3/camera` | Image | web (8080) |
| `/nasa_satellite5/camera` | Image | web (8080) |
| `/nasa_satellite5/imu` | Imu | rosbridge |
| `/model/nasa_satellite5/odometry` | Odometry | rosbridge |
| `/tf`, `/tf_static` | TFMessage | rosbridge |

**Part 2** (`mission.launch.py` 실행 후) — 각 deputy 기준:

| 토픽 (`deputy_formation` / `deputy_docking`) | 타입 | 접근 | 방향 |
|---|---|---|---|
| `/chief/eci_truth` | Odometry | rosbridge | sub |
| `/chief/eci_state` | Odometry | rosbridge | sub |
| `/chief/sun_vector_lvlh` | Vector3Stamped | rosbridge | sub |
| `/deputy_*/imu/data` | Imu | rosbridge | sub |
| `/deputy_*/star_tracker/attitude` | QuaternionStamped | rosbridge | sub |
| `/deputy_*/gps/odometry` | Odometry | rosbridge | sub |
| `/deputy_*/thruster/{fx,fy,fz}_{plus,minus}/cmd` | Float32 | rosbridge | **pub** |
| `/deputy_*/rw/{x,y,z}/cmd` | Float32 | rosbridge | **pub** |
| `/nasa_satellite/camera` (팀1) | Image | web (8080) | - |
| `/nasa_satellite2/camera` (팀2) | Image | web (8080) | - |

---

## 8. 시뮬레이션 실행

### 8.1 세미나 Part 1 — 통합 인트로 런치

하나의 명령어로 다음이 전부 켜집니다:

- Gazebo Harmonic (다중 위성 월드, `gco_test.world`)
- **3D LiDAR 포인트클라우드 브리지 + 누적 맵 매퍼**
- 카메라 / IMU / Odometry ROS 2 브리지
- **web_video_server** (브라우저에서 영상 스트림, http://localhost:8080)
- SetEntityPose 서비스 브리지
- 멀티 위성 CSV 궤적 컨트롤러 (LiDAR 탑재 nasa_satellite3 포함)

```bash
ros2 launch orbit_sim seminar_intro.launch.py
```

RViz 포인트클라우드 뷰도 자동으로 열려면:
```bash
ros2 launch orbit_sim seminar_intro.launch.py rviz:=true
```

### 8.1b (대안) 기본 GCO 시뮬레이션

LiDAR 없이 GCO 편대만 보려면:
```bash
ros2 launch orbit_sim gco_test.launch.py
```

Gazebo Harmonic 창이 열리면서 위성 모델이 표시됩니다.

### 8.2 토픽 확인 (별도 터미널)

```bash
# 전체 토픽 목록
ros2 topic list

# 노드 목록
ros2 node list

# 발행 빈도 확인 (예: LiDAR 포인트클라우드)
ros2 topic hz /lidar/points_raw/points

# 데이터 내용 확인
ros2 topic echo /model/nasa_satellite5/odometry
ros2 topic echo /nasa_satellite5/imu
```

**`seminar_intro.launch.py` 가 발행하는 전체 토픽 테이블:**

| 토픽 | 타입 | 역할 |
|---|---|---|
| `/lidar/points_raw/points` | `sensor_msgs/PointCloud2` | nasa_satellite3 의 3D LiDAR 포인트클라우드 |
| `/map_cloud` | `sensor_msgs/PointCloud2` | pointcloud_mapper 가 누적한 월드 프레임 맵 |
| `/nasa_satellite3/camera` | `sensor_msgs/Image` | nasa_satellite3 카메라 |
| `/nasa_satellite5/camera` | `sensor_msgs/Image` | nasa_satellite5 카메라 |
| `/nasa_satellite/camera`  | `sensor_msgs/Image` | nasa_satellite 카메라 |
| `/nasa_satellite5/imu` | `sensor_msgs/Imu` | IMU |
| `/model/nasa_satellite5/odometry` | `nav_msgs/Odometry` | 위성 위치/속도 |
| `/tf`, `/tf_static` | `tf2_msgs/TFMessage` | TF 트리 (nasa_satellite3 LiDAR 프레임 포함) |

**서비스:**

| 서비스 | 타입 | 역할 |
|---|---|---|
| `/world/space_world/set_pose` | `ros_gz_interfaces/srv/SetEntityPose` | 엔티티 텔레포트 |

**노드 목록** (`ros2 node list` 결과):
```
/camera_bridge
/imu_odo_bridge
/lidar_bridge
/multi_satellite_controller_service
/pointcloud_mapper
/set_pose_bridge
/web_video_server
/rviz2                           # rviz:=true 일 때만
```

### 8.3 카메라 영상 확인

`seminar_intro.launch.py` 가 카메라 브리지와 `web_video_server` 를 자동 실행합니다.

**방법 1: rqt_image_view (GUI)**
```bash
ros2 run rqt_image_view rqt_image_view
# 드롭다운에서 /nasa_satellite5/camera, /nasa_satellite3/camera, /nasa_satellite/camera 중 선택
```

**방법 2: web_video_server (브라우저)**

자동 실행된 서버에 접속:
```
http://localhost:8080/                                    # 스트림 가능한 토픽 목록
http://localhost:8080/stream?topic=/nasa_satellite5/camera
http://localhost:8080/stream?topic=/nasa_satellite3/camera
http://localhost:8080/stream?topic=/nasa_satellite/camera
```

**방법 3: Gazebo GUI 내장 카메라 뷰**

Gazebo 우측 패널 > Plugins > Image Display > Topic 에 `nasa_satellite5/camera` 등 입력.

### 8.3b RViz 에서 LiDAR 누적 맵 보기

```bash
ros2 launch orbit_sim seminar_intro.launch.py rviz:=true
```

또는 다른 터미널에서 수동 기동:
```bash
ros2 run rviz2 rviz2 -d \
    ~/space_ros_ws/install/orbit_sim/share/orbit_sim/config/lidar_mapping.rviz
```

확인 토픽: `/map_cloud` (월드 프레임), `/lidar/points_raw/points` (센서 프레임).

### 8.4 노드 연결 시각화

```bash
rqt_graph
```

### 8.5 데이터 녹화/재생 (ros2 bag)

```bash
# 녹화
ros2 bag record /model/nasa_satellite5/odometry /nasa_satellite5/imu

# 재생
ros2 bag play <bag_directory>
```

### 8.6 프로세스 정리

```bash
pkill -f gz && pkill -f ros2
```

또는 orbit_sim 제공 스크립트:
```bash
bash ~/kill_sim.sh
```

---

## 8b. 세미나 Part 2 — SSA 미션 (gz_cw_dynamics)

### 8b.1 미션 월드 실행 (메인 데스크탑만)

```bash
bash ~/kill_sim.sh
ros2 launch gz_cw_dynamics mission.launch.py
```

구성:
- **Chief** (intel_sat_dummy) — 원점 고정, 545 km SSO
- **deputy_formation** (nasa_satellite) — `(0, +5000, 0)` m, 팀 1 담당
- **deputy_docking** (nasa_satellite2) — `(0, -5000, 0)` m, 팀 2 담당
- 각 deputy 에 CW 동역학, 6 추력기, 3 반작용휠, IMU, 별센서, GPS 부착
- 3 초 후 `chief_propagator_node` 자동 시작 (Keplerian truth + SGP4 TLE 추정 + sun 벡터)

### 8b.2 학생 스타터 명령 (개인 노트북)

```bash
# 추력기 (병진)
ros2 run gz_cw_dynamics thruster_commander.py \
    --deputy deputy_docking --axis fy_plus --throttle 0.5 --duration 2

# 반작용휠 (자세)
ros2 run gz_cw_dynamics rw_commander.py \
    --deputy deputy_docking --axis z --torque 0.001 --duration 3

# 센서 모니터링
ros2 run gz_cw_dynamics sensor_monitor.py --deputy deputy_formation

# 카메라 저장
ros2 run gz_cw_dynamics camera_saver.py --deputy deputy_docking --out /tmp/frames
```

### 8b.3 주요 토픽

**Chief 공유**
- `/chief/eci_truth` — Keplerian 진실 (센서 내부용)
- `/chief/eci_state` — **SGP4+noise TLE 추정** (학생 네비게이션용)
- `/chief/sun_vector_lvlh` — 태양 방향 벡터 (LVLH)

**Deputy 공통 패턴** (각 deputy 마다 `/deputy_formation/...` 또는 `/deputy_docking/...` 로 네임스페이스됨)

| 토픽 | 타입 | 방향 | 설명 |
|---|---|---|---|
| `/deputy_*/imu/data` | `sensor_msgs/Imu` | 발행 | LVLH-aware IMU (자이로에 $\omega_{LVLH/I}=n$ 포함, accel 은 비중력 specific force) |
| `/deputy_*/star_tracker/attitude` | `geometry_msgs/QuaternionStamped` | 발행 | body-in-ECI 쿼터니언 + Gaussian 노이즈 (σ=0.05°) |
| `/deputy_*/gps/odometry` | `nav_msgs/Odometry` | 발행 | ECI 위치/속도 + 노이즈 (σ_pos=5 m, σ_vel=0.05 m/s) |
| `/deputy_*/cw_pseudo_accel` | `gz.msgs.Vector3d` | 발행 (gz transport) | CW pseudo-acceleration, IMU 보정용 내부 토픽 |
| `/deputy_*/thruster/fx_plus/cmd` | `std_msgs/Float32` | **구독** | +x 방향 추력 throttle [0,1] |
| `/deputy_*/thruster/fx_minus/cmd` | `std_msgs/Float32` | **구독** | -x 방향 추력 |
| `/deputy_*/thruster/fy_plus/cmd` | `std_msgs/Float32` | **구독** | +y 방향 추력 |
| `/deputy_*/thruster/fy_minus/cmd` | `std_msgs/Float32` | **구독** | -y 방향 추력 |
| `/deputy_*/thruster/fz_plus/cmd` | `std_msgs/Float32` | **구독** | +z 방향 추력 |
| `/deputy_*/thruster/fz_minus/cmd` | `std_msgs/Float32` | **구독** | -z 방향 추력 |
| `/deputy_*/rw/x/cmd` | `std_msgs/Float32` | **구독** | x축 반작용휠 토크 [N·m] |
| `/deputy_*/rw/y/cmd` | `std_msgs/Float32` | **구독** | y축 반작용휠 토크 |
| `/deputy_*/rw/z/cmd` | `std_msgs/Float32` | **구독** | z축 반작용휠 토크 |

**카메라** (gz transport, `ros-gz-image` 로 ROS 2 에 브리지 가능):

| Deputy | gz topic |
|---|---|
| `deputy_formation` | `/nasa_satellite/camera` |
| `deputy_docking`   | `/nasa_satellite2/camera` |

**`ros2 node list` 결과 (Part 2)**:
```
/chief_propagator
/thruster_<topic>_cmd × 12       # 각 deputy × 6 axis × 2 = 12 ROS 노드
/rw_<topic>_cmd × 6              # 각 deputy × 3 axis × 2 = 6 ROS 노드
/orbit_imu_<topic>_data × 2
/star_tracker_<topic>_attitude × 2
/gps_<topic>_odometry × 2
```
(각 플러그인이 자기 rclcpp::Node 를 띄우므로 다수)

### 8b.4 RTF 조정 (원거리 접근 시)

5 km 구간은 실시간이 지루함 → 빠르게 감기:
```bash
gz service -s /world/mission/set_physics \
    --reqtype gz.msgs.Physics --reptype gz.msgs.Boolean --timeout 1000 \
    --req 'max_step_size: 0.01, real_time_factor: 30.0'
```

근접 구간 (1 km 이내) 은 RTF=1 로 복귀 권장.

### 8b.5 전체 시스템 검증 (세미나 전 리허설)

```bash
bash ~/space_ros_ws/install/gz_cw_dynamics/lib/gz_cw_dynamics/run_full_system_test.sh
```

6 항목 (CW 3-orbit, 추력기 6 방향, IMU, Chief 전파, 반작용휠 3축, 종합 센서 7 체크) 자동 수행. 약 5분 30초. 모두 PASS 면 인프라 준비 완료.

### 8b.6 팀 브리프

세부 미션 설명:
- 팀 1 (4명, GCO 50 m 포메이션 + chief 사진):
  `~/space_ros_ws/install/gz_cw_dynamics/share/gz_cw_dynamics/docs/team1_formation_brief.md`
- 팀 2 (3명, 5 km → 도킹):
  `~/space_ros_ws/install/gz_cw_dynamics/share/gz_cw_dynamics/docs/team2_docking_brief.md`

---

## 9. 트러블슈팅

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
| gz_cw_dynamics 플러그인 로딩 실패 | `GZ_SIM_SYSTEM_PLUGIN_PATH` 에 `~/space_ros_ws/install/gz_cw_dynamics/lib` 포함 확인 |
| `python3-sgp4` 없음 | `sudo apt install -y python3-sgp4` 설치 |
| 학생 노트북에서 토픽 안 보임 | `ROS_DOMAIN_ID` 모든 기기 동일, 동일 LAN 확인 |
| Gazebo 창 프리즈 (반복 실행 후) | Windows PowerShell 에서 `wsl --shutdown` 후 재접속 (WSLg 리셋) |
| 전체 시스템 정상인지 확인 | `bash ~/space_ros_ws/install/gz_cw_dynamics/lib/gz_cw_dynamics/run_full_system_test.sh` |
| 노트북에서 `roslibpy` 연결 안 됨 | (1) 플랫샛에서 `ros2 launch rosbridge_server rosbridge_websocket_launch.xml` 실행 여부 (2) Windows 방화벽 9090 TCP 허용 (3) `ping 192.168.0.54` 성공 확인 |
| `pip install roslibpy` 가 필요한 경우 | `python3-roslibpy` apt 로 설치 실패 시 `pip3 install roslibpy --user` |
| 노트북 `ros2 topic list` 에 원격 토픽 없음 | 정상. rosbridge 경유는 CLI 아닌 roslibpy Python 스크립트로만 보임. 같은 서브넷 DDS 동작 시에만 CLI 접근 가능 |

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
