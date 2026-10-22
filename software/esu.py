#!/usr/bin/env python3
"""Path-independent Ubuntu/Humble setup helper. Never guesses a board or port."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'software' / 'ros2'
# Must equal firmware/shared/board_profile.hpp `baud` and protocol.py BAUD
# (enforced by test_install.py).
BAUD = 115200
# The humble agent image crashed on the lab host; the jazzy image is the one
# that worked there with this Humble firmware/PC stack. Override with --agent-image.
AGENT_IMAGE = 'microros/micro-ros-agent:jazzy'


def run(command, *, cwd=ROOT, env=None):
    print(shlex.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, env=env, check=True)


def core_dir():
    return Path(os.environ.get('PLATFORMIO_CORE_DIR', str(Path.home() / '.platformio')))


def pio():
    path = core_dir() / 'penv' / ('Scripts/platformio.exe' if os.name == 'nt' else 'bin/pio')
    if not path.is_file():
        raise RuntimeError('PlatformIO core venv missing. Run: python3 software/esu.py setup')
    return path


def require_linux():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Use Ubuntu 22.04 / ROS Humble for this build/runtime pipeline; '
                           'native Windows micro-ROS builds are not validated.')


def ros_command(executable, arguments, domain):
    require_linux()
    base = Path('/opt/ros/humble/setup.bash')
    overlay = WORKSPACE / 'install/setup.bash'
    if not base.is_file() or not overlay.is_file():
        raise RuntimeError('Install ROS Humble and run host-build first')
    # ROS_LOCALHOST_ONLY is inherited, not forced, so these nodes can still see
    # the lab's other ROS nodes. The agent container gets the same value.
    env = dict(os.environ, ROS_DOMAIN_ID=str(domain))
    run(['bash', '-c', 'source "$1" && source "$2" && shift 2 && exec "$@"',
         'esu', base, overlay, 'ros2', 'run', 'pedal_controller', executable, *arguments], env=env)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('setup', help='Create/reuse PlatformIO core venv; does not install OS packages')
    sub.add_parser('doctor', help='Read-only environment report')
    sub.add_parser('host-build', help='Build ROS workspace from its actual path')
    for action in ('build', 'flash'):
        p = sub.add_parser(action)
        p.add_argument('--board', choices=('v1', 'v2', 'v3'), required=True)
        if action == 'flash':
            p.add_argument('--port', required=True)
            p.add_argument('--fixture-confirmed', action='store_true')
        p.add_argument('--no-pedal', action='store_true',
                       help='Standalone/autonomous image: ignore pedal sense inputs')
    agent = sub.add_parser('agent')
    agent.add_argument('--port', required=True)
    agent.add_argument('--domain', type=int, default=0)
    agent.add_argument('--agent-image', default=AGENT_IMAGE)
    for action in ('logger', 'commander', 'mock'):
        p = sub.add_parser(action)
        p.add_argument('--board', choices=('v1', 'v2', 'v3'), required=True)
        p.add_argument('--domain', type=int, default=73 if action == 'mock' else 0)
        if action == 'commander':
            p.add_argument('--fixture-confirmed', action='store_true')
        if action == 'mock':
            p.add_argument('--no-pedal', action='store_true')
        if action == 'logger':
            p.add_argument('--trial', default='', help='Trial ID shared with the other recorders')
    args = parser.parse_args(argv)
    if hasattr(args, 'domain') and not 0 <= args.domain <= 101:
        parser.error('Use an isolated domain in range 0..101')
    if args.action == 'agent' and args.domain != 0:
        parser.error('Current ESP32 images use domain 0; agent environment cannot change firmware domain')
    if args.action in ('flash', 'commander') and not args.fixture_confirmed:
        parser.error('Requires --fixture-confirmed: generator physically disconnected')
    if args.action == 'doctor':
        print('Repository:', ROOT)
        print('Python:', sys.executable)
        print('PlatformIO core:', core_dir())
        for name in ('git', 'cmake', 'docker', 'colcon', 'rosdep'):
            print(name + ':', shutil.which(name) or 'not on PATH')
        print('ROS Humble:', Path('/opt/ros/humble/setup.bash').is_file())
        print(f'Supported pipeline: Ubuntu 22.04, ROS Humble, serial {BAUD}, one agent.')
        return
    require_linux()
    if args.action == 'setup':
        target = core_dir() / 'penv'
        interpreter = target / 'bin/python'
        if not interpreter.is_file():
            run([sys.executable, '-m', 'venv', target])
        run([interpreter, '-m', 'pip', 'install', 'platformio>=6.1,<7'])
    elif args.action in ('build', 'flash'):
        cmd = [pio(), 'run', '-d', ROOT / 'firmware', '-e', args.board]
        if args.action == 'flash':
            cmd += ['-t', 'upload', '--upload-port', args.port]
        env = dict(os.environ)
        env.pop('PLATFORMIO_BUILD_FLAGS', None)   # Only this helper's flags apply.
        if args.no_pedal:
            env['PLATFORMIO_BUILD_FLAGS'] = '-DESU_PEDAL_CONNECTED=0'
        if args.action == 'flash':
            env.update(ESU_FLASH_BOARD=args.board, ESU_FIXTURE_CONFIRMED='1')
        run(cmd, env=env)
    elif args.action == 'host-build':
        run(['bash', '-c', 'source /opt/ros/humble/setup.bash && '
             'colcon build --base-paths src --symlink-install --packages-select pedal_controller'],
            cwd=WORKSPACE)
    elif args.action == 'agent':
        port = Path(args.port)
        if not port.exists() or not port.is_char_device():
            raise RuntimeError('Select the actual ESP32 character device (prefer /dev/serial/by-id/...)')
        run(['docker', 'run', '--rm', '--name', 'esu-agent', '--network', 'host',
             '--device', f'{port}:/dev/esu', '-e', f'ROS_DOMAIN_ID={args.domain}',
             '-e', f"ROS_LOCALHOST_ONLY={os.environ.get('ROS_LOCALHOST_ONLY', '0')}",
             args.agent_image, 'serial', '--dev', '/dev/esu', '-b', str(BAUD), '-v4'])
    else:
        executable = {'logger': 'pedal_logger', 'commander': 'pedal_commander',
                      'mock': 'mock_esu_node'}[args.action]
        params = ['--ros-args', '-p', f'board_version:={args.board}']
        if args.action == 'commander':
            params += ['-p', 'fixture_confirmed:=true']
        if args.action == 'logger' and args.trial:
            params += ['-p', f'trial_id:={args.trial}']
        if args.action == 'mock' and args.no_pedal:
            params += ['-p', 'pedal_connected:=false']
        ros_command(executable, params, args.domain)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
