"""Install/flash guards with subprocess and SCons replaced; no device access."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('esu_install', ROOT / 'software/esu.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class InstallTests(unittest.TestCase):
    def test_missing_confirmation_or_profile_never_runs(self):
        for argv in (['build'], ['flash', '--board', 'v1', '--port', '/dev/fixture'],
                     ['commander', '--board', 'v3'],
                     ['agent', '--port', '/dev/fixture', '--domain', '73']):
            with self.subTest(argv=argv), patch.object(helper, 'run') as run:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    helper.main(argv)
                run.assert_not_called()

    def test_build_explicit_profile_no_upload(self):
        with patch.object(helper, 'require_linux'), patch.object(helper, 'pio', return_value='pio'), \
                patch.object(helper, 'run') as run:
            helper.main(['build', '--board', 'v1'])
        self.assertEqual(run.call_args.args[0], ['pio', 'run', '-d', ROOT / 'firmware', '-e', 'v1'])

    def test_confirmed_flash_passes_exact_profile_and_port(self):
        with patch.object(helper, 'require_linux'), patch.object(helper, 'pio', return_value='pio'), \
                patch.object(helper, 'run') as run:
            helper.main(['flash', '--board', 'v2', '--port', '/dev/fixture', '--fixture-confirmed'])
        self.assertEqual(run.call_args.args[0][-4:], ['-t', 'upload', '--upload-port', '/dev/fixture'])
        self.assertEqual(run.call_args.kwargs['env']['ESU_FLASH_BOARD'], 'v2')

    def test_host_build_scoped_to_workspace_src(self):
        with patch.object(helper, 'require_linux'), patch.object(helper, 'run') as run:
            helper.main(['host-build'])
        self.assertEqual(run.call_args.kwargs['cwd'], ROOT / 'software/ros2')
        self.assertIn('--base-paths src', run.call_args.args[0][-1])

    def test_baud_is_identical_everywhere(self):
        import re
        from pedal_controller.protocol import BAUD
        profile = (ROOT / 'firmware/shared/board_profile.hpp').read_text()
        firmware = int(re.search(r'constexpr uint32_t baud = (\d+);', profile).group(1))
        self.assertEqual({firmware, BAUD, helper.BAUD}, {115200})

    def test_agent_uses_shared_baud_and_inherits_localhost_setting(self):
        with patch.object(helper, 'require_linux'), patch.object(helper, 'run') as run, \
                patch.object(helper.Path, 'exists', return_value=True), \
                patch.object(helper.Path, 'is_char_device', return_value=True), \
                patch.dict(os.environ, {'ROS_LOCALHOST_ONLY': '0'}):
            helper.main(['agent', '--port', '/dev/fixture'])
        cmd = run.call_args.args[0]
        self.assertIn('microros/micro-ros-agent:jazzy', cmd)
        self.assertEqual(cmd[cmd.index('-b') + 1], str(helper.BAUD))
        self.assertIn('ROS_LOCALHOST_ONLY=0', cmd)

    def test_no_pedal_build_flag_only_when_requested(self):
        for argv, expected in ((['build', '--board', 'v1'], None),
                               (['build', '--board', 'v1', '--no-pedal'], '-DESU_PEDAL_CONNECTED=0')):
            with patch.object(helper, 'require_linux'), \
                    patch.object(helper, 'pio', return_value='pio'), \
                    patch.object(helper, 'run') as run, \
                    patch.dict(os.environ, {'PLATFORMIO_BUILD_FLAGS': '-DSTALE'}):
                helper.main(argv)
            self.assertEqual(run.call_args.kwargs['env'].get('PLATFORMIO_BUILD_FLAGS'), expected)

    def test_direct_upload_hook_fails_closed(self):
        script = ModuleType('SCons.Script')
        script.Import = lambda name: None
        script.COMMAND_LINE_TARGETS = ['upload']
        env = Mock()
        env.GetProjectOption.return_value = '-DESU_BOARD_VERSION=2'
        env.get.return_value = '/dev/fixture'
        modules = {'SCons': ModuleType('SCons'), 'SCons.Script': script}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                runpy.run_path(str(ROOT / 'firmware/check_upload.py'), init_globals={'env': env})
            os.environ.update(ESU_FLASH_BOARD='v1', ESU_FIXTURE_CONFIRMED='1')
            with self.assertRaises(RuntimeError):
                runpy.run_path(str(ROOT / 'firmware/check_upload.py'), init_globals={'env': env})
            os.environ['ESU_FLASH_BOARD'] = 'v2'
            runpy.run_path(str(ROOT / 'firmware/check_upload.py'), init_globals={'env': env})
            env.get.return_value = None
            with self.assertRaises(RuntimeError):
                runpy.run_path(str(ROOT / 'firmware/check_upload.py'), init_globals={'env': env})


if __name__ == '__main__':
    unittest.main()
