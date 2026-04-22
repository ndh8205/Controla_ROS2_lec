#!/usr/bin/env python3
"""교수님 실습 방해 도구 — 학생 팀에 외란 주입 (rosbridge 경유).

사용 시나리오:
    1. 팀이 PD 자세제어 완성 → `--mode random-torque` 로 흔들기 (soft)
    2. 팀이 V-bar 접근 안정 → `--mode random-thrust` 로 밀치기 (soft)
    3. 팀이 자세·궤도 모두 안정 → `--mode teleport-chief` 로 지도 뒤섞기 (hard)
    4. 디버그 테스트 → `--mode actuator-jam` 로 학생 명령 덮어쓰기 (hard)

주의:
    - 서버(플랫샛)와 같은 네트워크에서 실행. `--host localhost` 가능.
    - 실행 중 Ctrl+C 로 정상 종료 (모든 외란 중지).
    - 학생 팀이 무엇에 막혔는지 로그 남기면 수업 후 피드백에 유용.

사용법:
    python3 disturb.py --help
    python3 disturb.py --mode random-torque --target deputy_formation --duration 60 --amplitude 0.05
    python3 disturb.py --mode random-thrust --target deputy_docking --duration 30
    python3 disturb.py --mode teleport-chief --offset 300 200 50
    python3 disturb.py --mode actuator-jam  --target deputy_formation --topic rw/z --rate 50
"""
import argparse
import random
import signal
import sys
import time

import roslibpy


# ==============================================================
AXES_RW       = ('x', 'y', 'z')
AXES_THRUSTER = ('fx_plus', 'fx_minus',
                 'fy_plus', 'fy_minus',
                 'fz_plus', 'fz_minus')


def stop_all_rw(client, deputy):
    for ax in AXES_RW:
        pub = roslibpy.Topic(client, f'/{deputy}/rw/{ax}/cmd', 'std_msgs/Float32')
        for _ in range(3):
            pub.publish(roslibpy.Message({'data': 0.0}))
            time.sleep(0.08)


def stop_all_thrust(client, deputy):
    for ax in AXES_THRUSTER:
        pub = roslibpy.Topic(client, f'/{deputy}/thruster/{ax}/cmd',
                             'std_msgs/Float32')
        for _ in range(3):
            pub.publish(roslibpy.Message({'data': 0.0}))
            time.sleep(0.08)


# --------------- 모드 구현 ----------------------------------------

def mode_random_torque(client, args):
    """랜덤 토크 주입. 3–5 초마다 다른 축에 amplitude 이하 랜덤 토크."""
    print(f'[prof] random-torque → {args.target} for {args.duration}s '
          f'(amp ±{args.amplitude} N·m)')
    end = time.time() + args.duration
    next_pulse = 0.0
    current_ax, current_val = None, 0.0
    pub_cache = {ax: roslibpy.Topic(client,
                                    f'/{args.target}/rw/{ax}/cmd',
                                    'std_msgs/Float32')
                 for ax in AXES_RW}

    while time.time() < end:
        now = time.time()
        if now >= next_pulse:
            # 기존 축 정지
            if current_ax:
                for _ in range(3):
                    pub_cache[current_ax].publish(
                        roslibpy.Message({'data': 0.0}))
                    time.sleep(0.05)
            # 새 축/값
            current_ax = random.choice(AXES_RW)
            current_val = random.uniform(-args.amplitude, args.amplitude)
            burst_len = random.uniform(1.5, 3.0)
            next_pulse = now + burst_len + random.uniform(0.5, 2.0)
            print(f'  [{now-end+args.duration:+6.1f}s] rw/{current_ax} '
                  f'= {current_val:+.3f} N·m for {burst_len:.1f}s')
        # 현재 명령 유지 publish (plugin last-value 유지이므로 주기적 재발행)
        pub_cache[current_ax].publish(
            roslibpy.Message({'data': float(current_val)}))
        time.sleep(0.1)

    stop_all_rw(client, args.target)
    print('[prof] random-torque done, all rw stopped')


def mode_random_thrust(client, args):
    """랜덤 추력기 발사. 5–10 초 간격, 0.5–1.5 초 짧게."""
    print(f'[prof] random-thrust → {args.target} for {args.duration}s')
    end = time.time() + args.duration
    pub_cache = {ax: roslibpy.Topic(client,
                                    f'/{args.target}/thruster/{ax}/cmd',
                                    'std_msgs/Float32')
                 for ax in AXES_THRUSTER}

    while time.time() < end:
        axis = random.choice(AXES_THRUSTER)
        throttle = random.uniform(0.3, 1.0)
        burst = random.uniform(0.5, 1.5)
        print(f'  fire {axis} @ throttle={throttle:.2f} for {burst:.1f}s')
        t0 = time.time()
        while time.time() - t0 < burst:
            pub_cache[axis].publish(roslibpy.Message({'data': throttle}))
            time.sleep(0.05)
        # stop this axis
        for _ in range(3):
            pub_cache[axis].publish(roslibpy.Message({'data': 0.0}))
            time.sleep(0.08)
        time.sleep(random.uniform(5.0, 10.0))

    stop_all_thrust(client, args.target)
    print('[prof] random-thrust done')


def mode_teleport_chief(client, args):
    """Chief 를 지정 오프셋만큼 순간이동 (gz service set_pose).

    주의: 이건 gz service 라서 rosbridge 경유로는 직접 호출 불가 (gz transport
    영역). 서버 쪽 쉘에서 직접 호출해야 함. 아래는 명령 출력만.
    """
    ox, oy, oz = args.offset
    # 현재 chief 는 (0,0,0) 에 고정. offset 만큼 옮김.
    print(f'[prof] teleport-chief offset=({ox}, {oy}, {oz}) m')
    print('       rosbridge 로는 gz service 직접 호출 불가.')
    print('       서버 쪽 쉘에서 아래 명령 실행:')
    print()
    print(f'  gz service -s /world/mission/set_pose \\')
    print(f'    --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean --timeout 1000 \\')
    print(f'    --req \'name: "intel_sat_dummy", '
          f'position: {{x: {ox}, y: {oy}, z: {oz}}}\'')
    print()
    print('  또는 Python 에서 roslibpy Service 로 호출 가능하면 여기서 자동화.')


def mode_actuator_jam(client, args):
    """지정 토픽에 0 값을 고속 발행해서 학생 명령을 덮어쓰기."""
    print(f'[prof] actuator-jam → /{args.target}/{args.topic}/cmd '
          f'for {args.duration}s at {args.rate} Hz')
    topic = f'/{args.target}/{args.topic}/cmd'
    pub = roslibpy.Topic(client, topic, 'std_msgs/Float32')
    end = time.time() + args.duration
    period = 1.0 / max(args.rate, 1)
    while time.time() < end:
        pub.publish(roslibpy.Message({'data': 0.0}))
        time.sleep(period)
    print('[prof] jam done')


# --------------- 메인 -------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='Professor disturbance tool')
    ap.add_argument('--host',   default='localhost')
    ap.add_argument('--mode',   required=True,
                    choices=('random-torque', 'random-thrust',
                             'teleport-chief', 'actuator-jam'))
    ap.add_argument('--target', default='deputy_formation',
                    choices=('deputy_formation', 'deputy_docking'))
    ap.add_argument('--duration', type=float, default=60.0,
                    help='seconds (random-torque, random-thrust, jam)')
    ap.add_argument('--amplitude', type=float, default=0.05,
                    help='random-torque: max |τ| N·m (≤ 0.1 plugin clamp)')
    ap.add_argument('--offset', type=float, nargs=3, default=[300, 0, 0],
                    help='teleport-chief: Δx Δy Δz (m)')
    ap.add_argument('--topic', default='rw/z',
                    help='actuator-jam: e.g. rw/z, thruster/fy_plus')
    ap.add_argument('--rate',  type=float, default=50.0,
                    help='actuator-jam Hz')
    args = ap.parse_args()

    client = roslibpy.Ros(host=args.host, port=9090)
    client.run()

    # Ctrl+C 핸들러 — 안전 종료
    def _sigint(*_a):
        print('\n[prof] SIGINT, 정지 중...')
        try:
            stop_all_rw(client, args.target)
            stop_all_thrust(client, args.target)
        finally:
            client.terminate()
            sys.exit(0)
    signal.signal(signal.SIGINT, _sigint)

    try:
        if   args.mode == 'random-torque':  mode_random_torque(client, args)
        elif args.mode == 'random-thrust':  mode_random_thrust(client, args)
        elif args.mode == 'teleport-chief': mode_teleport_chief(client, args)
        elif args.mode == 'actuator-jam':   mode_actuator_jam(client, args)
    finally:
        client.terminate()


if __name__ == '__main__':
    main()
