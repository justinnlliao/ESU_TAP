# trash/

Files moved out of the active tree but kept for recoverability rather than
deleted outright. Nothing here is used by the current build. Safe to delete
permanently once you're confident you won't need to reference them.

Moved 2026-07-27:

- `TQ2-L2-5V.kicad_sym`, `TQ2.kicad_mod` — symbol/footprint for the Panasonic
  TQ2-L2-5V latching relays. Replaced by the Omron G6K-2F-Y (non-latching) in
  the sense-then-forward redesign. Removed from the schematic and from both
  `sym-lib-table` and `fp-lib-table` before moving, so the KiCad project no
  longer references them.

- `build.ps1` — Windows PowerShell build script for the ROS 2 workspace. Blue
  (Ubuntu) is the build machine now; `colcon build` is the supported path.
  Restore only if you resume building the workspace on the Windows laptop.

- `da_vinci_foot_pedal_project.md` — early project brainstorming doc,
  superseded by the current `README.md` and `docs/ESU_TAP_v2_change_list.md`.
  Historical reference only.
