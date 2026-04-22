# ADCS 실습 — 자세 결정 및 제어 (Attitude Determination & Control System)

**역할**: Star Tracker + IMU 로 현재 자세 파악 → Reaction Wheel 로 목표 자세 추종.
**짝 코드**: `student/attitude_controller.py`
**팀 공통**: Formation 팀 / Docking 팀 모두 필요.

---

## 오늘 할 일

1. 센서 데이터 확인 (Star Tracker 쿼터니언, 자이로, 가속도계)
2. 쿼터니언 연산 헬퍼 구현
3. 간단한 P 제어기로 현재 자세 "홀드"
4. D 항 추가해서 진동 감쇠 (PD)
5. 교수님의 외란 토크에 대응해 자세 복구
6. (도전) LVLH 프레임 정렬 / chief 포인팅

---

## 성공 기준 (실습 중 즉석 결정)

- [ ] rw 명령으로 body 회전 멈추기 (detumble) — Navigation 이 알려주는 ω 값 기준
- [ ] 목표 자세 근처에서 흔들림이 몇 ° 이하로 수렴
- [ ] 교수님이 외란 가했을 때 몇 초 내 복구

---

## 스캐폴드가 이미 해 준 것

`attitude_controller.py` 열어보면:
- rosbridge 접속 + 센서 구독 (`on_imu`, `on_star_tracker`)
- `state` dict 에 최신값 저장 (thread-safe)
- `send_rw(x, y, z)` 헬퍼 — 3축 RW 토크 한번에 발행
- 1 Hz print 루프 + `KeyboardInterrupt` 시 자동 `send_rw(0,0,0)`

→ 너희가 추가해야 할 건 **`# ▼▼▼ 여기에 제어 로직 넣기 ▼▼▼`** 아래 한 줄.

---

## Step 1 — 센서 그대로 관찰 (5분)

아무것도 바꾸지 말고 실행:
```bash
python3 student/attitude_controller.py --host 220.67.219.55 --deputy deputy_formation
```
(팀 Docking 이면 `deputy_docking`.)

1 Hz 로 출력되는 값 해석:
```
[GYRO]  (+1.0e-05, +2.3e-05, +1.10e-03) rad/s     ← z 값 ~0.0011 가 기본
[ACCEL] (+3.2e-04, -5.1e-04, -1.1e-03) m/s²       ← noise만 있으면 ~1e-3 수준
[Q]     (+0.0012, -0.0008, +0.7071, +0.7071)       ← body-in-ECI 쿼터니언
```

**체크**:
- 자이로 z 가 **약 1.1e-3 rad/s** 가 기본값 — chief 궤도 주기(n=1.0959e-3 rad/s)와 일치. LVLH 회전 때문.
- 가속도계는 추력 안 걸면 거의 0 (노이즈만).
- Star Tracker 쿼터니언은 body 축이 ECI 에서 어디 향하는지. 기동 안 했으면 거의 일정.

**안 보이면**: 서버 IP/포트/rosbridge 살아있는지 확인. `Test-NetConnection 220.67.219.55 -Port 9090`.

---

## Step 2 — 쿼터니언 수학 헬퍼 (10분)

코드 위쪽에 추가:

```python
def q_conj(q):
    """쿼터니언 켤레 (x,y,z,w) → (-x,-y,-z,w)."""
    return (-q[0], -q[1], -q[2], q[3])

def q_mul(a, b):
    """쿼터니언 곱 a ⊗ b (x,y,z,w 순서)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
        aw*bw - ax*bx - ay*by - az*bz,
    )

def q_to_axis_angle(q):
    """작은 회전 근사: 2*[x, y, z] ≈ rotation vector (rad)."""
    return (2.0*q[0], 2.0*q[1], 2.0*q[2])
```

**검증**: 별도 터미널에서 테스트
```python
>>> q_mul(q_conj((0,0,0,1)), (0,0,0,1))     # identity ⊗ identity
(0.0, 0.0, 0.0, 1.0)
>>> q_to_axis_angle((0.05, 0, 0, 0.999))     # 작은 roll
(0.1, 0.0, 0.0)
```

---

## Step 3 — "현재 자세 홀드" P 제어 (15분)

목표: 지금 이 순간의 자세를 유지 (더 이상 돌지 않게 만들기).

```python
# ===================== 초기 상태 저장 =====================
q_target = None     # 시작 시점의 자세를 target 으로 삼음
Kp = 2.0            # 비례 게인 (N·m/rad)

try:
    while True:
        time.sleep(0.2)     # 5 Hz 로 빠르게
        with lock:
            q = state.get('q_eci')
            gyro = state.get('gyro')
        if not (q and gyro):
            continue

        # 시작 시점 자세를 목표로
        if q_target is None:
            q_target = q
            print(f'  [lock] target = {q_target}')
            continue

        # 자세 오차 (target 기준 body 좌표계)
        q_err = q_mul(q_conj(q_target), q)
        theta = q_to_axis_angle(q_err)      # (θx, θy, θz) rad

        # P 제어 — 오차 반대 방향으로 토크
        tau_x = -Kp * theta[0]
        tau_y = -Kp * theta[1]
        tau_z = -Kp * theta[2]
        send_rw(tau_x, tau_y, tau_z)

        print(f'  [P] err=({theta[0]:+.3f},{theta[1]:+.3f},{theta[2]:+.3f}) rad  '
              f'tau=({tau_x:+.3f},{tau_y:+.3f},{tau_z:+.3f})')
```

실행 후:
- 교수님/팀원이 위성에 약한 외란 토크 줌 → 오차 생김 → P 제어가 반대 토크로 복구 시도
- 진동(overshoot) 가능. 다음 Step 에서 D 항으로 잡는다.

---

## Step 4 — D 항 추가 (PD, 10분)

위 코드에 `Kd` 와 gyro 피드백 추가:

```python
Kd = 5.0   # 미분 게인 (N·m / (rad/s))

# (while 루프 안에서)
tau_x = -Kp * theta[0] - Kd * gyro[0]
tau_y = -Kp * theta[1] - Kd * gyro[1]
tau_z = -Kp * theta[2] - Kd * gyro[2]
```

**게인 튜닝 팁** (100 kg 위성, Ixx=Iyy=14, Izz=10 kg·m² 기준):
- 시정수 목표 τ = 10 s 이면  Kd / I ≈ 1/τ → Kd ≈ 1
- 진동 안 나려면 ζ ≈ 1 (critically damped): Kd² ≈ 4·Kp·I → Kp = Kd²/(4·I)
- 예: Kd=5, I=14 → Kp ≈ 0.45. 너무 느리면 Kp 올리고 Kd 도 같이 올린다.
- plugin clamp = ±0.1 N·m 이므로 큰 오차에선 포화. `min(0.1, max(-0.1, tau))` 로 수동 saturation 해도 무방.

**체크**: 진동이 1–2 사이클에 수렴하는지.

---

## Step 5 — 외란 대응 테스트 (10분)

교수님/다른 팀원이:
```bash
# 외부에서 deputy 에 외란 토크 주입
python3 student/completed/laptop_rw.py --host 220.67.219.55 \
    --deputy deputy_formation --axis z --torque 0.05 --duration 3
```
→ yaw 방향 외란 가해짐.

**기대 결과**: PD 제어가 반대 토크를 내서 1–2초 뒤 yaw 오차를 다시 0 근처로 복원.

그래프 그리려면 `csv` 로 시간/오차/토크 기록:
```python
import csv
log_f = open(f'/tmp/adcs_{args.deputy}.csv', 'w', newline='')
log_w = csv.writer(log_f)
log_w.writerow(['t', 'err_x', 'err_y', 'err_z', 'tau_x', 'tau_y', 'tau_z'])
# 루프 안에:
log_w.writerow([time.time(), *theta, tau_x, tau_y, tau_z])
log_f.flush()
```

---

## 도전 과제

### (1) LVLH 정렬 — chief 따라 천천히 yaw 회전

LVLH 프레임은 ECI 기준 **n = 1.0959e-3 rad/s** 로 yaw 돈다. 이 각속도를 맞춰주면 **body 축이 LVLH 에 고정**. target 쿼터니언이 시간에 따라 회전해야 함. 힌트:
```python
# LVLH-in-ECI 쿼터니언을 ω_z = n 으로 스스로 propagate
```
Navigation 담당에게 LVLH-ECI 관계 물어보기.

### (2) Chief 포인팅 (팀 Formation 편대 관측 임무)

Navigation 이 알려주는 `r_rel_LVLH` (chief 방향 벡터) 를 body frame 으로 변환 → 카메라 z축이 그 방향 향하도록 target 설정. Vision 담당과 협조:
```
Vision: "chief 가 화면 왼쪽 아래 있음"
ADCS:   "yaw +3°, pitch -2° 돌림"
Vision: "좋아, 이제 가운데 왔어"
```

### (3) 교수님 하드 방해 감지

자이로 z 가 보통 1.1e-3 인데 갑자기 1.0e-1 이런 값 찍히면 외란 발생. 감지 알고리즘 만들어서 자동 Detumble 모드 진입.

---

## 흔한 실수

| 증상 | 원인 | 해결 |
|---|---|---|
| 값 수신 안 됨 | rosbridge 서버 오류 or 잘못된 IP | `Test-NetConnection ...` |
| RW 명령 보내도 안 움직임 | `--deputy` 오타 | `choices` 로 타입 체크됨 |
| P 게인 키워도 여전히 느리게 수렴 | 토크가 ±0.1 포화 | Kp 낮추거나 Kd 증가 |
| `KeyboardInterrupt` 눌러도 RW 안 멈춤 | stop 메시지 유실 race | scaffold 가 이미 `send_rw(0,0,0)` 호출. 10초 기다려도 회전 지속이면 opposite torque 로 Detumble |
| yaw 방향 계속 누적 | ADCS 명령 없는 상태에서 각운동량 보존 | 반대 부호로 상쇄 토크 필요 |

---

## Navigation 팀과 협업 포인트

Navigation 이 계산해주는 값 중 ADCS 가 쓸 것:
- **r_rel_LVLH**: chief 가 어느 방향인지 (카메라 포인팅용)
- **ω_LVLH = (0, 0, n)**: LVLH 기본 회전율 (자이로에서 뺄 값)

→ 같은 팀이면 한 화면에 navigation.py 띄워놓고 수치 보면서 제어.

---

## 참고

- 쿼터니언 오차가 180° 넘으면 small-angle 근사 깨짐. 큰 기동 시 `q_err` 부호 체크 (`if q_err[3] < 0: q_err = -q_err`).
- 실제 RW는 momentum saturation 있음 — 이 시뮬은 몰라도 되나 개념은 기억.
