# ODCS 실습 — 궤도 결정 및 제어 (Orbit Determination & Control System)

**역할**: GPS + Navigation 이 준 상대 상태 → 추력기 발사로 궤도 기동.
**짝 코드**: `student/orbit_controller.py`
**팀별 목표 다름**:
- **Formation 팀**: chief 기준 **50 m GCO** 로 이동 (편대 유지)
- **Docking 팀**: **5 km → 1 m** 접근

---

## 오늘 할 일

1. 상대 상태 관찰 (GPS, TLE, 가속도계)
2. 한 방향 테스트 분사 (1 N 미만, 짧게)
3. 거리 기반 접근 속도 전략
4. V-bar 접근 (along-track)
5. 브레이크 버닝 (정지)
6. (도전) CW 기반 2-impulse 전이

---

## 성공 기준 (실습 중 즉석 결정)

- [ ] 테스트 분사로 가속도계에 반응 확인
- [ ] 팀 Formation: 상대 거리 ~50 m 근처 유지
- [ ] 팀 Docking: 상대 거리 **몇 m 이하 + 접근 속도 몇 m/s 이하**
- [ ] 충돌 없이 (overshoot 거리 < target)

---

## 스캐폴드가 이미 해 준 것

`orbit_controller.py`:
- 센서 구독 (`on_gps`, `on_tle`, `on_imu`)
- 6개 추력기 publisher (`thrusters['fy_plus']` 등)
- `fire(axis, throttle)` / `stop_all()` 헬퍼
- `vec_sub`, `vec_norm` 벡터 헬퍼
- 1 Hz print 루프 + `KeyboardInterrupt` 시 자동 `stop_all()`

너희 할 일: **접근 전략 로직을 `# ▼▼▼ 여기에 ... ▼▼▼` 아래 추가**.

---

## Step 1 — 상대 상태 관찰 (5분)

```bash
python3 student/orbit_controller.py --host 220.67.219.55 --deputy deputy_docking
```

출력 예:
```
  [REL] 상대벡터: (-30,+4990,-10) m  거리: 4990 m (4.99 km)
```

**관찰**:
- Docking 팀은 **거리 ~5000 m 근처** 출발
- Formation 팀은 **거리 ~5000 m 근처** 출발 (목표는 편대 50 m 로 이동)
- TLE 노이즈로 수치가 ±수백 m 진동. Navigation 담당이 Coriolis 보정해주면 덜 덜덜.

---

## Step 2 — 단축 분사 테스트 (10분)

코드 수정 없이 **완성 스크립트**로 잠깐 쏴보기:
```bash
# 별도 터미널
python3 student/completed/laptop_thruster.py --host 220.67.219.55 \
    --deputy deputy_docking --axis fy_plus --throttle 1.0 --duration 2
```
→ `orbit_controller.py` 쪽에서 `[추력중! |a|=0.099]` 찍히는지 확인 (가속도 ≈ 0.1 m/s², 100 kg · 10 N / 100 kg).

**주의**: 분사 끝나도 관성으로 계속 이동함 (우주). **같은 크기로 반대 방향 쏴야 정지**.

---

## Step 3 — 거리 기반 throttle 전략 (15분)

단순한 단계식 제어:

```python
# while 루프 안에서
with lock:
    if 'gps_pos' not in state or 'tle_pos' not in state:
        continue
    dr = vec_sub(state['tle_pos'], state['gps_pos'])    # chief - deputy (ECI)
    dist = vec_norm(dr)

# 거리별 목표 속도
if dist > 1000:
    target_v = 1.0      # 원거리: 1 m/s
elif dist > 100:
    target_v = 0.3      # 중거리
elif dist > 10:
    target_v = 0.05     # 근접
else:
    target_v = 0.01     # 도킹 직전

# 간단화: 항상 +y 방향으로 접근 (docking 팀)
# 실제 v_y 계산은 gps_vel 필요
vy = state['gps_vel'][1]

err_v = target_v - vy   # 부호 주의: deputy_docking 은 +y 방향이 chief 쪽
if err_v > 0.02:
    fire('fy_plus', 0.5)    # 가속
elif err_v < -0.02:
    fire('fy_minus', 0.5)   # 감속 (브레이크)
else:
    stop_all()              # 순항
```

**체크**:
- 가속도계 값이 분사 중엔 0 아님 → OK
- 거리 줄어드는지 모니터 (Navigation 도 거리 표시해줌)

---

## Step 4 — V-bar 접근 (along-track, 10분)

CW 에서 **y 방향(along-track) 분사는 안정적**. x(radial)는 커플링 때문에 더 복잡.

Formation 팀 출발: `(0, +5000, 0)` LVLH
Docking 팀 출발: `(0, -5000, 0)` LVLH

각 팀이 chief(원점) 쪽으로 가려면:
- Formation (y=+5000): `fy_minus` 로 -y 방향 분사 (→ chief 쪽)
- Docking (y=-5000): `fy_plus` 로 +y 방향 분사 (→ chief 쪽)

```python
# --deputy 값에 따라 접근 방향 정하기
if args.deputy == 'deputy_formation':
    approach_axis = 'fy_minus'   # y 감소 방향
    sign = -1
else:   # docking
    approach_axis = 'fy_plus'
    sign = +1

# 목표 속도: chief 쪽으로 (부호는 sign)
target_vy = sign * target_v
err = target_vy - vy
# ...
```

---

## Step 5 — 브레이크 버닝 (10분)

도킹 시나리오: 10 m 이내 접근 시 **멈춰야 함**.
```python
if dist < 10:
    # 모든 축 속도를 0 에 맞추기
    for axis_idx, (plus, minus) in enumerate([('fx_plus','fx_minus'),
                                              ('fy_plus','fy_minus'),
                                              ('fz_plus','fz_minus')]):
        v_axis = state['gps_vel'][axis_idx]
        if v_axis > 0.01:
            fire(minus, 0.5)
        elif v_axis < -0.01:
            fire(plus, 0.5)
```

**안전 팁**: 접근 속도 ≤ 0.05 m/s 로 들어와야 overshoot 적음. 빠르게 오면 브레이크가 한 step 늦어서 충돌/미스.

---

## 도전 과제

### (1) CW 2-impulse 전이

CW 해석해를 써서 **두 번의 분사**로 정확히 target 위치에 도달:
1. 현재 위치 r0, target r1, 이동 시간 Δt 선택
2. CW 역방정식: 초기 속도 v0 = f(r0, r1, Δt) 계산
3. 첫 번째 impulse: 속도를 v0 으로 맞추는 Δv1
4. Δt 후 두 번째 impulse: 도착 속도를 원하는 값으로 맞추는 Δv2

Navigation 담당에게 `r_rel_LVLH`, `v_rel_LVLH` 실시간으로 받기.

### (2) Formation 팀 — 50 m GCO 주입

GCO (General Circular Orbit): chief 주변 50 m 반경 원운동. CW 해석적으로:
```
x(t) = A cos(nt + φ)
y(t) = -2A sin(nt + φ)
z(t) = B cos(nt + ψ)
```
→ 초기 조건 x=A, vx=0, y=0, vy=-2nA, z=0, vz=0 이면 Formation 유지.
A = 50 m 로 주입하는 Δv 계산.

### (3) Hill frame 전환

지금까지는 ECI 좌표로 대충 계산. Navigation 이 주는 LVLH 좌표로 바꾸면 훨씬 깔끔. 같은 팀이면 프로토콜 약속:
```
Nav     → prints  "r_rel_LVLH=(-30,+4990,-10)"
ODCS    reads it manually, or ODCS reads /deputy_*/nav/relative 토픽
```

---

## 흔한 실수

| 증상 | 원인 | 해결 |
|---|---|---|
| 가속도 항상 0 | 추력기 명령 안 감 | `--deputy` 매치? `fire('fy_plus', 0.5)` throttle > 0? |
| 거리 안 줄어듦 | 반대 방향 분사 | `args.deputy` 조건분기 확인 |
| 멈췄는데도 거리 계속 변함 | 우주 관성 — 반대 Δv 필요 | `KeyboardInterrupt` → `stop_all()` 는 throttle=0 만. 속도는 안 줄임. 브레이크 burn 필요 |
| 거리 수치가 3 km 왔다갔다 | GPS-TLE 타임스탬프 비동기 | Navigation 담당이 Coriolis 보정 + 스무딩 구현하면 개선 |
| 가까이 왔는데 갑자기 멀어짐 | overshoot + CW 커플링 (radial 방향 분사 시) | V-bar (y축) 만 써라 |

---

## Navigation / ADCS 팀과 협업

**입력**: Navigation 이 제공
- 정제된 LVLH 상대 위치/속도
- 접근 속도 권장치 (거리별)
- Chief 가 어느 방향 (ECI 벡터)

**출력**: ADCS 에게 알려야 할 것
- "지금 x 방향 분사 중" → 가속도계 외란 예상 알림
- "10 m 이내" → 카메라 포인팅 요청

---

## 참고

- 추력기는 0/1 bang-bang 이 아니라 throttle [0,1] 연속값 가능.
- CW 동역학: radial(+x) 분사는 along-track(y) 으로 흘러감. **단축 분사가 하나의 축만 가속시키지 않음**.
- 완전한 정지는 연료 낭비. 임무상 필요할 때만.
