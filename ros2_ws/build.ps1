# Build ros2_ws after sourcing your ROS 2 install (so `ros2` and `colcon` work).
# Example (cmd, before this script): call C:\dev\ros2_humble\local_setup.bat
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Get-Command ros2 -ErrorAction SilentlyContinue)) {
    Write-Error "ROS 2 is not on PATH. Open a ROS 2 terminal or run your install's local_setup. See SETUP.md."
}

if (-not (Get-Command colcon -ErrorAction SilentlyContinue)) {
    Write-Error "colcon not found. Run: python -m pip install -U colcon-common-extensions"
}

colcon build --merge-install --packages-select pedal_controller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Build OK. In this shell, overlay this workspace with:" -ForegroundColor Green
Write-Host "  .\\install\\local_setup.ps1" -ForegroundColor Cyan
Write-Host "If `local_setup.ps1` is missing, use cmd: call install\local_setup.bat" -ForegroundColor DarkGray
