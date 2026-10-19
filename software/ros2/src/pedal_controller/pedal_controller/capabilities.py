"""Strict, ROS-independent protocol-2 capability contract."""
import json
from .protocol import BAUD, revision_channels


def parse_capabilities(text, expected='auto'):
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('Malformed capability JSON') from exc
    if not isinstance(data, dict) or type(data.get('protocol')) is not int or data['protocol'] != 2:
        raise ValueError('Requires shared protocol-2 firmware; do not guess legacy capabilities')
    channels = revision_channels(data.get('board'))
    if expected != 'auto' and data['board'] != expected:
        raise ValueError('Firmware profile differs from selected board_version')
    if type(data.get('channel_count')) is not int or data['channel_count'] != len(channels):
        raise ValueError('Invalid capability channel count')
    if type(data.get('pedal_connected')) is not bool:
        raise ValueError('Invalid pedal_connected field; reflash current firmware')
    # Pedals work offline only when the image reads them at all.
    if (data.get('offline_pedals') is not data['pedal_connected']
            or data.get('requires_arm') is not True):
        raise ValueError('Unsupported control policy')
    if type(data.get('watchdog')) is not bool or data['watchdog'] != (data['board'] != 'v1'):
        raise ValueError('Watchdog capability disagrees with board profile')
    for key in ('baud', 'lease_ms', 'refresh_ms', 'state', 'boot_id', 'dropped_events'):
        if type(data.get(key)) is not int or data[key] < 0:
            raise ValueError(f'Invalid capability {key}')
    if not (0 < data['refresh_ms'] < data['lease_ms'] // 2 <= 5000):
        raise ValueError('Unsupported lease/refresh limits')
    if data['baud'] != BAUD or data['state'] >= (1 << len(channels)):
        raise ValueError(f'Invalid baud (expected {BAUD}) or snapshot state')
    if type(data.get('armed')) is not bool or not isinstance(data.get('firmware'), str):
        raise ValueError('Invalid firmware/armed fields')
    return data
