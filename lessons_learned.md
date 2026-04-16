# gz_cw_dynamics 개발 회고록 (2026-04-16)

> 하루(약 12시간) 만에 궤도역학 시뮬레이션 전체 스택을 구축한 기록.
> 무엇이 잘 됐고, 어디서 삽질했고, 어떻게 고쳤고, 다음에는 어떻게 하면 되는지.

---

## 1. 전체 타임라인

| 시간대 | 작업 | 결과 |
|---|---|---|
| 시작 | CW 방정식 설계 논의 + 서베이 | LVLH pseudo-force 방식 확정 |
| +1h | CW 플러그인 작성 + 첫 월드 | GUI 검은 화면 → GzScene3D 교체로 해결 |
| +2h | 50m GCO 초기조건 + 검증 | SetLinearVelocity 실패 → impulsive force 로 해결 |
| +3h | 3-orbit 수치 검증 (CSV) | |r| 오차 < 3 cm, drift < 7 mm/orbit ✅ |
| +4h | 추력기 6개 + 자동 테스트 | 6/6 PASS ✅ |
| +5h | OrbitImu (LVLH 회전 보정) | gyro_z = n 확인 ✅ |
| +6h | ChiefPropagator (ECI) | 월드-레벨 rclcpp → GUI 프리즈 → Python 노드로 분리 |
| +7h | StarTracker + GPS + TLE/SGP4 | 7/7 센서 테스트 PASS ✅ |
| +8h | Reaction Wheel | joint axis 방향 버그 → expressed_in="__model__" 해결 |
| +9h | Mission 월드 (2 deputy) | 인라인 모델 GUI 안 됨 → headless-rendering 전환 |
| +10h | rosbridge + web + 학생 코드 | QoS 불일치 → RELIABLE 로 변경 |
| +11h | 시스템 플러그인 누락 발견 | Physics+UserCommands+SceneBroadcaster 명시 → 전체 해결 |
| +12h | 세미나 실행 + 디버깅 | 학생 노트북 ros2 run 불가 → python3 직접 실행 안내 |

---

## 2. 실수 → 원인 → 해결 → 교훈

### 실수 1: SetLinearVelocity 로 초기속도 부여

**증상**: Deputy 가 한 스텝(0.001초) 만 이동 후 정지.

**원인**: `WorldLinearVelocityCmd` 컴포넌트가 PhysicsSystem 에서 1회 처리 후 소멸. 이후 속도 = 0.

**해결**: Impulsive force 방식 — 첫 PreUpdate 에서 `F = m * v_init / dt` 인가.
```cpp
force += (this->mass / dt) * this->initialVelocity;
```

**교훈**: gz-sim 의 `SetLinearVelocity` 는 "매 스텝 속도 오버라이드" 가 아니라 "1회 명령". 속도 유지하려면 힘을 지속 인가하거나 impulsive 로.

---

### 실수 2: GzScene3D 사용

**증상**: Gazebo 창 열리지만 완전 검은 화면.

**원인**: `GzScene3D` 는 gz-sim Garden 이후 deprecated. Harmonic (8.11.0) 에서 제거됨. MinimalScene 으로 대체되지만, 내부적으로 폴백이 불완전.

**해결**: orbit_sim 기존 월드가 `GzScene3D` 를 쓰고 있었고 "돌아가긴" 했지만, 불안정. 경고 로그 확인 필수:
```
[Wrn] The [GzScene3D] GUI plugin has been removed since Garden.
```

**교훈**: 기존에 돌아가던 코드라도 deprecated 경고가 있으면 신뢰하지 말 것. 새 프로젝트에선 최신 API 사용.

---

### 실수 3: 월드-레벨 플러그인에서 rclcpp::init

**증상**: ChiefPropagator 플러그인 (월드 레벨) 활성화 → GUI 완전 프리즈.

**원인**: 월드-레벨 `<plugin>` 의 Configure 에서 `rclcpp::init()` + executor 스레드 시작 → Ogre2 렌더링 스레드와 교착.

**해결**: ChiefPropagator 를 gz-sim 플러그인에서 **독립 ROS 2 노드** (`chief_propagator_node.py`) 로 전환.

**교훈**: 
- 모델-레벨 플러그인의 rclcpp 는 OK (Thruster, IMU 등 잘 동작).
- **월드-레벨** 플러그인에서 rclcpp 사용은 WSL2 에서 GUI 프리즈 유발.
- 의심 시 "해당 플러그인 주석처리 → GUI 동작?" 로 이진 검색.

---

### 실수 4: revolute joint axis 방향

**증상**: RW z 축만 동작, x/y 축 무반응 (body 각속도 변화 없음).

**원인**: `<axis><xyz>1 0 0</xyz>` 는 **child link 로컬 프레임** 기준. child link 에 pose 회전이 있으면 실제 joint axis 가 의도와 다른 월드 방향.
- wheel_x (pitch 90°): child +x = world -z → joint axis 가 -z 방향으로 됨.

**해결**: `<xyz expressed_in="__model__">1 0 0</xyz>` — model 프레임 고정.

**교훈**: SDF joint axis 는 기본이 child frame. **pose 회전된 child 에는 반드시 `expressed_in` 명시**.

---

### 실수 5: QoS 불일치 (추력기/RW 무반응)

**증상**: `ros2 topic info -v` 에 subscriber 보이지만, 명령 보내도 가속도 0.

**원인**: 
- 플러그인 subscriber: `rclcpp::SensorDataQoS()` = **BEST_EFFORT**
- `ros2 topic pub` 기본: **RELIABLE**
- ROS 2 에서 RELIABLE publisher → BEST_EFFORT subscriber 는 **수신 가능** (이론적). 하지만 DDS 구현 따라 실패 가능.

**해결**: subscriber QoS 를 `10` (기본 RELIABLE, depth=10) 으로 변경.

**교훈**: 액추에이터 (명령 수신) 는 **RELIABLE QoS** 사용. SensorDataQoS 는 센서 발행용.

---

### 실수 6: 시스템 플러그인 미명시

**증상**: 모든 플러그인 "configured" 로그 정상, 토픽 발행됨. 하지만 GUI 엔티티 트리 비어있고, wrench/set_pose 서비스 없음.

**원인**: mission.sdf 에 `<plugin filename="gz-sim-sensors-system">` 을 명시하자, gz-sim 이 **기본 server.config 의 Physics/UserCommands/SceneBroadcaster 를 로드 안 함**.

**해결**: 5개 시스템 플러그인 전부 명시:
```xml
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
<plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
  <render_engine>ogre2</render_engine>
</plugin>
<plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
```

**교훈**: **월드에 시스템 플러그인 1개라도 명시하면, 나머지도 전부 명시해야 함.** "부분 명시" 는 기본 로드를 무효화. 이것이 이 프로젝트 **최대 삽질 원인**.

---

### 실수 7: 인라인 모델 + revolute joint → GUI 렌더 안 됨

**증상**: 인라인 `<model>` 에 base_link + 3 wheel links + 3 revolute joints → headless 에서 정상이지만 GUI 에서 엔티티 트리 빈 채로.

**원인**: 정확한 원인 미확인. gz-sim 8.11.0 의 Ogre2 렌더러가 인라인 모델 + 다수 joint 조합에서 scene graph 를 제대로 구성하지 못하는 것으로 추정.

**해결**: 
- 최종: 시스템 플러그인 5개 명시로 해결됨 (실수 6).
- 대안: `<include>` 기반 + 가상 토크 RW (joint 없이 AddWorldWrench).
- 대안: `--headless-rendering` 모드 (GUI 없이 카메라 센서 동작).

**교훈**: GUI 렌더링 문제 시 headless-rendering 으로 우회 가능. 학생들이 웹으로 접근하면 GUI 불필요.

---

### 실수 8: 학생 노트북에서 ros2 run 안 됨

**증상**: `no executable found` 에러.

**원인**: 학생 노트북에 gz_cw_dynamics 패키지가 빌드 안 돼 있음. `ros2 run` 은 colcon install 된 패키지에서만 동작.

**해결**: 학생은 `python3 student/completed/laptop_monitor.py --host ...` 로 직접 실행. roslibpy 만 필요, ROS 2 불필요.

**교훈**: rosbridge 아키텍처면 클라이언트(학생) 에 ROS 2 설치 자체가 불필요. 문서에 "ros2 run" 과 "python3 직접실행" 을 명확히 구분.

---

### 실수 9: web_video_server 무한 로딩

**증상**: `http://localhost:8080/stream?topic=...` 브라우저 무한 로딩.

**원인**: 기본 스트림 코덱이 브라우저 비호환. + WSL2 localhost 가 Windows 에서 접근 시 WSL IP 필요.

**해결**: URL 에 `&type=mjpeg` 추가 + WSL IP (`hostname -I`) 사용.

**교훈**: web_video_server 는 반드시 `type=mjpeg` 명시. WSL2 는 `localhost` 대신 실제 IP.

---

### 실수 10: WSL2 포트포워딩 누락

**증상**: WSL 내부에서 `curl localhost:8080` 동작하지만, Windows 브라우저에서 `192.168.0.54:8080` 안 됨.

**원인**: WSL2 는 NAT 뒤. Windows LAN IP → WSL IP 포트포워딩 필요.

**해결**:
```cmd
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=<WSL_IP>
netsh interface portproxy add v4tov4 listenport=9090 listenaddress=0.0.0.0 connectport=9090 connectaddress=<WSL_IP>
```

**교훈**: WSL2 네트워크 = NAT. 외부 접근 시 반드시 portproxy 설정. WSL 재부팅 시 IP 변경됨 → 재설정 필요.

---

## 3. 잘 된 것들

### CW 동역학 검증
- 50 m GCO, 3 orbit 검증: |r| 오차 < 3 cm, drift < 7 mm/orbit.
- DART + pseudo-force 방식이 정확하고 안정적.
- MATLAB lvlh_check_ver1.m 결과와 일관.

### 센서 모델링
- OrbitImu: LVLH 회전 자동 보정 + MATLAB 동일 노이즈 파라미터.
- StarTracker: body-in-ECI 쿼터니언 + 자세 변경 시 정확 추적 (30° 회전 테스트).
- GPS: ECI 위치/속도 + Gaussian 노이즈.
- 전부 자동 테스트 (run_all_sensors_test.sh 7/7 PASS).

### SGP4/TLE Chief 전파
- Keplerian truth + SGP4 TLE estimate 이중 발행.
- J2 drift + 노이즈 → 실제 TLE 불확실성 재현.
- "VBN 없이 도킹 불가" 동기 부여 성공.

### rosbridge 아키텍처
- DDS 없이 안정적 원격 접속.
- 학생 노트북에 ROS 2 설치 불필요 (roslibpy 만).
- web_video_server 로 브라우저 카메라 스트림.

### 자동 검증 체계
- run_full_system_test.sh: 6 항목 (CW + 추력기 + IMU + Chief + RW + 종합) 5분 30초.
- test_all_student_scripts.sh: 학생 코드 6종 자동 실행.
- CSV 검증 (verify_gco.py): MATLAB 대조용 데이터 생성.

---

## 4. 다음에 더 빠르게 하려면

### 설계 단계
1. **gz-sim 버전 확인 먼저** — deprecated API (GzScene3D 등) 사전 파악.
2. **시스템 플러그인 리스트를 월드 SDF 에 항상 명시** — 부분 명시 함정 피하기.
3. **QoS 를 처음부터 RELIABLE 로** — 액추에이터 subscriber 는 SensorDataQoS 쓰지 말 것.
4. **월드-레벨 플러그인에서 rclcpp 사용 금지** — 별도 노드로 분리.

### 구현 단계
5. **인라인 모델보다 `<include>` 우선** — 별도 model.sdf 패키지로 관리.
6. **revolute joint axis 는 `expressed_in="__model__"` 습관화**.
7. **headless-rendering 을 기본 테스트 모드로** — GUI 문제와 물리/센서 문제 분리.
8. **rosbridge + roslibpy 를 초기 설계에 반영** — DDS 크로스머신은 WSL2 에서 불안정.

### 테스트 단계
9. **PIPESTATUS[0] 로 파이프라인 exit code 캡처** — `cmd | tail` 은 tail 의 exit code.
10. **WSL2 포트포워딩 세미나 전 반드시 확인** — WSL IP 변경 가능성.
11. **kill_sim.sh 를 저장소에 포함** — fresh clone 에서도 바로 사용.

### 세미나/배포 단계
12. **학생 노트북 ≠ 플랫샛** 구분 철저히 — `ros2 run` vs `python3` 혼용 금지.
13. **web_video_server URL 에 `&type=mjpeg` 항상 포함**.
14. **pip3 install 시 `--break-system-packages` 필요** (Ubuntu 24.04 PEP 668).

---

## 5. 최종 산출물

### 저장소
- `gz_cw_dynamics` (GitHub): 플러그인 7종 + 월드 4종 + 런치 5종 + 검증 6종
- `Controla_ROS2_lec` (GitHub): 세미나 가이드 + 학생 코드 7종 + 모델 자원

### 플러그인
| 이름 | 기능 |
|---|---|
| CWDynamics | Clohessy-Wiltshire pseudo-force (J2/SS 옵션) |
| Thruster | ROS 2 Float32 → body-frame 추력 |
| ReactionWheel | ROS 2 Float32 → body torque (가상 또는 joint) |
| OrbitImu | LVLH-aware IMU (gyro ω_LVLH + accel CW 보정 + 노이즈 + RW bias) |
| StarTracker | body-in-ECI 쿼터니언 + Gaussian 노이즈 |
| GPS | ECI 위치/속도 + Gaussian 노이즈 |
| ChiefPropagator | (레거시, Python 노드로 대체) |

### 노드
| 이름 | 기능 |
|---|---|
| chief_propagator_node.py | Keplerian truth + SGP4 TLE estimate + sun vector |

---

*작성: 2026-04-16 ~ 04-17, ControLA SSA 세미나 준비 중*
