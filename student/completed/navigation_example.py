#!/usr/bin/env python3
"""[완성 예시] Navigation — 상대 상태 추정 + CW 전파 + TLE 건전성 모니터.

Navigation 담당은 actuator 안 씀. "팀의 두뇌" 로 센서 융합 결과를 콘솔에
뿌리고 (선택) CSV 에 기록. 이 예시에는 navigation.py 스캐폴드의 4 개
TODO 가 전부 채워져 있음:

    [1] Coriolis 보정 — LVLH 속도를 정확히 계산
    [2] 거리 스무딩 — 10 샘플 이동평균으로 TLE 노이즈 완화
    [3] CW 예측 vs 실제 검증 — 10 초 전 예측치와 현재 관측 비교
    [4] TLE 점프 감지 — chief 위치가 비정상적으로 튀면 경보

사용법:
    python3 navigation_example.py --host 220.67.219.55 --deputy deputy_formation
    python3 navigation_example.py --host 220.67.219.55 --deputy deputy_docking --log-csv /tmp/nav.csv
"""

# ─────────────────────────────────────────────────────────────────────
# 1) Imports
#    collections.deque : 고정 길이 큐 (이동평균용, 초과분 자동 제거)
#    math              : sqrt, cos, sin, pi
# ─────────────────────────────────────────────────────────────────────
import argparse
import csv
import math
import time
from collections import deque
from threading import Lock

import roslibpy


# ─────────────────────────────────────────────────────────────────────
# 2) 물리 상수
#    N_MEAN : chief orbit 평균 운동각속도 [rad/s]. 545 km SSO 에서 계산된 값.
#             이 값이 mission.sdf 의 CW plugin 과 반드시 일치해야 함.
#    T_ORBIT: 궤도 주기 = 2π/n ≈ 5733 s
# ─────────────────────────────────────────────────────────────────────
N_MEAN  = 1.0959e-3
T_ORBIT = 2 * math.pi / N_MEAN


# ─────────────────────────────────────────────────────────────────────
# 3) 명령줄 인자
# ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--host',    default='220.67.219.55')
ap.add_argument('--deputy',  default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'))
ap.add_argument('--log-csv', default=None,
                help='지정하면 매 tick 결과를 CSV 로 저장 (예: /tmp/nav.csv)')
args = ap.parse_args()


# ─────────────────────────────────────────────────────────────────────
# 4) rosbridge 접속
# ─────────────────────────────────────────────────────────────────────
client = roslibpy.Ros(host=args.host, port=9090)
client.run()
print(f'[nav] 접속: {args.host}:9090  target={args.deputy}')
print(f'[nav] n={N_MEAN:.4e} rad/s  orbit T={T_ORBIT:.0f} s')


# ─────────────────────────────────────────────────────────────────────
# 5) 센서 구독 (GPS, TLE)
# ─────────────────────────────────────────────────────────────────────
state = {}
lock  = Lock()

def on_gps(msg):
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['r_me'] = (p['x'], p['y'], p['z'])
        state['v_me'] = (v['x'], v['y'], v['z'])

def on_tle(msg):
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['r_ch'] = (p['x'], p['y'], p['z'])
        state['v_ch'] = (v['x'], v['y'], v['z'])

roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)


# ─────────────────────────────────────────────────────────────────────
# 6) 벡터 수학 (numpy 없이)
#    ECI → LVLH 변환에 필요한 것들만.
# ─────────────────────────────────────────────────────────────────────
def sub3(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def add3(a, b):
    return (a[0]+b[0], a[1]+b[1], a[2]+b[2])

def scale3(v, s):
    return (v[0]*s, v[1]*s, v[2]*s)

def dot3(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def cross3(a, b):
    """외적 a × b."""
    return (a[1]*b[2] - a[2]*b[1],
            a[2]*b[0] - a[0]*b[2],
            a[0]*b[1] - a[1]*b[0])

def norm3(v):
    return math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])


# ─────────────────────────────────────────────────────────────────────
# 7) ECI → LVLH 좌표계 basis 계산
#    LVLH (Hill frame):
#        x̂ = r_chief / |r_chief|            (radial out, 지구 반대 방향)
#        ẑ = (r × v) / |r × v|               (orbit normal)
#        ŷ = ẑ × x̂                          (along-track, velocity 방향)
#    반환: 3×3 회전행렬 역할의 tuple of tuple. 곱하면 ECI → LVLH.
# ─────────────────────────────────────────────────────────────────────
def eci_to_lvlh_basis(r_ch, v_ch):
    # x̂ = r / |r|
    rn = norm3(r_ch)
    x_hat = scale3(r_ch, 1.0/rn)
    # h = r × v  (orbit 각운동량 방향), ẑ = h / |h|
    h = cross3(r_ch, v_ch)
    hn = norm3(h)
    z_hat = scale3(h, 1.0/hn)
    # ŷ = ẑ × x̂
    y_hat = cross3(z_hat, x_hat)
    return (x_hat, y_hat, z_hat)


def eci_to_lvlh(v_eci, basis):
    """ECI 좌표계 벡터를 LVLH 로 회전."""
    return (dot3(basis[0], v_eci),
            dot3(basis[1], v_eci),
            dot3(basis[2], v_eci))


# ─────────────────────────────────────────────────────────────────────
# 8) Coriolis 보정
#    LVLH 는 회전 프레임이므로 속도 변환에 Coriolis 보정 필요.
#    v_LVLH = R·v_ECI − ω × r_LVLH       where ω = (0, 0, N_MEAN)
#    (회전축 = orbit normal = LVLH z 축)
# ─────────────────────────────────────────────────────────────────────
OMEGA_LVLH = (0.0, 0.0, N_MEAN)

def correct_lvlh_velocity(v_lvlh_approx, r_lvlh):
    coriolis = cross3(OMEGA_LVLH, r_lvlh)
    return sub3(v_lvlh_approx, coriolis)


# ─────────────────────────────────────────────────────────────────────
# 9) CW (Clohessy-Wiltshire) 해석적 전파
#    dt 초 뒤 상대 위치 예측 (무추력 가정).
#    공식: Hill/CW equations analytical solution.
# ─────────────────────────────────────────────────────────────────────
def cw_forecast(r, v, dt, n=N_MEAN):
    c, s = math.cos(n*dt), math.sin(n*dt)
    x0, y0, z0 = r
    vx0, vy0, vz0 = v
    x = (4 - 3*c)*x0 + s/n * vx0 + 2/n*(1 - c)*vy0
    y = 6*(s - n*dt)*x0 + y0 - 2/n*(1 - c)*vx0 + (4*s - 3*n*dt)/n * vy0
    z = c*z0 + s/n * vz0
    return (x, y, z)


# ─────────────────────────────────────────────────────────────────────
# 10) 거리 스무딩 (이동평균 필터)
#     deque(maxlen=10) 에 최근 10 샘플 저장. 평균 내면 TLE 노이즈 감쇠.
# ─────────────────────────────────────────────────────────────────────
dist_window = deque(maxlen=10)
def smooth(new_value):
    dist_window.append(new_value)
    return sum(dist_window) / len(dist_window)


# ─────────────────────────────────────────────────────────────────────
# 11) TLE 점프 감지
#     정상이면 chief ECI 는 궤도 속도 ~7.6 km/s 로 연속 이동. 1 초 간격
#     샘플의 차이는 약 7.6 km 내. 그보다 훨씬 크면 "순간이동" 의심 →
#     교수님이 외란 가했거나 TLE 데이터 오류.
#     임계치 15 km : 정상 7.6 km 의 2 배. 여유있게.
# ─────────────────────────────────────────────────────────────────────
JUMP_THRESHOLD_M = 15000.0
prev_r_ch = None


# ─────────────────────────────────────────────────────────────────────
# 12) CW 예측 검증용 히스토리
#     key = 검증 시각 (t0 + 10 초 뒤 예정), value = 예측한 r_LVLH
#     현재 시각이 key 를 넘으면 꺼내서 실제값과 비교.
# ─────────────────────────────────────────────────────────────────────
forecast_history = {}


# ─────────────────────────────────────────────────────────────────────
# 13) CSV 로거 초기화 (선택)
# ─────────────────────────────────────────────────────────────────────
log_writer = None
log_file = None
if args.log_csv:
    log_file = open(args.log_csv, 'w', newline='')
    log_writer = csv.writer(log_file)
    log_writer.writerow(['t', 'dist_m', 'dist_smooth',
                         'x_lvlh', 'y_lvlh', 'z_lvlh',
                         'vx_lvlh', 'vy_lvlh', 'vz_lvlh',
                         'tle_jump'])
    print(f'[nav] CSV 로깅: {args.log_csv}')


# ─────────────────────────────────────────────────────────────────────
# 14) 메인 루프 (1 Hz)
# ─────────────────────────────────────────────────────────────────────
print('[nav] 센서 수신 대기 (GPS 1 Hz + TLE 1 Hz)...\n')

try:
    while True:
        time.sleep(1.0)
        # 센서 snapshot
        with lock:
            r_me = state.get('r_me')
            v_me = state.get('v_me')
            r_ch = state.get('r_ch')
            v_ch = state.get('v_ch')
        if not (r_me and v_me and r_ch and v_ch):
            print('  [waiting] GPS/TLE ...')
            continue

        # ─── (4) TLE 점프 감지 ─────────────────────
        tle_jump_flag = 0
        if prev_r_ch is not None:
            jump = norm3(sub3(r_ch, prev_r_ch))
            if jump > JUMP_THRESHOLD_M:
                tle_jump_flag = 1
                print(f'\n⚠⚠⚠  TLE JUMP  {jump:.0f} m — chief 텔레포트 or '
                      f'TLE 이상!  ⚠⚠⚠\n')
        prev_r_ch = r_ch

        # ─── ECI 상대 벡터 ─────────────────────────
        r_rel_eci = sub3(r_me, r_ch)
        v_rel_eci = sub3(v_me, v_ch)

        # ─── ECI → LVLH basis from chief pose ─────
        R = eci_to_lvlh_basis(r_ch, v_ch)

        # 상대 위치 LVLH
        r_rel_lvlh = eci_to_lvlh(r_rel_eci, R)
        # 속도 LVLH (Coriolis 전 근사)
        v_rel_lvlh_raw = eci_to_lvlh(v_rel_eci, R)

        # ─── (1) Coriolis 보정 ───────────────────
        v_rel_lvlh = correct_lvlh_velocity(v_rel_lvlh_raw, r_rel_lvlh)

        # ─── (2) 거리 스무딩 ─────────────────────
        dist_raw = norm3(r_rel_lvlh)
        dist_sm  = smooth(dist_raw)

        # ─── CW 전파 ──────────────────────────────
        r10 = cw_forecast(r_rel_lvlh, v_rel_lvlh, 10.0)
        r30 = cw_forecast(r_rel_lvlh, v_rel_lvlh, 30.0)
        r60 = cw_forecast(r_rel_lvlh, v_rel_lvlh, 60.0)

        # ─── (3) 10 초 전 예측 vs 현재 실측 ───────
        now = time.time()
        forecast_history[now + 10.0] = r_rel_lvlh   # 미래 나와 비교하려고 예측
        err_str = ''
        for past_t in list(forecast_history.keys()):
            if past_t <= now:
                predicted = forecast_history.pop(past_t)
                # 10 초 전 예측이 현재 실측과 얼마나 다른지
                diff = norm3(sub3(predicted, r_rel_lvlh))
                err_str = f'  [verify] 10s pred err = {diff:.1f} m'

        # ─── 출력 ─────────────────────────────────
        print(f'[nav] dist raw={dist_raw:8.1f}  smooth={dist_sm:8.1f} m   '
              f'LVLH=({r_rel_lvlh[0]:+7.1f}, {r_rel_lvlh[1]:+7.1f}, '
              f'{r_rel_lvlh[2]:+7.1f})  '
              f'v=({v_rel_lvlh[0]:+.3f}, {v_rel_lvlh[1]:+.3f}, '
              f'{v_rel_lvlh[2]:+.3f}){err_str}')
        print(f'      CW +10s=({r10[0]:+7.1f}, {r10[1]:+7.1f}, {r10[2]:+7.1f})'
              f'  +30s=({r30[0]:+7.1f}, {r30[1]:+7.1f}, {r30[2]:+7.1f})'
              f'  +60s=({r60[0]:+7.1f}, {r60[1]:+7.1f}, {r60[2]:+7.1f})')

        # CSV 기록 (선택)
        if log_writer:
            log_writer.writerow([f'{now:.3f}', f'{dist_raw:.1f}',
                                 f'{dist_sm:.1f}',
                                 *[f'{x:.2f}' for x in r_rel_lvlh],
                                 *[f'{x:.4f}' for x in v_rel_lvlh],
                                 tle_jump_flag])
            log_file.flush()

except KeyboardInterrupt:
    print('\n[nav] 사용자 중단.')
finally:
    if log_file:
        log_file.close()
    client.terminate()
    print('[nav] 연결 종료.')
