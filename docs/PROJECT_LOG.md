# 项目日志

本日志用于按日期记录 `PFC cyclic particle` 项目的主要工作内容、关键结果和后续注意事项。它偏向给人阅读，详细参数和运行命令仍以 `docs/PROJECT_SUMMARY.md` 与 `docs/PFC_AUTOMATION.md` 为准。

## 2026-05-13

### 建立初始颗粒堆积模型

- 保存了第一版 PFC3D 随机颗粒堆积模型。
- 当时的思路是使用贴壁镜面对称颗粒，让靠近墙面的颗粒在几何上更规整。
- 该版本作为后续方案的历史基线保留在 git 提交中：
  - `add266b Save wall-symmetric random-interior PFC pack`

### 增加颗粒 STL 导出能力

- 添加了将 PFC 当前颗粒模型导出为 STL 的脚本。
- 导出逻辑支持按目标长方体盒子裁切颗粒，并可控制是否导出 wall 面。
- 该阶段的提交为：
  - `94c41d5 Add STL export for PFC pack`

## 2026-05-20

### 从镜面对称转向周期颗粒边界

- 讨论并确认：镜面对称并不等于真正的循环颗粒边界。
- 真正目标是：一个完整颗粒被 RVE 边界切开后，一部分出现在左面，另一部分出现在右面；两侧按周期平移拼合后应恢复为同一个完整颗粒。
- 因此项目方向从“贴壁对称颗粒”改为“周期切面互补颗粒”。

### 建立中间方案 `cyclic_pack`

- 增加了 `run_cyclic_pack.dat`、`cyclic_pack.py`、`cyclic_pack_check.py`、`cyclic_pack_project.py` 等文件。
- 支持 `x`、`y`、`z` 三组相对面按需要启用周期颗粒。
- 增加了检查脚本，用来验证：
  - 颗粒是否在边界范围内。
  - 周期颗粒是否成对出现。
  - 几何孔隙率是否接近目标值。
- 该阶段提交为：
  - `ab1d3fe Add cyclic cut-face particle packing`

### 增加项目说明文档

- 新增项目总结文档，开始系统记录目标、目录结构、运行方式、输出文件和历史版本。
- 对应提交为：
  - `8028457 Add project summary document`

## 2026-05-21

### 确认中间方案不足

- 发现 `cyclic_pack` 虽然能让两侧截面看起来相互对应，但本质上仍像是在目标盒子内直接“硬放置”周期颗粒。
- 用户提出新的判断：直接在一个 wall 范围内生成颗粒很难得到真实周期颗粒结构。
- 于是确定新方案：先在更大的区域中生成自然随机堆积，再从中截取一个代表性体积单元 RVE，并补充周期镜像颗粒。

### 启动新主线 `cyclicparticle2.0`

- 新增 `run_cyclicparticle2.dat` 作为主入口。
- 新增 `cyclicparticle2.py` 生成大区域自然颗粒堆积。
- 大区域范围：
  - `x,y in [-4.5, 4.5]`
  - `z in [-9.0, 9.0]`
- 目标 RVE 范围：
  - `x,y in [-1.5, 1.5]`
  - `z in [-3.0, 3.0]`
- 新增 RVE 提取脚本：
  - `extract_cyclicparticle2_rve.py`
  - `extract_cyclicparticle2_rve_trimmed.py`
- 新增 RVE 检查脚本：
  - `check_cyclicparticle2_rve.py`

### 修正 RVE 颗粒过密问题

- 曾出现一个面上截面颗粒过多、视觉密度过高的问题。
- 原因是提取 RVE 时把所有与 RVE 相交的 halo 颗粒都当成 primary 颗粒，导致实际固体体积偏大。
- 修正后只保留“球心位于所选 RVE 窗口内”的 primary 颗粒；如果 primary 颗粒跨越边界，再通过周期平移生成对应 image。
- 最新接受的 RVE 结果：

```text
rve offset:         (0.750, 0.250, 2.000)
rve balls/images:   680
primary images:     473
periodic images:    207
unique source ids:  473
trimmed sources:    3
primary porosity:   0.39998525
```

### 修正颗粒 STL 导出

- 发现 STL 中出现多余的墙体或裁切内容。
- 将 `export_pack_stl.py` 修正为默认不导出 wall，只导出最终颗粒模型。
- 修正切面 cap 没有被其它盒子平面继续裁切的问题，避免圆盘或面片越界。
- 新增 `export_cyclicparticle2_stl.py`，专门导出 `cyclicparticle2.0` 的最终 RVE 颗粒模型。
- 当前颗粒模型 STL：

```text
outputs/stl/cyclicparticle2-rve.stl
```

### 增加流体域导出

- 根据“外部长方体减去内部颗粒模型”的需求，新增 `export_cyclicparticle2_fluid_domain.py`。
- 第一版采用体素化布尔减法，输出：

```text
outputs/fluid_stl/cyclicparticle2/cp2_voxel_dx0p05.stl
```

- 该版本可以表达流体域，但表面有 `0.05 mm` 的阶梯近似，不适合直接作为高质量 Fluent Meshing 几何。

### 将流体域 STL 与颗粒 STL 分目录存放

- 颗粒模型 STL 保持在：

```text
outputs/stl/
```

- 流体域 STL 独立放在：

```text
outputs/fluid_stl/
```

### 改进为光滑流体域 STL

- 为了让 Fluent Meshing 更容易划分网格，将流体域导出从体素阶梯面改为光滑解析面。
- 新版本使用：
  - 颗粒内壁：球面三角片段。
  - 外部长方体面：带颗粒圆形开孔的三角剖分面。
- 当前推荐流体域 STL：

```text
outputs/fluid_stl/cyclicparticle2/cp2_smooth.stl
```

## 2026-05-28 补充：cyclicparticle3.0 去除悬浮颗粒

- 问题：检查发现上一版 3.0 中有少量 primary 颗粒完全不与其它颗粒接触，在真实堆积中不合理。
- 处理：在 3.0 抽取脚本和检查脚本中加入周期最小镜像距离下的接触图；抽取时只保留最大接触连通分量，再重新生成周期镜像。
- 结果：当前 connected RVE 已无孤立颗粒，同时保持孔隙率和边界颗粒 45%/55% 切割约束。

```text
rve offset:         (0.750, 1.750, 4.000)
rve balls/images:   627
primary images:     469
periodic images:    158
unique source ids:  469
balanced boundary:  158
floating removed:   8
contact components: 1
connected primary:  469
cut volume range:   0.450000 - 0.550000
final solid:        32.40705127 mm3
final porosity:     0.39986942
```

## 2026-05-28 补充：直接导出 OpenFOAM 周期流体网格

- 为避免 SpaceClaim 中 STL 自动修复、转实体和布尔剪切失败，新增直接从颗粒参数生成 OpenFOAM `polyMesh` 的流程。
- 新增精确颗粒参数导出：

```text
outputs/geometry/cyclicparticle3_particles.csv
```

- 新增 OpenFOAM case 输出：

```text
outputs/openfoam/cyclicparticle3_cartesian/
```

- 当前第一版采用 `60 x 60 x 120` 笛卡尔流体网格，优先保证左右和前后周期面拓扑严格成对。

```text
cell size:         0.05000000 0.05000000 0.05000000 mm
fluid cells:       190936
fluid volume frac: 0.44198148
cyclic_x_min/max:  2776 / 2776
cyclic_y_min/max:  3123 / 3123
particle_walls:    173683
```

- 注意：这是 topology-first 的网格，颗粒壁面是阶梯近似；后续可以通过提高 `NX/NY/NZ` 或基于 CSV 做 level-set/smooth 网格继续提高颗粒壁面精度。

## 2026-05-29：增加浏览器网格预览

- 新增 `tools/openfoam_polyMesh_to_html.js`，可以把 OpenFOAM `polyMesh` 边界面转换为自带 WebGL 的 HTML 预览。
- 当前预览文件：

```text
outputs/openfoam/cyclicparticle3_cartesian/mesh_preview.html
```

- 生成命令：

```powershell
node tools\openfoam_polyMesh_to_html.js outputs\openfoam\cyclicparticle3_cartesian 60000
```

- 当前预览包含全部周期面和上下边界面，颗粒壁面抽样显示 `57895 / 173683` 个面，用于在未安装 ParaView 的 Windows 环境中快速检查网格形状和周期 patch 位置。

## 2026-05-29：创建 cyclicparticle4.0 方案 A

- 目标：放弃 STL -> SpaceClaim 实体布尔路线，改为直接从颗粒参数生成 Fluent Meshing 可导入的流体域表面几何。
- 先尝试方案 A，方案 B 的 CAD/STEP-BREP 路线留到方案 A 评估后再做。
- 发现逐个导出 shrunken sphere surface 仍然会保留颗粒重叠区域的内部相交面，因此进一步升级为 level-set 方法。
- level-set 方法定义：

```text
fluid = inside RVE box AND outside union(shrunken particles)
```

- 当前推荐输出：

```text
outputs/fluid_stl/cyclicparticle4/recommended/cp4A_fluent.stl
outputs/geometry/cyclicparticle4_particles_shrink0p002.csv
```

- 当前参数和结果：

```text
periodic axes:     x,y
radius shrink:     0.00200000 mm
grid spacing:      0.02500000 mm
smooth sigma:      2.2000 cells
smooth clip:       0.15000000 mm
level offset:      -0.00800000 mm
grid dimensions:   123 x 123 x 243
balls/images:      599
vtk points:        635030
vtk triangles:     1272104
vertex bounds:     x [-1.5, 1.5], y [-1.5, 1.5], z [-3.0, 3.0]
```

- 说明：这是 4.0-A 的第一个 Fluent Meshing 候选几何。它通过固体并集去除了相交颗粒内部多余面，但表面仍是 level-set 三角面近似；如果 Fluent Meshing 表现仍不理想，再进入方案 B。
- 根据 Fluent Meshing 视觉检查反馈，进一步加入周期一致的隐式场强平滑，优先去除尖锐连接、针状点和薄片特征。当前保留面片分类 `particle_walls/x_min/x_max/y_min/y_max/z_min/z_max`。

## 2026-05-29：整理 fluid_stl 输出目录

- 将流体域 STL 按版本和用途分组，避免所有历史文件堆在同一层目录。
- 当前分类：

```text
outputs/fluid_stl/cyclicparticle2/
outputs/fluid_stl/cyclicparticle4/recommended/
outputs/fluid_stl/cyclicparticle4/variants/
```

- 当前推荐 Fluent Meshing 输入改为短文件名：

```text
outputs/fluid_stl/cyclicparticle4/recommended/cp4A_fluent.stl
```

- 详细参数和命名规则记录在：

```text
outputs/fluid_stl/README.md
```

- 最新检查结果：

```text
balls/images:     680
sphere segments:  lat 24 lon 48
circle segments:  72
boundary holes:   442
sphere triangles: 1081804
box triangles:    20082
total triangles:  1101886
vertex bounds:    x [-1.5, 1.5], y [-1.5, 1.5], z [-3.0, 3.0]
```

## 2026-05-24

### 增加项目日志

- 新增本文档 `docs/PROJECT_LOG.md`。
- 目的：
  - 让项目进展可以按日期快速回看。
  - 把“为什么改方案”与“每天产出了什么”分开记录。
  - 避免 `PROJECT_SUMMARY.md` 越来越像运行参数堆叠，读起来不够顺。

### 分离 cyclicparticle 第一版与 cyclicparticle2.0

- 将第一版周期颗粒方案移动到：

```text
projects/cyclicparticle1/
```

- 将当前主线 `cyclicparticle2.0` 移动到：

```text
projects/cyclicparticle2/
```

- 两个版本各自保留独立的 `run_*.dat`、生成脚本、检查脚本和 STL 导出脚本。
- `tools/run_pfc_console.ps1` 与 `tools/send_to_pfc_gui.ps1` 的默认入口已改为：

```text
projects/cyclicparticle2/run_cyclicparticle2.dat
```

- `.dat` 文件中的 `program call` 已改为显式路径，避免从仓库根目录运行时找不到移动后的脚本。

## 2026-05-28

### 创建 cyclicparticle3.0

- 新增当前主线目录：

```text
projects/cyclicparticle3/
```

- 3.0 继续使用 2.0 的“大区域自然堆积 -> 截取 RVE -> 生成周期镜像”框架。
- 发现如果只删除小截片边界颗粒，最终 RVE 会明显变疏，孔隙率约为 `0.466958`，无法满足目标 `0.40`。
- 因此 3.0 改为在选定 primary 颗粒并匹配孔隙率后，对跨周期边界颗粒做法向投影：
  - 跨边界颗粒只保留一个周期切割方向。
  - 靠近棱边导致多方向切割的颗粒会被推回其它方向的盒内。
  - 保留的周期切割方向被投影到 `45% / 55%` 的体积分割位置。
- 这样既避免 2.0 中低于 `5%` 的极小碎片，又保持最终实体体积和孔隙率。

### cyclicparticle3.0 验证结果

```text
rve offset:         (0.750, 0.250, 2.000)
rve balls/images:   636
primary images:     473
periodic images:    163
unique source ids:  473
balanced boundary:  163
trimmed sources:    3
cut volume range:   0.450000 - 0.550000
final solid:        32.40079650 mm^3
final porosity:     0.39998525
```

输出文件：

```text
outputs/cyclicparticle3_rve_porosity_0p40.sav
outputs/stl/cyclicparticle3-rve.stl
```

STL 顶点范围检查：

```text
x [-1.5, 1.5], y [-1.5, 1.5], z [-3.0, 3.0]
```

## 当前建议优先使用的文件

- 主流程入口：

```text
projects/cyclicparticle3/run_cyclicparticle3_connected.dat
```

- 最终 RVE 保存文件：

```text
outputs/cyclicparticle3_rve_porosity_0p40.sav
```

- 最终颗粒模型 STL：

```text
outputs/stl/cyclicparticle3-rve.stl
```

- 当前推荐流体域 STL：

```text
outputs/fluid_stl/cyclicparticle2/cp2_smooth.stl
```

## 后续注意事项

- 如果 Fluent Meshing 导入光滑流体域 STL 后提示 `self-intersection`、`non-manifold` 或 surface repair 问题，下一步需要重点检查 DEM 颗粒之间的微小重叠，以及颗粒与边界圆孔之间的拓扑连接。
- 如果需要更高质量网格，可继续提高 `SPHERE_LAT_SEGMENTS`、`SPHERE_LON_SEGMENTS` 和 `CIRCLE_SEGMENTS`，但 STL 文件会明显变大。
- 如果只是检查周期颗粒边界是否互补，应优先查看颗粒 STL；如果要做 CFD 网格，应优先查看 smooth fluid-domain STL。
## 2026-05-30

- Created `cyclic_particle_plugin/` as an independent reusable plugin package.
- Added JSON configuration files under `cyclic_particle_plugin/config/`.
- Added strict config validation for domain size, porosity, output mode, periodic axes, and 1-5 radius bins.
- Added `scripts/run_pipeline.py` as the single PFC-driven pipeline entry.
- Added smooth level-set fluid STL exporter with preserved Fluent surface zones.
- Added PowerShell desktop config editor at `ui/edit_config.ps1`.
- Added PFC entry file at `pfc/run_plugin.dat`.
- Added ParaView install helper at `tools/install_paraview.ps1`.
- Added plugin user guide at `cyclic_particle_plugin/docs/USER_GUIDE.md`.
- Added Chinese plugin user guide at `cyclic_particle_plugin/docs/USER_GUIDE_CN.md`.
- Added double-click Windows launchers: `cyclic_particle_plugin/Start_Config_Editor.vbs` and `cyclic_particle_plugin/Start_Config_Editor.cmd`.
- Improved the Windows config editor with grouped sections, inline help text, PFC GUI path selection, and a `Save and Run PFC` button.
- Added a compiled Windows executable launcher: `cyclic_particle_plugin/CyclicParticlePlugin.exe`.
- Added `cyclic_particle_plugin/tools/run_and_watch_pfc.ps1` for automated PFC launch, Console monitoring, and error capture.
- Added precursor-pack progress logging during particle generation.
