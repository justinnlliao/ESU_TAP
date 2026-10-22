#!/usr/bin/env bash
# Launcher for a ROS 2 workspace that contains only the pedal_controller package
# (copied to <ws>/src/pedal_controller). The board must already be flashed from
# the ESU-TAP repository; this script does not flash.
#
#   bash src/pedal_controller/esu_run.sh v2 [trial-id]   agent + logger + commander in tmux
#   bash src/pedal_controller/esu_run.sh stop            stop the tmux session and the agent
#   bash src/pedal_controller/esu_run.sh agent | logger v2 [trial-id] | commander v2 | build
#
# ESU_PORT=/dev/serial/by-id/... selects the ESP32 when several serial devices exist.
# ROS_DOMAIN_ID defaults to 0.
set -eo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ws=$(cd "$here/../.." && pwd)
self="$here/esu_run.sh"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
AGENT_IMAGE=microros/micro-ros-agent:jazzy

say() { printf '[esu] %s\n' "$*"; }
die() { printf '[esu] error: %s\n' "$*" >&2; exit 1; }

ros_env() {
  # shellcheck source=/dev/null
  source /opt/ros/humble/setup.bash
  [ -f "$ws/install/setup.bash" ] || cmd_build
  # shellcheck source=/dev/null
  source "$ws/install/setup.bash"
}

board_arg() {
  case "${1:-}" in
    v1|v2|v3) ;;
    *) die "give the board revision: v1, v2 or v3" ;;
  esac
}

find_port() {
  if [ -n "${ESU_PORT:-}" ]; then echo "$ESU_PORT"; return; fi
  local ports=(/dev/serial/by-id/*)
  [ -e "${ports[0]}" ] || die "no serial device under /dev/serial/by-id (ESP32 plugged in?)"
  [ ${#ports[@]} -eq 1 ] || die "several serial devices; set ESU_PORT to one of: ${ports[*]}"
  echo "${ports[0]}"
}

cmd_build() {
  # shellcheck source=/dev/null
  source /opt/ros/humble/setup.bash
  (cd "$ws" && colcon build --packages-select pedal_controller)
}

cmd_agent() {
  local port; port=$(find_port)
  say "agent on $port (domain $ROS_DOMAIN_ID)"
  [ -z "$(docker ps -q -f name='^esu-agent$')" ] || die "an esu-agent container is already running (docker stop esu-agent)"
  exec docker run --rm --name esu-agent --network host \
    --device "$port":/dev/esu \
    -e ROS_DOMAIN_ID="$ROS_DOMAIN_ID" -e ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}" \
    "$AGENT_IMAGE" serial --dev /dev/esu -b 115200 -v4
}

cmd_logger() {
  board_arg "${1:-}"; ros_env
  local params=(--ros-args -p board_version:="$1")
  [ -n "${2:-}" ] && params+=(-p trial_id:="$2")
  exec ros2 run pedal_controller pedal_logger "${params[@]}"
}

cmd_commander() {
  board_arg "${1:-}"; ros_env
  exec ros2 run pedal_controller pedal_commander \
    --ros-args -p board_version:="$1" -p fixture_confirmed:=true
}

cmd_run() {
  board_arg "${1:-}"
  local board=$1 trial=${2:-}
  [ -f "$ws/install/setup.bash" ] || cmd_build
  if ! command -v tmux >/dev/null; then
    say "tmux is not installed (sudo apt install tmux). Run these in three terminals instead:"
    printf '  bash %s agent\n  bash %s logger %s %s\n  bash %s commander %s\n' \
      "$self" "$self" "$board" "$trial" "$self" "$board"
    return
  fi
  tmux has-session -t esu 2>/dev/null && die "an 'esu' tmux session already exists: tmux attach -t esu"
  tmux new-session -d -s esu -n esu "bash '$self' agent; read -r -p 'agent exited; Enter to close'"
  sleep 2
  tmux split-window -h -t esu "bash '$self' logger $board $trial; read -r -p 'logger exited; Enter to close'"
  tmux split-window -v -t esu "bash '$self' commander $board; read -r -p 'commander exited; Enter to close'"
  tmux select-layout -t esu tiled >/dev/null
  say "started. Detach: Ctrl+B then D. Stop: bash $self stop"
  tmux attach -t esu
}

cmd_stop() {
  if command -v tmux >/dev/null; then tmux kill-session -t esu 2>/dev/null || true; fi
  docker rm -f esu-agent >/dev/null 2>&1 || true
  say "stopped"
}

case "${1:-}" in
  v1|v2|v3) cmd_run "$@" ;;
  agent) cmd_agent ;;
  logger) shift; cmd_logger "$@" ;;
  commander) shift; cmd_commander "$@" ;;
  build) cmd_build ;;
  stop) cmd_stop ;;
  *) sed -n '2,12p' "$self"; exit 1 ;;
esac
