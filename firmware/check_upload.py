"""PlatformIO pre-hook: accidental/default-profile uploads must fail closed."""
import os
import re
from SCons.Script import COMMAND_LINE_TARGETS, Import

Import('env')
if 'upload' in COMMAND_LINE_TARGETS:
    flags = str(env.GetProjectOption('build_flags'))
    match = re.search(r'ESU_BOARD_VERSION=([123])', flags)
    expected = 'v' + match.group(1) if match else None
    if (expected is None or os.environ.get('ESU_FLASH_BOARD') != expected
            or os.environ.get('ESU_FIXTURE_CONFIRMED') != '1'
            or not env.get('UPLOAD_PORT')):
        raise RuntimeError('Use software/esu.py flash --board vN --port DEVICE '
                           '--fixture-confirmed; no automatic board/port selection')
