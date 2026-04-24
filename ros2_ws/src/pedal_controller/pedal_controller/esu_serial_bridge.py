#!/usr/bin/env python3
"""
esu_serial_bridge.py

ROS2 <-> MCU serial bridge for electrosurgery activation sensing + commanding.

Publishes:
  /esu/activation_state   (std_msgs/String)
    Payload example: "cut=0 coag=1 ts=123456"

Subscribes:
  /esu/command            (std_msgs/String)
    Commands (case-insensitive):
      "CUT_ON <ms>"
      "COAG_ON <ms>"
      "CUT_OFF"
      "COAG_OFF"

Serial protocol (newline-delimited ASCII):
  MCU -> PC:
    "STATE cut=<0|1> coag=<0|1> ts=<int>\n"
  PC -> MCU:
    "CUT_ON <ms>\n"
    "COAG_ON <ms>\n"
    "CUT_OFF\n"
    "COAG_OFF\n"
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import serial  # pyserial
except Exception:  # pragma: no cover
    serial = None


@dataclass
class ParsedState:
    cut: int | None = None
    coag: int | None = None
    ts: int | None = None


def _parse_state_line(line: str) -> ParsedState | None:
    # Expected: "STATE cut=0 coag=1 ts=123"
    line = line.strip()
    if not line:
        return None
    if not line.upper().startswith("STATE"):
        return None

    parts = line.split()
    kv = {}
    for p in parts[1:]:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        kv[k.strip().lower()] = v.strip()

    st = ParsedState()
    try:
        if "cut" in kv:
            st.cut = int(kv["cut"])
        if "coag" in kv:
            st.coag = int(kv["coag"])
        if "ts" in kv:
            st.ts = int(kv["ts"])
    except Exception:
        return None
    return st


class EsuSerialBridge(Node):
    def __init__(self):
        super().__init__("esu_serial_bridge")

        # Parameters
        # Default is platform-aware (override via ROS params or launch file)
        default_port = "COM3" if __import__("os").name == "nt" else "/dev/ttyUSB0"
        self.declare_parameter("port", default_port)
        self.declare_parameter("baud", 115200)
        self.declare_parameter("read_timeout_s", 0.2)
        self.declare_parameter("reconnect_s", 1.0)

        self._port = self.get_parameter("port").get_parameter_value().string_value
        self._baud = self.get_parameter("baud").get_parameter_value().integer_value
        self._read_timeout_s = float(
            self.get_parameter("read_timeout_s").get_parameter_value().double_value
        )
        self._reconnect_s = float(
            self.get_parameter("reconnect_s").get_parameter_value().double_value
        )

        # ROS interfaces
        self._pub_state = self.create_publisher(String, "/esu/activation_state", 10)
        self.create_subscription(String, "/esu/command", self._on_command, 10)

        # Serial thread management
        self._lock = threading.Lock()
        self._ser = None
        self._stop = False
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)

        if serial is None:
            self.get_logger().error(
                "pyserial is not available. Install it (pip install pyserial) and rebuild."
            )
        else:
            self._rx_thread.start()

        self.get_logger().info(
            f"esu_serial_bridge ready (port={self._port}, baud={self._baud})."
        )

    def destroy_node(self):
        self._stop = True
        try:
            if self._rx_thread.is_alive():
                self._rx_thread.join(timeout=1.0)
        except Exception:
            pass
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
        super().destroy_node()

    # ---- ROS callbacks -------------------------------------------------
    def _on_command(self, msg: String):
        cmd = (msg.data or "").strip()
        if not cmd:
            return
        self._serial_write_line(cmd)

    # ---- Serial helpers ------------------------------------------------
    def _serial_connect(self):
        if serial is None:
            return None
        try:
            ser = serial.Serial(
                self._port,
                int(self._baud),
                timeout=self._read_timeout_s,
                write_timeout=0.5,
            )
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            self.get_logger().info(f"Connected to MCU on {self._port}")
            return ser
        except Exception as e:
            self.get_logger().warn(f"Serial connect failed ({self._port}): {e}")
            return None

    def _serial_write_line(self, line: str):
        line = line.strip()
        if not line:
            return
        payload = (line + "\n").encode("utf-8", errors="ignore")
        with self._lock:
            ser = self._ser
        if ser is None:
            self.get_logger().warn(f"Dropped command (not connected): {line}")
            return
        try:
            ser.write(payload)
            ser.flush()
        except Exception as e:
            self.get_logger().warn(f"Serial write failed: {e}")
            with self._lock:
                try:
                    if self._ser is not None:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None

    def _rx_loop(self):
        # Keep attempting to connect + read until shutdown.
        while not self._stop:
            with self._lock:
                ser = self._ser

            if ser is None:
                ser = self._serial_connect()
                with self._lock:
                    self._ser = ser
                if ser is None:
                    time.sleep(self._reconnect_s)
                    continue

            try:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
            except Exception as e:
                self.get_logger().warn(f"Serial read failed: {e}")
                with self._lock:
                    try:
                        if self._ser is not None:
                            self._ser.close()
                    except Exception:
                        pass
                    self._ser = None
                time.sleep(self._reconnect_s)
                continue

            st = _parse_state_line(line)
            if st is None:
                # Forward unknown lines as debug once in a while (avoid spam)
                self.get_logger().debug(f"MCU: {line}")
                continue

            # Publish a simple, parseable string
            out = String()
            cut = st.cut if st.cut is not None else -1
            coag = st.coag if st.coag is not None else -1
            ts = st.ts if st.ts is not None else -1
            out.data = f"cut={cut} coag={coag} ts={ts}"
            self._pub_state.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = EsuSerialBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

