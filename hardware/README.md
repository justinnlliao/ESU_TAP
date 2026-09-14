# Hardware

Each revision contains a KiCad project and project-local libraries registered
through `${KIPRJMOD}` in its symbol and footprint tables.

- [v1](esu-tap-v1/README.md): historical monopolar design.
- [v2](esu-tap-v2/README.md): CUT/COAG/bipolar design.
- [v3](esu-tap-v3/README.md): four-channel prototype, reviewed using KiCad 10.

Read [protection and validation status](../docs/SAFETY_AND_VALIDATION.md).
Manufacturing checks are not functional or clinical-use approval. The v3
watchdog arrangement has an independent-shutdown/sustained-bypass gap, and the
four-channel firmware implementation has not been physically qualified.

Revision-specific exports live in `fabrication/`. Use Gerbers, BOM, and CPL from
the same saved design. Some generated files (including Gerbers, drill files,
and ZIPs) are Git-ignored; do not assume a clone contains the complete release.

For JLCPCB, the CPL must contain `Designator,Mid X,Mid Y,Rotation,Layer`, with
coordinates in mm and layers Top/Bottom. Native KiCad position CSV headers may
need conversion. Verify the reference set against the assembly BOM and confirm
part-specific orientations in the assembler preview.
