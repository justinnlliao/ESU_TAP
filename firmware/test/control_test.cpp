#include "../shared/control.hpp"
#include <assert.h>
#include <stdio.h>

#if !ESU_PEDAL_CONNECTED
// Standalone build: pressed/floating sense inputs never drive relays or block
// arming; ROS commands still work and still expire.
int main() {
    esu::Controller c;
    bool inputs[4] = {true, true, true, true};
    for (uint32_t t = 0; t < 200; t += 10) c.sample(inputs, t);
    assert(c.state_bits() == 0);
    c.set_connected(true);
    assert(c.arm(true));
    assert(c.request(0, true, 200)); c.sample(inputs, 210);
    assert(c.state_bits() == 1);
    c.sample(inputs, 700); assert(!c.armed && c.state_bits() == 0);
    printf("v%d standalone control tests passed (%u channels)\n", ESU_BOARD_VERSION, esu::channel_count);
}
#else
int main() {
    esu::Controller c;
    bool inputs[4] = {};
    assert(!c.request(0, true, 0));
    assert(!c.arm(true));
    // Pedal press/release, including before any connection.
    inputs[0] = true;
    c.sample(inputs, 10); assert(!c.effective[0]);
    c.sample(inputs, 39); assert(!c.effective[0]);
    c.sample(inputs, 40); assert(c.effective[0]);
    c.set_connected(true);
    assert(!c.arm(true)); // Held pedal prevents arming computer commands.
    inputs[0] = false; c.sample(inputs, 50); c.sample(inputs, 80);
    assert(!c.effective[0]);
    assert(c.arm(true));
    for (unsigned i = 0; i < esu::channel_count; ++i) assert(c.request(i, true, 100));
    assert(!c.request(esu::channel_count, true, 100));
    c.sample(inputs, 101);
    assert(c.state_bits() == (1u << esu::channel_count) - 1);
    c.sample(inputs, 599); assert(c.armed);
    c.sample(inputs, 600); assert(!c.armed && c.state_bits() == 0);
    assert(!c.request(0, true, 601)); // Expiry cannot be undone by late refresh.
    assert(c.arm(true)); assert(c.request(0, true, 700));
    assert(c.request(0, true, 1100)); c.sample(inputs, 1500); assert(c.effective[0]);
    inputs[0] = true; c.sample(inputs, 1510); c.sample(inputs, 1540);
    c.sample(inputs, 1600); assert(!c.armed && c.effective[0]); // Pedal survives expiry.
    c.set_connected(false); c.sample(inputs, 1610); assert(c.effective[0]);
    inputs[0] = false; c.sample(inputs, 1620); c.sample(inputs, 1650); assert(!c.effective[0]);
    c.set_connected(true); assert(!c.armed && !c.command[0]);
    assert(c.arm(true)); assert(c.request(0, true, 1700));
    assert(c.request(0, false, 1701)); c.sample(inputs, 1702); assert(!c.effective[0]);
    assert(c.arm(false)); assert(!c.armed);
    // Rollover and late request processing without an intervening sample.
    assert(c.arm(true)); assert(c.request(0, true, 0xFFFFFF00u));
    c.sample(inputs, 0xF3u); assert(c.armed);
    assert(!c.request(0, true, 0xF4u)); assert(!c.armed);
    // Profile sanity: no output/sense/LED GPIO collisions, including watchdog.
    for (unsigned i = 0; i < esu::channel_count; ++i) {
        const unsigned a[] = {esu::pins[i].sense, esu::pins[i].relay, esu::pins[i].led};
        for (unsigned k = 0; k < 3; ++k) {
            assert(int(a[k]) != esu::watchdog_pin);
            for (unsigned j = 0; j < esu::channel_count; ++j) {
                const unsigned b[] = {esu::pins[j].sense, esu::pins[j].relay, esu::pins[j].led};
                for (unsigned l = 0; l < 3; ++l)
                    if (i != j || k != l) assert(a[k] != b[l]);
            }
        }
    }
    printf("v%d control tests passed (%u channels)\n", ESU_BOARD_VERSION, esu::channel_count);
}
#endif
