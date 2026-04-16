# 역할별 스타터 코드 (학생용)

노트북에서 `python3 <스크립트>.py` 로 직접 실행합니다.
플랫샛 (192.168.0.54) 의 Gazebo 시뮬레이션에 rosbridge 경유로 연결됩니다.

## 필요 설치 (1회)

```bash
sudo apt install -y python3-roslibpy
# 또는
pip3 install roslibpy --user
```

## 역할 배정

### 팀 1: Formation (50 m GCO → chief 사진)

| 역할 | 파일 | 토픽 (주력) |
|---|---|---|
| **자세 제어** | `attitude_controller.py --deputy deputy_formation` | star_tracker + imu → rw 명령 |
| **궤도 제어** | `orbit_controller.py --deputy deputy_formation` | gps + tle → thruster 명령 |
| **영상 담당** | `vision_operator.py --deputy deputy_formation` | camera (web), gps (거리) |
| **미션 매니저** | 3개 모두 모니터 또는 `laptop_monitor.py --deputy deputy_formation` | 전체 |

### 팀 2: Docking (5 km → 1 m)

| 역할 | 파일 | 토픽 (주력) |
|---|---|---|
| **자세 제어** | `attitude_controller.py --deputy deputy_docking` | star_tracker + imu → rw 명령 |
| **궤도 제어** | `orbit_controller.py --deputy deputy_docking` | gps + tle → thruster 명령 |
| **영상 담당** | `vision_operator.py --deputy deputy_docking` | camera (web), gps (거리) |

## 실행 예시

```bash
# 자세 담당 (노트북에서)
python3 attitude_controller.py --host 192.168.0.54 --deputy deputy_docking

# 궤도 담당 (노트북에서)
python3 orbit_controller.py --host 192.168.0.54 --deputy deputy_docking

# 영상 담당 (노트북에서)
python3 vision_operator.py --host 192.168.0.54 --deputy deputy_docking
```

## 카메라 브라우저 URL

```
http://192.168.0.54:8080/                                      # 전체 토픽 목록
http://192.168.0.54:8080/stream?topic=/nasa_satellite/camera   # 팀 1
http://192.168.0.54:8080/stream?topic=/nasa_satellite2/camera  # 팀 2
```

## 코드 구조

각 파일은 동일 패턴:
1. rosbridge 접속 (`roslibpy.Ros(host, 9090)`)
2. 센서 토픽 구독 (subscribe)
3. 제어 루프 (`while True:`)
4. **`# TODO: 학생이 구현할 부분!`** — 제어 알고리즘을 여기에 넣으세요
5. 종료 시 액추에이터 정지 (KeyboardInterrupt)

## 각 역할이 해야 할 일

### 자세 제어 담당
- Star Tracker 쿼터니언 → 현재 body-in-ECI 자세 확인
- 목표 자세 결정 (카메라를 chief 쪽으로 정렬 등)
- 자세 오차 → PD 제어 → Reaction Wheel 토크 명령

### 궤도 제어 담당
- GPS (내 ECI) - TLE (chief ECI) = 상대 벡터 (ECI) 계산
- 접근 전략: V-bar 접근 (+y 방향 추력)
- 속도 제어: 거리 따라 접근속도 조절
- **주의: TLE 오차 ~1 km → 근접 시 영상 담당과 협조 필수**

### 영상 담당
- 브라우저로 카메라 영상 관측
- Chief 가 FOV 에 보이는지 자세 담당에게 피드백
- 원하는 각도에서 스크린샷 저장 (팀 1)
- VBN: chief 가 화면 어디 있는지 → 상대 방향 추정 (팀 2, 선택)
