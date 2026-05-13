# PFC3D wall-symmetric random-interior packing workflow

This folder contains a ready-to-run particle packing setup for PFC3D 6.0. Only
particles near the four side walls are mirror-symmetric; interior particles are
randomly distributed across the full specimen so no artificial inner/outer
interface channel is created.

## Files

- `run_symmetric_pack.dat`: main PFC data file. It builds the 3 mm x 3 mm x 6 mm wall box, calls the generator, relaxes the assembly, checks it, saves the model, and exports STL.
- `symmetric_pack.py`: particle generator. Edit the top parameter section to change target porosity, radius bins, random seed, and placement tolerance.
- `symmetric_pack_check.py`: verifies bounds, geometric porosity, side-wall clearance for random balls, and mirror symmetry for wall balls.
- `symmetric_pack_project.py`: after relaxation, projects wall mirror groups back to exact symmetry and keeps random balls inside the full-box constraints.
- `export_pack_stl.py`: exports particles and the six wall faces to one ASCII STL file.
- `run_pfc_console.ps1`: optional PowerShell wrapper for `D:\PFC\exe64\pfc3d600_console.exe`.

## Manual PFC Console Run

Open PFC3D and run this in the Console:

```text
program call 'E:/codexfile/pfc cyclic particle/run_symmetric_pack.dat'
```

The final state is saved as:

```text
symmetric_pack_porosity_0p40.sav
```

The particle and wall STL is exported as:

```text
E:\codexfile\pfc cyclic particle\STLfile\cyc-particles-1.stl
```

## Optional Console Helper

From PowerShell in this folder:

```powershell
.\run_pfc_console.ps1
```

On this PFC3D 6.0 installation, `pfc3d600_console.exe` starts an interactive
prompt but does not consume normal PowerShell/cmd piped input. The helper prints
the exact command to run.

## Optional GUI Command Sender

With PFC3D already open and the Console input line focused:

```powershell
.\send_to_pfc_gui.ps1
```

This sends the same `program call ...` command to the running PFC3D GUI window.
If the command appears in the editor instead of the Console, click the Console
input line and run the script again.

## Console Bridge For Codex

`pfc_console_bridge.ps1` attaches to the running PFC3D GUI with Windows UI
Automation, writes a command into `itasca3d::PromptLineEdit`, and reads the
tail of `itasca3d::TextOutput`.

Example:

```powershell
.\pfc_console_bridge.ps1 -Command "program call 'E:/codexfile/pfc cyclic particle/run_symmetric_pack.dat'" -WaitSeconds 5
```

This is the preferred bridge when Codex needs to see PFC Console errors directly.

## Parameters To Edit Later

In `symmetric_pack.py`, adjust:

- `TARGET_POROSITY`
- `RADIUS_BINS`
- `RANDOM_SEED`
- `WALL_BAND_THICKNESS`
- `WALL_SOLID_VOLUME_FRACTION`
- `RANDOM_SIDE_WALL_CLEARANCE`
- `MIN_CENTER_SPACING_FACTOR`
- `MAX_INSERT_ATTEMPTS`

The generator creates mirror groups only for particles in the side-wall band.
Random particles are not confined to the old central `1.5 x 1.5 x 6 mm` region;
they can fill the full interior and naturally contact the mirror-symmetric wall
fabric. The small `RANDOM_SIDE_WALL_CLEARANCE` keeps random balls from becoming
the actual side-wall-contacting particles.
