#pragma once
#include "board_profile.hpp"

namespace esu {
// No Arduino/ROS dependencies. Caller serializes access; only the control task
// writes GPIO. Unsigned subtraction intentionally handles millis() rollover.
struct Controller {
    bool connected = false, armed = false;
    bool took_over = false; // Set by the sample() in which a pedal ended autonomous control.
    // Set with took_over when the takeover opened no computer output (pedal pressed
    // on the channel the computer already held, or armed with nothing commanded):
    // the caller still reports the hand-over with an unchanged-state message.
    bool takeover_unchanged = false;
    bool raw[4] = {}, sensed[4] = {}, command[4] = {};
    bool desired[4] = {};   // sensed OR command, before the break-before-make interlock
    bool effective[4] = {}; // what the relays/LEDs are driven to and what telemetry reports
    // Per-sample output edges and who caused them: 0 pedal, 1 computer, 3 takeover.
    bool edge[4] = {};
    uint8_t edge_source[4] = {}, cause[4] = {};
    bool released_before = false;
    uint32_t raw_since[4] = {}, renewed[4] = {}, last_release = 0;

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
        took_over = false;
        takeover_unchanged = false;
        expire(now);
        bool sensed_changed[4] = {};
        for (unsigned i = 0; i < channel_count; ++i) {
            // Standalone builds ignore the sense pins entirely.
            const bool input = pedal_connected && inputs[i];
            if (input != raw[i]) { raw[i] = input; raw_since[i] = now; }
            if (uint32_t(now - raw_since[i]) >= debounce_ms && sensed[i] != raw[i]) {
                sensed[i] = raw[i];
                sensed_changed[i] = true;
            }
        }
        // Manual priority: a debounced pedal press ends autonomous control on
        // every channel. Re-entering it needs a deliberate re-arm (pedals released).
        for (unsigned i = 0; i < channel_count; ++i)
            if (sensed[i] && armed) { disarm(); took_over = true; break; }
        for (unsigned i = 0; i < channel_count; ++i) {
            const bool want = sensed[i] || command[i]; // Local pedals work without ROS.
            if (want != desired[i]) {
                desired[i] = want;
                cause[i] = sensed_changed[i] ? 0 : took_over ? 3 : 1;
            }
            edge[i] = false;
        }
        // Break-before-make: open outputs first. A closing output waits until no
        // output has opened within interlock_ms, i.e. the next 10 ms cycle, so two
        // channels' contacts never overlap during a takeover or a fast switch.
        bool takeover_edge = false;
        for (unsigned i = 0; i < channel_count; ++i)
            if (effective[i] && !desired[i]) {
                effective[i] = false;
                edge[i] = true; edge_source[i] = cause[i];
                takeover_edge = takeover_edge || cause[i] == 3;
                last_release = now; released_before = true;
            }
        const bool interlocked = released_before && uint32_t(now - last_release) < interlock_ms;
        for (unsigned i = 0; i < channel_count; ++i)
            if (!effective[i] && desired[i] && !interlocked) {
                effective[i] = true;
                edge[i] = true; edge_source[i] = cause[i];
            }
        takeover_unchanged = took_over && !takeover_edge;
    }
    uint8_t state_bits() const {
        uint8_t result = 0;
        for (unsigned i = 0; i < channel_count; ++i) result |= unsigned(effective[i]) << i;
        return result;
    }
};
}
