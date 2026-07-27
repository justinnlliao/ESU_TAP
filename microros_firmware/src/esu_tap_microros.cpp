/*
 * esu_tap_microros.ino
 *
 * micro-ROS firmware for the ESU-TAP interposer on ESP32.
 *
 * Replaces the plain-serial firmware. The ESP32 is now a first-class ROS 2
 * node that connects to the micro-ROS agent on the PC over a WIRED serial
 * (USB) transport.
 *
 * ROS 2 interfaces hosted on this node ("esu_tap_node"):
 *
 *   SERVICES (request/response -- for COMPUTER-commanded activation):
 *     /esu/cut   (std_srvs/srv/SetBool)  data=true -> close CUT relay,  false -> open
 *     /esu/coag  (std_srvs/srv/SetBool)  data=true -> close COAG relay, false -> open
 *     Response: success=true, message="cut on" / "cut off" / etc.
 *
 *   TOPIC (streamed status -- for logging ALL activations, surgeon + computer):
 *     /esu/activation_state  (std_msgs/msg/Int32MultiArray)
 *        data = [cut, coag, source]
 *          cut    : 0/1  current EFFECTIVE CUT active state
 *          coag   : 0/1  current EFFECTIVE COAG active state
 *          source : 0 = surgeon (pedal contacts moved)
 *                   1 = computer (relay commanded via service)
 *                   2 = baseline (boot-time sync message; not a real event)
 *        One message is published PER CHANGED CHANNEL, so each edge carries
 *        its own source attribution.
 *
 * Hardware:
 *   Footswitch: Bovie BV-1253B via AMP CPC Series 1 connectors
 *     (TE 206430-1 female panel / 206429-1 male inline).
 *     Pin 1 = Common, Pin 2 = CUT, Pin 3 = COAG, Pin 4 = tied to Pin 1.
 *     Simple dry contacts, no resistor ladder.
 *   Sensing:   pedal dry contacts read DIRECTLY on IO34/IO35 (schematic nets
 *              CUT_SENSE / COAG_SENSE). Active-low, external 10k pull-ups
 *              R5/R6. Optocouplers were removed in the final v1 architecture.
 *   Actuation: G6K-2F-Y relays close the generator-side contacts (schematic
 *              nets GEN_CUT / GEN_COAG). Active-HIGH drive via MMBT3904.
 *
 *   IMPORTANT: CUT_SENSE and GEN_CUT are SEPARATE nets, as are COAG_SENSE and
 *   GEN_COAG. A relay command does NOT move the pedal contacts, so a
 *   computer-commanded activation produces NO sensed edge. Effective state is
 *   therefore (sensed OR commanded) -- sensing alone would silently drop every
 *   robot activation and mislabel the dataset.
 *
 * micro-ROS setup notes:
 *   - Uses only STANDARD message/service types (std_srvs/SetBool,
 *     std_msgs/Int32MultiArray) so NO custom library rebuild is needed.
 *   - The rclc executor must have enough handles for 2 services + timer = 3.
 *   - Serial (USB) transport keeps things deterministic and wired.
 *
 * Agent (run on the PC):
 *   docker run -it --rm -v /dev:/dev --privileged --net=host \
 *     microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200
 *
 * Build: PlatformIO (see ../platformio.ini). Uses micro_ros_platformio, NOT
 * micro_ros_arduino -- the transport setup calls differ between them.
 */

#include <Arduino.h>
#include <micro_ros_platformio.h>

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

// For rmw_uros_ping_agent(), used to wait for the agent instead of failing once.
#include <rmw_microros/rmw_microros.h>

#include <std_srvs/srv/set_bool.h>
#include <std_msgs/msg/int32_multi_array.h>

// Needed for rosidl_runtime_c__String__init / __assign, used to populate the
// SetBool response .message field. Not pulled in transitively by the service
// or message headers above.
#include <rosidl_runtime_c/string_functions.h>

// ----------------------------- Pin map -----------------------------
// Sense inputs: PEDAL dry contacts, read directly. LOW = pedal pressed.
// These do NOT reflect relay state -- see the note in the header block.
const int PIN_SENSE_CUT  = 34;   // input-only, external pull-up required (R5)
const int PIN_SENSE_COAG = 35;   // input-only, external pull-up required (R6)

// Relay drives (HIGH = relay closed = generator activated)
const int PIN_RELAY_CUT  = 26;
const int PIN_RELAY_COAG = 27;

// Status LEDs (optional)
const int PIN_LED_CUT    = 18;
const int PIN_LED_COAG   = 21;

// ------------------------- micro-ROS entities ----------------------
rcl_node_t          node;
rclc_support_t      support;
rcl_allocator_t     allocator;
rclc_executor_t     executor;

// Two SetBool services
rcl_service_t       srv_cut;
rcl_service_t       srv_coag;
std_srvs__srv__SetBool_Request  req_cut,  req_coag;
std_srvs__srv__SetBool_Response resp_cut, resp_coag;

// Status publisher
rcl_publisher_t             pub_state;
std_msgs__msg__Int32MultiArray state_msg;
int32_t state_data[3];   // [cut, coag, source] -- backing store for state_msg.data

// Periodic timer to poll sense inputs
rcl_timer_t         timer;

// ------------------------- State tracking --------------------------
// Source codes published in field 2 of /esu/activation_state.
const int SRC_SURGEON  = 0;
const int SRC_COMPUTER = 1;
// Emitted ONLY by the boot-time baseline publish. Never produced by a real
// activation. If a consumer sees this mid-session it means the ESP32 restarted,
// and any state change implied by it is a device reset, NOT a surgeon action.
// Attributing the baseline to the surgeon produced phantom events in the CSV.
const int SRC_BASELINE = 2;

// Effective state = sensed (surgeon) OR commanded (computer).
// Edge detection and publishing both operate on the effective state.
int lastEffCut  = 0;
int lastEffCoag = 0;

// Last debounced SENSED values, used to distinguish a surgeon edge from a
// computer edge without needing a timing heuristic.
int lastSensedCut  = 0;
int lastSensedCoag = 0;

// Commanded relay state, set by the service callbacks. Declared volatile
// because the rclc executor may run a service callback between timer ticks.
volatile int cmdCut  = 0;
volatile int cmdCoag = 0;

// Debounce
const unsigned long DEBOUNCE_MS = 30;
int rawCut = 0, rawCoag = 0;
int stableCut = 0, stableCoag = 0;
int lastRawCut = 0, lastRawCoag = 0;
unsigned long lastRawChangeCutMs = 0, lastRawChangeCoagMs = 0;

// ------------------------- Error handling --------------------------
// error_loop() used to give no clue WHICH call failed -- every failure looked
// identical. These capture the failure site so it can be printed.
volatile int g_err_line = 0;
volatile int g_err_rc   = 0;

void error_loop();

#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) { \
    g_err_line = __LINE__; g_err_rc = (int)rc; error_loop(); } }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

void error_loop() {
  // Fast blink on BOTH LEDs = fatal init error.
  // (Slow blink on the COAG LED alone = still waiting for the agent.)
  //
  // Also prints the failure site over Serial. Serial is the micro-ROS
  // transport, so this is only readable once the agent is NOT running:
  // stop the agent, open the PlatformIO Serial Monitor at 115200, press EN.
  while (1) {
    Serial.print("[ESU-TAP] micro-ROS init FAILED at line ");
    Serial.print(g_err_line);
    Serial.print(", rcl_ret_t = ");
    Serial.println(g_err_rc);

    for (int i = 0; i < 6; i++) {
      digitalWrite(PIN_LED_CUT,  !digitalRead(PIN_LED_CUT));
      digitalWrite(PIN_LED_COAG, !digitalRead(PIN_LED_COAG));
      delay(150);
    }
  }
}

// --------------------- Connection state machine --------------------
// micro-ROS does not auto-reconnect. If the agent restarts or drops, entities
// created against the old session go stale and the board looks dead until a
// manual reset (the "press EN every time" problem). This state machine pings
// the agent, creates entities when it appears, and destroys + rebuilds them
// when it goes away -- so start/stop/restart of the agent just works.
enum AgentState { WAITING_AGENT, AGENT_AVAILABLE, AGENT_CONNECTED, AGENT_DISCONNECTED };
static AgentState agent_state = WAITING_AGENT;

bool create_entities();
void destroy_entities();

// Run once at a fixed interval. Returns true if it fired this call.
#define EVERY_MS(MS) for (static volatile int64_t _t = -1; \
  (_t == -1) || ((int32_t)(millis() - _t) >= (MS)); _t = millis())

// --------------------- Publish current state -----------------------
// state_msg is fully initialised once in setup() via
// std_msgs__msg__Int32MultiArray__init, which zeroes BOTH the data sequence
// and the nested layout (layout.dim). Skipping that init leaves layout.dim
// with garbage size/capacity on the stack; the serializer then walks a
// bogus-length dim sequence and overruns the buffer -- the
// "sequence size exceeds remaining buffer" flood. Here we only update the
// three payload values; the sequence storage is already wired up.
void publish_state(int cut, int coag, int source) {
  state_data[0] = cut;
  state_data[1] = coag;
  state_data[2] = source;   // 0 = surgeon, 1 = computer, 2 = baseline
  state_msg.data.data = state_data;
  state_msg.data.size = 3;
  state_msg.data.capacity = 3;
  RCSOFTCHECK(rcl_publish(&pub_state, &state_msg, NULL));
}

// --------------------- Service callbacks ---------------------------
void cut_service_callback(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq =
      (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs =
      (std_srvs__srv__SetBool_Response *)resp;

  // Only set the command flag. The timer callback owns ALL relay and LED
  // writes, driving them from the effective (sensed OR commanded) state. If we
  // also wrote the relay here we'd have two writers racing on the same pin.
  cmdCut = rq->data ? 1 : 0;
  rs->success = true;
  rosidl_runtime_c__String__assign(&rs->message, rq->data ? "cut on" : "cut off");
  // Relay closes and the state change publishes on the next timer tick
  // (<= 10 ms later).
}

void coag_service_callback(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq =
      (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs =
      (std_srvs__srv__SetBool_Response *)resp;

  // See cut_service_callback: flag only, timer owns the outputs.
  cmdCoag = rq->data ? 1 : 0;
  rs->success = true;
  rosidl_runtime_c__String__assign(&rs->message, rq->data ? "coag on" : "coag off");
}

// --------------------- Timer: poll sense + publish -----------------
void timer_callback(rcl_timer_t *t, int64_t last_call_time) {
  RCLC_UNUSED(last_call_time);
  if (t == NULL) return;

  unsigned long now = millis();

  // Read pedal dry contacts (active-low: LOW = pressed)
  rawCut  = (digitalRead(PIN_SENSE_CUT)  == LOW) ? 1 : 0;
  rawCoag = (digitalRead(PIN_SENSE_COAG) == LOW) ? 1 : 0;

  // Debounce CUT
  if (rawCut != lastRawCut) { lastRawCut = rawCut; lastRawChangeCutMs = now; }
  if ((now - lastRawChangeCutMs) >= DEBOUNCE_MS) { stableCut = rawCut; }

  // Debounce COAG
  if (rawCoag != lastRawCoag) { lastRawCoag = rawCoag; lastRawChangeCoagMs = now; }
  if ((now - lastRawChangeCoagMs) >= DEBOUNCE_MS) { stableCoag = rawCoag; }

  // Snapshot the commanded state once, so a service callback running mid-tick
  // cannot change it between the edge test and the publish.
  int cCut  = cmdCut;
  int cCoag = cmdCoag;

  // Effective state: the generator fires if EITHER the surgeon presses the
  // pedal OR the computer closes the relay.
  int effCut  = (stableCut  || cCut)  ? 1 : 0;
  int effCoag = (stableCoag || cCoag) ? 1 : 0;

  // FORWARD the surgeon's press to the generator.
  //
  // In the sense-then-forward architecture the pedal is NOT electrically
  // connected to the generator while the board is powered -- the bypass relay
  // only passes through when unpowered. So a surgeon press reaches the
  // generator ONLY if the firmware re-issues it here. Without this, pressing
  // the pedal senses and logs but the generator never fires.
  //
  // We drive the relay from the EFFECTIVE state, so surgeon and computer share
  // one output path: whoever asserts a channel closes that relay. The LED
  // follows the same effective state so it reflects a surgeon press too
  // (previously the LED was computer-only, driven in the service callback).
  digitalWrite(PIN_RELAY_CUT,  effCut  ? HIGH : LOW);
  digitalWrite(PIN_RELAY_COAG, effCoag ? HIGH : LOW);
  digitalWrite(PIN_LED_CUT,    effCut  ? HIGH : LOW);
  digitalWrite(PIN_LED_COAG,   effCoag ? HIGH : LOW);

  // Per-channel attribution. A change in the sensed line is ground truth for a
  // surgeon action and takes precedence; otherwise the computer drove it.
  // Publish one message per changed channel so each edge carries its own
  // source -- a single combined message would force one source value onto two
  // independent events.
  if (effCut != lastEffCut) {
    int src = (stableCut != lastSensedCut) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(effCut, lastEffCoag, src);
    lastEffCut = effCut;
  }
  if (effCoag != lastEffCoag) {
    int src = (stableCoag != lastSensedCoag) ? SRC_SURGEON : SRC_COMPUTER;
    publish_state(lastEffCut, effCoag, src);
    lastEffCoag = effCoag;
  }

  lastSensedCut  = stableCut;
  lastSensedCoag = stableCoag;
}

// ---------------- Entity create / destroy (for reconnection) --------
// Split out of setup() so loop() can rebuild them whenever the agent returns.
bool create_entities() {
  allocator = rcl_get_default_allocator();

  if (rclc_support_init(&support, 0, NULL, &allocator) != RCL_RET_OK) return false;
  if (rclc_node_init_default(&node, "esu_tap_node", "", &support) != RCL_RET_OK) return false;

  if (rclc_publisher_init_default(
        &pub_state, &node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray),
        "/esu/activation_state") != RCL_RET_OK) return false;

  if (rclc_service_init_default(
        &srv_cut, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
        "/esu/cut") != RCL_RET_OK) return false;

  if (rclc_service_init_default(
        &srv_coag, &node,
        ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
        "/esu/coag") != RCL_RET_OK) return false;

  if (rclc_timer_init_default(
        &timer, &support, RCL_MS_TO_NS(10), timer_callback) != RCL_RET_OK) return false;

  if (rclc_executor_init(&executor, &support.context, 8, &allocator) != RCL_RET_OK) return false;
  if (rclc_executor_add_service(
        &executor, &srv_cut, &req_cut, &resp_cut, cut_service_callback) != RCL_RET_OK) return false;
  if (rclc_executor_add_service(
        &executor, &srv_coag, &req_coag, &resp_coag, coag_service_callback) != RCL_RET_OK) return false;
  if (rclc_executor_add_timer(&executor, &timer) != RCL_RET_OK) return false;

  // Response strings and the publish message are process-lifetime, not
  // session-lifetime -- init them once (guarded) so repeated reconnects don't
  // leak or double-init.
  static bool msg_inited = false;
  if (!msg_inited) {
    rosidl_runtime_c__String__init(&resp_cut.message);
    rosidl_runtime_c__String__init(&resp_coag.message);
    std_msgs__msg__Int32MultiArray__init(&state_msg);
    msg_inited = true;
  }

  // Baseline publish on every (re)connect, so a consumer that (re)subscribes
  // after a reconnect still gets a known starting state. Reflects the CURRENT
  // effective state, not a hard 0/0 -- if a channel is held across a reconnect
  // the consumer should learn it's active.
  publish_state(lastEffCut, lastEffCoag, SRC_BASELINE);
  return true;
}

void destroy_entities() {
  // Best-effort teardown. Order mirrors creation in reverse. Finalize calls
  // are not checked -- if the agent already vanished some will error, and
  // that's fine; we just want the local handles cleared for the next attempt.
  rmw_context_t *rmw_context = rcl_context_get_rmw_context(&support.context);
  (void)rmw_uros_set_context_entity_destroy_session_timeout(rmw_context, 0);

  rcl_service_fini(&srv_cut, &node);
  rcl_service_fini(&srv_coag, &node);
  rcl_publisher_fini(&pub_state, &node);
  rcl_timer_fini(&timer);
  rclc_executor_fini(&executor);
  rcl_node_fini(&node);
  rclc_support_fini(&support);
}

// ----------------------------- Setup -------------------------------
void setup() {
  // GPIO
  pinMode(PIN_SENSE_CUT,  INPUT);   // external pull-up on board (IO34/35 have none)
  pinMode(PIN_SENSE_COAG, INPUT);
  pinMode(PIN_RELAY_CUT,  OUTPUT);
  pinMode(PIN_RELAY_COAG, OUTPUT);
  pinMode(PIN_LED_CUT,    OUTPUT);
  pinMode(PIN_LED_COAG,   OUTPUT);

  digitalWrite(PIN_RELAY_CUT,  LOW);   // safe: relays open on boot
  digitalWrite(PIN_RELAY_COAG, LOW);
  digitalWrite(PIN_LED_CUT,    LOW);
  digitalWrite(PIN_LED_COAG,   LOW);

  // micro-ROS transport over USB serial.
  //
  // This is the micro_ros_platformio form. micro_ros_arduino instead uses a
  // bare set_microros_transports() with no Serial.begin(). The two libraries
  // are not interchangeable -- see platformio.ini.
  //
  // Baud must match platformio.ini monitor_speed AND the agent's -b argument.
  Serial.begin(115200);
  set_microros_serial_transports(Serial);
  delay(2000);

  // Entities and agent connection are handled entirely by the state machine in
  // loop() -- setup() does NOT block waiting for the agent. This is what lets
  // the board reconnect on its own after an agent restart without an EN press.

  // NOTE: micro-ROS entities are NOT created here anymore. loop() creates them
  // via the connection state machine once the agent is reachable, and rebuilds
  // them if the agent restarts. This removes the boot-order dependency and the
  // need to press EN after (re)starting the agent.
  //
  // The relay/LED outputs are already driven to a safe OFF above, and the
  // timer_callback that forwards the pedal only runs once entities exist and
  // the executor spins -- so while waiting for the agent, the board is inert
  // and the pedal does not reach the generator through the firmware path. The
  // hardware bypass relay covers the unpowered case; a powered-but-not-yet-
  // connected board is a brief startup window only.
}

// ----------------------------- Loop --------------------------------
// Connection-managed spin. Replaces the old "spin forever, assume connected"
// loop. See the AgentState machine above create_entities().
void loop() {
  switch (agent_state) {
    case WAITING_AGENT:
      // Ping every 500 ms until the agent answers. Slow-blink COAG LED so the
      // board visibly signals "waiting" rather than looking dead.
      EVERY_MS(500) {
        agent_state = (rmw_uros_ping_agent(100, 1) == RMW_RET_OK)
                      ? AGENT_AVAILABLE : WAITING_AGENT;
        if (agent_state == WAITING_AGENT) {
          digitalWrite(PIN_LED_COAG, !digitalRead(PIN_LED_COAG));
        }
      }
      break;

    case AGENT_AVAILABLE:
      // Agent is up -- build entities. On success go CONNECTED; on failure tear
      // down whatever partially built and drop back to waiting.
      digitalWrite(PIN_LED_COAG, LOW);
      agent_state = create_entities() ? AGENT_CONNECTED : WAITING_AGENT;
      if (agent_state == WAITING_AGENT) destroy_entities();
      break;

    case AGENT_CONNECTED:
      // Normal operation. Check the link twice a second; if it drops, go to
      // DISCONNECTED. Between checks, spin the executor (services + timer).
      EVERY_MS(500) {
        agent_state = (rmw_uros_ping_agent(100, 1) == RMW_RET_OK)
                      ? AGENT_CONNECTED : AGENT_DISCONNECTED;
      }
      if (agent_state == AGENT_CONNECTED) {
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10));
      }
      break;

    case AGENT_DISCONNECTED:
      // Link lost. Force relays/LEDs OFF (fail safe -- do not leave the
      // generator energised through a dead link), tear down stale entities,
      // and go back to waiting for the agent to return.
      digitalWrite(PIN_RELAY_CUT,  LOW);
      digitalWrite(PIN_RELAY_COAG, LOW);
      digitalWrite(PIN_LED_CUT,    LOW);
      digitalWrite(PIN_LED_COAG,   LOW);
      cmdCut = 0; cmdCoag = 0;
      lastEffCut = 0; lastEffCoag = 0;
      destroy_entities();
      agent_state = WAITING_AGENT;
      break;
  }
}
