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
 *          cut    : 0/1  current CUT active state (sensed)
 *          coag   : 0/1  current COAG active state (sensed)
 *          source : 0 = surgeon (sensed edge, no recent command)
 *                   1 = computer (edge within command window)
 *        Published on every state change.
 *
 * Hardware (unchanged from the electrical design):
 *   Footswitch: Bovie BV-1253B via Bulgin 400-series 3-pole connector
 *     Pin 1 = switched, Pins 2&3 = common (bridged). Press shorts 1 to 2/3.
 *   Actuation: relay shorts pin 1 to pin 2 on the generator side.
 *   Sensing:   optocoupler across pin 1 & pin 2, active-low into MCU.
 *
 * micro-ROS setup notes:
 *   - Uses only STANDARD message/service types (std_srvs/SetBool,
 *     std_msgs/Int32MultiArray) so NO custom library rebuild is needed.
 *   - The rclc executor must have enough handles for 2 services + timer = 3.
 *   - Serial (USB) transport keeps things deterministic and wired.
 *
 * Agent (run on the PC):
 *   ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200
 */

#include <Arduino.h>
#include <micro_ros_arduino.h>

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <std_srvs/srv/set_bool.h>
#include <std_msgs/msg/int32_multi_array.h>

// ----------------------------- Pin map -----------------------------
// Sense inputs (optocoupler output; LOW = pedal pressed / relay closed)
const int PIN_SENSE_CUT  = 34;   // input-only, external pull-up required
const int PIN_SENSE_COAG = 35;   // input-only, external pull-up required

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
int32_t state_data[3];   // [cut, coag, source]

// Periodic timer to poll sense inputs
rcl_timer_t         timer;

// ------------------------- State tracking --------------------------
int lastCut  = 0;
int lastCoag = 0;

// Command-window tracking for surgeon-vs-computer attribution.
// If a sensed edge occurs within CMD_WINDOW_MS of a service command on that
// channel, we attribute it to the computer; otherwise to the surgeon.
const unsigned long CMD_WINDOW_MS = 750;
unsigned long lastCmdMsCut  = 0;
unsigned long lastCmdMsCoag = 0;

// Debounce
const unsigned long DEBOUNCE_MS = 30;
int rawCut = 0, rawCoag = 0;
int stableCut = 0, stableCoag = 0;
int lastRawCut = 0, lastRawCoag = 0;
unsigned long lastRawChangeCutMs = 0, lastRawChangeCoagMs = 0;

// ------------------------- Error handling --------------------------
#define RCCHECK(fn) { rcl_ret_t rc = fn; if (rc != RCL_RET_OK) { error_loop(); } }
#define RCSOFTCHECK(fn) { rcl_ret_t rc = fn; (void)rc; }

void error_loop() {
  // Blink both LEDs to signal a fatal micro-ROS error.
  while (1) {
    digitalWrite(PIN_LED_CUT,  !digitalRead(PIN_LED_CUT));
    digitalWrite(PIN_LED_COAG, !digitalRead(PIN_LED_COAG));
    delay(150);
  }
}

// --------------------- Publish current state -----------------------
void publish_state(int cut, int coag, int source) {
  state_data[0] = cut;
  state_data[1] = coag;
  state_data[2] = source;   // 0 = surgeon, 1 = computer
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

  lastCmdMsCut = millis();   // mark command time for attribution

  if (rq->data) {
    digitalWrite(PIN_RELAY_CUT, HIGH);
    digitalWrite(PIN_LED_CUT,   HIGH);
    rs->success = true;
    rosidl_runtime_c__String__assign(&rs->message, "cut on");
  } else {
    digitalWrite(PIN_RELAY_CUT, LOW);
    digitalWrite(PIN_LED_CUT,   LOW);
    rs->success = true;
    rosidl_runtime_c__String__assign(&rs->message, "cut off");
  }
}

void coag_service_callback(const void *req, void *resp) {
  const std_srvs__srv__SetBool_Request *rq =
      (const std_srvs__srv__SetBool_Request *)req;
  std_srvs__srv__SetBool_Response *rs =
      (std_srvs__srv__SetBool_Response *)resp;

  lastCmdMsCoag = millis();

  if (rq->data) {
    digitalWrite(PIN_RELAY_COAG, HIGH);
    digitalWrite(PIN_LED_COAG,   HIGH);
    rs->success = true;
    rosidl_runtime_c__String__assign(&rs->message, "coag on");
  } else {
    digitalWrite(PIN_RELAY_COAG, LOW);
    digitalWrite(PIN_LED_COAG,   LOW);
    rs->success = true;
    rosidl_runtime_c__String__assign(&rs->message, "coag off");
  }
}

// --------------------- Timer: poll sense + publish -----------------
void timer_callback(rcl_timer_t *t, int64_t last_call_time) {
  RCLC_UNUSED(last_call_time);
  if (t == NULL) return;

  unsigned long now = millis();

  // Read optocoupler sense (active-low: LOW = pressed/active)
  rawCut  = (digitalRead(PIN_SENSE_CUT)  == LOW) ? 1 : 0;
  rawCoag = (digitalRead(PIN_SENSE_COAG) == LOW) ? 1 : 0;

  // Debounce CUT
  if (rawCut != lastRawCut) { lastRawCut = rawCut; lastRawChangeCutMs = now; }
  if ((now - lastRawChangeCutMs) >= DEBOUNCE_MS) { stableCut = rawCut; }

  // Debounce COAG
  if (rawCoag != lastRawCoag) { lastRawCoag = rawCoag; lastRawChangeCoagMs = now; }
  if ((now - lastRawChangeCoagMs) >= DEBOUNCE_MS) { stableCoag = rawCoag; }

  // On any change, attribute source and publish
  if (stableCut != lastCut || stableCoag != lastCoag) {
    int source = 0;  // default surgeon
    // If the change is on CUT and a CUT command was recent -> computer
    if (stableCut != lastCut && (now - lastCmdMsCut) <= CMD_WINDOW_MS) source = 1;
    // If the change is on COAG and a COAG command was recent -> computer
    if (stableCoag != lastCoag && (now - lastCmdMsCoag) <= CMD_WINDOW_MS) source = 1;

    publish_state(stableCut, stableCoag, source);

    lastCut  = stableCut;
    lastCoag = stableCoag;
  }
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

  // micro-ROS transport over USB serial
  set_microros_transports();
  delay(2000);

  allocator = rcl_get_default_allocator();
  RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
  RCCHECK(rclc_node_init_default(&node, "esu_tap_node", "", &support));

  // Publisher: /esu/activation_state
  RCCHECK(rclc_publisher_init_default(
      &pub_state,
      &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray),
      "/esu/activation_state"));

  // Service: /esu/cut
  RCCHECK(rclc_service_init_default(
      &srv_cut,
      &node,
      ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
      "/esu/cut"));

  // Service: /esu/coag
  RCCHECK(rclc_service_init_default(
      &srv_coag,
      &node,
      ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool),
      "/esu/coag"));

  // Timer: poll sense inputs every 10 ms
  RCCHECK(rclc_timer_init_default(
      &timer, &support, RCL_MS_TO_NS(10), timer_callback));

  // Executor: 2 services + 1 timer = 3 handles
  RCCHECK(rclc_executor_init(&executor, &support.context, 3, &allocator));
  RCCHECK(rclc_executor_add_service(
      &executor, &srv_cut, &req_cut, &resp_cut, cut_service_callback));
  RCCHECK(rclc_executor_add_service(
      &executor, &srv_coag, &req_coag, &resp_coag, coag_service_callback));
  RCCHECK(rclc_executor_add_timer(&executor, &timer));

  // Initialise the response message strings once
  rosidl_runtime_c__String__init(&resp_cut.message);
  rosidl_runtime_c__String__init(&resp_coag.message);
}

// ----------------------------- Loop --------------------------------
void loop() {
  RCSOFTCHECK(rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10)));
}
