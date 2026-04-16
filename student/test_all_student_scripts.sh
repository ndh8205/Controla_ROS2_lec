#!/usr/bin/env bash
# test_all_student_scripts.sh
#
# 모든 학생용 Python 스크립트가 정상 실행되는지 자동 검증.
# 플랫샛에서 실행: gz sim (mission) + rosbridge + chief_propagator 를
# 자동으로 띄우고, 각 스크립트를 3초씩 돌려서 crash 없이 출력 나오는지 체크.
#
# Usage:
#   bash student/test_all_student_scripts.sh

set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="localhost"  # 같은 머신에서 테스트

: "${ROS_DISTRO:=jazzy}"
[ -z "${AMENT_PREFIX_PATH:-}" ] && source "/opt/ros/${ROS_DISTRO}/setup.bash"
[ -f "${HOME}/space_ros_ws/install/setup.bash" ] && source "${HOME}/space_ros_ws/install/setup.bash"

export GZ_SIM_RESOURCE_PATH="${HOME}/space_ros_ws/install/orbit_sim/share/orbit_sim/models${GZ_SIM_RESOURCE_PATH:+:${GZ_SIM_RESOURCE_PATH}}"
export GZ_SIM_SYSTEM_PLUGIN_PATH="${HOME}/space_ros_ws/install/gz_cw_dynamics/lib${GZ_SIM_SYSTEM_PLUGIN_PATH:+:${GZ_SIM_SYSTEM_PLUGIN_PATH}}"

PIDS=()
cleanup() {
  for p in "${PIDS[@]}"; do kill -9 "$p" 2>/dev/null || true; done
  bash "${HOME}/kill_sim.sh" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "============================================"
echo " Student Scripts Integration Test"
echo "============================================"

# 1. Start gz sim (mission, headless)
echo "[setup] Starting gz sim (mission, headless)..."
bash "${HOME}/kill_sim.sh" > /dev/null 2>&1 || true
sleep 1
gz sim -s -r --verbose 2 \
  "${HOME}/space_ros_ws/install/gz_cw_dynamics/share/gz_cw_dynamics/worlds/mission.sdf" \
  > /tmp/test_student_gz.log 2>&1 &
PIDS+=($!)
sleep 3

# 2. Start rosbridge
echo "[setup] Starting rosbridge_server..."
ros2 launch rosbridge_server rosbridge_websocket_launch.xml \
  > /tmp/test_student_rosbridge.log 2>&1 &
PIDS+=($!)
sleep 2

# 3. Start chief propagator
echo "[setup] Starting chief_propagator_node..."
python3 "${HOME}/space_ros_ws/install/gz_cw_dynamics/lib/gz_cw_dynamics/chief_propagator_node.py" \
  --ros-args -p world_name:=mission > /tmp/test_student_chief.log 2>&1 &
PIDS+=($!)
sleep 2

# Test function
RESULTS=()
run_test() {
  local name="$1"
  local cmd="$2"
  local duration="${3:-3}"

  echo ""
  echo "[test] ${name} (${duration}s)..."
  local LOG="/tmp/test_student_${name// /_}.log"
  timeout "${duration}" bash -c "${cmd}" > "${LOG}" 2>&1 || true
  local lines
  lines=$(wc -l < "${LOG}")
  if [ "${lines}" -gt 0 ]; then
    echo "  output: ${lines} lines"
    tail -2 "${LOG}" | sed 's/^/  > /'
    RESULTS+=("PASS|${name}")
  else
    echo "  NO OUTPUT — likely failed to connect or crashed"
    RESULTS+=("FAIL|${name}")
  fi
}

# 4. Run each script
echo ""
echo "============================================"
echo " Running student scripts..."
echo "============================================"

run_test "completed/laptop_monitor" \
  "python3 ${SCRIPT_DIR}/completed/laptop_monitor.py --host ${HOST} --deputy deputy_formation" 5

run_test "completed/laptop_thruster" \
  "python3 ${SCRIPT_DIR}/completed/laptop_thruster.py --host ${HOST} --deputy deputy_docking --axis fy_plus --throttle 0.3 --duration 1" 3

run_test "completed/laptop_rw" \
  "python3 ${SCRIPT_DIR}/completed/laptop_rw.py --host ${HOST} --deputy deputy_docking --axis z --torque 0.001 --duration 1" 3

run_test "attitude_controller" \
  "python3 ${SCRIPT_DIR}/attitude_controller.py --host ${HOST} --deputy deputy_formation" 4

run_test "orbit_controller" \
  "python3 ${SCRIPT_DIR}/orbit_controller.py --host ${HOST} --deputy deputy_docking" 4

run_test "vision_operator" \
  "python3 ${SCRIPT_DIR}/vision_operator.py --host ${HOST} --deputy deputy_formation" 4

# 5. Summary
echo ""
echo "============================================"
echo "                SUMMARY"
echo "============================================"
N_PASS=0; N_FAIL=0
for r in "${RESULTS[@]}"; do
  st="${r%%|*}"; nm="${r#*|}"
  printf "  [%-4s] %s\n" "${st}" "${nm}"
  [ "${st}" = "PASS" ] && N_PASS=$((N_PASS+1)) || N_FAIL=$((N_FAIL+1))
done
echo "--------------------------------------------"
echo "  ${N_PASS} / ${#RESULTS[@]} passed"
echo "============================================"
[ "${N_FAIL}" -eq 0 ] && exit 0 || exit 1
