# Cyclic Particle PFC Plugin User Guide

This folder is an independent Windows + PFC3D 6.x plugin package. It generates
cyclic particle models and/or smooth Fluent-ready fluid-domain STL files from a
single JSON configuration. The default unit is `mm`.

Chinese guide: `USER_GUIDE_CN.md`

## Folder Layout

```text
cyclic_particle_plugin/
  config/
    model_config.json
    model_config.example.json
  scripts/
    run_pipeline.py
    validate_config.py
    export_fluid_levelset.py
    generate_pack.py
    extract_rve.py
    export_particles_stl.py
  ui/
    edit_config.ps1
  pfc/
    run_plugin.dat
  tools/
    install_paraview.ps1
  docs/
    USER_GUIDE.md
```

## Basic Workflow

1. Edit configuration:

Double-click the executable launcher in the plugin root:

```text
cyclic_particle_plugin/CyclicParticlePlugin.exe
```

If the exe is blocked by Windows policy, use the fallback launcher:

```text
cyclic_particle_plugin/Start_Config_Editor.vbs
```

If `.vbs` launch is blocked by your Windows policy, double-click:

```text
cyclic_particle_plugin/Start_Config_Editor.cmd
```

Or run manually:

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\ui\edit_config.ps1
```

2. Validate configuration:

```powershell
python cyclic_particle_plugin\scripts\validate_config.py cyclic_particle_plugin\config\model_config.json
```

3. Run in PFC3D:

The config window can do this directly. Click:

```text
Save and Run PFC
```

It saves the current JSON config, opens PFC GUI if needed, and sends the command
to the PFC Console automatically.

Manual alternative:

```text
program call 'E:/codexfile/pfc cyclic particle/cyclic_particle_plugin/pfc/run_plugin.dat'
```

The PFC entry calls:

```text
cyclic_particle_plugin/scripts/run_pipeline.py
```

## Configuration

The stable user-facing interface is `config/model_config.json`.

Important fields:

- `model_name`: case folder name.
- `unit`: fixed to `mm` in v1.
- `domain`: RVE size in mm.
- `target_porosity`: final particle porosity target.
- `periodic_axes`: any combination of `x`, `y`, `z`.
- `output_mode`: `particles`, `fluid`, or `both`.
- `output_dir`: parent output directory.
- `radius_bins`: 1 to 5 particle-size bins.
- `fluid_surface`: smoothing and level-set parameters for the Fluent-ready fluid STL.
- `paraview.pvpython_path`: ParaView Python executable used for VTK/scipy surface extraction.
- `pfc.gui_path`: PFC3D GUI executable used by the run button.

`radius_bins` rules:

- 1 to 5 bins.
- `r_min` and `r_max` must be positive.
- `r_min < r_max`.
- `volume_fraction` values must sum to `1.0`.

## Outputs

Each run writes one case folder:

```text
<output_dir>/<model_name>/
  config_used.json
  run_log.txt
  geometry/
    particles.csv
  particles/
    particles.stl
  fluid/
    fluid_fluent.stl
    fluid_surface_report.txt
```

`particles.csv` is the shared geometry source for both STL exporters. It records
particle position, radius, source particle id, periodic shift, layer, and size bin.

## Fluid STL Surface Zones

The fluid STL keeps the current Fluent-friendly surface classification:

```text
particle_walls
x_min
x_max
y_min
y_max
z_min
z_max
```

This lets Fluent Meshing keep inlet/outlet/wall/cyclic patches separated.

## ParaView Dependency

Fluid STL export uses ParaView's `pvpython` because the exporter depends on VTK,
NumPy, and SciPy.

If ParaView is missing, install it to the default D drive path:

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\tools\install_paraview.ps1
```

Or choose another folder:

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\tools\install_paraview.ps1 -InstallDir "D:\ParaView 6.1.0"
```

Then set:

```json
"paraview": {
  "pvpython_path": "D:/ParaView 6.1.0/bin/pvpython.exe"
}
```

## Geometry Notes

The pipeline follows the cyclicparticle3/4 strategy:

- Generate a larger precursor pack.
- Relax it in PFC.
- Extract a connected RVE.
- Reject floating particles by keeping the largest contact-connected component.
- Project boundary-crossing particles so cyclic cut fragments are balanced.
- Export particles and/or a smooth level-set fluid surface.

For cyclic boundary inspection, use `periodic_axes` to control which opposing
faces receive periodic particle images. For OpenFOAM cyclic boundaries, keep the
same periodic axes through meshing and solver setup.

## First Test Cases

Recommended checks:

- `output_mode = "particles"` with default `3 x 3 x 6 mm`, porosity `0.40`.
- `output_mode = "fluid"` using the existing ParaView path.
- `output_mode = "both"` with a custom output folder.
- One radius bin.
- Five radius bins.

After each run, inspect `run_log.txt` for:

- final porosity,
- particle count,
- removed floating particles,
- boundary cut fragment range,
- fluid surface parameters,
- output file paths.

## Auto Run And Watch

To let the plugin start/connect PFC, send the run command, and watch Console/log
output for errors:

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\tools\run_and_watch_pfc.ps1
```

The watcher prints `run_log.txt` progress and stops on `Python error`,
`Traceback`, or `ERROR:`. For small particle radii or dense cases, watch for
`pack progress` lines before assuming the run is stuck.
