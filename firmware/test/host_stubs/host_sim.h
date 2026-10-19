#pragma once
// Host stand-ins for Arduino, FreeRTOS and micro-ROS: just enough to compile
// firmware/shared/runtime.hpp on a PC and run it with real threads. They do not
// model XRCE serialisation, the ESP32 scheduler, or electrical behavior.
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <mutex>
#include <deque>
#include <vector>
#include <atomic>
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
void pinMode(int, int); void digitalWrite(int, int); int digitalRead(int);
unsigned long millis(); void delay(unsigned long);
struct HostSerial { void begin(unsigned long b); };
extern HostSerial Serial;
inline void set_microros_serial_transports(HostSerial&) {}
uint32_t esp_random();
struct Preferences {
    bool begin(const char*, bool);
    uint32_t getUInt(const char*, uint32_t);
    size_t putUInt(const char*, uint32_t);
    void end() {}
};
// FreeRTOS
typedef uint32_t TickType_t; typedef int BaseType_t;
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
struct portMUX_TYPE { std::recursive_mutex m; };
#define portMUX_INITIALIZER_UNLOCKED {}
#define portENTER_CRITICAL(x) (x)->m.lock()
#define portEXIT_CRITICAL(x) (x)->m.unlock()
struct SimQueue { std::mutex m; std::deque<std::vector<char>> q; size_t cap, item; };
typedef SimQueue* QueueHandle_t;
QueueHandle_t xQueueCreate(size_t n, size_t sz);
BaseType_t xQueueSend(QueueHandle_t, const void*, TickType_t);
BaseType_t xQueueReceive(QueueHandle_t, void*, TickType_t);
void xQueueReset(QueueHandle_t);
TickType_t xTaskGetTickCount();
void vTaskDelayUntil(TickType_t*, TickType_t);
BaseType_t xTaskCreatePinnedToCore(void (*)(void*), const char*, int, void*, int, void*, int);
// rcl
typedef int rcl_ret_t; typedef int rmw_ret_t;
#define RCL_RET_OK 0
#define RCL_RET_TIMEOUT 2
#define RMW_RET_OK 0
#define RCL_MS_TO_NS(ms) ((int64_t)(ms)*1000000LL)
struct rcl_allocator_t { int u; }; struct rmw_context_t { int u; };
struct rcl_context_t { rmw_context_t rmw; }; struct rclc_support_t { rcl_context_t context; };
struct rcl_node_t { int init; }; struct rcl_publisher_t { int init; };
typedef void (*rclc_service_callback_t)(const void*, void*);
struct rcl_service_t { const char* name; const char* type; rclc_service_callback_t cb; void* req; void* resp; int init; };
struct rclc_executor_t { int handles, used; };
struct rmw_publisher_t { int u; };
#define ROSIDL_GET_MSG_TYPE_SUPPORT(a,b,c) (#a "/" #b "/" #c)
#define ROSIDL_GET_SRV_TYPE_SUPPORT(a,b,c) (#a "/" #b "/" #c)
rcl_node_t rcl_get_zero_initialized_node(); rcl_publisher_t rcl_get_zero_initialized_publisher();
rcl_service_t rcl_get_zero_initialized_service(); rclc_executor_t rclc_executor_get_zero_initialized_executor();
rcl_allocator_t rcl_get_default_allocator();
rcl_ret_t rclc_support_init(rclc_support_t*, int, const char* const*, rcl_allocator_t*);
rcl_ret_t rclc_node_init_default(rcl_node_t*, const char*, const char*, rclc_support_t*);
rcl_ret_t rclc_publisher_init_default(rcl_publisher_t*, rcl_node_t*, const char*, const char*);
rmw_publisher_t* rcl_publisher_get_rmw_handle(rcl_publisher_t*);
rmw_ret_t rmw_uros_set_publisher_session_timeout(rmw_publisher_t*, int);
rcl_ret_t rclc_service_init_default(rcl_service_t*, rcl_node_t*, const char*, const char*);
rcl_ret_t rclc_executor_init(rclc_executor_t*, rcl_context_t*, size_t, rcl_allocator_t*);
rcl_ret_t rclc_executor_add_service(rclc_executor_t*, rcl_service_t*, void*, void*, rclc_service_callback_t);
rcl_ret_t rclc_executor_spin_some(rclc_executor_t*, int64_t);
rcl_ret_t rcl_publish(rcl_publisher_t*, const void*, void*);
rcl_ret_t rcl_service_fini(rcl_service_t*, rcl_node_t*); rcl_ret_t rcl_publisher_fini(rcl_publisher_t*, rcl_node_t*);
rcl_ret_t rclc_executor_fini(rclc_executor_t*); rcl_ret_t rcl_node_fini(rcl_node_t*); rcl_ret_t rclc_support_fini(rclc_support_t*);
rmw_context_t* rcl_context_get_rmw_context(rcl_context_t*);
rmw_ret_t rmw_uros_set_context_entity_destroy_session_timeout(rmw_context_t*, int);
rmw_ret_t rmw_uros_ping_agent(int, int); void rcl_reset_error();
struct rosidl_runtime_c__String { char* data; size_t size; size_t capacity; };
struct std_srvs__srv__SetBool_Request { bool data; };
struct std_srvs__srv__SetBool_Response { bool success; rosidl_runtime_c__String message; };
struct std_srvs__srv__Trigger_Request { uint8_t structure_needs_at_least_one_member; };
struct std_srvs__srv__Trigger_Response { bool success; rosidl_runtime_c__String message; };
struct std_msgs__msg__Int32 { int32_t data; };
