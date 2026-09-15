/*
 * esu_tap_microros.cpp
 *
 * micro-ROS firmware for the ESU-TAP v2 interposer on ESP32.
 *
 * REVIEW NOTE (2026-09-14): v3 has a separate four-channel firmware project.
 * The ROS logger supports this v2 payload. Powered-offline forwarding
 * and independent watchdog activation shutdown are incomplete. See
 * docs/SAFETY_AND_VALIDATION.md. This note does not change firmware behavior.
 *
 * v2 adds the BIPOLAR channel and a hardware WATCHDOG pet, on top of the v1
 * monopolar sense-then-forward design.
 *
 * The ESP32 is a first-class ROS 2 node that connects to the micro-ROS agent
 * on the PC over a WIRED serial (USB) transport. NOTE: USB carries the ROS
 * link and barrel-jack carries board power; in normal operation BOTH are
 * connected. USB is the data path -- it is not disconnected during sessions.
 *
 * ROS 2 interfaces hosted on this node ("esu_tap_node"):
 *
 *   SERVICES (request/response -- for COMPUTER-commanded activation):
 *     /esu/cut      (std_srvs/srv/SetBool)  true -> close CUT relay,  false -> open
 *     /esu/coag     (std_srvs/srv/SetBool)  true -> close COAG relay, false -> open
 *     /esu/bipolar  (std_srvs/srv/SetBool)  true -> close BI relay,   false -> open
 *
 *   TOPIC (streamed status -- for logging ALL activations, surgeon + computer):
 *     /esu/activation_state  (std_msgs/msg/Int32MultiArray)
 *        data = [cut, coag, bipolar, source]
 *          cut/coag/bipolar : 0/1  current EFFECTIVE active state per channel
 *          source : 0 = surgeon (pedal contacts moved)
 *                   1 = computer (relay commanded via service)
 *                   2 = baseline (boot-time sync message; not a real event)
 *        One message is published PER CHANGED CHANNEL, so each edge carries
 *        its own source attribution.
 *
 *   NOTE (breaking change from v1): the activation_state array is now FOUR
 *   elements [cut, coag, bipolar, source], not three. The ROS-side consumer
 *   (pedal_logger.py) supports both widths.
 *
 * Hardware (v2):
 *   Sensing: pedal dry contacts read DIRECTLY. Active-low, external 10k
 *            pull-ups. Input-only pins have no internal pull-up.
 *            CUT_SENSE = IO35, COAG_SENSE = IO34  (NOTE: swapped vs v1 to match
 *            the v2 board -- verified against the netlist), BI_SENSE = IO17.
 *   Actuation: G6K-2F-Y relays, driven active-HIGH via AO3400A MOSFETs.
 *            CUT = IO26, COAG = IO27, BI = IO19.
 *   LEDs:    CUT = IO23, COAG = IO22, BI = IO21 (active-HIGH).
 *   Watchdog: TPS3823A-33 supervisor. WDI = IO14. It is EDGE-triggered: the
 *            firmware must TOGGLE IO14 periodically. Holding it high OR low
 *            past the ~1.6 s (0.9-2.5 s worst case) timeout trips RESET, which
 *            temporarily releases the bypass-relay coils. RESET is not wired
 *            to ESP32 EN and does not independently disable activation relays.
 *            This is not guaranteed sustained fallback or fail-safe shutdown.
 *
 *   IMPORTANT: SENSE and CTRL are SEPARATE nets per channel. A relay command
 *   does NOT move the pedal contacts, so a computer-commanded activation
 *   produces NO sensed edge. Effective state = (sensed OR commanded).
 *
 * micro-ROS setup notes:
 *   - Standard message/service types only (std_srvs/SetBool,
 *     std_msgs/Int32MultiArray) -- no custom library rebuild.
 *   - The rclc executor needs handles for 3 services + timer = 4.
 *   - colcon.meta MUST set RMW_UXRCE_MAX_SERVICES=3 (was 2 in v1). After
 *     editing colcon.meta: pio run -t clean_microros.
 *   - Serial (USB) transport, wired.
 *
 * Agent (run on the PC):
 *   docker run -it --rm -v /dev:/dev --privileged --net=host \
 *     microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200
 *
 * Build: PlatformIO. Uses micro_ros_platformio, NOT micro_ros_arduino.
 */

#include <Arduino.h>
#include <micro_ros_platformio.h>

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <rmw_microros/rmw_microros.h>

#include <std_srvs/srv/set_bool.h>
#include <std_msgs/msg/int32.h>

#include <rosidl_runtime_c/string_functions.h>

// ----------------------------- Pin map (v2) ------------------------
// Sense inputs: PEDAL dry contacts, read directly. LOW = pedal pressed.
// These do NOT reflect relay state.
const int PIN_SENSE_CUT  = 35;   // CUT_SENSE  (IO35) -- swapped vs v1 to match board
const int PIN_SENSE_COAG = 34;   // COAG_SENSE (IO34)
const int PIN_SENSE_BI   = 17;   // BI_SENSE   (IO17)

// Relay drives (HIGH = relay closed = generator activated)
const int PIN_RELAY_CUT  = 26;   // CUT_CTRL
const int PIN_RELAY_COAG = 27;   // COAG_CTRL
const int PIN_RELAY_BI   = 19;   // BI_CTRL

// Status LEDs (active-HIGH)
const int PIN_LED_CUT    = 23;   // D8
const int PIN_LED_COAG   = 22;   // D9
const int PIN_LED_BI     = 21;   // D10

// Watchdog pet (edge-triggered -- must TOGGLE, not hold)
const int PIN_WDT        = 14;   // WDI on TPS3823A

// ------------------------- micro-ROS entities ----------------------
rcl_node_t          node;
rclc_support_t      support;
rcl_allocator_t     allocator;
rclc_executor_t     executor;

// Three SetBool services
rcl_service_t       srv_cut, srv_coag, srv_bi;
std_srvs__srv__SetBool_Request  req_cut,  req_coag,  req_bi;
std_srvs__srv__SetBool_Response resp_cut, resp_coag, resp_bi;

// Status publisher.
// NOTE: we publish a single packed Int32, NOT Int32MultiArray. Int32MultiArray
// carries a variable-length layout.dim sequence that does not serialize
// reliably over micro-ROS/XRCE -- it produced a persistent
// "sequence size exceeds remaining buffer" flood on the subscriber. A plain
// Int32 has no sequences and serializes deterministically.
//
// Packing (matches the ROS-side decoder in protocol.py):
//   bit 0    : cut      (0/1)
//   bit 1    : coag     (0/1)
//   bit 2    : bipolar  (0/1)
//   bits 4-5 : source   (0=surgeon, 1=computer, 2=baseline)
rcl_publisher_t     pub_state;
std_msgs__msg__Int32 state_msg;

// Periodic timer to poll sense inputs + pet the watchdog
rcl_timer_t         timer;

// ------------------------- State tracking --------------------------
const int SRC_SURGEON  = 0;
const int SRC_COMPUTER = 1;
const int SRC_BASELINE = 2;

// Effective state = sensed (surgeon) OR commanded (computer).
int lastEffCut  = 0, lastEffCoag = 0, lastEffBi = 0;

// Last debounced SENSED values, to distinguish surgeon vs computer edges.
int lastSensedCut = 0, lastSensedCoag = 0, lastSensedBi = 0;

// Commanded relay state, set by the service callbacks.
volatile int cmdCut = 0, cmdCoag = 0, cmdBi = 0;

// Debounce
const unsigned long DEBOUNCE_MS = 30;
int rawCut = 0, rawCoag = 0, rawBi = 0;
int stableCut = 0, stableCoag = 0, stableBi = 0;
int lastRawCut = 0, lastRawCoag = 0, lastRawBi = 0;
unsigned long lastRawChangeCutMs = 0, lastRawChangeCoagMs = 0, lastRawChangeBiMs = 0;

// Watchdog pet: toggle PIN_WDT on an interval well inside the ~1.6 s timeout.
// The timeout has wide production tolerance (~0.9-2.5 s), so pet FAST.
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
  // Fast blink on all LEDs = fatal init error.
  // Serial is the micro-ROS transport, so this print is only readable with the
  // agent stopped (open the Serial Monitor at 115200, press EN).
  while (1) {
    Serial.print("[ESU-TAP] micro-ROS init FAILED at line ");
    Serial.print(g_err_line);
    Serial.print(", rcl_ret_t = ");
    Serial.println(g_err_rc);

    for (int i = 0; i < 6; i++) {
      digitalWrite(PIN_LED_CUT,  !digitalRead(PIN_LED_CUT));
      digitalWrite(PIN_LED_COAG, !digitalRead(PIN_LED_COAG));
      digitalWrite(PIN_LED_BI,   !digitalRead(PIN_LED_BI));
      // Keep petting the watchdog even while blinking an init error, so an
      // init failure doesn't ALSO trip the watchdog and mask the real fault.
      digitalWrite(PIN_WDT, (i & 1));
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
// Edge-triggered: toggling WDI resets the timer. Called from timer_callback
// (which runs every 10 ms while entities exist) and from the waiting loop, so
// the board is petted whenever the firmware is alive. A genuine hang stops
// both paths, but RESET only briefly releases the bypass coils. Independent
// activation drive is not removed; a watchdog pulse is not a safety guarantee.
inline void pet_watchdog() {
  unsigned long now = millis();
  if ((now - lastWdtToggleMs) >= WDT_TOGGLE_MS) {
    lastWdtToggleMs = now;
    wdtLevel = !wdtLevel;
    digitalWrite(PIN_WDT, wdtLevel);
  }
}

// --------------------- Publish current state -----------------------
// Packs cut/coag/bipolar/source into one Int32. See the field layout above.
void publish_state(int cut, int coag, int bipolar, int source) {
  state_msg.data = (cut & 1)
                 | ((coag & 1) << 1)
                 | ((bipolar & 1) << 2)
                 | ((source & 0x3) << 4);
  RCSOFTCHECK(rcl_publish(&pub_state, &state_msg, NULL));
}

// --------------------- Service callbacks ---------------------------
// Callbacks ONLY set command flags. timer_callback owns ALL relay and LED
// writes, driving them from the effective (sensed OR commanded) state, so
// there is a single writer per output.
//
// We return success only -- NO response .message string. The human-readable
// confirmation the operator sees ("cut on", "coag off", ...) is generated on
// the PC side (pedal_commander) from which service was called + success. This
// keeps the wire payload minimal and robust: a variable-length string is the
// largest and most corruption-prone thing on a marginal serial link, and it
// grows with each added channel (bipolar, ligasure). Translate on the host,
// not over the wire.
void cut_service_callback(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdCut = rq->data ? 1 : 0;
  rs->success = true;
}

void coag_service_callback(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdCoag = rq->data ? 1 : 0;
  rs->success = true;
}

void bi_service_callback(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq = (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs = (std_srvs__srv__SetBool_Response *)resp;
  cmdBi = rq->data ? 1 : 0;
  rs->success = true;
}

// --------------------- Timer: poll sense + publish + pet -----------
void timer_callback(rcl_timer_t *t, int64_t last_call_time) {
  RCLC_UNUSED(last_call_time);
  if (t == NULL) return;

  // Pet the watchdog from the live control path.
  pet_watchdog();

  unsigned long now = millis();

  // Read pedal dry contacts (active-low: LOW = pressed)
  rawCut  = (digitalRead(PIN_SENSE_CUT)  == LOW) ? 1 : 0;
  rawCoag = (digitalRead(PIN_SENSE_COAG) == LOW) ? 1 : 0;
  rawBi   = (digitalRead(PIN_SENSE_BI)   == LOW) ? 1 : 0;

  // Debounce each channel
  if (rawCut  != lastRawCut)  { lastRawCut  = rawCut;  lastRawChangeCutMs  = now; }
  if ((now - lastRawChangeCutMs)  >= DEBOUNCE_MS) { stableCut  = rawCut;  }
  if (rawCoag != lastRawCoag) { lastRawCoag = rawCoag; lastRawChangeCoagMs = now; }
  if ((now - lastRawChangeCoagMs) >= DEBOUNCE_MS) { stableCoag = rawCoag; }
  if (rawBi   != lastRawBi)   { lastRawBi   = rawBi;   lastRawChangeBiMs   = now; }
  if ((now - lastRawChangeBiMs)   >= DEBOUNCE_MS) { stableBi   = rawBi;   }

  // Snapshot commanded state so a callback mid-tick can't change it between
  // the edge test and the publish.
  int cCut = cmdCut, cCoag = cmdCoag, cBi = cmdBi;

  // Effective state: fire if surgeon presses OR computer commands.
  int effCut  = (stableCut  || cCut)  ? 1 : 0;
  int effCoag = (stableCoag || cCoag) ? 1 : 0;
  int effBi   = (stableBi   || cBi)   ? 1 : 0;

  // Forward to the generator + drive the LED from effective state.
  digitalWrite(PIN_RELAY_CUT,  effCut  ? HIGH : LOW);
  digitalWrite(PIN_RELAY_COAG, effCoag ? HIGH : LOW);
  digitalWrite(PIN_RELAY_BI,   effBi   ? HIGH : LOW);
  digitalWrite(PIN_LED_CUT,    effCut  ? HIGH : LOW);
  digitalWrite(PIN_LED_COAG,   effCoag ? HIGH : LOW);
  digitalWrite(PIN_LED_BI,     effBi   ? HIGH : LOW);

  // Per-channel attribution: a change in the sensed line is ground truth for a
  // surgeon action and takes precedence; otherwise the computer drove it.
  // One message per changed channel so each edge carries its own source.
  if (effCut != lastEffCut) {
    int src = (stableCut != lastSensedCut) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(effCut, lastEffCoag, lastEffBi, src);
    lastEffCut = effCut;
  }
  if (effCoag != lastEffCoag) {
    int src = (stableCoag != lastSensedCoag) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(lastEffCut, effCoag, lastEffBi, src);
    lastEffCoag = effCoag;
  }
  if (effBi != lastEffBi) {
    int src = (stableBi != lastSensedBi) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(lastEffCut, lastEffCoag, effBi, src);
    lastEffBi = effBi;
  }

  lastSensedCut  = stableCut;
  lastSensedCoag = stableCoag;
  lastSensedBi   = stableBi;
}

// ---------------- Entity create / destroy (for reconnection) --------
bool create_entities() {
  allocator = rcl_get_default_allocator();

  if (rclc_support_init(&support, 0, NULL, &allocator) != RCL_RET_OK) return false;
  if (rclc_node_init_default(&node, "esu_tap_node", "", &support) != RCL_RET_OK) return false;

  if (rclc_publisher_init_default(
        &pub_state, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32),
        "/esu/activation_state") != RCL_RET_OK) return false;

  if (rclc_service_init_default(
        &srv_cut, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
        "/esu/cut") != RCL_RET_OK) return false;

  if (rclc_service_init_default(
        &srv_coag, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
        "/esu/coag") != RCL_RET_OK) return false;

  if (rclc_service_init_default(
        &srv_bi, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
        "/esu/bipolar") != RCL_RET_OK) return false;

  if (rclc_timer_init_default(
        &timer, &support, RCL_MS_TO_NS(10), timer_callback) != RCL_RET_OK) return false;

  // 3 services + 1 timer = 4 handles.
  if (rclc_executor_init(&executor, &support.context, 4, &allocator) != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_cut,  &req_cut,  &resp_cut,  cut_service_callback)  != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_coag, &req_coag, &resp_coag, coag_service_callback) != RCL_RET_OK) return false;
  if (rclc_executor_add_service(&executor, &srv_bi,   &req_bi,   &resp_bi,   bi_service_callback)   != RCL_RET_OK) return false;
  if (rclc_executor_add_timer(&executor, &timer) != RCL_RET_OK) return false;

  static bool msg_inited = false;
  if (!msg_inited) {
    rosidl_runtime_c__String__init(&resp_cut.message);
    rosidl_runtime_c__String__init(&resp_coag.message);
    rosidl_runtime_c__String__init(&resp_bi.message);
    state_msg.data = 0;
    msg_inited = true;
  }

  // Baseline publish on every (re)connect, reflecting CURRENT effective state.
  publish_state(lastEffCut, lastEffCoag, lastEffBi, SRC_BASELINE);
  return true;
}

void destroy_entities() {
  rmw_context_t *rmw_context = rcl_context_get_rmw_context(&support.context);
  (void)rmw_uros_set_context_entity_destroy_session_timeout(rmw_context, 0);

  rcl_service_fini(&srv_cut, &node);
  rcl_service_fini(&srv_coag, &node);
  rcl_service_fini(&srv_bi, &node);
  rcl_publisher_fini(&pub_state, &node);
  rcl_timer_fini(&timer);
  rclc_executor_fini(&executor);
  rcl_node_fini(&node);
  rclc_support_fini(&support);
}

// ----------------------------- Setup -------------------------------
void setup() {
  // Sense inputs: pedal dry contacts, active-low. External 10k pull-ups on the
  // board. IO34/35 are INPUT-ONLY and have NO internal pull-up, so they rely on
  // the external one. IO17 (bipolar) DOES support an internal pull-up -- enable
  // it as a backup so that if the bipolar pedal is UNPLUGGED on the bench, the
  // line is held HIGH (inactive) instead of floating and reading random noise
  // as phantom "surgeon pressed bipolar" events.
  pinMode(PIN_SENSE_CUT,  INPUT);          // external pull-up only (input-only pin)
  pinMode(PIN_SENSE_COAG, INPUT);          // external pull-up only (input-only pin)
  pinMode(PIN_SENSE_BI,   INPUT_PULLUP);   // internal pull-up backs the external
  pinMode(PIN_RELAY_CUT,  OUTPUT);
  pinMode(PIN_RELAY_COAG, OUTPUT);
  pinMode(PIN_RELAY_BI,   OUTPUT);
  pinMode(PIN_LED_CUT,    OUTPUT);
  pinMode(PIN_LED_COAG,   OUTPUT);
  pinMode(PIN_LED_BI,     OUTPUT);
  pinMode(PIN_WDT,        OUTPUT);

  digitalWrite(PIN_RELAY_CUT,  LOW);   // request activation OFF on boot
  digitalWrite(PIN_RELAY_COAG, LOW);
  digitalWrite(PIN_RELAY_BI,   LOW);
  digitalWrite(PIN_LED_CUT,    LOW);
  digitalWrite(PIN_LED_COAG,   LOW);
  digitalWrite(PIN_LED_BI,     LOW);
  digitalWrite(PIN_WDT,        LOW);

  // micro-ROS transport over USB serial (micro_ros_platformio form).
  // 57600 (not 115200) for robustness on a marginal USB/serial link -- a lower
  // baud is far more tolerant of line noise, which showed up as intermittent
  // "sequence size exceeds remaining buffer" corruption at 115200. Foot-pedal
  // events are human-scale, so the added latency is irrelevant. Must match the
  // agent's -b argument and platformio.ini monitor_speed.
  Serial.begin(57600);
  set_microros_serial_transports(Serial);
  delay(2000);

  // Entities + agent connection handled by the state machine in loop().
  // Activation outputs are requested OFF; pedal forwarding only runs once
  // entities exist. Unpowered bypass is intended, not a verified fault guarantee.
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
      // Pet the watchdog while waiting for the agent, so a board that is up but
      // not yet connected does not sit in a watchdog-reset loop.
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
          // Also pet after executor return. This does not prove the pedal/control
          // timer is healthy; a blocked call would not reach this statement.
          pet_watchdog();
        } else {
          missed_pings = 0;
        }
      }
      break;

    case AGENT_DISCONNECTED:
      // Link lost. Request relays/LEDs OFF, tear down stale entities,
      // return to waiting. Keep petting -- a dropped agent is NOT a firmware
      // hang, and we don't want to also drop the board into hardware bypass
      // just because the PC-side agent restarted. LIMITATION: pedal forwarding
      // stops while waiting, despite continued petting. This is not safe offline
      // operation; see docs/SAFETY_AND_VALIDATION.md.
      digitalWrite(PIN_RELAY_CUT,  LOW);
      digitalWrite(PIN_RELAY_COAG, LOW);
      digitalWrite(PIN_RELAY_BI,   LOW);
      digitalWrite(PIN_LED_CUT,    LOW);
      digitalWrite(PIN_LED_COAG,   LOW);
      digitalWrite(PIN_LED_BI,     LOW);
      cmdCut = 0; cmdCoag = 0; cmdBi = 0;
      lastEffCut = 0; lastEffCoag = 0; lastEffBi = 0;
      destroy_entities();
      pet_watchdog();
      agent_state = WAITING_AGENT;
      break;
  }
}
