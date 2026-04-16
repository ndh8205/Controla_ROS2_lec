#!/usr/bin/env python3
"""영상 담당 — 노트북 스타터 (rosbridge + web_video_server).

역할: 카메라로 chief 위성 탐색/관측 + 사진 확보
목표:
  - 팀 1: chief 주변 GCO 궤도에서 다각도 사진 6장 확보
  - 팀 2: 접근 중 chief 식별 (VBN 용 시각 확인)

카메라 이미지:
  브라우저에서 직접 확인 (web_video_server):
    http://192.168.0.54:8080/stream?topic=/nasa_satellite/camera    (팀 1)
    http://192.168.0.54:8080/stream?topic=/nasa_satellite2/camera   (팀 2)

  전체 토픽 목록: http://192.168.0.54:8080/

사용법:
    python3 vision_operator.py --host 192.168.0.54 --deputy deputy_formation
"""

import argparse
import os
import time
import webbrowser
from threading import Lock

import roslibpy

# ===================== 설정 =====================
ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='192.168.0.54')
ap.add_argument('--deputy', default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'))
ap.add_argument('--out',    default='./captured_frames')
args = ap.parse_args()

os.makedirs(args.out, exist_ok=True)

# Deputy 별 카메라 토픽/URL 매핑
CAM_TOPIC = {
    'deputy_formation': '/nasa_satellite/camera',
    'deputy_docking':   '/nasa_satellite2/camera',
}
cam_topic = CAM_TOPIC[args.deputy]
web_url = f'http://{args.host}:8080/stream?topic={cam_topic}'

print(f'[vision] deputy={args.deputy}')
print(f'[vision] 카메라 브라우저 URL: {web_url}')
print(f'[vision] 프레임 저장 경로: {args.out}/')
print()

# ===================== 브라우저 자동 열기 =====================
try:
    webbrowser.open(web_url)
    print('[vision] 브라우저에서 카메라 스트림을 확인하세요.')
except Exception:
    print(f'[vision] 브라우저를 수동으로 여세요: {web_url}')

# ===================== rosbridge 접속 (센서 보조용) =====================
client = roslibpy.Ros(host=args.host, port=9090)
client.run()

state = {}
lock = Lock()


def on_gps(msg):
    p = msg['pose']['pose']['position']
    with lock:
        state['gps'] = (p['x'], p['y'], p['z'])


def on_tle(msg):
    p = msg['pose']['pose']['position']
    with lock:
        state['tle'] = (p['x'], p['y'], p['z'])


roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)

# ===================== 메인 루프 =====================
# TODO: 학생이 구현할 부분!
#
# 아이디어:
#   1. GPS + TLE 로 chief 까지 상대 거리 추정 (orbit 담당이 알려주기도 함)
#   2. 카메라 FOV 에 chief 가 보이는지 확인 (브라우저)
#   3. 자세 담당에게 "카메라 방향 틀어달라" 요청
#   4. 원하는 각도에서 스크린샷 저장 (브라우저 캡처 또는 아래 키 입력)
#
# 간단한 "키 입력 시 스크린샷 저장" 구현:

import math

frame_count = 0

print('\n[vision] 모니터 시작. 아래 명령 가능:')
print('  s  → 현재 상태를 기록 (상대 거리 + 시각)')
print('  q  → 종료')
print('  (카메라 캡처는 브라우저에서 스크린샷/Ctrl+S 사용)\n')

try:
    while True:
        time.sleep(1.0)
        with lock:
            if 'gps' in state and 'tle' in state:
                dr = tuple(state['tle'][i] - state['gps'][i] for i in range(3))
                dist = math.sqrt(sum(x*x for x in dr))
                print(f'  [거리] chief 까지: {dist:.0f} m ({dist/1000:.2f} km)')
            else:
                print('  (GPS/TLE 대기 중...)')

except KeyboardInterrupt:
    print(f'\n[vision] 종료. 저장 디렉토리: {args.out}/')

client.terminate()
