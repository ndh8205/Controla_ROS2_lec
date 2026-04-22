#!/usr/bin/env python3
"""[완성 예시] ODCS 궤도 제어 — V-bar (along-track) 접근.

이 파일은 orbit_controller.py 스캐폴드의 완성본 예시. 학생이 따라 읽으며
파이썬 + 우주역학 기초를 동시에 익히도록 줄별 주석을 최대한 풀어놓음.

전략:
    1) GPS 로 본 내 ECI 위치 − Chief TLE 로 본 chief ECI 위치 = 상대 벡터
    2) 거리에 따라 목표 접근 속도 단계별 조절 (멀면 빠르게, 가까우면 천천히)
    3) V-bar (along-track, body y) 축 추력기로 접근. CW 에서 가장 안정.
    4) 도킹 거리 이내면 완전 정지 (브레이크)

주의:
    - deputy_formation 은 y=+5000 에서 출발 → chief (y=0) 가려면 −y 방향
      → fy_minus 분사 필요. sign 변수로 자동 처리.
    - deputy_docking  은 y=−5000 에서 출발 → +y 방향 → fy_plus.

사용법:
    python3 orbit_controller_example.py --host 220.67.219.55 --deputy deputy_docking
"""

# ─────────────────────────────────────────────────────────────────────
# 1) Imports
#    math.sqrt : 벡터 크기 계산
#    roslibpy  : ROS 2 토픽을 rosbridge 로 다루기
# ─────────────────────────────────────────────────────────────────────
import argparse
import math
import time
from threading import Lock

import roslibpy


# ─────────────────────────────────────────────────────────────────────
# 2) 명령줄 인자
# ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='220.67.219.55')
ap.add_argument('--deputy', default='deputy_docking',
                choices=('deputy_formation', 'deputy_docking'))
args = ap.parse_args()


# ─────────────────────────────────────────────────────────────────────
# 3) 접근 방향 자동 결정
#    Formation 은 +5000 에서 왔으니 y 감소 방향(−y) 으로 감.
#    Docking  은 −5000 에서 왔으니 y 증가 방향(+y) 으로 감.
#    sign: +1 이면 +y (chief 쪽), −1 이면 −y (chief 쪽).
# ─────────────────────────────────────────────────────────────────────
if args.deputy == 'deputy_formation':
    APPROACH_AXIS_FWD  = 'fy_minus'   # chief 쪽 가속
    APPROACH_AXIS_REV  = 'fy_plus'    # 브레이크 (반대 방향)
    SIGN = -1                          # chief 방향이 body −y
else:  # deputy_docking
    APPROACH_AXIS_FWD  = 'fy_plus'
    APPROACH_AXIS_REV  = 'fy_minus'
    SIGN = +1


# ─────────────────────────────────────────────────────────────────────
# 4) 서버 접속 + 토픽 구독/발행 설정
# ─────────────────────────────────────────────────────────────────────
client = roslibpy.Ros(host=args.host, port=9090)
client.run()
print(f'[odcs] 접속: {args.host}:9090  target={args.deputy}')
print(f'[odcs] 접근 전략: {APPROACH_AXIS_FWD} (chief 쪽),  sign={SIGN:+d}')

state = {}
lock = Lock()


def on_gps(msg):
    """내 GPS — ECI 위치/속도. 1 Hz."""
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['gps_pos'] = (p['x'], p['y'], p['z'])
        state['gps_vel'] = (v['x'], v['y'], v['z'])


def on_tle(msg):
    """Chief TLE 추정 — SGP4 + 노이즈 기반."""
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['tle_pos'] = (p['x'], p['y'], p['z'])
        state['tle_vel'] = (v['x'], v['y'], v['z'])


def on_imu(msg):
    """가속도계 — 추력기 발사 확인용 (자체 명령 외에 외란 감지)."""
    a = msg['linear_acceleration']
    with lock:
        state['accel'] = (a['x'], a['y'], a['z'])


# 토픽 구독 (메시지 올 때마다 콜백 자동 호출)
roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)
roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(on_imu)


# ─────────────────────────────────────────────────────────────────────
# 5) 6 축 추력기 publisher 생성
#    for 문으로 6 개 토픽 한 번에 생성해 dict 에 저장 → 코드 간결.
# ─────────────────────────────────────────────────────────────────────
AXES = ('fx_plus', 'fx_minus', 'fy_plus', 'fy_minus', 'fz_plus', 'fz_minus')
thrusters = {
    ax: roslibpy.Topic(client,
                       f'/{args.deputy}/thruster/{ax}/cmd',
                       'std_msgs/Float32')
    for ax in AXES
}


def fire(axis, throttle):
    """지정 축 추력기 켜기. throttle 0~1 (plugin max_force=10 N)."""
    thrusters[axis].publish(roslibpy.Message({'data': float(throttle)}))


def stop_all():
    """모든 추력기 끄기 (data=0.0)."""
    for t in thrusters.values():
        t.publish(roslibpy.Message({'data': 0.0}))


# ─────────────────────────────────────────────────────────────────────
# 6) 벡터 헬퍼 (numpy 없이 간단히)
# ─────────────────────────────────────────────────────────────────────
def sub3(a, b):
    """두 3D 벡터 빼기."""
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def norm3(v):
    """3D 벡터 크기 |v|."""
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


# ─────────────────────────────────────────────────────────────────────
# 7) 거리별 목표 접근 속도
#    단계식 제어 (gain schedule):
#       5 km 이상 : 2.0 m/s  (원거리 이동)
#       1 km 이상 : 1.0 m/s
#       100 m 이상: 0.3 m/s
#       10  m 이상: 0.05 m/s
#       10 m 이내: 0 (정지, 도킹 안정)
#    이 숫자들은 "안전하게 overshoot 최소" 경험치. 더 공격적이면 위험.
# ─────────────────────────────────────────────────────────────────────
def target_speed(distance_m):
    if distance_m > 5000: return 2.0
    if distance_m > 1000: return 1.0
    if distance_m > 100:  return 0.3
    if distance_m > 10:   return 0.05
    return 0.0


# ─────────────────────────────────────────────────────────────────────
# 8) 실제 y 방향 속도 추출
#    GPS 속도는 ECI 인데, 이 시뮬에선 chief orbit 평면이 ECI 와 거의 정렬
#    되어 있어 LVLH y 와 ECI y 가 근사 일치 → 간단화.
#    엄밀한 LVLH 변환은 Navigation 담당이 제공 (팀 협업).
# ─────────────────────────────────────────────────────────────────────
def get_along_track_velocity():
    with lock:
        if 'gps_vel' not in state or 'tle_vel' not in state:
            return None
        # chief 속도를 빼서 "상대" 속도로 만듦 (chief 의 공전 속도 제거)
        rel_v = sub3(state['gps_vel'], state['tle_vel'])
    # rel_v[1] 이 along-track 성분 (근사).
    # SIGN 곱하면 "chief 쪽으로 향한 속도" 가 양수.
    return SIGN * rel_v[1]


# ─────────────────────────────────────────────────────────────────────
# 9) 제어 본체
#    - 오차 = 목표속도 − 현재속도
#    - 오차 > 임계치면 정방향 추력 (가속)
#    - 오차 < −임계치면 역방향 추력 (감속)
#    - 그 사이면 정지 (순항)
#    임계치 THRESH 가 너무 작으면 추력기가 자주 껐다켰다 (chattering).
# ─────────────────────────────────────────────────────────────────────
THRESH = 0.02   # m/s — 이보다 가까우면 그냥 coast
THROTTLE = 0.5  # 부스팅·브레이크 강도 (10 N × 0.5 = 5 N)


def control_step(distance, v_approach):
    """한 tick 의 추력기 결정.

    distance    : 현재 상대 거리 [m]
    v_approach  : chief 쪽 접근 속도 (양수 = 접근 중)
    """
    v_target = target_speed(distance)
    err = v_target - v_approach    # + 면 더 가속 필요, − 면 감속 필요

    if distance <= 10.0:
        # 도킹 안정 — 모든 축 정지
        stop_all()
        return ('brake_final', err)

    if err > THRESH:
        # 너무 느림 → 가속 (forward thrust)
        fire(APPROACH_AXIS_FWD, THROTTLE)
        return (APPROACH_AXIS_FWD, err)
    elif err < -THRESH:
        # 너무 빠름 → 감속 (reverse thrust)
        fire(APPROACH_AXIS_REV, THROTTLE)
        return (APPROACH_AXIS_REV, err)
    else:
        # 적당한 속도 유지 → 코스트
        stop_all()
        return ('coast', err)


# ─────────────────────────────────────────────────────────────────────
# 10) 메인 루프
#     1 Hz print 주기. 제어 자체는 5 Hz (time.sleep 0.2).
# ─────────────────────────────────────────────────────────────────────
print('[odcs] V-bar 접근 시작. Ctrl+C 로 종료.')
last_print = 0.0

try:
    while True:
        time.sleep(0.2)   # 제어 5 Hz

        # 센서 아직 안 왔으면 대기
        v_app = get_along_track_velocity()
        with lock:
            if 'gps_pos' not in state or 'tle_pos' not in state or v_app is None:
                continue
            dr = sub3(state['tle_pos'], state['gps_pos'])   # chief − me (ECI)

        dist = norm3(dr)
        action, err = control_step(dist, v_app)

        now = time.time()
        if now - last_print >= 1.0:
            v_tgt = target_speed(dist)
            print(f'[odcs] dist={dist:8.1f} m   v_now={v_app:+.3f} '
                  f'v_tgt={v_tgt:+.3f} (SIGN={SIGN:+d})  '
                  f'err={err:+.3f}  action={action}')
            last_print = now

except KeyboardInterrupt:
    print('\n[odcs] 사용자 중단 — 모든 추력기 정지.')
finally:
    # stop 메시지는 반드시 여러 번 반복 (rosbridge flush race 방지)
    for _ in range(5):
        stop_all()
        time.sleep(0.05)
    client.terminate()
    print('[odcs] 연결 종료.')
