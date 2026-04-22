#!/usr/bin/env python3
"""[완성 예시] ADCS 자세 제어 — PD 제어로 현재 자세 홀드.

이 파일은 attitude_controller.py 스캐폴드를 참고해서 **바로 실행 가능한**
완성본으로 만든 예시입니다. 파이썬이 익숙하지 않은 학생을 위해 매 줄에
주석을 달아 "이 변수가 왜 있는지", "이 함수가 뭘 하는지", "왜 이런 식으로
짰는지" 를 설명합니다.

동작 요약:
    1. rosbridge(ws://HOST:9090) 로 플랫샛에 접속
    2. Star Tracker(쿼터니언) + IMU(자이로) 구독
    3. 실행 시점의 자세를 "목표 자세" 로 기억 (홀드 모드)
    4. 매 0.2 s 마다 목표 대비 오차 계산 → PD 제어로 반작용휠 토크 명령
    5. 종료 시 자동으로 RW 정지

사용법:
    python3 attitude_controller_example.py --host 220.67.219.55 --deputy deputy_formation

※ scaffold (attitude_controller.py) 와 달리 TODO 가 전부 채워져 있습니다.
  읽고 이해한 뒤 자기 scaffold 에 직접 구현해 보세요.
"""

# ─────────────────────────────────────────────────────────────────────
# 1) 필요한 라이브러리 import
#    argparse : 명령줄 인자 (--host 220.67.219.55 같은 값) 처리
#    math     : sin/cos/sqrt 등 수학 함수. 여기선 쿼터니언 정규화에만 씀
#    time     : time.sleep(초) 로 루프 주기 만들기
#    threading.Lock : 여러 스레드가 센서 값을 동시에 쓰고 읽기 때문에
#                     자료 읽는 중에 덮어쓰기 방지용 "잠금"
#    roslibpy : rosbridge 를 통해 ROS 2 토픽을 Python 에서 쓰게 해주는 라이브러리
# ─────────────────────────────────────────────────────────────────────
import argparse
import math
import time
from threading import Lock

import roslibpy


# ─────────────────────────────────────────────────────────────────────
# 2) 명령줄 인자 설정
#    학생이 실행할 때 --host 와 --deputy 를 바꿀 수 있게 함.
#    ap = ArgumentParser()  ← 인자 처리기를 만든다
#    ap.add_argument(...)   ← 받을 인자 하나씩 등록
#    args = ap.parse_args() ← 실제로 파싱해서 args.host, args.deputy 로 씀
# ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='220.67.219.55',
                help='플랫샛 서버 IP. 학교 LAN 이면 기본값 그대로.')
ap.add_argument('--deputy', default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'),
                help='제어 대상. 팀에 따라 formation 또는 docking.')
args = ap.parse_args()


# ─────────────────────────────────────────────────────────────────────
# 3) 서버에 접속
#    roslibpy.Ros(host=..., port=9090) : rosbridge WebSocket 접속 객체 생성
#    client.run() : 실제로 연결 시도. 이 시점부터 토픽 pub/sub 가능.
#    connection 실패하면 예외가 뜨니 try/except 로 감싸도 OK.
# ─────────────────────────────────────────────────────────────────────
client = roslibpy.Ros(host=args.host, port=9090)
client.run()
print(f'[adcs] 접속 완료: {args.host}:9090  target={args.deputy}')


# ─────────────────────────────────────────────────────────────────────
# 4) 센서 값 저장소
#    state : 딕셔너리. 센서 콜백에서 값을 덮어쓰고, 제어 루프에서 읽음.
#    lock  : state 를 여러 곳에서 동시에 접근하므로 Lock 으로 보호.
#            roslibpy 는 내부 IO 스레드에서 콜백을 호출함 → 메인 루프와
#            다른 스레드라서 공유 변수 보호 필요.
# ─────────────────────────────────────────────────────────────────────
state = {}
lock = Lock()


# ─────────────────────────────────────────────────────────────────────
# 5) 센서 콜백 함수들
#    on_imu 는 /deputy_*/imu/data 토픽 메시지를 받을 때마다 호출됨.
#    msg 는 딕셔너리 형태 (roslibpy 가 JSON → dict 변환).
#    예: msg['angular_velocity']['x'] == gyro x 성분
# ─────────────────────────────────────────────────────────────────────
def on_imu(msg):
    """IMU 메시지 수신 콜백."""
    # 자이로는 body 축 기준 각속도 [rad/s]
    g = msg['angular_velocity']
    # 가속도계 — 여기선 안 쓰지만 저장은 해둠 (추력 감지 등에 유용)
    a = msg['linear_acceleration']
    with lock:  # state 에 쓰는 동안 다른 스레드가 못 읽게
        state['gyro']  = (g['x'], g['y'], g['z'])
        state['accel'] = (a['x'], a['y'], a['z'])


def on_star_tracker(msg):
    """Star Tracker 쿼터니언 수신 콜백.

    쿼터니언 (x, y, z, w) 는 body 축이 ECI (고정 관성계) 에서 어디를
    향하는지 나타내는 4개짜리 숫자. 회전 행렬보다 수학적으로 다루기 편함.
    """
    q = msg['quaternion']
    with lock:
        state['q_eci'] = (q['x'], q['y'], q['z'], q['w'])


# ─────────────────────────────────────────────────────────────────────
# 6) 토픽 구독
#    roslibpy.Topic(client, topic_name, msg_type) 로 토픽 객체 생성
#    .subscribe(콜백) 호출하면 토픽이 올 때마다 콜백이 자동 실행됨
# ─────────────────────────────────────────────────────────────────────
roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(on_imu)
roslibpy.Topic(client, f'/{args.deputy}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(on_star_tracker)


# ─────────────────────────────────────────────────────────────────────
# 7) 액추에이터 publisher
#    3축 Reaction Wheel 에 각각 토크 명령을 보낼 publisher 3개.
#    std_msgs/Float32 는 data: float 하나뿐인 간단한 메시지.
# ─────────────────────────────────────────────────────────────────────
rw_x = roslibpy.Topic(client, f'/{args.deputy}/rw/x/cmd', 'std_msgs/Float32')
rw_y = roslibpy.Topic(client, f'/{args.deputy}/rw/y/cmd', 'std_msgs/Float32')
rw_z = roslibpy.Topic(client, f'/{args.deputy}/rw/z/cmd', 'std_msgs/Float32')


def send_rw(tx, ty, tz):
    """3축 토크를 한 번에 publish. plugin 이 ±0.1 N·m 로 clamp 함."""
    rw_x.publish(roslibpy.Message({'data': float(tx)}))
    rw_y.publish(roslibpy.Message({'data': float(ty)}))
    rw_z.publish(roslibpy.Message({'data': float(tz)}))


# ─────────────────────────────────────────────────────────────────────
# 8) 쿼터니언 헬퍼 함수
#    쿼터니언은 (x, y, z, w) 4개 값. 회전 합성·역회전·축각 변환이 필요.
#    아래 3개 함수로 충분.
# ─────────────────────────────────────────────────────────────────────
def q_conjugate(q):
    """쿼터니언 켤레. 회전의 '역방향' 에 해당.

    q = (x, y, z, w) 이면 conj(q) = (-x, -y, -z, w).
    회전 합성에서 "목표 → 현재" 오차 구할 때 필요.
    """
    return (-q[0], -q[1], -q[2], q[3])


def q_multiply(a, b):
    """두 쿼터니언의 곱 (회전 합성).

    수학적으로 a ⊗ b 는 "먼저 b 로 회전, 그 다음 a 로 회전" 을 의미.
    공식: (x, y, z, w) = (ax·bw + aw·bx + ay·bz − az·by,
                          ay·bw + aw·by + az·bx − ax·bz,
                          az·bw + aw·bz + ax·by − ay·bx,
                          aw·bw − ax·bx − ay·by − az·bz)
    """
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
        aw*bw - ax*bx - ay*by - az*bz,
    )


def q_to_axis_angle_small(q):
    """작은 회전 쿼터니언을 (θx, θy, θz) 벡터로 변환.

    작은 회전에서 q ≈ (axis·sin(θ/2), cos(θ/2))  이고 θ 작으면
    sin(θ/2) ≈ θ/2 이므로, 회전벡터 ≈ 2·(x, y, z).
    제어 오차 계산에 쓰기 좋음 (각도가 작다는 가정 하).
    """
    # q[3] (=w) 가 음수이면 반대 방향 회전이므로 부호 뒤집기 (shortest path)
    if q[3] < 0:
        q = (-q[0], -q[1], -q[2], -q[3])
    return (2.0 * q[0], 2.0 * q[1], 2.0 * q[2])


# ─────────────────────────────────────────────────────────────────────
# 9) PD 제어 게인
#    위성 관성 Ixx = Iyy = 14,  Izz = 10 kg·m² (100 kg 위성)
#    τ = -Kp·θ - Kd·ω 형태. 폐루프 미분방정식:
#          I·θ̈ + Kd·θ̇ + Kp·θ = 0
#       → ω_n = √(Kp/I),  ζ = Kd / (2·√(Kp·I))
#    ζ=1 (critically damped, 진동 없음), 시정수 τ ≈ 1/ω_n ≈ 10 s 목표:
#          ω_n = 0.1 rad/s  →  Kp = I·ω_n² = 14·0.01 = 0.14 N·m/rad
#          Kd = 2·ζ·√(Kp·I) = 2·1·√(0.14·14) = 2.80 N·m/(rad/s)
#    plugin max_torque = ±0.1 N·m 이라 실제로는 큰 오차에서 saturation.
#    아래 값은 "적당히 빠른 복귀" 타협치.
# ─────────────────────────────────────────────────────────────────────
KP = 0.15     # 비례 게인 [N·m/rad]
KD = 2.5      # 미분 게인 [N·m/(rad/s)]
TAU_LIMIT = 0.1   # 수동 saturation 한계 (plugin 도 같은 값으로 clamp)


def saturate(x, limit):
    """x 를 [-limit, +limit] 로 자름. clamp 함수."""
    return max(-limit, min(limit, x))


# ─────────────────────────────────────────────────────────────────────
# 10) 메인 제어 루프
#     q_target 을 None 으로 시작 → 처음 센서 값 도착 시 그 쿼터니언을
#     "목표" 로 기억. 이후부터는 그 자세를 유지하려고 토크를 냄 (홀드 모드).
# ─────────────────────────────────────────────────────────────────────
print('[adcs] PD 자세 홀드 시작. Ctrl+C 로 종료.')
print(f'[adcs] gains: Kp={KP}  Kd={KD}  saturation=±{TAU_LIMIT} N·m')
q_target = None          # 목표 쿼터니언 (아직 설정 전)
last_print = 0.0         # 마지막 print 시각 (출력 rate 낮추기용)

try:
    while True:
        time.sleep(0.2)   # 5 Hz 제어 주기. 너무 빠르면 네트워크 지연.

        # 센서 값 꺼내기 (lock 안에서 복사 → 밖에서 계산)
        with lock:
            q = state.get('q_eci')     # None 일 수도 (아직 수신 전)
            gyro = state.get('gyro')

        # 센서가 아직 안 도착했으면 건너뛰기
        if q is None or gyro is None:
            continue

        # 최초 1회: 현재 자세를 "목표" 로 고정 (attitude hold)
        if q_target is None:
            q_target = q
            print(f'[adcs] 목표 자세 고정: q = '
                  f'({q[0]:+.4f}, {q[1]:+.4f}, {q[2]:+.4f}, {q[3]:+.4f})')
            continue

        # ─── 오차 계산 ───────────────────────────────
        # q_err = q_target* ⊗ q   (body 좌표계 기준 회전 오차)
        q_err = q_multiply(q_conjugate(q_target), q)
        # 축각 벡터 (작은 각 근사): (θx, θy, θz) [rad]
        theta = q_to_axis_angle_small(q_err)

        # ─── PD 법칙 ─────────────────────────────────
        # τ = -Kp·θ - Kd·ω   (각 축 독립)
        # 부호 주의: 오차를 0 으로 되돌리려면 반대 부호 토크.
        tau_x = -KP * theta[0] - KD * gyro[0]
        tau_y = -KP * theta[1] - KD * gyro[1]
        tau_z = -KP * theta[2] - KD * gyro[2]

        # 수동 saturation (plugin 도 ±0.1 로 자르지만 안전용)
        tau_x = saturate(tau_x, TAU_LIMIT)
        tau_y = saturate(tau_y, TAU_LIMIT)
        tau_z = saturate(tau_z, TAU_LIMIT)

        # RW 에 명령 전송
        send_rw(tau_x, tau_y, tau_z)

        # ─── 상태 출력 1 Hz ─────────────────────────
        now = time.time()
        if now - last_print >= 1.0:
            # 오차 크기 (rad → deg 로 환산해서 읽기 편하게)
            err_deg = [t * 180.0 / math.pi for t in theta]
            print(f'[adcs] err(deg)=({err_deg[0]:+6.2f},'
                  f'{err_deg[1]:+6.2f},{err_deg[2]:+6.2f})  '
                  f'tau=({tau_x:+.3f},{tau_y:+.3f},{tau_z:+.3f}) N·m')
            last_print = now

# Ctrl+C 나 예외가 발생해도 반드시 RW 정지 후 연결 종료
except KeyboardInterrupt:
    print('\n[adcs] 사용자 중단 — RW 정지 후 종료.')
finally:
    # 5 번 반복 = WebSocket flush race 방지 (stop 메시지가 확실히 가도록)
    for _ in range(5):
        send_rw(0.0, 0.0, 0.0)
        time.sleep(0.05)
    client.terminate()
    print('[adcs] 연결 종료.')
