# Vision 실습 — 시각 항법 및 관측 (Visual Observation)

**역할**: 카메라로 chief 탐색·관측·캡처. ADCS 에게 포인팅 피드백 제공.
**짝 코드**: `student/vision_operator.py`
**팀별 목표**:
- **Formation 팀**: chief 주변에서 **다양한 각도 사진 6장** 확보
- **Docking 팀**: **chief 시각 추적** + VBN (Visual Based Navigation) 으로 근접 정렬 보조

---

## 오늘 할 일

1. 카메라 스트림 브라우저 확인
2. 카메라 로 chief 위치 파악 (화면 어디에 있는지)
3. ADCS 담당에게 방향 피드백
4. 스크린샷 캡처
5. (도전) 화면 내 chief 픽셀 위치 → body frame bearing 역산
6. (도전) 자동 중앙 정렬 (Vision ↔ ADCS 루프)

---

## 성공 기준 (실습 중 즉석 결정)

- [ ] 카메라 영상 실시간 확인
- [ ] chief 가 화면 **어디에 있는지** 팀에 전달 ("오른쪽 위", 또는 픽셀 좌표)
- [ ] 임무별 사진 수 확보 (Formation 팀) / 시각 추적 유지 (Docking 팀)

---

## 스캐폴드가 이미 해 준 것

`vision_operator.py`:
- 브라우저 자동 오픈 (`webbrowser.open(web_url)`)
- rosbridge 접속 + GPS/TLE 구독 (거리 모니터용)
- `state` 에 위치 저장
- 카메라 토픽/URL 매핑 (`CAM_TOPIC`)

너희 할 일: **화면 정렬 피드백 + 스크린샷 캡처**.

---

## Step 1 — 브라우저로 카메라 보기 (5분)

```bash
python3 student/vision_operator.py --host 220.67.219.55 --deputy deputy_formation
```
스크립트 실행하면 자동으로 기본 브라우저에 카메라 URL 열림:
```
http://220.67.219.55:8080/stream?topic=/nasa_satellite/camera     (Formation 팀)
http://220.67.219.55:8080/stream?topic=/nasa_satellite2/camera    (Docking 팀)
```

**안 열리면** 직접 URL 주소창에 붙여넣기:
- `http://220.67.219.55:8080/` — 전체 스트림 목록 (캘리번호 확인 가능)
- URL 뒤에 `&type=mjpeg` 붙이면 재생 안정 (h264 보다)

**팁**: 5개 스트림이 동시에 뜸:
- `/nasa_satellite/camera` — Formation deputy 탑재 카메라
- `/nasa_satellite2/camera` — Docking deputy 탑재 카메라
- `/observer/chief/camera` — chief 외부 관측
- `/observer/formation/camera` — Formation deputy 외부 관측
- `/observer/docking/camera` — Docking deputy 외부 관측

**초반엔 chief 가 안 보임** (5 km 떨어져 있어서 점 하나도 안 됨). ODCS 가 분사해서 가까이 가야 보이기 시작. Formation 팀은 50 m 까지, Docking 팀은 1 m 까지 가면 chief 가 명확히 보임.

---

## Step 2 — 시각적 관측 (15분)

chief 가 화면에 보이기 시작하면:

1. **화면 좌표계 파악**: 영상 좌측 상단 (0,0), 우측 하단 (640, 480). 중심 (320, 240).
2. **chief 위치 리포트**: 팀 채팅/음성에 실시간 공유.
   ```
   "chief 가 오른쪽 1/3 지점, 약간 위쪽 (대략 px=430, py=180)"
   ```
3. **ADCS 에게 요청**: "pitch 를 살짝 아래로 → yaw 을 왼쪽으로" 같이 대략 방향 지시.

Navigation 담당이 주는 LVLH 상대 벡터도 참고:
```
Nav: r_rel_LVLH = (-30, +4990, -10)     # chief 는 body +y 방향, 약간 -z
Vision: 카메라가 body +y 향하고 있으면 chief 는 화면 중앙에 있어야 함
```

---

## Step 3 — 스크린샷 캡처 (15분)

`web_video_server` 에 `/snapshot?topic=...&type=jpeg` 엔드포인트 있음. Python `requests` 로 프레임 저장:

```python
import requests, os
from datetime import datetime

os.makedirs(args.out, exist_ok=True)

def capture():
    snap_url = f'http://{args.host}:8080/snapshot?topic={cam_topic}&type=jpeg'
    r = requests.get(snap_url, timeout=3)
    if r.status_code == 200:
        fname = f'{args.out}/chief_{datetime.now().strftime("%H%M%S")}.jpg'
        with open(fname, 'wb') as f:
            f.write(r.content)
        print(f'[vision] saved {fname} ({len(r.content)} bytes)')
    else:
        print(f'[vision] snapshot fail: HTTP {r.status_code}')
```

(requests 설치: `pip3 install requests --break-system-packages`)

**반복 캡처 루프** (팀 Formation 6장 목표):
```python
shots_taken = 0
while shots_taken < 6:
    time.sleep(10)    # 10 초마다 한 장 (chief 주변 GCO 주기 고려)
    capture()
    shots_taken += 1
print(f'[vision] 총 {shots_taken} 장 확보')
```

**주의**: ADCS 담당이 자세를 chief 쪽으로 돌려줘야 유효한 사진이 됨. 타이밍 맞추기.

---

## Step 4 — 화면 내 chief 픽셀 위치 추정 (도전)

이미지 분석으로 **chief 가 화면 어디** 있는지 자동 검출:

**방법 1 — 밝기 기반 (간단)**:
chief 는 주로 밝은 점 (태양광 반사). 가장 밝은 픽셀 → chief 후보.
```python
import numpy as np
from PIL import Image
import io

def find_bright_spot(jpeg_bytes):
    img = np.array(Image.open(io.BytesIO(jpeg_bytes)).convert('L'))
    # 가장 밝은 픽셀 좌표
    idx = np.unravel_index(np.argmax(img), img.shape)
    y, x = idx
    brightness = img[y, x]
    return x, y, brightness
```

**방법 2 — OpenCV 물체 검출 (고급)**:
```python
import cv2
img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if contours:
    c = max(contours, key=cv2.contourArea)
    M = cv2.moments(c)
    cx = int(M['m10']/M['m00'])
    cy = int(M['m01']/M['m00'])
    print(f'chief at px ({cx}, {cy})')
```

---

## Step 5 — Body frame bearing 역산 (도전)

카메라 FOV = 1.047 rad (60°), 해상도 640×480. 화면 중심에서 픽셀 오프셋 → body 방향:

```python
import math

FOV_H = 1.047       # 수평 FOV (rad)
FOV_V = FOV_H * 480/640
CX, CY = 320, 240   # 화면 중심

def pixel_to_bearing(px, py):
    """화면 픽셀 → body frame 방향 각도 (yaw, pitch)."""
    dx = px - CX          # 화면 x 오프셋
    dy = CY - py          # 화면 y 오프셋 (위가 +)
    yaw   = math.atan2(dx, 320 / math.tan(FOV_H/2))
    pitch = math.atan2(dy, 240 / math.tan(FOV_V/2))
    return yaw, pitch
```

**ADCS 에게 전달**: "chief 는 body +yaw 3.5°, +pitch 1.2° 방향"

---

## Step 6 — 자동 중앙 정렬 (도전)

Vision 이 bearing 계산 → ADCS 담당에게 push → ADCS 가 target 쿼터니언 갱신 → 자세 돌아감 → Vision 다시 측정 루프.

```python
while True:
    r = requests.get(snap_url, timeout=3)
    x, y, _ = find_bright_spot(r.content)
    dx, dy = x - CX, CY - y

    # 간단: 직접 RW 명령 (임시 독단)
    if abs(dx) > 20:
        tau_z = 0.05 * (-1 if dx > 0 else 1)
        # ADCS 역할 담당 없으면 여기서 직접 rw/z 퍼블리시
        rw_z = roslibpy.Topic(client, f'/{args.deputy}/rw/z/cmd', 'std_msgs/Float32')
        rw_z.publish(roslibpy.Message({'data': tau_z}))
    time.sleep(1.0)
```

→ **ADCS 와 충돌 주의**: 같은 RW 토픽에 둘이 동시에 발행하면 마지막 쓰는 사람이 이김.

---

## 흔한 실수

| 증상 | 원인 | 해결 |
|---|---|---|
| 브라우저 열었는데 화면 까맣다 | chief/딥yuty 가 너무 멀어서 안 보임 | ODCS 가 접근한 후 다시 확인 |
| 스트림 끊김 or 로딩 멈춤 | 네트워크 병목, 10명 동시 접속 | URL 뒤 `&type=mjpeg` 추가, 해상도 낮추기 (교수에 요청) |
| 스크린샷 HTTP 500 | 해당 토픽에 데이터 없음 | `ros2 topic hz /nasa_satellite/camera` 로 발행 확인 |
| OpenCV import 에러 | 노트북에 미설치 | `pip3 install opencv-python --break-system-packages` |
| 밝기 기반 탐지에 태양 걸림 | 태양이 더 밝음 | 마스크로 화면 일부만, 또는 color 로 판단 |

---

## 팀 협업

- **ADCS** 가 자세 정렬 → Vision 확인 → 피드백 → ADCS 미세 조정 (폐루프)
- **ODCS** 가 접근 → Vision 이 chief 보임 확인 → 접근 속도 조절 피드백
- **Navigation** 이 LVLH 상대 방향 → Vision 이 카메라 방향 예측 / 실제 관측 비교 (센서 검증)

---

## 참고

- 카메라 sensor pose: `<pose>0 0.4 0 0 0 1.5708</pose>` → body 원점에서 +y 방향 0.4 m 앞, yaw 90° 회전. 즉 카메라 광축이 body +x 를 향함 (회전 없으면).
- 기본 FOV 60° (horizontal). 좁은 화각이라 chief 가 화면 안 들어오는 경우 많음.
- `http://220.67.219.55:8080/stream_viewer?topic=...&type=mjpeg` 가 가장 호환성 좋음 (h264 는 일부 브라우저 이슈).
