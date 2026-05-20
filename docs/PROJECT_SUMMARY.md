# PFC3D 颗粒堆积模型阶段总结

记录日期：2026-05-20

## 当前目标

本阶段目标是在 PFC3D 6.0 中建立一个 `3 mm x 3 mm x 6 mm` 的长方体颗粒堆积模型：

- 坐标范围：`x,y in [-1.5, 1.5]`，`z in [-3.0, 3.0]`。
- 六个边界面均用 wall 建模。
- 顶面命名/分组为 `inlet`，底面为 `outlet`。
- 四个侧面分别为 `wall_left`、`wall_right`、`wall_front`、`wall_back`。
- 全局孔隙率采用几何孔隙率验收：

```text
porosity = 1 - sum(ball volumes) / box volume
```

## 建模思路更新

上一阶段采用的是“贴壁镜像对称 + 内部随机”方案：靠近四个侧壁的颗粒关于 `x=0`、`y=0` 成四球镜像组。这个方案能让侧壁附近形态对称，但它不是严格意义上的循环颗粒。

当前阶段改为“周期切面对齐”方案：

- 通过 `PERIODIC_AXES` 选择周期方向，可设置为 `x`、`y`、`z` 的任意组合。
- 对每个启用方向，在两个相对切面附近生成成对颗粒。
- 成对颗粒具有相同半径、相同横向坐标，以及相同的切面内缩距离。
- 周期颗粒的切面内缩距离小于颗粒半径，因此颗粒会穿过边界面。
- STL 导出时会按盒体边界裁掉盒外部分，并给被切开的颗粒补圆形切面 cap，便于直接比较相对切面是否一致。
- 内部颗粒仍然随机分布，并与周期面对颗粒自然接触。
- 随机颗粒与启用的周期切面保持小间距，避免切面形态被非成对随机颗粒破坏。

默认配置现在是：

```python
PERIODIC_AXES = ("x", "y", "z")
```

也就是说，上下、前后、左右三组相对切面都启用周期颗粒。

周期切开深度由以下参数控制：

```python
PERIODIC_CUT_OFFSET_FRACTION_MIN = 0.25
PERIODIC_CUT_OFFSET_FRACTION_MAX = 0.75
```

这表示周期颗粒球心到切面的距离为 `0.25r` 到 `0.75r`，所以每个周期颗粒都会被切面截开。

## 当前目录结构

- `run_cyclic_pack.dat`
  主 PFC 脚本。负责新建模型、生成六个 wall、调用颗粒生成器、松弛、检查、保存 `.sav`，并导出 STL。

- `cyclic_pack.py`
  颗粒生成器。顶部集中放置可调参数，包括目标孔隙率、粒径 bins、随机种子、周期方向、周期带厚度、周期颗粒固体体积分数等。

- `cyclic_pack_project.py`
  松弛后投影脚本。将周期颗粒重新投影为严格的相对切面对；随机颗粒限制在完整盒体范围内。

- `cyclic_pack_check.py`
  验收脚本。检查颗粒边界、随机颗粒周期切面安全距离、周期颗粒配对关系和几何孔隙率。

- `export_pack_stl.py`
  STL 导出脚本。默认将当前 PFC 模型中的颗粒裁切到盒体内部，并导出带切面 cap 的 ASCII STL。默认不导出 wall 面，避免遮挡颗粒切面。

- `docs/`
  文档目录，包括本总结和运行说明。

- `tools/`
  PFC Console/GUI 辅助脚本。

- `outputs/`
  PFC 保存状态和 STL 等生成产物。

## 运行方式

在 PFC3D Console 中运行：

```text
program call 'E:/codexfile/pfc cyclic particle/run_cyclic_pack.dat'
```

Codex 侧可通过桥接脚本执行并读取 PFC Console 输出：

```powershell
.\tools\pfc_console_bridge.ps1 -Command "program call 'E:/codexfile/pfc cyclic particle/run_cyclic_pack.dat'" -WaitSeconds 70 -TailChars 12000
```

## 输出文件

PFC 保存状态：

```text
E:\codexfile\pfc cyclic particle\outputs\cyclic_pack_porosity_0p40.sav
```

STL 导出文件：

```text
E:\codexfile\pfc cyclic particle\outputs\stl\cyclic-particles-1.stl
```

最近一次 PFC Console 验收结果：

```text
=== Cyclic-face pack check passed ===
ball count:      477
random balls:    285
periodic x:     64 balls (32 face pairs)
periodic y:     62 balls (31 face pairs)
periodic z:     66 balls (33 face pairs)
solid volume:    32.41521842 mm^3
porosity:        0.39971818
```

对应 STL 导出结果：

```text
balls:      477
walls:      0
triangles:  256644
```

## 历史保存点

仓库中已有旧方案提交：

```text
add266b Save wall-symmetric random-interior PFC pack
94c41d5 Add STL export for PFC pack
```

这些提交保留了上一阶段的镜面对称实现，当前工作树已经开始切换到周期切面对齐方案。
