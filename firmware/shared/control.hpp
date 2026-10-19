#pragma once
#include "board_profile.hpp"

namespace esu {
// No Arduino/ROS dependencies. Caller serializes access; only the control task
// writes GPIO. Unsigned subtraction intentionally handles millis() rollover.
struct Controller {
    bool connected = false, armed = false;
    bool raw[4] = {}, sensed[4] = {}, command[4] = {}, effective[4] = {};
    uint32_t raw_since[4] = {}, renewed[4] = {};

    void disarm() {
        armed = false;
        for (unsigned i = 0; i < channel_count; ++i) command[i] = false;
    }
    void set_connected(bool value) {
        if (!value || value != connected) disarm();
        connected = value;
    }
    void expire(uint32_t now) {
        for (unsigned i = 0; i < channel_count; ++i)
            if (command[i] && uint32_t(now - renewed[i]) >= lease_ms) {
                disarm();
                break;
            }
    }
    bool arm(bool value) {
        if (!value) { disarm(); return true; }
        if (!connected) return false;
        for (unsigned i = 0; i < channel_count; ++i)
            if (raw[i] || sensed[i] || command[i]) return false;
        armed = true;
        return true;
    }
    bool request(unsigned i, bool on, uint32_t now) {
        if (i >= channel_count) return false;
        expire(now); // A late renewal must not revive an expired command.
        if (!on) { command[i] = false; return true; }
        if (!armed || !connected) return false;
        command[i] = true;
        renewed[i] = now;
        return true;
    }
    void sample(const bool inputs[4], uint32_t now) {
        expire(now);
        for (unsigned i = 0; i < channel_count; ++i) {
            // Standalone builds ignore the sense pins entirely.
            const bool input = pedal_connected && inputs[i];
            if (input != raw[i]) { raw[i] = input; raw_since[i] = now; }
            if (uint32_t(now - raw_since[i]) >= debounce_ms) sensed[i] = raw[i];
            effective[i] = sensed[i] || command[i]; // Local pedals work without ROS.
        }
    }
    uint8_t state_bits() const {
        uint8_t result = 0;
        for (unsigned i = 0; i < channel_count; ++i) result |= unsigned(effective[i]) << i;
        return result;
    }
};
}
