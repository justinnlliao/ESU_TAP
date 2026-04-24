/*
 * Da Vinci Pedal Controller - ESU Hardware Interface
 * 
 * Target Board: ESP32 / Arduino Uno
 * 
 * Description:
 * This firmware acts as the hardware bridge communicating with `esu_serial_bridge.py`.
 * It handles the CUT (Yellow) and COAG (Blue) pedals.
 * 
 * Protocol:
 *   MCU -> PC:  "STATE cut=<0|1> coag=<0|1> ts=<int>\n"
 *   PC -> MCU:  "CUT_ON <ms>\n", "COAG_ON <ms>\n", "CUT_OFF\n", "COAG_OFF\n"
 */

// --- Physical Switch Inputs (Surgeon) ---
const int PIN_SW_CUT = 4;
const int PIN_SW_COAG = 5;

// --- Actuator/Relay Outputs (Computer) ---
const int PIN_RELAY_CUT = 6;
const int PIN_RELAY_COAG = 7;

// --- State Tracking ---
int currentCut = 0;
int currentCoag = 0;
int lastCut = 0;
int lastCoag = 0;

unsigned long cutAutoOffTime = 0;
unsigned long coagAutoOffTime = 0;

// --- Debounce (non-blocking) ---
const unsigned long DEBOUNCE_MS = 30;
int rawCut = 0;
int rawCoag = 0;
int stableCut = 0;
int stableCoag = 0;
int lastRawCut = 0;
int lastRawCoag = 0;
unsigned long lastRawChangeCutMs = 0;
unsigned long lastRawChangeCoagMs = 0;

void setup() {
  Serial.begin(115200);
  
  // Inputs from limit switches (LOW = pressed)
  pinMode(PIN_SW_CUT, INPUT_PULLUP);
  pinMode(PIN_SW_COAG, INPUT_PULLUP);
  
  // Outputs to Relays/Actuators
  pinMode(PIN_RELAY_CUT, OUTPUT);
  pinMode(PIN_RELAY_COAG, OUTPUT);
  
  digitalWrite(PIN_RELAY_CUT, LOW);
  digitalWrite(PIN_RELAY_COAG, LOW);
}

void loop() {
  unsigned long now = millis();
  
  // 1. Read Physical Limit Switches
  // Invert because INPUT_PULLUP makes a press = LOW
  rawCut = (digitalRead(PIN_SW_CUT) == LOW) ? 1 : 0;
  rawCoag = (digitalRead(PIN_SW_COAG) == LOW) ? 1 : 0;

  // Debounce CUT
  if (rawCut != lastRawCut) {
    lastRawCut = rawCut;
    lastRawChangeCutMs = now;
  }
  if ((now - lastRawChangeCutMs) >= DEBOUNCE_MS) {
    stableCut = rawCut;
  }

  // Debounce COAG
  if (rawCoag != lastRawCoag) {
    lastRawCoag = rawCoag;
    lastRawChangeCoagMs = now;
  }
  if ((now - lastRawChangeCoagMs) >= DEBOUNCE_MS) {
    stableCoag = rawCoag;
  }

  currentCut = stableCut;
  currentCoag = stableCoag;

  // 2. Publish state if it changes (non-blocking)
  if (currentCut != lastCut || currentCoag != lastCoag) {
    Serial.print("STATE cut=");
    Serial.print(currentCut);
    Serial.print(" coag=");
    Serial.print(currentCoag);
    Serial.print(" ts=");
    Serial.println(now);

    lastCut = currentCut;
    lastCoag = currentCoag;
  }
  
  // 3. Handle Auto-Off Timers for Actuators
  if (cutAutoOffTime > 0 && now >= cutAutoOffTime) {
    digitalWrite(PIN_RELAY_CUT, LOW);
    cutAutoOffTime = 0;
  }
  if (coagAutoOffTime > 0 && now >= coagAutoOffTime) {
    digitalWrite(PIN_RELAY_COAG, LOW);
    coagAutoOffTime = 0;
  }

  // 4. Handle incoming Serial Commands from ROS 2
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();
    
    if (cmd.startsWith("CUT_ON")) {
      digitalWrite(PIN_RELAY_CUT, HIGH);
      // Parse optional duration
      int spaceIdx = cmd.indexOf(' ');
      if (spaceIdx > 0) {
        long ms = cmd.substring(spaceIdx + 1).toInt();
        if (ms > 0) cutAutoOffTime = now + ms;
      }
    } 
    else if (cmd.startsWith("COAG_ON")) {
      digitalWrite(PIN_RELAY_COAG, HIGH);
      int spaceIdx = cmd.indexOf(' ');
      if (spaceIdx > 0) {
        long ms = cmd.substring(spaceIdx + 1).toInt();
        if (ms > 0) coagAutoOffTime = now + ms;
      }
    }
    else if (cmd == "CUT_OFF") {
      digitalWrite(PIN_RELAY_CUT, LOW);
      cutAutoOffTime = 0;
    }
    else if (cmd == "COAG_OFF") {
      digitalWrite(PIN_RELAY_COAG, LOW);
      coagAutoOffTime = 0;
    }
  }
}
