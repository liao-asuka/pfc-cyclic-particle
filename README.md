# PFC Cyclic Particle Plugin

Windows + PFC3D workflow for generating cyclic particle RVEs and smooth
Fluent-ready fluid-domain STL files.

The current recommended interface is the standalone plugin folder:

```text
cyclic_particle_plugin/
```

## What It Does

- Generates random packed particle RVEs in PFC3D.
- Supports cyclic particle boundaries on `x`, `y`, and/or `z`.
- Keeps boundary-cut particle fragments balanced, typically around 40-60% split.
- Removes floating disconnected particles from the final RVE.
- Exports particle parameters to CSV.
- Exports particle STL.
- Exports smooth level-set fluid-domain STL for Fluent Meshing.
- Preserves fluid STL surface zones:

```text
particle_walls
x_min
x_max
y_min
y_max
z_min
z_max
```

## Quick Start

Double-click:

```text
cyclic_particle_plugin/CyclicParticlePlugin.exe
```

Then edit the model parameters and click:

```text
Save and Run PFC
```

The plugin will save the JSON config, open or connect to PFC3D, and run the
generation pipeline.

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
  <model_name>.sav
```

## Requirements

- Windows
- PFC3D 6.x
- ParaView with `pvpython` for fluid STL export

Default paths used by the plugin:

```text
D:/PFC/exe64/pfc3d600_gui.exe
D:/ParaView 6.1.0/bin/pvpython.exe
```

Both paths can be changed in the plugin window.

## Documentation

User guides:

```text
cyclic_particle_plugin/docs/USER_GUIDE.md
cyclic_particle_plugin/docs/USER_GUIDE_CN.md
```

Project notes:

```text
docs/PROJECT_LOG.md
docs/PROJECT_SUMMARY.md
docs/PFC_AUTOMATION.md
```

## 中文简介

本项目用于在 PFC3D 中生成循环颗粒代表体积单元，并可直接导出用于
Fluent Meshing 的平滑流体域 STL。

推荐直接使用：

```text
cyclic_particle_plugin/CyclicParticlePlugin.exe
```

在窗口中设置模型尺寸、目标孔隙率、周期方向、粒径分布和输出目录后，
点击 `Save and Run PFC` 即可自动调用 PFC 完成生成。

详细中文说明见：

```text
cyclic_particle_plugin/docs/USER_GUIDE_CN.md
```
