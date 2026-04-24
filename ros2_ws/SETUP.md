# Build and run `pedal_controller` on Windows

The ROS 2 package now lives in a standard colcon workspace:

`ros2_ws/src/pedal_controller/`

## 1. Install ROS 2 (required)

This project targets **ROS 2 Humble** and uses `rclpy` and `std_msgs`.

- **Official install (long checklist: VS, OpenSSL, Python, etc.):**  
  [https://docs.ros.org/en/humble/Installation/Windows-Install-Binary.html](https://docs.ros.org/en/humble/Installation/Windows-Install-Binary.html)
- Unpack the Humble **Windows** release zip to a path you will keep, e.g. `C:\dev\ros2_humble`.
- **Newer LTS (e.g. Jazzy) may work** if you install that distro instead, but the docs and `ros2` path will differ; install one distro and stay consistent with its tutorials.

After install, you must open a shell where the ROS environment is loaded. The installer usually provides **Start Menu** shortcuts such as “ROS 2 Humble” that run the right `local_setup` for you. If you use a normal PowerShell, run the setup script from your install directory first (example for a typical unpack location):

**cmd.exe:**

`call C:\dev\ros2_humble\local_setup.bat`

**PowerShell (if your install has `local_setup.ps1`):**

`C:\dev\ros2_humble\local_setup.ps1`

(Adjust the path to match your actual ROS 2 root.)

Confirm:

`ros2 --version`

## 2. Colcon and Python tools

Use the same terminal where `ros2` already works and install the build tool if needed:

`python -m pip install -U colcon-common-extensions`

(If the ROS docs pinned a different `python` path, use that interpreter so colcon goes into the right environment.)

## 3. PySerial (used by the serial bridge)

With ROS’s environment still active:

`python -m pip install pyserial`

## 4. Build this workspace

From the `ros2_ws` folder (the parent of `src`):

`colcon build --merge-install --packages-select pedal_controller`

Then load the overlay in **every** new shell before running nodes (still from the same kind of “ROS” terminal, or after sourcing the ROS install):

**cmd.exe:**

`call install\local_setup.bat`

**PowerShell:**

`.\install\local_setup.ps1`

## 5. Run the nodes

**Serial bridge (COM port):** The launch file defaults to `COM3` on Windows. Override with an environment variable if needed.

`set ESU_SERIAL_PORT=COM3`

`ros2 launch pedal_controller esu_serial_bridge.launch.py`

**Log only (needs `/esu/activation_state` and optionally `/esu/command`):**

`ros2 run pedal_controller pedal_logger`

**Send commands (for testing with the logger):**

`ros2 run pedal_controller pedal_commander`

For a one-off in **cmd**: `set ESU_SERIAL_PORT=COM4` (then run the launch in the same window).

## 6. If `python` is wrong on your PC

The Microsoft Store / alias can steal `python`. On Windows, `py` often works, or use the full path to the Python that ROS 2’s docs installed (Humble’s binary guide used `C:\Python38` in the past). **Use the Python version that matches your ROS 2 install**, not necessarily Python 3.14 from a separate install.

## 7. Optional: WSL2 or Linux

Many teams find **Ubuntu + ROS 2** easier than native Windows. The same `ros2_ws` layout is valid there: install ROS 2 on Ubuntu, copy or clone the workspace, then `source /opt/ros/humble/setup.bash`, `colcon build`, `source install/local_setup.bash`, and use `/dev/ttyUSB0` instead of `COM*`.

## What was added in the repo

- `ros2_ws/src/pedal_controller` — the package in the correct colcon `src` layout (moved from the repo root).
- `ros2_ws/src/pedal_controller/resource/pedal_controller` — ament index marker (required to build).
- `pedal_controller/__init__.py` — so the module is a proper Python package.
- `package.xml` — `ament_python` build tool dependency.
- `ros2_ws/.gitignore` — ignores `build/`, `install/`, `log/`.

You can use `build.ps1` in this folder after ROS 2 is installed and your shell has `ros2` on `PATH`.
