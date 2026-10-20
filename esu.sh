#!/usr/bin/env bash
# ESU-TAP one-stop helper for a fresh clone or a `git pull` on Ubuntu 22.04 / ROS 2 Humble.
#
#   ./esu.sh setup                 one time: PlatformIO + ROS package (+ optional Docker agent image)
#   ./esu.sh flash v1 pedal        build + flash: board v1|v2|v3, mode pedal|nopedal
#   ./esu.sh update                git pull, rebuild, offer to reflash the last board/mode
#   ./esu.sh agent | logger | commander | mock   start one runtime piece
#   ./esu.sh run                   agent + logger (+ commander) in tmux panes; ./esu.sh stop
#   ./esu.sh docker                pull the micro-ROS agent image (optional)
#   ./esu.sh port                  show which ESP32 serial port would be used
#   ./esu.sh status                what this computer has / what was last flashed
#
# The ESP32 port is found automatically under /dev/serial/by-id (asks if there is
# more than one). Flashing always asks you to confirm the generator is disconnected.
# Everything real is done by software/esu.py; this script only picks sensible
# defaults and remembers the last board/mode in .esu-board (not committed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER=(python3 "$ROOT/software/esu.py")
STATE="$ROOT/.esu-board"
SERIAL_DIR="${ESU_SERIAL_DIR:-/dev/serial/by-id}"
AGENT_IMAGE="${ESU_AGENT_IMAGE:-microros/micro-ros-agent:jazzy}"

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
ask()  { local reply; read -r -p "$1 [y/N] " reply || true; [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]; }

usage() { sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

# ---------- remembered board / mode ----------
saved_board() { [[ -f "$STATE" ]] && sed -n 's/^board=//p' "$STATE" || true; }
saved_mode()  { [[ -f "$STATE" ]] && sed -n 's/^mode=//p' "$STATE" || true; }
remember()    { printf 'board=%s\nmode=%s\n' "$1" "$2" > "$STATE"; }

check_board() {
  case "${1:-}" in
    v1|v2|v3) ;;
    "") die "Which board? Use v1, v2 or v3 (e.g. ./esu.sh flash v1 pedal)." ;;
    *) die "Unknown board '$1': use v1, v2 or v3." ;;
  esac
}

normalize_mode() {
  case "${1:-pedal}" in
    pedal|with-pedal|withpedal) echo pedal ;;
    nopedal|no-pedal|without-pedal|withoutpedal|standalone) echo nopedal ;;
    *) die "Unknown mode '$1': use pedal or nopedal." ;;
  esac
}

board_or_saved() {
  local board="${1:-$(saved_board)}"
  [[ -n "$board" ]] || die "No board given and none flashed from here yet. Add v1, v2 or v3."
  check_board "$board"
  echo "$board"
}

# ---------- serial port ----------
find_port() {
  if [[ -n "${ESU_PORT:-}" ]]; then echo "$ESU_PORT"; return; fi
  [[ -d "$SERIAL_DIR" ]] || die "No serial devices found ($SERIAL_DIR missing). Plug in the ESP32 with a DATA USB cable."
  local all=() esp=() dev
  for dev in "$SERIAL_DIR"/*; do [[ -e "$dev" ]] && all+=("$dev"); done
  # Common ESP32 DevKitC USB bridges: Silicon Labs CP210x, WCH CH340/CH9102, FTDI.
  for dev in "${all[@]}"; do
    [[ "$(basename "$dev")" =~ CP210|Silicon_Labs|CH34|CH910|1a86|QinHeng|FTDI|FT232 ]] && esp+=("$dev")
  done
  ((${#esp[@]})) || esp=("${all[@]}")
  case ${#esp[@]} in
    0) die "No serial devices found. Plug in the ESP32 with a DATA USB cable." ;;
    1) echo "${esp[0]}" ;;
    *)
      warn "More than one serial device. Unplug/replug the ESP32 if unsure which it is."
      local i=1
      for dev in "${esp[@]}"; do printf '  %d) %s\n' "$i" "$(basename "$dev")" >&2; i=$((i + 1)); done
      local pick
      read -r -p "Which one is the ESP32? [1-${#esp[@]}] " pick
      if ! [[ "$pick" =~ ^[0-9]+$ ]] || ((pick < 1 || pick > ${#esp[@]})); then
        die "No port chosen."
      fi
      echo "${esp[$((pick - 1))]}" ;;
  esac
}

check_port_access() {
  local port="$1"
  [[ -r "$port" && -w "$port" ]] && return
  die "No permission for $port. Run: sudo usermod -aG dialout \"\$USER\"  then log out and back in."
}

stop_agent_if_running() {
  command -v docker >/dev/null 2>&1 || return 0
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx esu-agent; then
    say "Stopping the running esu-agent so the serial port is free..."
    docker stop esu-agent >/dev/null
  fi
}

# ---------- commands ----------
cmd_setup() {
  say "Checking this computer..."
  local missing=()
  command -v python3 >/dev/null || missing+=("python3")
  python3 -c 'import venv' 2>/dev/null || missing+=("python3-venv")
  command -v git >/dev/null || missing+=("git")
  command -v cmake >/dev/null || missing+=("cmake")
  [[ -f /opt/ros/humble/setup.bash ]] || missing+=("ROS 2 Humble (/opt/ros/humble)")
  command -v colcon >/dev/null || [[ -f /opt/ros/humble/setup.bash ]] || missing+=("colcon")
  if ((${#missing[@]})); then
    warn "Missing: ${missing[*]}"
    warn "Typical fix: sudo apt install git cmake build-essential python3-pip python3-venv python3-colcon-common-extensions"
    warn "ROS 2 Humble itself: https://docs.ros.org/en/humble/Installation.html"
    ask "Continue anyway?" || exit 1
  fi
  if ! id -nG | grep -qw dialout; then
    warn "Your account is not in the 'dialout' group, so flashing may be refused."
    warn "Fix once: sudo usermod -aG dialout \"\$USER\"  (then log out and back in)"
  fi

  say "Installing PlatformIO for firmware builds (per user, no sudo)..."
  "${HELPER[@]}" setup
  say "Building the ROS 2 package..."
  "${HELPER[@]}" host-build

  if [[ "${1:-}" == "--with-docker" ]]; then
    cmd_docker
  elif [[ "${1:-}" != "--no-docker" ]] && command -v docker >/dev/null; then
    if ask "Also pull the micro-ROS agent Docker image now? (optional; 'run' pulls it later anyway)"; then
      cmd_docker
    fi
  fi
  say "Setup done. Next: ./esu.sh flash v1 pedal   (or nopedal; v2/v3 for newer boards)"
}

cmd_docker() {
  command -v docker >/dev/null || die "Docker is not installed. It is only needed for the agent."
  say "Pulling $AGENT_IMAGE ..."
  docker pull "$AGENT_IMAGE"
}

cmd_flash() {
  local board mode port flags=()
  board="${1:-}"; check_board "$board"
  mode="$(normalize_mode "${2:-pedal}")"
  [[ "$mode" == nopedal ]] && flags+=(--no-pedal)
  port="$(find_port)"
  check_port_access "$port"
  say "Board $board, mode: $([[ $mode == pedal ]] && echo 'WITH pedal' || echo 'WITHOUT pedal (standalone)')"
  say "Port: $port"
  warn "Flashing must be done with the electrosurgical generator DISCONNECTED."
  ask "Is the generator disconnected?" || die "Not flashed."
  stop_agent_if_running
  "${HELPER[@]}" flash --board "$board" --port "$port" --fixture-confirmed "${flags[@]}"
  remember "$board" "$mode"
  say "Flashed $board ($mode). Start it with: ./esu.sh run"
}

cmd_update() {
  say "Pulling the latest code..."
  git -C "$ROOT" pull --ff-only
  say "Rebuilding the ROS 2 package..."
  "${HELPER[@]}" host-build
  local board mode
  board="$(saved_board)"; mode="$(saved_mode)"
  if [[ -z "$board" ]]; then
    say "No board flashed from this computer yet. To flash: ./esu.sh flash v1 pedal"
  elif ask "Reflash the ESP32 as $board ($mode) with the new firmware?"; then
    cmd_flash "$board" "$mode"
  fi
}

cmd_agent() {
  local port; port="$(find_port)"; check_port_access "$port"
  "${HELPER[@]}" agent --port "$port" --agent-image "$AGENT_IMAGE"
}

cmd_logger()    { "${HELPER[@]}" logger --board "$(board_or_saved "${1:-}")"; }
cmd_commander() {
  local board; board="$(board_or_saved "${1:-}")"
  warn "Computer commands are for a disconnected test fixture (or the mock), not a live generator."
  ask "Is the generator disconnected?" || die "Commander not started."
  "${HELPER[@]}" commander --board "$board" --fixture-confirmed
}
cmd_mock() {
  local board mode flags=()
  board="$(board_or_saved "${1:-}")"
  mode="$(normalize_mode "${2:-pedal}")"
  [[ "$mode" == nopedal ]] && flags+=(--no-pedal)
  "${HELPER[@]}" mock --board "$board" "${flags[@]}"
}

cmd_run() {
  local board self
  board="$(board_or_saved "${1:-}")"
  self="$ROOT/esu.sh"
  if ! command -v tmux >/dev/null; then
    say "tmux is not installed (sudo apt install tmux). Run these in three terminals instead:"
    printf '  %s agent\n  %s logger %s\n  %s commander %s\n' "$self" "$self" "$board" "$self" "$board"
    return
  fi
  tmux has-session -t esu 2>/dev/null && die "An 'esu' tmux session already exists: tmux attach -t esu"
  tmux new-session -d -s esu -n esu "bash '$self' agent; read -r -p 'agent exited; Enter to close'"
  sleep 2
  tmux split-window -h -t esu "bash '$self' logger $board; read -r -p 'logger exited; Enter to close'"
  tmux split-window -v -t esu "bash '$self' commander $board; read -r -p 'commander exited; Enter to close'"
  tmux select-layout -t esu tiled >/dev/null
  say "Started agent, logger and commander in tmux. Detach: Ctrl+B then D. Stop: ./esu.sh stop"
  tmux attach -t esu
}

cmd_stop() {
  command -v tmux >/dev/null && tmux kill-session -t esu 2>/dev/null || true
  stop_agent_if_running
  say "Stopped."
}

cmd_status() {
  printf 'Repository:     %s\n' "$ROOT"
  printf 'Last flashed:   %s\n' "$( [[ -f $STATE ]] && echo "$(saved_board) ($(saved_mode))" || echo 'nothing from this computer')"
  printf 'ESP32 port:     %s\n' "$( (find_port) 2>/dev/null </dev/null || echo 'none or several (./esu.sh port to choose)')"
  printf 'PlatformIO:     %s\n' "$( [[ -x ~/.platformio/penv/bin/pio ]] && echo installed || echo 'missing (./esu.sh setup)')"
  printf 'ROS package:    %s\n' "$( [[ -f $ROOT/software/ros2/install/setup.bash ]] && echo built || echo 'not built (./esu.sh setup)')"
  printf 'Docker image:   %s\n' "$(command -v docker >/dev/null && docker image inspect "$AGENT_IMAGE" >/dev/null 2>&1 && echo pulled || echo 'not pulled (optional: ./esu.sh docker)')"
}

main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    setup)      cmd_setup "$@" ;;
    flash)      cmd_flash "$@" ;;
    update)     cmd_update ;;
    agent)      cmd_agent ;;
    logger)     cmd_logger "$@" ;;
    commander)  cmd_commander "$@" ;;
    mock)       cmd_mock "$@" ;;
    run)        cmd_run "$@" ;;
    stop)       cmd_stop ;;
    docker)     cmd_docker ;;
    port)       find_port ;;
    status)     cmd_status ;;
    help|-h|--help) usage 0 ;;
    *) warn "Unknown command: $cmd"; usage 1 ;;
  esac
}

main "$@"
