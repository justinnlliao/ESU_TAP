#pragma once
#include <stdint.h>

#ifndef ESU_BOARD_VERSION
#error Select an explicit v1, v2, or v3 PlatformIO environment.
#endif

namespace esu {
struct ChannelPins { uint8_t sense, relay, led; };
#if ESU_BOARD_VERSION == 1
constexpr unsigned channel_count = 2;
constexpr int watchdog_pin = -1;
constexpr ChannelPins pins[] = {{34, 26, 18}, {35, 27, 21}};
#elif ESU_BOARD_VERSION == 2
constexpr unsigned channel_count = 3;
constexpr int watchdog_pin = 14;
constexpr ChannelPins pins[] = {{35, 26, 23}, {34, 27, 22}, {17, 19, 21}};
#elif ESU_BOARD_VERSION == 3
constexpr unsigned channel_count = 4;
constexpr int watchdog_pin = 14;
constexpr ChannelPins pins[] = {{35, 26, 23}, {34, 27, 22}, {17, 19, 21}, {25, 33, 18}};
#else
#error Unknown board profile; never infer pin mapping from the ESP32 model.
#endif
// PEDAL_CONNECTED (default 1): a foot pedal is wired to the sense inputs.
// Build with -DESU_PEDAL_CONNECTED=0 (software/esu.py --no-pedal) for
// standalone/autonomous use: sense inputs are then ignored, so unwired
// inputs cannot read as phantom presses. Only ROS commands drive relays.
#ifndef ESU_PEDAL_CONNECTED
#define ESU_PEDAL_CONNECTED 1
#endif
constexpr bool pedal_connected = ESU_PEDAL_CONNECTED != 0;
// Serial baud, every profile. The PC side checks the same value
// (pedal_controller/protocol.py BAUD, software/esu.py BAUD); a test keeps
// all three equal.
constexpr uint32_t baud = 115200;
constexpr uint32_t lease_ms = 500; // Prototype bench setting, NOT a validated safety limit.
constexpr uint32_t refresh_ms = 100;
constexpr uint32_t debounce_ms = 30;
constexpr const char* services[] = {"/esu/cut", "/esu/coag", "/esu/bipolar", "/esu/ligasure"};
}
