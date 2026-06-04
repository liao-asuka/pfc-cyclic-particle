# Cyclic Particle PFC 插件中文使用说明

本插件是一个独立的 Windows + PFC3D 6.x 工具包，用于从参数配置自动生成循环颗粒模型和/或适合 Fluent Meshing 使用的平滑流体域 STL。默认单位为 `mm`。

## 1. 插件目录

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
    USER_GUIDE_CN.md
```

## 2. 基本使用流程

### 第一步：编辑配置

推荐直接双击插件根目录下的 exe 启动程序：

```text
cyclic_particle_plugin/CyclicParticlePlugin.exe
```

这会像普通 Windows 软件一样打开配置窗口。

如果 exe 被系统策略拦截，也可以双击备用启动文件：

```text
cyclic_particle_plugin/Start_Config_Editor.vbs
```

如果系统限制了 `.vbs`，也可以双击：

```text
cyclic_particle_plugin/Start_Config_Editor.cmd
```

或者手动运行 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\ui\edit_config.ps1
```

也可以直接编辑：

```text
cyclic_particle_plugin/config/model_config.json
```

### 第二步：检查配置是否合法

```powershell
python cyclic_particle_plugin\scripts\validate_config.py cyclic_particle_plugin\config\model_config.json
```

如果显示：

```text
CONFIG OK
```

说明配置可以被插件读取。

### 第三步：运行 PFC

新版配置窗口可以直接完成这一步。点击：

```text
Save and Run PFC
```

插件会先保存当前配置，然后自动打开 PFC GUI，并把运行命令发送到 PFC Console。

如果希望手动运行，也可以在 PFC3D Console 或 PFC 命令窗口中执行：

```text
program call 'E:/codexfile/pfc cyclic particle/cyclic_particle_plugin/pfc/run_plugin.dat'
```

该入口会自动调用：

```text
cyclic_particle_plugin/scripts/run_pipeline.py
```

## 3. 配置文件说明

主要配置文件是：

```text
cyclic_particle_plugin/config/model_config.json
```

关键参数如下。

### 模型名称

```json
"model_name": "sample_case"
```

该名称会作为输出 case 文件夹名称。

### 单位

```json
"unit": "mm"
```

当前版本固定为 `mm`，不做单位换算。

### 模型尺寸

```json
"domain": {
  "x": 3.0,
  "y": 3.0,
  "z": 6.0
}
```

表示最终 RVE 的尺寸为 `3 mm x 3 mm x 6 mm`。

### 目标孔隙率

```json
"target_porosity": 0.40
```

插件会尽量让最终截取出的颗粒模型接近该孔隙率。

### 周期方向

```json
"periodic_axes": ["x", "y"]
```

可选方向为：

```text
x
y
z
```

例如：

```json
"periodic_axes": ["x", "y", "z"]
```

表示左右、前后、上下三组面都生成循环颗粒边界。

### 输出模式

```json
"output_mode": "both"
```

可选值：

```text
particles
fluid
both
```

含义：

- `particles`：只导出颗粒 STL 和颗粒 CSV。
- `fluid`：只导出颗粒 CSV 和流体域 STL。
- `both`：同时导出颗粒 STL 和流体域 STL。

### 输出文件夹

```json
"output_dir": "E:/cyclic_particle_outputs"
```

每次运行会在该目录下新建一个以 `model_name` 命名的 case 文件夹。

### 粒径分布

```json
"radius_bins": [
  {
    "name": "fine",
    "r_min": 0.2125,
    "r_max": 0.24,
    "volume_fraction": 0.25
  },
  {
    "name": "medium",
    "r_min": 0.24,
    "r_max": 0.275,
    "volume_fraction": 0.45
  },
  {
    "name": "coarse",
    "r_min": 0.275,
    "r_max": 0.30,
    "volume_fraction": 0.30
  }
]
```

规则：

- 最少 1 组，最多 5 组。
- `r_min` 和 `r_max` 必须大于 0。
- `r_min` 必须小于 `r_max`。
- 所有 `volume_fraction` 之和必须等于 `1.0`。

### 流体域表面参数

```json
"fluid_surface": {
  "enabled": true,
  "method": "cp4a_smooth",
  "radius_shrink": 0.002,
  "grid_spacing": 0.025,
  "smooth_sigma_cells": 2.2,
  "smooth_clip_distance": 0.150,
  "level_offset": -0.008,
  "anti_spike_sigma_cells": 0.0,
  "max_normal_angle_degrees": 80.0,
  "mesh_smooth_iterations": 0,
  "mesh_smooth_pass_band": 0.08,
  "robust_open_cells": 1,
  "robust_close_cells": 1,
  "robust_min_component_voxels": 800,
  "robust_keep_largest_component": true,
  "robust_sdf_smooth_sigma_cells": 0.65
}
```

常用调节建议：

- `method` 推荐使用 `robust_v2`；它会在 STL contour 前清理体素流体域，减少孤立流体碎片和薄片桥接。
- `robust_open_cells` 用于去除细长、扁平的流体桥接；默认 `1`。
- `robust_close_cells` 用于填补很小的裂缝；默认 `1`。
- `robust_keep_largest_component` 会删除独立流体碎片，并在判断连通性时考虑周期面连接。
- `robust_sdf_smooth_sigma_cells` 用于平滑重建后的 signed-distance 场。
- 想要更光滑：适当增大 `smooth_sigma_cells`。
- 想保留更多颗粒细节：适当减小 `smooth_sigma_cells` 或 `grid_spacing`。
- 想让流体域和颗粒之间略微留出间隙：增大 `radius_shrink`。
- 想降低 STL 面片数量：增大 `grid_spacing`。

- 想减少尖锐、扁平、针状的局部结构：增大 `anti_spike_sigma_cells`，例如从 `0.8` 调到 `1.0` 或 `1.2`。
- `max_normal_angle_degrees` 用于统计相邻 STL 面片法向夹角，默认 `80` 度。
- `mesh_smooth_iterations` 和 `mesh_smooth_pass_band` 会尝试后处理平滑；只有不破坏水密性且不增加锐边数量时才会被接受。
目前设计原则是：优先保证流体域光滑、边界面分类清楚、周期面几何对应；孔隙率精确性排在其后。

### ParaView 路径

```json
"paraview": {
  "pvpython_path": "D:/ParaView 6.1.0/bin/pvpython.exe"
}
```

流体域 STL 导出需要使用 ParaView 自带的 `pvpython`，因为该步骤依赖 VTK、NumPy 和 SciPy。

### PFC 路径

```json
"pfc": {
  "gui_path": "D:/PFC/exe64/pfc3d600_gui.exe"
}
```

配置窗口中的 `Save and Run PFC` 按钮会使用该路径打开 PFC GUI。若 PFC 已经打开，插件会直接连接当前 PFC 窗口并发送：

```text
program call '<插件目录>/pfc/run_plugin.dat'
```

## 4. 输出文件结构

插件输出结构为：

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

说明：

- `config_used.json`：本次运行实际使用的配置。
- `run_log.txt`：运行日志，包括最终孔隙率、颗粒数量、去除的悬浮颗粒数量等。
- `geometry/particles.csv`：最终颗粒参数，是颗粒 STL 和流体 STL 的共同几何来源。
- `particles/particles.stl`：颗粒模型 STL。
- `fluid/fluid_fluent.stl`：适合 Fluent Meshing 使用的平滑流体域 STL。
- `fluid/fluid_surface_report.txt`：流体域导出报告。

## 5. 流体 STL 的面分类

流体域 STL 会保留 7 个 surface zone：

```text
particle_walls
x_min
x_max
y_min
y_max
z_min
z_max
```

对于写在 `periodic_axes` 中的周期方向，流体域导出器会在 contour 之前同步相对两侧边界附近的一小段 level-set 网格。边界面仍然和 `particle_walls` 来自同一个 VTK 闭合曲面，因此流体域 STL 会保持水密闭合，内部流体表面会和外部边界面连接起来。

其中：

- `particle_walls`：颗粒表面，也就是流体与固体颗粒接触的内壁面。
- `x_min` / `x_max`：左右边界。
- `y_min` / `y_max`：前后边界。
- `z_min` / `z_max`：上下边界。

这些分类在 Fluent Meshing 中非常重要，可以方便后续设置 wall、inlet、outlet 或 cyclic 边界。

## 6. ParaView 安装

如果没有安装 ParaView，可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\tools\install_paraview.ps1
```

默认安装到：

```text
D:\ParaView 6.1.0
```

如果想指定安装位置：

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\tools\install_paraview.ps1 -InstallDir "D:\ParaView 6.1.0"
```

安装完成后，确认配置文件中路径正确：

```json
"paraview": {
  "pvpython_path": "D:/ParaView 6.1.0/bin/pvpython.exe"
}
```

## 7. 推荐测试

第一次使用时建议按以下顺序测试：

1. 使用默认 `3 x 3 x 6 mm`、孔隙率 `0.40`、`output_mode = "particles"`。
2. 检查 `geometry/particles.csv` 和 `particles/particles.stl` 是否正常生成。
3. 设置 `output_mode = "fluid"`，测试流体域 STL。
4. 设置 `output_mode = "both"`，测试完整流程。
5. 分别测试 1 级粒径分布和 5 级粒径分布。

## 8. 自动运行与错误监控

如果需要自动发送 PFC 命令并持续读取 Console 错误反馈，可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File cyclic_particle_plugin\tools\run_and_watch_pfc.ps1
```

该脚本会：

- 自动启动或连接 PFC GUI。
- 发送 `program call '<插件目录>/pfc/run_plugin.dat'`。
- 周期性读取 PFC Console 输出。
- 周期性读取当前 case 的 `run_log.txt`。
- 检测到 `Python error`、`Traceback` 或 `ERROR:` 时停止并打印错误上下文。

当模型很大或粒径很小时，生成前驱颗粒可能需要较长时间。此时优先查看 `run_log.txt` 中的 `pack progress`，确认颗粒生成仍在推进。

## 9. 常见问题

### 配置校验失败

优先检查：

- `radius_bins` 是否超过 5 组。
- `r_min` 是否小于 `r_max`。
- 所有 `volume_fraction` 是否加起来等于 `1.0`。
- `output_mode` 是否为 `particles`、`fluid` 或 `both`。
- `output_dir` 是否为空或不可写。

### 流体域导出失败

优先检查：

- `paraview.pvpython_path` 是否指向真实存在的 `pvpython.exe`。
- 是否已经安装 ParaView。
- `geometry/particles.csv` 是否已经生成。

### STL 面片太多

可以适当增大：

```json
"grid_spacing": 0.03
```

或继续增大到：

```json
"grid_spacing": 0.04
```

但 `grid_spacing` 越大，几何细节越少。

### 流体域不够光滑

可以适当增大：

```json
"smooth_sigma_cells": 2.6
```

或：

```json
"smooth_sigma_cells": 3.0
```

同时注意，过度平滑会牺牲部分孔隙结构细节。

## 10. 当前版本假设

- 目标平台为 Windows。
- PFC 版本为 PFC3D 6.x。
- 默认单位固定为 `mm`。
- 流体域 STL 使用 cyclicparticle4.0 的强平滑 level-set 方法。
- 流体域建模中，光滑性和周期面对应优先于孔隙率的绝对精确。
- 插件是独立文件夹，不依赖用户直接修改 `projects/cyclicparticle1-4`。
