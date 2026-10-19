#pragma once
// Shared bench firmware. No independent hardware shutdown is implied.
#include <Arduino.h>
#include <esp_system.h>
#include <Preferences.h>
#include <micro_ros_platformio.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <rmw_microros/rmw_microros.h>
#include <std_msgs/msg/int32.h>
#include <std_srvs/srv/set_bool.h>
#include <std_srvs/srv/trigger.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include "control.hpp"

namespace {
esu::Controller control;
portMUX_TYPE control_lock = portMUX_INITIALIZER_UNLOCKED;
QueueHandle_t events;
struct Event { int32_t data; uint32_t generation; };
uint32_t generation = 0;
uint32_t dropped = 0, boot_id = 0;
bool control_ready = false;
// Set when telemetry was lost (queue full or publish failed). The ROS loop then
// publishes a fresh baseline snapshot instead of tearing the session down.
bool resync = false;

// Transport never runs on this task. Agent discovery/entity teardown cannot
// block pedal polling or command expiry. No rcl/rmw calls under the spinlock.
void control_task(void*) {
    TickType_t next = xTaskGetTickCount();
    uint32_t last_pet = millis();
    bool pet_level = false;
    for (;;) {
        bool inputs[4] = {};
        for (unsigned i = 0; i < esu::channel_count; ++i)
            inputs[i] = digitalRead(esu::pins[i].sense) == LOW;
        const uint32_t now = millis();
        Event changed[4]; unsigned count = 0;
        portENTER_CRITICAL(&control_lock);
        bool previous_sensed[4];
        uint8_t previous = control.state_bits();
        for (unsigned i = 0; i < esu::channel_count; ++i) previous_sensed[i] = control.sensed[i];
        control.sample(inputs, now);
        for (unsigned i = 0; i < esu::channel_count; ++i) {
            digitalWrite(esu::pins[i].relay, control.effective[i] ? HIGH : LOW);
            digitalWrite(esu::pins[i].led, control.effective[i] ? HIGH : LOW);
            if (bool(previous & (1u << i)) != control.effective[i]) {
                previous ^= 1u << i;
                const int source = control.sensed[i] != previous_sensed[i] ? 0 : 1;
                if (control.connected) changed[count++] = {previous | (source << 4), generation};
            }
        }
        control_ready = true;
        portEXIT_CRITICAL(&control_lock);
        for (unsigned i = 0; i < count; ++i) {
            if (xQueueSend(events, &changed[i], 0) != pdTRUE) {
                portENTER_CRITICAL(&control_lock); ++dropped; resync = true; portEXIT_CRITICAL(&control_lock);
            }
        }
        // Only pet after a completed local control cycle. This does NOT make
        // the existing bypass-only watchdog an independent activation cutoff.
        if (esu::watchdog_pin >= 0 && uint32_t(now - last_pet) >= 250) {
            pet_level = !pet_level;
            digitalWrite(esu::watchdog_pin, pet_level);
            last_pet = now;
        }
        vTaskDelayUntil(&next, pdMS_TO_TICKS(10));
    }
}

rclc_support_t support{};
rcl_allocator_t allocator;
rcl_node_t node = rcl_get_zero_initialized_node();
rcl_publisher_t publisher = rcl_get_zero_initialized_publisher();
rcl_service_t channel_services[4], arm_service, capabilities_service;
rclc_executor_t executor = rclc_executor_get_zero_initialized_executor();
std_srvs__srv__SetBool_Request requests[4]{}, arm_request{};
std_srvs__srv__SetBool_Response responses[4]{}, arm_response{};
std_srvs__srv__Trigger_Request capabilities_request{};
std_srvs__srv__Trigger_Response capabilities_response{};
char empty_messages[5][1] = {};
char capability_buffer[768];
bool support_ok = false, node_ok = false, publisher_ok = false;
bool executor_ok = false, arm_ok = false, capabilities_ok = false;
unsigned services_ok = 0;
bool online = false;
uint32_t last_ping = 0; unsigned missed = 0;

void request_channel(unsigned i, const void* req, void* resp) {
    const auto* rq = static_cast<const std_srvs__srv__SetBool_Request*>(req);
    auto* rs = static_cast<std_srvs__srv__SetBool_Response*>(resp);
    portENTER_CRITICAL(&control_lock);
    rs->success = control.request(i, rq->data, millis());
    portEXIT_CRITICAL(&control_lock);
}
void cut(const void* a, void* b) { request_channel(0, a, b); }
void coag(const void* a, void* b) { request_channel(1, a, b); }
void bipolar(const void* a, void* b) { request_channel(2, a, b); }
void ligasure(const void* a, void* b) { request_channel(3, a, b); }
void (*callbacks[])(const void*, void*) = {cut, coag, bipolar, ligasure};
void arm(const void* req, void* resp) {
    const auto* rq = static_cast<const std_srvs__srv__SetBool_Request*>(req);
    auto* rs = static_cast<std_srvs__srv__SetBool_Response*>(resp);
    portENTER_CRITICAL(&control_lock);
    control.expire(millis());
    rs->success = control_ready && control.arm(rq->data);
    portEXIT_CRITICAL(&control_lock);
}
void capabilities(const void*, void* resp) {
    auto* rs = static_cast<std_srvs__srv__Trigger_Response*>(resp);
    portENTER_CRITICAL(&control_lock);
    const bool armed = control.armed;
    const unsigned state = control.state_bits();
    const uint32_t drops = dropped;
    portEXIT_CRITICAL(&control_lock);
    const int size = snprintf(capability_buffer, sizeof(capability_buffer),
        "{\"protocol\":2,\"firmware\":\"3.0.0-bench\",\"board\":\"v%d\","
        "\"channel_count\":%u,\"watchdog\":%s,\"baud\":%u,\"lease_ms\":%u,"
        "\"refresh_ms\":%u,\"offline_pedals\":%s,\"requires_arm\":true,"
        "\"pedal_connected\":%s,"
        "\"armed\":%s,\"state\":%u,\"boot_id\":%u,\"dropped_events\":%u}",
        ESU_BOARD_VERSION, esu::channel_count, esu::watchdog_pin >= 0 ? "true" : "false",
        unsigned(esu::baud), unsigned(esu::lease_ms), unsigned(esu::refresh_ms),
        // A standalone image ignores the pedal, so it has no offline pedal path.
        esu::pedal_connected ? "true" : "false", esu::pedal_connected ? "true" : "false",
        armed ? "true" : "false", state, unsigned(boot_id), unsigned(drops));
    rs->success = size > 0 && size < int(sizeof(capability_buffer));
    rs->message.size = rs->success ? size_t(size) : 0;
    if (!rs->success) capability_buffer[0] = '\0';
}

void destroy_entities() {
    // Only finalize entities successfully initialized. Partial setup must not
    // access an uninitialized context or finalize arbitrary service objects.
    if (support_ok) {
        auto* ctx = rcl_context_get_rmw_context(&support.context);
        if (ctx) (void)rmw_uros_set_context_entity_destroy_session_timeout(ctx, 0);
    }
    if (executor_ok) { (void)rclc_executor_fini(&executor); executor_ok = false; }
    if (capabilities_ok) { (void)rcl_service_fini(&capabilities_service, &node); capabilities_ok = false; }
    if (arm_ok) { (void)rcl_service_fini(&arm_service, &node); arm_ok = false; }
    while (services_ok) (void)rcl_service_fini(&channel_services[--services_ok], &node);
    if (publisher_ok) { (void)rcl_publisher_fini(&publisher, &node); publisher_ok = false; }
    if (node_ok) { (void)rcl_node_fini(&node); node_ok = false; }
    if (support_ok) { (void)rclc_support_fini(&support); support_ok = false; }
    rcl_reset_error();
}

bool create_entities() {
    support = {};
    node = rcl_get_zero_initialized_node();
    publisher = rcl_get_zero_initialized_publisher();
    executor = rclc_executor_get_zero_initialized_executor();
    arm_service = rcl_get_zero_initialized_service();
    capabilities_service = rcl_get_zero_initialized_service();
    allocator = rcl_get_default_allocator();
    if (rclc_support_init(&support, 0, nullptr, &allocator) != RCL_RET_OK) return false;
    support_ok = true;
    if (rclc_node_init_default(&node, "esu_tap_node", "", &support) != RCL_RET_OK) return false;
    node_ok = true;
    if (rclc_publisher_init_default(&publisher, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32), "/esu/activation_state") != RCL_RET_OK) return false;
    publisher_ok = true;
    // Bound reliable publication waits; telemetry is not the local control clock.
    // A publish that misses this window is counted and resynced (see publish()),
    // never treated as a dead link: link health comes from the agent ping.
    (void)rmw_uros_set_publisher_session_timeout(rcl_publisher_get_rmw_handle(&publisher), 50);
    for (unsigned i = 0; i < esu::channel_count; ++i) {
        channel_services[i] = rcl_get_zero_initialized_service();
        if (rclc_service_init_default(&channel_services[i], &node,
            ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), esu::services[i]) != RCL_RET_OK) return false;
        ++services_ok;
    }
    if (rclc_service_init_default(&arm_service, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/esu/arm") != RCL_RET_OK) return false;
    arm_ok = true;
    if (rclc_service_init_default(&capabilities_service, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, Trigger), "/esu/capabilities") != RCL_RET_OK) return false;
    capabilities_ok = true;
    if (rclc_executor_init(&executor, &support.context, esu::channel_count + 2, &allocator) != RCL_RET_OK) return false;
    executor_ok = true;
    for (unsigned i = 0; i < esu::channel_count; ++i)
        if (rclc_executor_add_service(&executor, &channel_services[i], &requests[i], &responses[i], callbacks[i]) != RCL_RET_OK) return false;
    if (rclc_executor_add_service(&executor, &arm_service, &arm_request, &arm_response, arm) != RCL_RET_OK) return false;
    if (rclc_executor_add_service(&executor, &capabilities_service, &capabilities_request, &capabilities_response, capabilities) != RCL_RET_OK) return false;
    return true;
}

// Publish one state message. A failure (e.g. delivery not confirmed in time on a
// marginal link) is counted and triggers a resync baseline; it does NOT drop the
// session, which would disarm computer control on every lost message.
bool publish(int32_t data) {
    std_msgs__msg__Int32 message{};
    message.data = data;
    if (rcl_publish(&publisher, &message, nullptr) == RCL_RET_OK) return true;
    portENTER_CRITICAL(&control_lock); ++dropped; resync = true; portEXIT_CRITICAL(&control_lock);
    return false;
}

// Baseline = full current state with source 2. Bumping the generation in the
// same critical section discards queued edges that predate the snapshot.
void publish_baseline() {
    portENTER_CRITICAL(&control_lock);
    ++generation;
    resync = false;
    const int32_t data = control.state_bits() | (2 << 4);
    portEXIT_CRITICAL(&control_lock);
    publish(data); // On failure resync is set again and retried next loop.
}

// Boot counter in NVS, so the ID changes on every boot (esp_random() before the
// RF subsystem starts is not guaranteed to). Returns 0 = "unknown" unless the
// new value was both written and read back: a failed NVS write would otherwise
// hand out the same ID again. The PC treats 0 as "reboot tracking unavailable".
uint32_t next_boot_id() {
    Preferences prefs;
    if (!prefs.begin("esu_tap", false)) return 0;
    uint32_t id = prefs.getUInt("boots", 0) + 1;
    if (id == 0) id = 1; // Skip the "unknown" value on wrap-around.
    const bool saved = prefs.putUInt("boots", id) == sizeof(id)
                       && prefs.getUInt("boots", 0) == id;
    prefs.end();
    return saved ? id : 0;
}

void disconnect() {
    portENTER_CRITICAL(&control_lock);
    control.set_connected(false); // Local task clears command drive on its next cycle.
    ++generation;
    resync = false;
    portEXIT_CRITICAL(&control_lock);
    online = false; missed = 0;
    destroy_entities();
    xQueueReset(events);
    last_ping = millis();
}
}

void setup() {
    for (unsigned i = 0; i < esu::channel_count; ++i) {
        digitalWrite(esu::pins[i].relay, LOW);
        pinMode(esu::pins[i].relay, OUTPUT);
        digitalWrite(esu::pins[i].led, LOW);
        pinMode(esu::pins[i].led, OUTPUT);
        // Board pull-ups hold released inputs HIGH. GPIO34-39 are input-only with
        // no internal pull-up; other sense pins add the internal one as backup.
        pinMode(esu::pins[i].sense, esu::pins[i].sense >= 34 ? INPUT : INPUT_PULLUP);
    }
    if (esu::watchdog_pin >= 0) {
        digitalWrite(esu::watchdog_pin, LOW); pinMode(esu::watchdog_pin, OUTPUT);
    }
    // Statically backed ROS strings: never pass them to generated __fini().
    for (unsigned i = 0; i < 4; ++i) responses[i].message = {empty_messages[i], 0, 1};
    arm_response.message = {empty_messages[4], 0, 1};
    capabilities_response.message = {capability_buffer, 0, sizeof(capability_buffer)};
    boot_id = next_boot_id();
    events = xQueueCreate(64, sizeof(Event));
    if (!events || xTaskCreatePinnedToCore(control_task, "esu_control", 4096,
            nullptr, 2, nullptr, 1) != pdPASS) {
        // No transport/commands and no watchdog petting after setup failure.
        for (;;) delay(1000);
    }
    Serial.begin(esu::baud);
    set_microros_serial_transports(Serial);
    // No debug printing on the binary XRCE transport.
}

void loop() {
    const uint32_t now = millis();
    if (!online) {
        if (uint32_t(now - last_ping) >= 500) {
            last_ping = now;
            if (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) {
                if (create_entities()) {
                    xQueueReset(events);
                    portENTER_CRITICAL(&control_lock);
                    control.set_connected(true);
                    portEXIT_CRITICAL(&control_lock);
                    online = true; missed = 0;
                    publish_baseline();
                } else disconnect();
            }
        }
    } else {
        if (uint32_t(now - last_ping) >= 500) {
            last_ping = now;
            if (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) missed = 0;
            else if (++missed >= 3) { disconnect(); return; }
        }
        const auto rc = rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));
        if (rc != RCL_RET_OK && rc != RCL_RET_TIMEOUT) { disconnect(); return; }
        portENTER_CRITICAL(&control_lock);
        const bool need_resync = resync;
        portEXIT_CRITICAL(&control_lock);
        if (need_resync) publish_baseline();
        // Bound work per loop so callbacks and link checks cannot starve.
        for (unsigned i = 0; i < 8; ++i) {
            Event event{};
            if (xQueueReceive(events, &event, 0) != pdTRUE) break;
            if (event.generation != generation) continue; // Superseded by a baseline/session.
            if (!publish(event.data)) break;              // Resync next loop.
        }
    }
    delay(1);
}
