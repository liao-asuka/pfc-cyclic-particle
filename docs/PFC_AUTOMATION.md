# PFC3D cyclic-face random-interior packing workflow

This folder contains a ready-to-run particle packing setup for PFC3D 6.0.
Opposite cut faces can be made cyclic along any subset of `x`, `y`, and `z`.
For each enabled direction, particles near the two opposite faces are generated
as matching pairs with the same radius, same transverse coordinates, and same
inward distance from the two faces. The inward distance is smaller than the
particle radius, so the particles cross the cut faces and produce visible,
matching sections after STL clipping. Interior particles remain random.

## Folder Layout

- `run_cyclic_pack.dat`: main PFC data file. It builds the 3 mm x 3 mm x 6 mm
  wall box, calls the generator, relaxes the assembly, checks it, saves the
  model, and exports STL.
- `cyclic_pack.py`: particle generator. Edit the top parameter section to change
  target porosity, radius bins, random seed, and cyclic face settings.
- `cyclic_pack_check.py`: verifies bounds, geometric porosity, random-particle
  face clearance, and cyclic face-pair correspondence.
- `cyclic_pack_project.py`: after relaxation, projects cyclic particles back to
  exact face-pair constraints and keeps random balls inside the box constraints.
- `export_pack_stl.py`: exports particles to one ASCII STL file. By default it
  clips particles to the box and exports no wall faces, so the particle cut
  sections are visible for cyclic-boundary inspection.
- `docs/`: project notes and workflow documentation.
- `tools/`: optional PowerShell helpers for PFC Console/GUI automation.
- `outputs/`: generated `.sav` and `.stl` outputs.

## Cyclic Face Settings

In `cyclic_pack.py`, adjust:

```python
PERIODIC_AXES = ("x", "y", "z")
PERIODIC_BAND_THICKNESS = 0.55
PERIODIC_SOLID_VOLUME_FRACTION = 0.40
RANDOM_PERIODIC_FACE_CLEARANCE = 0.03
PERIODIC_CUT_OFFSET_FRACTION_MIN = 0.25
PERIODIC_CUT_OFFSET_FRACTION_MAX = 0.75
```

Examples:

```python
PERIODIC_AXES = ("z",)           # inlet/outlet only
PERIODIC_AXES = ("x", "y")      # left/right and front/back
PERIODIC_AXES = ("x", "y", "z") # all three opposite face pairs
```

## Manual PFC Console Run

Open PFC3D and run this in the Console:

```text
program call 'E:/codexfile/pfc cyclic particle/run_cyclic_pack.dat'
```

The final state is saved as:

```text
outputs/cyclic_pack_porosity_0p40.sav
```

The clipped particle STL is exported as:

```text
E:\codexfile\pfc cyclic particle\outputs\stl\cyclic-particles-1.stl
```

`export_pack_stl.py` uses `EXPORT_WALLS = False` by default. Keep it this way
when checking whether opposite particle cut faces match; wall faces lie on the
same planes and can visually hide the cut caps.

## Optional Console Helper

From PowerShell in this folder:

```powershell
.\tools\run_pfc_console.ps1
```

On this PFC3D 6.0 installation, `pfc3d600_console.exe` starts an interactive
prompt but does not consume normal PowerShell/cmd piped input. The helper prints
the exact command to run.

## Optional GUI Command Sender

With PFC3D already open and the Console input line focused:

```powershell
.\tools\send_to_pfc_gui.ps1
```

This sends the same `program call ...` command to the running PFC3D GUI window.
If the command appears in the editor instead of the Console, click the Console
input line and run the script again.

## Console Bridge For Codex

`tools/pfc_console_bridge.ps1` attaches to the running PFC3D GUI with Windows UI
Automation, writes a command into `itasca3d::PromptLineEdit`, and reads the tail
of `itasca3d::TextOutput`.

Example:

```powershell
.\tools\pfc_console_bridge.ps1 -Command "program call 'E:/codexfile/pfc cyclic particle/run_cyclic_pack.dat'" -WaitSeconds 5
```
