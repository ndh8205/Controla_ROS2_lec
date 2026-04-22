# Navigation 실습 — 상대 항법 및 예측 (Relative Navigation)

**역할**: 여러 센서(GPS, TLE, IMU)를 융합해 **팀의 "상태 추정 허브"**. CW 전파로 미래 위치 예측. TLE 건전성 감시.
**짝 코드**: `student/navigation.py`
**팀 공통**: Formation / Docking 모두 필요 (팀별 GPS·TLE 자체는 동일하지만 deputy 다름)

Navigation 은 **액추에이터를 직접 쏘지 않음**. 대신 ADCS / ODCS / Vision 에게 "지금 상황 분석" 을 제공.

---

## 오늘 할 일

1. 센서 수신 확인 (GPS 1 Hz + TLE 1 Hz)
2. LVLH 상대 벡터 / 거리 계산 (스캐폴드 기본 동작)
3. Coriolis 보정으로 LVLH 속도 정확도 향상
4. CW 전파 예측 검증 (예측 vs 실제)
5. TLE 건전성 모니터 (교수님 하드 방해 감지)
6. 팀에 상태 푸시 (CSV 로그 or ROS 토픽 재퍼블리시)

---

## 성공 기준 (실습 중 즉석 결정)

- [ ] 거리 수치가 **안정적으로 수렴** (±100 m 이내 스무딩 후)
- [ ] CW 예측 +10 s 가 실제와 **일정 오차 이내** 일치
- [ ] 교수님이 chief 텔레포트 시 **몇 초 내 감지 경보**
- [ ] ADCS/ODCS/Vision 이 Navigation 데이터로 의사결정 수행

---

## 스캐폴드가 이미 해 준 것

`navigation.py`:
- 센서 구독 3종 (GPS, TLE, IMU)
- ECI → LVLH basis 계산 (`eci_to_lvlh_basis`)
- CW 해석적 전파 (`cw_forecast`)
- 1 Hz 출력: 거리, LVLH 상대위치, +10/30/60 s 예측
- 벡터 헬퍼 (`cross`, `norm`, `scale`, `sub`, `dot`, `mat_vec`)

너희 할 일: **4개 TODO 블록 중 최소 [1] 과 [2] 구현**.

---

## Step 1 — 기본 출력 확인 (5분)

```bash
python3 student/navigation.py --host 220.67.219.55 --deputy deputy_formation
```

출력 예 (Docking 팀은 부호 반대):
```
[nav] dist=   5024.3 m  LVLH=(   -3.2, +5020.1,    +1.4)  v_rad=+0.042 m/s
      CW +10s LVLH=(   -3.4, +5020.2,    +1.4)
      CW +30s LVLH=(   -3.9, +5020.4,    +1.4)
      CW +60s LVLH=(   -4.8, +5020.8,    +1.4)
```

**관찰**:
- **거리 수치가 ±1~3 km 진동**하면 → 정상 (GPS/TLE 타임스탬프 비동기 때문). **이거 고치는 게 Step 3**.
- 자세 초기값 (Formation 팀은 `(0, +5000, 0)` 근처 LVLH) 이면 OK.
- CW 예측이 현재값과 거의 똑같으면 → 정지 상태. ODCS 가 분사하면 예측 곡선이 달라짐.

**체크**: `v_radial` 값. 음수 = chief 쪽 접근 중, 양수 = 멀어지는 중.

---

## Step 2 — Coriolis 보정 (15분)

LVLH 는 **회전 프레임**이라 속도를 그냥 ECI→LVLH 좌표변환하면 틀림. ω = chief 궤도각속도.

**수식**:
```
v_LVLH_correct = R·v_ECI − ω × r_LVLH
   where ω = (0, 0, n),  n = 1.0959e-3 rad/s
```

TODO [1] 블록에 이 수식을 구현:
```python
OMEGA = (0.0, 0.0, N_MEAN)   # LVLH frame 의 ECI 기준 각속도

# 기존 v_rel_lvlh 계산 후:
coriolis = cross(OMEGA, r_rel_lvlh)
v_rel_lvlh_true = (v_rel_lvlh[0] - coriolis[0],
                   v_rel_lvlh[1] - coriolis[1],
                   v_rel_lvlh[2] - coriolis[2])
```

**검증**: 분사 없을 때 deputy_formation `(0, +5000, 0)` LVLH 는 **CW 에서 정지 해** (순수 along-track offset).
→ 보정 후 `v_rel_lvlh_true` 가 ~0 에 가까워야 함 (노이즈만).

---

## Step 3 — 거리 스무딩 (10분)

GPS-TLE 비동기로 거리 ±2 km 튀는 걸 줄이려면 이동평균:
```python
from collections import deque
dist_window = deque(maxlen=10)   # 최근 10 샘플

# 루프 안에서:
dist_window.append(dist)
dist_smoothed = sum(dist_window) / len(dist_window)
```

또는 **저역 필터**:
```python
dist_lpf = 0.9 * dist_lpf + 0.1 * dist    # 초기값 = 첫 dist
```

→ 타팀에 보고할 땐 스무딩한 값 사용.

---

## Step 4 — CW 예측 vs 실제 비교 (15분)

지금 예측한 +10 s 후 위치가 10 초 뒤 실제 관측치와 얼마나 맞는지 측정:
```python
# 10 s 전 예측치 저장
predicted_history = {}   # key: timestamp, value: predicted r

# 루프 안에서:
now = time.time()
predicted_history[now + 10.0] = r10    # 미래 예측

# 과거 예측중 now 도달한 것 pop
for past_t in list(predicted_history.keys()):
    if past_t <= now:
        past_pred = predicted_history.pop(past_t)
        err = norm(sub(past_pred, r_rel_lvlh))
        print(f'  [verify] 10s ago 예측 vs 현재 실측 오차: {err:.1f} m')
```

**기대**:
- 분사 없을 때 오차 < 100 m
- 분사 중일 때 오차 급증 (CW 가 thrust 반영 못함)

---

## Step 5 — TLE 건전성 모니터 (15분, TODO [2])

교수님이 **chief 위치를 텔레포트**하면 TLE 추정치가 갑자기 점프. 감지:
```python
prev_r_chief = None

# 루프 안에서:
if prev_r_chief is not None:
    jump = norm(sub(r_c, prev_r_chief))
    # 정상 궤도 속도 ≈ 7.6 km/s → 1 sec 간 7600 m 이동이 normal
    # 이보다 훨씬 많이 튀면 텔레포트 의심
    if jump > 15000:
        print(f'\n⚠⚠⚠ TLE JUMP {jump:.0f} m — chief 텔레포트 의심 ⚠⚠⚠\n')
prev_r_chief = r_c
```

**팀에 알림**: ADCS/ODCS 담당도 이 경보를 보고 경계 모드 진입.

---

## Step 6 — 팀 공유 (10분)

### 옵션 A — CSV 로그
```python
import csv
log_f = open(f'/tmp/nav_{args.deputy}.csv', 'w', newline='')
log_w = csv.writer(log_f)
log_w.writerow(['t', 'dist', 'x_lvlh', 'y_lvlh', 'z_lvlh', 'vx', 'vy', 'vz'])

# 루프 안에서:
log_w.writerow([time.time(), dist, *r_rel_lvlh, *v_rel_lvlh_true])
log_f.flush()
```
팀이 나중에 그래프 그리거나 분석.

### 옵션 B — ROS 토픽 재퍼블리시
Navigation 결과를 다른 역할이 **구독**할 수 있게 ROS 토픽으로 재발행:
```python
nav_pub = roslibpy.Topic(
    client,
    f'/{args.deputy}/nav/relative_lvlh',
    'geometry_msgs/Point'    # 간단한 타입
)

# 루프 안에서:
nav_pub.publish(roslibpy.Message({
    'x': r_rel_lvlh[0],
    'y': r_rel_lvlh[1],
    'z': r_rel_lvlh[2]
}))
```

그러면 ODCS 코드에서:
```python
roslibpy.Topic(client, f'/{args.deputy}/nav/relative_lvlh',
               'geometry_msgs/Point').subscribe(on_nav)
```
바로 받아쓸 수 있음.

### 옵션 C — 음성/채팅
**가장 빠름**: 팀에게 구두로 "거리 500 m, 접근 속도 0.3 m/s, 30 초 후 100 m 예상". 세미나라서 가능.

---

## 도전 과제

### (1) 간단 EKF (Extended Kalman Filter)

GPS 1 Hz 는 드문드문. IMU 100 Hz 로 사이사이 **적분**해서 보간:
- Predict: 이전 state + IMU accel 로 전방 전파
- Update: GPS 도착 시 measurement 반영

상태: `[x, y, z, vx, vy, vz]` LVLH
프로세스 모델: CW 동역학
측정: GPS → LVLH 변환

(심화 과제. 팀에 수학 좋아하는 사람이 맡아서 구현.)

### (2) 접근 경로 계획

ODCS 한테 "지금 0.5 m/s 로 접근 중. 10 초 뒤 거리 495 m. 브레이크 burn 타이밍은 X 시간 후".

### (3) 다중 가설 추적

TLE 바이어스 때문에 "진짜 chief 위치" 가 ±100 m 범위. 몇 개 후보 궤적 유지하고 Vision 관측으로 좁혀가기 (파티클 필터).

---

## 흔한 실수

| 증상 | 원인 | 해결 |
|---|---|---|
| "waiting" 만 찍히고 값 안 나옴 | GPS 1 Hz, TLE 도 느림. 보통 2–3 초 걸림 | 더 기다려. 10 초 지나도 안 되면 `ros2 topic hz /deputy_*/gps/odometry` |
| 거리 계속 ±3 km 진동 | GPS-TLE 타임스탬프 비동기 | Step 3 스무딩 적용 |
| Coriolis 보정 후 v 여전히 큼 | 부호 실수 (외적) | `cross(OMEGA, r)` 순서 확인, `r × ω` 아님 |
| CW 예측이 실제와 완전 다름 | 분사 중이거나 초기속도 잘못됨 | 분사 없을 때만 검증 |
| TLE jump 경보 과다 | 임계치 15 km 가 너무 낮음 | 정상 속도 7.6 km/s × dt ≈ ? 고려 |

---

## 타 역할과 인터페이스

**출력 (Navigation → 타팀)**:
| 값 | 쓰는 곳 |
|---|---|
| `r_rel_LVLH` | ADCS (카메라 포인팅), ODCS (접근 방향) |
| `v_rel_LVLH` | ODCS (접근 속도 제어) |
| `dist_smoothed` | ODCS (단계 결정), Vision (기대 크기) |
| `CW forecast +30s` | ODCS (브레이크 burn 타이밍) |
| `TLE jump 경보` | 전원 (주의 모드) |

**입력 (타팀 → Navigation)**:
| 값 | 출처 |
|---|---|
| "지금 분사중" | ODCS (CW 예측 신뢰도 낮춤) |
| "chief 시각 확인됨" | Vision (TLE bias 보정 trigger) |

---

## 참고

- CW 해석해는 **상수 n 과 선형** 가정. J2 보정 없음 → 장시간(궤도 여러 바퀴) 전파 시 드리프트.
- ECI ↔ LVLH 변환은 chief 의 현재 r, v 를 기준. TLE 에 노이즈 있으면 basis 자체가 흔들림.
- 완성 스크립트 `completed/laptop_monitor.py` 와 Navigation 은 다름. monitor 는 raw 센서만 출력, navigation 은 **가공된 상황 해석**.
