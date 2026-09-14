/*
 * esu_tap_microros.cpp  (v3 -- four channel)
 *
 * micro-ROS firmware for the ESU-TAP v3 interposer on ESP32.
 *
 * v3 adds the LIGASURE (vessel-seal) channel on top of the v2 three-channel
 * design (CUT, COAG, BIPOLAR). Same sense-then-forward architecture and same
 * watchdog-held bypass failsafe.
 *
 * The ESP32 is a ROS 2 node that connects to the micro-ROS agent on the PC over
 * a WIRED serial (USB) transport. USB carries the ROS link; the barrel jack
 * carries board power. In normal operation BOTH are connected.
 *
 * ROS 2 interfaces hosted on this node ("esu_tap_node"):
 *
 *   SERVICES (request/response -- COMPUTER-commanded activation):
 *     /esu/cut       (std_srvs/srv/SetBool)
 *     /esu/coag      (std_srvs/srv/SetBool)
 *     /esu/bipolar   (std_srvs/srv/SetBool)
 *     /esu/ligasure  (std_srvs/srv/SetBool)
 *
 *   TOPIC (streamed status -- logs ALL activations, surgeon + computer):
 *     /esu/activation_state  (std_msgs/msg/Int32MultiArray)
 *        data = [cut, coag, bipolar, ligasure, source]        (FIVE elements)
 *          cut/coag/bipolar/ligasure : 0/1 current EFFECTIVE active state
 *          source : 0 = surgeon (pedal contacts moved)
 *                   1 = computer (relay commanded via service)
 *                   2 = baseline (boot-time sync; not a real event)
 *        One message per CHANGED channel, so each edge carries its own source.
 *
 *   NOTE (breaking change from v2): activation_state is now FIVE elements
 *   [cut, coag, bipolar, ligasure, source], not four. The ROS-side consumer
 *   (pedal_logger.py) must be updated to match.
 *
 * Hardware (v3), verified against esu_tap_v3 netlist:
 *   Sense (pedal dry contacts, direct read, active-low, external 10k pull-ups):
 *     CUT_SENSE = IO35, COAG_SENSE = IO34, BI_SENSE = IO17, LIGA_SENSE = IO25
 *   Relay drive (active-HIGH via AO3400A):
 *     CUT = IO26, COAG = IO27, BI = IO19, LIGA = IO33
 *   LEDs (active-HIGH):
 *     CUT = IO23 (D9), COAG = IO22 (D10), BI = IO21 (D11), LIGA = IO18 (D12)
 *   Watchdog (TPS3823A-33, U10): WDI = IO14. EDGE-triggered -- must TOGGLE.
 *     Holding it high OR low past the ~1.6 s (0.9-2.5 s worst case) timeout
 *     trips RESET, dropping the bypass-relay coils into pass-through.
 *
 *   SENSE and CTRL are SEPARATE nets per channel: a relay command does NOT move
 *   the pedal contacts, so effective state = (sensed OR commanded).
 *
 * micro-ROS setup:
 *   - Standard types only (std_srvs/SetBool, std_msgs/Int32MultiArray).
 *   - Executor handles: 4 services + 1 timer = 5.
 *   - colcon.meta must allow >= 4 services (RMW_UXRCE_MAX_SERVICES). The
 *     checked-in colcon.meta uses 5, which is sufficient.
 *   - Serial (USB) transport.
 *
 * Agent (on the PC):
 *   docker run -it --rm -v /dev:/dev --privileged --net=host \
 *     microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200
 *
 * Build: PlatformIO. micro_ros_platformio, NOT micro_ros_arduino.
 */

#include <Arduino.h>
#include <micro_ros_platformio.h>

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <rmw_microros/rmw_microros.h>

#include <std_srvs/srv/set_bool.h>
#include <std_msgs/msg/int32_multi_array.h>

#include <rosidl_runtime_c/string_functions.h>

// ------------------------------- Pin map (v3) ----------------------
// Sense inputs (PEDAL dry contacts, direct read). LOW = pressed.
const int PIN_SENSE_CUT  = 35;
const int PIN_SENSE_COAG = 34;
const int PIN_SENSE_BI   = 17;
const int PIN_SENSE_LIGA = 25;

// Relay drives (HIGH = relay closed = generator activated)
const int PIN_RELAY_CUT  = 26;
const int PIN_RELAY_COAG = 27;
const int PIN_RELAY_BI   = 19;
const int PIN_RELAY_LIGA = 33;

// Status LEDs (active-HIGH)
const int PIN_LED_CUT    = 23;   // D9
const int PIN_LED_COAG   = 22;   // D10
const int PIN_LED_BI     = 21;   // D11
const int PIN_LED_LIGA   = 18;   // D12

// Watchdog pet (edge-triggered -- TOGGLE, do not hold)
const int PIN_WDT        = 14;

// ------------------------- micro-ROS entities ----------------------
rcl_node_t          node;
rclc_support_t      support;
rcl_allocator_t     allocator;
rclc_executor_t     executor;

rcl_service_t       srv_cut, srv_coag, srv_bi, srv_liga;
std_srvs__srv__SetBool_Request  req_cut,  req_coag,  req_bi,  req_liga;
std_srvs__srv__SetBool_Response resp_cut, resp_coag, resp_bi, resp_liga;

rcl_publisher_t                pub_state;
std_msgs__msg__Int32MultiArray state_msg;
int32_t state_data[5];   // [cut, coag, bipolar, ligasure, source]

rcl_timer_t         timer;

// ------------------------- State tracking --------------------------
const int SRC_SURGEON  = 0;
const int SRC_COMPUTER = 1;
const int SRC_BASELINE = 2;

int lastEffCut = 0, lastEffCoag = 0, lastEffBi = 0, lastEffLiga = 0;
int lastSensedCut = 0, lastSensedCoag = 0, lastSensedBi = 0, lastSensedLiga = 0;
volatile int cmdCut = 0, cmdCoag = 0, cmdBi = 0, cmdLiga = 0;

// Debounce
const unsigned long DEBOUNCE_MS = 30;
int rawCut=0, rawCoag=0, rawBi=0, rawLiga=0;
int stableCut=0, stableCoag=0, stableBi=0, stableLiga=0;
int lastRawCut=0, lastRawCoag=0, lastRawBi=0, lastRawLiga=0;
unsigned long tCut=0, tCoag=0, tBi=0, tLiga=0;

// Watchdog pet interval -- well inside the ~1.6 s (0.9-2.5 s worst-case) window.
const unsigned long WDT_TOGGLE_MS = 250;
unsigned long lastWdtToggleMs = 0;
int wdtLevel = 0;

// ------------------------- Error handling --------------------------
volatile int g_err_line = 0;
volatile int g_err_rc   = 0;
void error_loop();

#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) { \
    g_err_line = __LINE__; g_err_rc = (int)rc; error_loop(); } }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

void error_loop() {
  while (1) {
    Serial.print("[ESU-TAP v3] micro-ROS init FAILED at line ");
    Serial.print(g_err_line);
    Serial.print(", rcl_ret_t = ");
    Serial.println(g_err_rc);
    for (int i = 0; i < 6; i++) {
      digitalWrite(PIN_LED_CUT,  !digitalRead(PIN_LED_CUT));
      digitalWrite(PIN_LED_COAG, !digitalRead(PIN_LED_COAG));
      digitalWrite(PIN_LED_BI,   !digitalRead(PIN_LED_BI));
      digitalWrite(PIN_LED_LIGA, !digitalRead(PIN_LED_LIGA));
      digitalWrite(PIN_WDT, (i & 1));   // keep petting through an init error
      delay(150);
    }
  }
}

// --------------------- Connection state machine --------------------
enum AgentState { WAITING_AGENT, AGENT_AVAILABLE, AGENT_CONNECTED, AGENT_DISCONNECTED };
static AgentState agent_state = WAITING_AGENT;

bool create_entities();
void destroy_entities();

#define EVERY_MS(MS) for (static volatile int64_t _t = -1; \
  (_t == -1) || ((int32_t)(millis() - _t) >= (MS)); _t = millis())

// --------------------- Watchdog pet --------------------------------
inline void pet_watchdog() {
  unsigned long now = millis();
  if ((now - lastWdtToggleMs) >= WDT_TOGGLE_MS) {
    lastWdtToggleMs = now;
    wdtLevel = !wdtLevel;
    digitalWrite(PIN_WDT, wdtLevel);
  }
}

// --------------------- Publish current state -----------------------
void publish_state(int cut, int coag, int bipolar, int ligasure, int source) {
  state_data[0] = cut;
  state_data[1] = coag;
  state_data[2] = bipolar;
  state_data[3] = ligasure;
  state_data[4] = source;
  state_msg.data.data = state_data;
  state_msg.data.size = 5;
  state_msg.data.capacity = 5;
  RCSOFTCHECK(rcl_publish(&pub_state, &state_msg, NULL));
}

// --------------------- Service callbacks ---------------------------
// Callbacks ONLY set command flags; timer_callback owns all relay/LED writes.
void cut_cb(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdCut = rq->data ? 1 : 0;
  rs->success = true;
  rosidl_runtime_c__String__assign(&rs->message, rq->data ? "cut on" : "cut off");
}
void coag_cb(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdCoag = rq->data ? 1 : 0;
  rs->success = true;
  rosidl_runtime_c__String__assign(&rs->message, rq->data ? "coag on" : "coag off");
}
void bi_cb(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdBi = rq->data ? 1 : 0;
  rs->success = true;
  rosidl_runtime_c__String__assign(&rs->message, rq->data ? "bipolar on" : "bipolar off");
}
void liga_cb(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdLiga = rq->data ? 1 : 0;
  rs->success = true;
  rosidl_runtime_c__String__assign(&rs->message, rq->data ? "ligasure on" : "ligasure off");
}

// --------------------- Timer: poll sense + publish + pet -----------
void timer_callback(rcl_timer_t *t, int64_t last_call_time) {
  RCLC_UNUSED(last_call_time);
  if (t == NULL) return;

  pet_watchdog();

  unsigned long now = millis();

  rawCut  = (digitalRead(PIN_SENSE_CUT)  == LOW) ? 1 : 0;
  rawCoag = (digitalRead(PIN_SENSE_COAG) == LOW) ? 1 : 0;
  rawBi   = (digitalRead(PIN_SENSE_BI)   == LOW) ? 1 : 0;
  rawLiga = (digitalRead(PIN_SENSE_LIGA) == LOW) ? 1 : 0;

  if (rawCut  != lastRawCut)  { lastRawCut  = rawCut;  tCut  = now; }
  if ((now - tCut)  >= DEBOUNCE_MS) stableCut  = rawCut;
  if (rawCoag != lastRawCoag) { lastRawCoag = rawCoag; tCoag = now; }
  if ((now - tCoag) >= DEBOUNCE_MS) stableCoag = rawCoag;
  if (rawBi   != lastRawBi)   { lastRawBi   = rawBi;   tBi   = now; }
  if ((now - tBi)   >= DEBOUNCE_MS) stableBi   = rawBi;
  if (rawLiga != lastRawLiga) { lastRawLiga = rawLiga; tLiga = now; }
  if ((now - tLiga) >= DEBOUNCE_MS) stableLiga = rawLiga;

  int cCut = cmdCut, cCoag = cmdCoag, cBi = cmdBi, cLiga = cmdLiga;

  int effCut  = (stableCut  || cCut)  ? 1 : 0;
  int effCoag = (stableCoag || cCoag) ? 1 : 0;
  int effBi   = (stableBi   || cBi)   ? 1 : 0;
  int effLiga = (stableLiga || cLiga) ? 1 : 0;

  digitalWrite(PIN_RELAY_CUT,  effCut  ? HIGH : LOW);
  digitalWrite(PIN_RELAY_COAG, effCoag ? HIGH : LOW);
  digitalWrite(PIN_RELAY_BI,   effBi   ? HIGH : LOW);
  digitalWrite(PIN_RELAY_LIGA, effLiga ? HIGH : LOW);
  digitalWrite(PIN_LED_CUT,    effCut  ? HIGH : LOW);
  digitalWrite(PIN_LED_COAG,   effCoag ? HIGH : LOW);
  digitalWrite(PIN_LED_BI,     effBi   ? HIGH : LOW);
  digitalWrite(PIN_LED_LIGA,   effLiga ? HIGH : LOW);

  if (effCut != lastEffCut) {
    int src = (stableCut != lastSensedCut) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(effCut, lastEffCoag, lastEffBi, lastEffLiga, src);
    lastEffCut = effCut;
  }
  if (effCoag != lastEffCoag) {
    int src = (stableCoag != lastSensedCoag) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(lastEffCut, effCoag, lastEffBi, lastEffLiga, src);
    lastEffCoag = effCoag;
  }
  if (effBi != lastEffBi) {
    int src = (stableBi != lastSensedBi) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(lastEffCut, lastEffCoag, effBi, lastEffLiga, src);
    lastEffBi = effBi;
  }
  if (effLiga != lastEffLiga) {
    int src = (stableLiga != lastSensedLiga) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(lastEffCut, lastEffCoag, lastEffBi, effLiga, src);
    lastEffLiga = effLiga;
  }

  lastSensedCut  = stableCut;
  lastSensedCoag = stableCoag;
  lastSensedBi   = stableBi;
  lastSensedLiga = stableLiga;
}

// ---------------- Entity create / destroy --------------------------
bool create_entities() {
  allocator = rcl_get_default_allocator();

  if (rclc_support_init(&support, 0, NULL, &allocator) != RCL_RET_OK) return false;
  if (rclc_node_init_default(&node, "esu_tap_node", "", &support) != RCL_RET_OK) return false;

  if (rclc_publisher_init_default(
        &pub_state, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray),
        "/esu/activation_state") != RCL_RET_OK) return false;

  if (rclc_service_init_default(&srv_cut,  &node, ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/esu/cut")      != RCL_RET_OK) return false;
  if (rclc_service_init_default(&srv_coag, &node, ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/esu/coag")     != RCL_RET_OK) return false;
  if (rclc_service_init_default(&srv_bi,   &node, ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/esu/bipolar")  != RCL_RET_OK) return false;
  if (rclc_service_init_default(&srv_liga, &node, ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/esu/ligasure") != RCL_RET_OK) return false;

  if (rclc_timer_init_default(&timer, &support, RCL_MS_TO_NS(10), timer_callback) != RCL_RET_OK) return false;

  // 4 services + 1 timer = 5 handles.
  if (rclc_executor_init(&executor, &support.context, 5, &allocator) != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_cut,  &req_cut,  &resp_cut,  cut_cb)  != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_coag, &req_coag, &resp_coag, coag_cb) != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_bi,   &req_bi,   &resp_bi,   bi_cb)   != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_liga, &req_liga, &resp_liga, liga_cb) != RCL_RET_OK) return false;
  if (rclc_executor_add_timer(&executor, &timer) != RCL_RET_OK) return false;

  static bool msg_inited = false;
  if (!msg_inited) {
    rosidl_runtime_c__String__init(&resp_cut.message);
    rosidl_runtime_c__String__init(&resp_coag.message);
    rosidl_runtime_c__String__init(&resp_bi.message);
    rosidl_runtime_c__String__init(&resp_liga.message);
    std_msgs__msg__Int32MultiArray__init(&state_msg);
    msg_inited = true;
  }

  publish_state(lastEffCut, lastEffCoag, lastEffBi, lastEffLiga, SRC_BASELINE);
  return true;
}

void destroy_entities() {
  rmw_context_t *rmw_context = rcl_context_get_rmw_context(&support.context);
  (void)rmw_uros_set_context_entity_destroy_session_timeout(rmw_context, 0);

  rcl_service_fini(&srv_cut, &node);
  rcl_service_fini(&srv_coag, &node);
  rcl_service_fini(&srv_bi, &node);
  rcl_service_fini(&srv_liga, &node);
  rcl_publisher_fini(&pub_state, &node);
  rcl_timer_fini(&timer);
  rclc_executor_fini(&executor);
  rcl_node_fini(&node);
  rclc_support_fini(&support);
}

// ----------------------------- Setup -------------------------------
void setup() {
  pinMode(PIN_SENSE_CUT,  INPUT);
  pinMode(PIN_SENSE_COAG, INPUT);
  pinMode(PIN_SENSE_BI,   INPUT);
  pinMode(PIN_SENSE_LIGA, INPUT);
  pinMode(PIN_RELAY_CUT,  OUTPUT);
  pinMode(PIN_RELAY_COAG, OUTPUT);
  pinMode(PIN_RELAY_BI,   OUTPUT);
  pinMode(PIN_RELAY_LIGA, OUTPUT);
  pinMode(PIN_LED_CUT,    OUTPUT);
  pinMode(PIN_LED_COAG,   OUTPUT);
  pinMode(PIN_LED_BI,     OUTPUT);
  pinMode(PIN_LED_LIGA,   OUTPUT);
  pinMode(PIN_WDT,        OUTPUT);

  digitalWrite(PIN_RELAY_CUT,  LOW);
  digitalWrite(PIN_RELAY_COAG, LOW);
  digitalWrite(PIN_RELAY_BI,   LOW);
  digitalWrite(PIN_RELAY_LIGA, LOW);
  digitalWrite(PIN_LED_CUT,    LOW);
  digitalWrite(PIN_LED_COAG,   LOW);
  digitalWrite(PIN_LED_BI,     LOW);
  digitalWrite(PIN_LED_LIGA,   LOW);
  digitalWrite(PIN_WDT,        LOW);

  Serial.begin(115200);
  set_microros_serial_transports(Serial);
  delay(2000);
}

// ----------------------------- Loop --------------------------------
void loop() {
  switch (agent_state) {
    case WAITING_AGENT:
      EVERY_MS(500) {
        agent_state = (rmw_uros_ping_agent(100, 1) == RMW_RET_OK)
                      ? AGENT_AVAILABLE : WAITING_AGENT;
        if (agent_state == WAITING_AGENT) {
          digitalWrite(PIN_LED_COAG, !digitalRead(PIN_LED_COAG));
        }
      }
      pet_watchdog();
      break;

    case AGENT_AVAILABLE:
      digitalWrite(PIN_LED_COAG, LOW);
      agent_state = create_entities() ? AGENT_CONNECTED : WAITING_AGENT;
      if (agent_state == WAITING_AGENT) destroy_entities();
      pet_watchdog();
      break;

    case AGENT_CONNECTED:
      {
        static int missed_pings = 0;
        EVERY_MS(500) {
          if (rmw_uros_ping_agent(200, 1) == RMW_RET_OK) {
            missed_pings = 0;
          } else if (++missed_pings >= 3) {
            agent_state = AGENT_DISCONNECTED;
          }
        }
        if (agent_state == AGENT_CONNECTED) {
          rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10));
          pet_watchdog();
        } else {
          missed_pings = 0;
        }
      }
      break;

    case AGENT_DISCONNECTED:
      // Link lost: force all channels OFF (fail safe), tear down, re-wait.
      // Keep petting -- a dropped agent is not a firmware hang.
      digitalWrite(PIN_RELAY_CUT,  LOW);
      digitalWrite(PIN_RELAY_COAG, LOW);
      digitalWrite(PIN_RELAY_BI,   LOW);
      digitalWrite(PIN_RELAY_LIGA, LOW);
      digitalWrite(PIN_LED_CUT,    LOW);
      digitalWrite(PIN_LED_COAG,   LOW);
      digitalWrite(PIN_LED_BI,     LOW);
      digitalWrite(PIN_LED_LIGA,   LOW);
      cmdCut = 0; cmdCoag = 0; cmdBi = 0; cmdLiga = 0;
      lastEffCut = 0; lastEffCoag = 0; lastEffBi = 0; lastEffLiga = 0;
      destroy_entities();
      pet_watchdog();
      agent_state = WAITING_AGENT;
      break;
  }
}
