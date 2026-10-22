// Runs firmware/shared/runtime.hpp on a PC: the control task and loop() on real
// threads, with micro-ROS/Arduino replaced by host_stubs. Checks the runtime
// behavior that the pure control tests cannot: telemetry, resync, reconnect,
// pin setup, capabilities and watchdog petting. Not a model of the ESP32
// scheduler, XRCE transport or hardware. Build (from repo root):
//   g++ -std=gnu++17 -pthread -Ifirmware/test/host_stubs -DESU_BOARD_VERSION=3
//       firmware/test/runtime_sim.cpp -o /tmp/esu-runtime-sim && /tmp/esu-runtime-sim
#include "host_sim.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <string>
#include <thread>

static auto t0 = std::chrono::steady_clock::now();
static std::atomic<int> pin_level[64], pin_mode[64], pin_writes[64];
static std::atomic<int> floating{0}, agent_up{1}, fail_next_publish{0}, creates{0};
static std::mutex pub_m;
static std::vector<int> pubs;
static std::vector<rcl_service_t*> services;
static unsigned long baud;
HostSerial Serial;

void HostSerial::begin(unsigned long b) { baud = b; }
unsigned long millis() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - t0).count();
}
void delay(unsigned long ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
void pinMode(int p, int m) { pin_mode[p] = m; }
static std::atomic<int> watch_overlap{0}, overlaps{0};
static int relay_pin_count();
static bool is_relay_pin(int p);
void digitalWrite(int p, int l) {
    if (pin_level[p] != (l ? 1 : 0)) ++pin_writes[p];
    pin_level[p] = l ? 1 : 0;
    // Break-before-make check: two relay outputs must never be HIGH together.
    if (watch_overlap && l && is_relay_pin(p) && relay_pin_count() > 1) ++overlaps;
}
int digitalRead(int p) {
    if (floating && pin_mode[p] != OUTPUT) return rand() & 1;   // unwired input noise
    return pin_level[p];
}
uint32_t esp_random() { return 0xDEAD; }
static uint32_t stored_boots = 0;
static int nvs_write_fails = 0;
bool Preferences::begin(const char*, bool) { return true; }
uint32_t Preferences::getUInt(const char*, uint32_t) { return stored_boots; }
size_t Preferences::putUInt(const char*, uint32_t v) {
    if (nvs_write_fails) return 0;
    stored_boots = v;
    return 4;
}

QueueHandle_t xQueueCreate(size_t n, size_t sz) { auto* q = new SimQueue; q->cap = n; q->item = sz; return q; }
BaseType_t xQueueSend(QueueHandle_t q, const void* v, TickType_t) {
    std::lock_guard<std::mutex> g(q->m);
    if (q->q.size() >= q->cap) return 0;
    q->q.emplace_back((const char*)v, (const char*)v + q->item);
    return pdTRUE;
}
BaseType_t xQueueReceive(QueueHandle_t q, void* v, TickType_t) {
    std::lock_guard<std::mutex> g(q->m);
    if (q->q.empty()) return 0;
    memcpy(v, q->q.front().data(), q->item); q->q.pop_front();
    return pdTRUE;
}
void xQueueReset(QueueHandle_t q) { std::lock_guard<std::mutex> g(q->m); q->q.clear(); }
TickType_t xTaskGetTickCount() { return millis(); }
void vTaskDelayUntil(TickType_t* next, TickType_t inc) {
    *next += inc;
    const long d = long(*next) - long(millis());
    if (d > 0) delay(d);
}
BaseType_t xTaskCreatePinnedToCore(void (*fn)(void*), const char*, int, void*, int, void*, int) {
    std::thread(fn, nullptr).detach();
    return pdPASS;
}

rcl_node_t rcl_get_zero_initialized_node() { return {}; }
rcl_publisher_t rcl_get_zero_initialized_publisher() { return {}; }
rcl_service_t rcl_get_zero_initialized_service() { return {}; }
rclc_executor_t rclc_executor_get_zero_initialized_executor() { return {}; }
rcl_allocator_t rcl_get_default_allocator() { return {}; }
rcl_ret_t rclc_support_init(rclc_support_t*, int, const char* const*, rcl_allocator_t*) { ++creates; services.clear(); return 0; }
rcl_ret_t rclc_node_init_default(rcl_node_t*, const char*, const char*, rclc_support_t*) { return 0; }
static std::string pub_type, pub_topic;
rcl_ret_t rclc_publisher_init_default(rcl_publisher_t*, rcl_node_t*, const char* t, const char* n) { pub_type = t; pub_topic = n; return 0; }
rmw_publisher_t* rcl_publisher_get_rmw_handle(rcl_publisher_t*) { static rmw_publisher_t p; return &p; }
rmw_ret_t rmw_uros_set_publisher_session_timeout(rmw_publisher_t*, int) { return 0; }
rcl_ret_t rclc_service_init_default(rcl_service_t* s, rcl_node_t*, const char* t, const char* n) { s->name = n; s->type = t; return 0; }
rcl_ret_t rclc_executor_init(rclc_executor_t* e, rcl_context_t*, size_t n, rcl_allocator_t*) { e->handles = int(n); e->used = 0; return 0; }
rcl_ret_t rclc_executor_add_service(rclc_executor_t* e, rcl_service_t* s, void* rq, void* rs, rclc_service_callback_t cb) {
    if (++e->used > e->handles) return 1;
    s->cb = cb; s->req = rq; s->resp = rs; services.push_back(s);
    return 0;
}

// Service requests are queued by the test thread and executed inside
// spin_some on the loop thread, as rclc does.
struct Call { std::string name; bool data; int* ok; std::string* msg; std::atomic<int>* done; };
static std::mutex call_m;
static std::deque<Call> calls;
rcl_ret_t rclc_executor_spin_some(rclc_executor_t*, int64_t) {
    std::lock_guard<std::mutex> g(call_m);
    while (!calls.empty()) {
        Call c = calls.front(); calls.pop_front();
        *c.ok = -1;
        for (auto* s : services) {
            if (c.name != s->name) continue;
            if (!strcmp(s->type, "std_srvs/srv/Trigger")) {
                s->cb(s->req, s->resp);
                auto* r = static_cast<std_srvs__srv__Trigger_Response*>(s->resp);
                *c.ok = r->success; c.msg->assign(r->message.data, r->message.size);
            } else {
                static_cast<std_srvs__srv__SetBool_Request*>(s->req)->data = c.data;
                s->cb(s->req, s->resp);
                *c.ok = static_cast<std_srvs__srv__SetBool_Response*>(s->resp)->success;
            }
        }
        *c.done = 1;
    }
    return RCL_RET_TIMEOUT;
}
rcl_ret_t rcl_publish(rcl_publisher_t*, const void* m, void*) {
    if (fail_next_publish.exchange(0)) return 1;
    std::lock_guard<std::mutex> g(pub_m);
    pubs.push_back(static_cast<const std_msgs__msg__Int32*>(m)->data);
    return 0;
}
rcl_ret_t rcl_service_fini(rcl_service_t*, rcl_node_t*) { return 0; }
rcl_ret_t rcl_publisher_fini(rcl_publisher_t*, rcl_node_t*) { return 0; }
rcl_ret_t rclc_executor_fini(rclc_executor_t*) { return 0; }
rcl_ret_t rcl_node_fini(rcl_node_t*) { return 0; }
rcl_ret_t rclc_support_fini(rclc_support_t*) { services.clear(); return 0; }
rmw_context_t* rcl_context_get_rmw_context(rcl_context_t* c) { return &c->rmw; }
rmw_ret_t rmw_uros_set_context_entity_destroy_session_timeout(rmw_context_t*, int) { return 0; }
rmw_ret_t rmw_uros_ping_agent(int timeout, int) { if (!agent_up) { delay(timeout); return 1; } return 0; }
void rcl_reset_error() {}

#include "../shared/runtime.hpp"

static int call(const char* name, bool data, std::string* msg = nullptr) {
    int ok = -2; std::string m; std::atomic<int> done{0};
    { std::lock_guard<std::mutex> g(call_m); calls.push_back({name, data, &ok, &m, &done}); }
    for (int i = 0; i < 1000 && !done; ++i) delay(1);
    if (msg) *msg = m;
    return ok;
}
static std::vector<int> take() { std::lock_guard<std::mutex> g(pub_m); auto v = pubs; pubs.clear(); return v; }
static int relay(unsigned i) { return pin_level[esu::pins[i].relay]; }
static bool is_relay_pin(int p) {
    for (unsigned i = 0; i < esu::channel_count; ++i) if (esu::pins[i].relay == p) return true;
    return false;
}
static int relay_pin_count() {
    int on = 0;
    for (unsigned i = 0; i < esu::channel_count; ++i) on += relay(i);
    return on;
}
static void press(unsigned i, bool on) { pin_level[esu::pins[i].sense] = on ? 0 : 1; }

int main() {
    for (auto& p : pin_level) p = 1;   // board pull-ups: released pedals read HIGH
    setup();
    std::thread([] { for (;;) loop(); }).detach();
    const int n = int(esu::channel_count);

    assert(baud == 115200);
    for (int i = 0; i < n; ++i) {
        assert(pin_mode[esu::pins[i].sense] == (esu::pins[i].sense >= 34 ? INPUT : INPUT_PULLUP));
        assert(pin_mode[esu::pins[i].relay] == OUTPUT && relay(i) == 0);
    }
    delay(800);
    assert(creates == 1 && pub_type == "std_msgs/msg/Int32" && pub_topic == "/esu/activation_state");
    assert(int(services.size()) == n + 2);
    assert(take() == std::vector<int>{32});                         // baseline, all off

    std::string caps;
    assert(call("/esu/capabilities", false, &caps) == 1);
    assert(caps.find("\"baud\":115200") != std::string::npos);
    assert(caps.find("\"boot_id\":1,") != std::string::npos);      // NVS boot counter
    const std::string mode = esu::pedal_connected ? "true" : "false";
    assert(caps.find("\"pedal_connected\":" + mode) != std::string::npos);
    assert(caps.find("\"offline_pedals\":" + mode) != std::string::npos);

    // Boot ID: increments while NVS works; 0 ("unknown") if the write fails.
    assert(next_boot_id() == 2);
    nvs_write_fails = 1;
    assert(next_boot_id() == 0 && stored_boots == 2);
    nvs_write_fails = 0;

    if (esu::pedal_connected) {
        press(0, true); delay(100);
        assert(relay(0) == 1);
        press(0, false); delay(100);
        assert((take() == std::vector<int>{0x01, 0x00}));           // surgeon on/off
    }

    assert(call("/esu/cut", true) == 0);                             // not armed
    assert(call("/esu/arm", true) == 1);
    assert(call("/esu/cut", true) == 1);
    delay(60); assert(relay(0) == 1);
    delay(650); assert(relay(0) == 0 && !control.armed);            // 500 ms lease expired
    assert((take() == std::vector<int>{0x11, 0x10}));

    // Manual priority: pressing a pedal while autonomous drops the computer command.
    if (esu::pedal_connected) {
        assert(call("/esu/arm", true) == 1);
        assert(call(esu::services[n - 1], true) == 1);
        delay(60); assert(relay(n - 1) == 1);
        watch_overlap = 1;
        press(0, true); delay(60);
        watch_overlap = 0;
        assert(!control.armed && relay(n - 1) == 0 && relay(0) == 1);
        assert(overlaps == 0);                                       // break-before-make
        assert(call(esu::services[n - 1], true) == 0);              // renewal refused
        press(0, false); delay(100);
        const int cmd = 1 << (n - 1);
        // Computer on; computer channel opened by takeover (source 3) BEFORE the
        // pedal channel closes (source 0, next cycle); pedal off.
        assert((take() == std::vector<int>{cmd | 0x10, 0x30, 0x01, 0x00}));

        // Same-channel takeover: output stays closed, hand-over still reported.
        assert(call("/esu/arm", true) == 1);
        assert(call(esu::services[0], true) == 1);
        delay(60);
        press(0, true); delay(60);
        assert(!control.armed && relay(0) == 1);
        press(0, false); delay(100);
        assert((take() == std::vector<int>{0x11, 0x31, 0x00}));
    }

    // A failed publish is counted and resynced; the session is NOT torn down.
    if (esu::pedal_connected) {
        fail_next_publish = 1;
        press(1, true); delay(150);
        assert(creates == 1 && online && dropped == 1);
        assert(take() == std::vector<int>{0x22});                    // baseline: coag on
        press(1, false); delay(100);
        assert(take() == std::vector<int>{0x00});
    }

    // Agent loss: session dropped, local pedal still forwarded, rebaseline on return.
    agent_up = 0; delay(2600);
    assert(!online);
    if (esu::pedal_connected) {
        press(n - 1, true); delay(80);
        assert(relay(n - 1) == 1);
        press(n - 1, false); delay(80);
    }
    agent_up = 1; delay(1200);
    assert(online && creates == 2);
    auto v = take();
    assert(!v.empty() && v.back() == 32);

    if (esu::watchdog_pin >= 0) {
        const int before = pin_writes[esu::watchdog_pin];
        delay(1000);
        assert(pin_writes[esu::watchdog_pin] - before >= 3);
    }

    // Unwired inputs: only a standalone build is immune to floating pins.
    floating = 1;
    int on = 0;
    for (int i = 0; i < 200; ++i) { for (int c = 0; c < n; ++c) on += relay(c); delay(3); }
    if (!esu::pedal_connected) {
        assert(on == 0);
        assert(call("/esu/arm", true) == 1);
    }
    floating = 0;
    printf("v%d %s runtime simulation passed (relay samples ON with floating inputs: %d)\n",
           ESU_BOARD_VERSION, esu::pedal_connected ? "pedal" : "standalone", on);
    fflush(stdout);
    std::_Exit(0);   // loop()/control threads never return
}
