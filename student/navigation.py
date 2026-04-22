#!/usr/bin/env python3
"""Navigation 담당 — 노트북 스타터 (rosbridge 경유).

[역할]
  GPS + Chief TLE 를 받아 상대 상태 계산 + CW 전파로 미래 위치 예측.
  ADCS / ODCS / Vision 에게 상황 브리핑 (거리, 접근 벡터, 도달 시간) 제공.
  TLE 건전성 모니터 (교수님 하드 방해 탐지).

[센서 입력]
  /deputy_*/gps/odometry    → 내 ECI 위치/속도 (노이즈 σ_pos=5 m, σ_vel=0.05 m/s)
  /chief/eci_state          → Chief TLE 추정 ECI (노이즈 σ=100 m + J2 drift)
  /deputy_*/imu/data        → 가속도계 (추력 감지용, 선택)

[출력 (콘솔 1 Hz)]
  * LVLH 상대 위치 (radial, along-track, cross-track)
  * 상대 거리 (m)
  * CW 전파 → +10 s / +30 s / +60 s 뒤 예상 위치
  * 접근 속도 (선택, 상대 속도 radial 성분)

[주의]
  - TLE 오차 ~100 m ~ 몇 km. CW 전파 정확도는 입력 상태의 스무딩 품질에 의존.
  - ODCS 담당에게 접근 전략(V-bar / R-bar / +z cross-track) 결정에 참고 제공.
  - 교수님이 chief 위치를 텔레포트하면 TLE 거리가 순간적으로 튀어오름 → 경보 로직 TODO.

사용법:
    python3 navigation.py --host 220.67.219.55 --deputy deputy_formation
"""
import argparse
import math
import time
from threading import Lock

import roslibpy

# ===================== 상수 =====================
N_MEAN = 1.0959e-3   # chief 평균 운동각속도 (rad/s). mission.sdf 와 동일.
T_ORBIT = 2 * math.pi / N_MEAN  # 궤도 주기 ≈ 5733 s

# ===================== CLI =====================
ap = argparse.ArgumentParser(
    description='Navigation: GPS + TLE → LVLH + CW forecast')
ap.add_argument('--host',   default='220.67.219.55')
ap.add_argument('--deputy', default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'))
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090)
client.run()
print(f'[nav] 접속: {args.host}:9090, deputy={args.deputy}')
print(f'[nav] CW n = {N_MEAN:.4e} rad/s, 주기 T = {T_ORBIT:.0f} s')

# ===================== 센서 구독 =====================
state = {}
lock = Lock()


def on_gps(msg):
    """GPS 콜백: deputy ECI 위치 + 속도."""
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['r_deputy_eci'] = (p['x'], p['y'], p['z'])
        state['v_deputy_eci'] = (v['x'], v['y'], v['z'])


def on_tle(msg):
    """Chief TLE 콜백: SGP4+노이즈 기반 ECI."""
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['r_chief_eci'] = (p['x'], p['y'], p['z'])
        state['v_chief_eci'] = (v['x'], v['y'], v['z'])


def on_imu(msg):
    """IMU 콜백: 가속도계 (body frame)."""
    a = msg['linear_acceleration']
    with lock:
        state['accel_body'] = (a['x'], a['y'], a['z'])


roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)
roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(on_imu)

# ===================== 벡터/행렬 헬퍼 =====================
def cross(a, b):
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])


def norm(v):
    return math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])


def scale(v, s):
    return (v[0]*s, v[1]*s, v[2]*s)


def sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def mat_vec(M, v):
    """M = 3 rows tuple. 각 row 가 basis vector. 반환: M @ v."""
    return (dot(M[0], v), dot(M[1], v), dot(M[2], v))


def eci_to_lvlh_basis(r_chief, v_chief):
    """Chief pose 에서 LVLH basis (행렬 형태). r_chief != 0 가정.

    LVLH (Hill frame):
        x̂ = r_chief / |r_chief|               (radial outward)
        ẑ = (r × v) / |r × v|                 (orbit normal)
        ŷ = ẑ × x̂                            (along-track)
    """
    x_hat = scale(r_chief, 1.0 / norm(r_chief))
    h = cross(r_chief, v_chief)
    z_hat = scale(h, 1.0 / norm(h))
    y_hat = cross(z_hat, x_hat)
    return (x_hat, y_hat, z_hat)


def cw_forecast(r, v, dt, n=N_MEAN):
    """CW 해석해 기반 전파.

    Input:
        r = (x, y, z) LVLH 위치 (m)
        v = (vx, vy, vz) LVLH 속도 (m/s)
        dt = 전파 시간 (s)

    Return:
        (r_future, v_future) LVLH
    """
    c, s = math.cos(n * dt), math.sin(n * dt)
    x0, y0, z0 = r
    vx0, vy0, vz0 = v
    x_f = (4 - 3*c)*x0 + s/n * vx0 + 2/n*(1 - c)*vy0
    y_f = 6*(s - n*dt)*x0 + y0 - 2/n*(1 - c)*vx0 + (4*s - 3*n*dt)/n * vy0
    z_f = c*z0 + s/n * vz0
    vx_f = 3*n*s*x0 + c*vx0 + 2*s*vy0
    vy_f = 6*n*(c - 1)*x0 - 2*s*vx0 + (4*c - 3)*vy0
    vz_f = -n*s*z0 + c*vz0
    return (x_f, y_f, z_f), (vx_f, vy_f, vz_f)


# ===================== 메인 루프 =====================
print('[nav] 센서 수신 대기 중 (GPS 1 Hz + TLE 1 Hz 모두 필요)...\n')

last_tle_dist = None  # 이전 tick 의 거리 (TLE 점프 감지용)

try:
    while True:
        time.sleep(1.0)
        with lock:
            r_d = state.get('r_deputy_eci')
            v_d = state.get('v_deputy_eci')
            r_c = state.get('r_chief_eci')
            v_c = state.get('v_chief_eci')

        if not (r_d and v_d and r_c and v_c):
            print('  [waiting] gps/tle 수신 중...')
            continue

        # 1. ECI 상대 벡터
        r_rel_eci = sub(r_d, r_c)
        v_rel_eci = sub(v_d, v_c)

        # 2. LVLH basis (chief 기준)
        R = eci_to_lvlh_basis(r_c, v_c)

        # 3. 상대 위치/속도 LVLH 변환
        #    NOTE: 회전 프레임이라 속도에는 Coriolis 보정 필요.
        #    v_rel_LVLH = R @ v_rel_ECI - ω × r_rel_LVLH, ω = (0, 0, n)
        #    아래는 근사 (순수 좌표변환). Coriolis 보정은 TODO.
        r_rel_lvlh = mat_vec(R, r_rel_eci)
        v_rel_lvlh = mat_vec(R, v_rel_eci)  # approx

        # 4. 상대 거리
        dist = norm(r_rel_lvlh)

        # 5. CW 전파 예측 10s / 30s / 60s
        r10, _ = cw_forecast(r_rel_lvlh, v_rel_lvlh, 10.0)
        r30, _ = cw_forecast(r_rel_lvlh, v_rel_lvlh, 30.0)
        r60, _ = cw_forecast(r_rel_lvlh, v_rel_lvlh, 60.0)

        # 6. 접근 속도 (radial 성분, 음수 = 접근 중)
        v_radial = v_rel_lvlh[0]  # x 성분이 radial (chief→deputy 방향)

        # 출력
        print(f'[nav] dist={dist:8.1f} m  '
              f'LVLH=({r_rel_lvlh[0]:+8.1f}, {r_rel_lvlh[1]:+8.1f}, {r_rel_lvlh[2]:+7.1f})  '
              f'v_rad={v_radial:+.3f} m/s')
        print(f'      CW +10s LVLH=({r10[0]:+8.1f}, {r10[1]:+8.1f}, {r10[2]:+7.1f})')
        print(f'      CW +30s LVLH=({r30[0]:+8.1f}, {r30[1]:+8.1f}, {r30[2]:+7.1f})')
        print(f'      CW +60s LVLH=({r60[0]:+8.1f}, {r60[1]:+8.1f}, {r60[2]:+7.1f})')

        # ----------------------------------------------------------------
        # TODO: 학생이 구현할 부분!
        #
        # [1] Coriolis 보정 (정확한 LVLH 속도)
        #     ω = (0, 0, N_MEAN)
        #     v_rel_lvlh_true = v_rel_lvlh_approx - cross(ω, r_rel_lvlh)
        #
        # [2] TLE 건전성 모니터 — 교수님 하드 방해 감지
        #     - 지난 tick 대비 dist 변화가 |Δdist| > 500 m 이면
        #       "⚠ TLE JUMP — chief 텔레포트 가능성!"
        #     - CW 예측치 vs 실제 관측 차이가 누적되면 TLE 바이어스 의심
        #
        # [3] 임무 단계 결정
        #     - 팀 Formation (5 km): dist > 100 m → "장거리 접근 단계"
        #                            5 m < dist < 100 m → "근접 정렬"
        #                            dist < 5 m → "편대 유지 루프"
        #     - 팀 Docking (5 km → 1 m): 단계별 접근 속도 상한 가이드
        #
        # [4] 팀 공유
        #     - 결과를 CSV 로그로 저장해서 사후 분석
        #     - Discord/Slack webhook 으로 거리 push
        #     - 또는 별도 ROS 토픽 발행해서 ADCS/ODCS 가 구독
        # ----------------------------------------------------------------

        last_tle_dist = dist

except KeyboardInterrupt:
    print('\n[nav] 종료')

client.terminate()
