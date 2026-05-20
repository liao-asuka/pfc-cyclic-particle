# PFC3D 颗粒堆积模型阶段总结

记录日期：2026-05-20

## 目标

本阶段目标是在 PFC3D 6.0 中建立一个 `3 mm x 3 mm x 6 mm` 的长方体颗粒堆积模型：

- 坐标范围：`x,y in [-1.5, 1.5]`，`z in [-3.0, 3.0]`。
- 六个边界面均用 wall 建模。
- 顶面命名/分组为 `inlet`，底面为 `outlet`。
- 四个侧面分别为 `wall_left`、`wall_right`、`wall_front`、`wall_back`。
- 颗粒粒径分布、目标孔隙率、随机种子等参数放在脚本顶部，便于后续修改。
- 全局孔隙率采用几何孔隙率验收：

```text
porosity = 1 - sum(ball volumes) / box volume
```

## 关键建模思路

最初方案是整体镜像对称，随后改成“中心内层随机、外层镜像”。实际观察后发现，硬性内外分区会让内层和外层之间产生人为界面，容易形成非物理优势通道。

最终采用当前方案：

- 只有靠近四个侧壁的颗粒属于 `wall` 组，并保持关于 `x=0`、`y=0` 的双镜面对称。
- 内部颗粒属于 `random` 组，在整个盒体内部随机分布。
- `random` 颗粒不再被限制在中心 `1.5 x 1.5 x 6 mm` 范围内。
- `random` 颗粒允许与 `wall` 颗粒自然接触，从而消除人为内外层界面。
- `random` 颗粒只保留一个很小的侧壁安全距离，确保真正贴近侧壁的颗粒来自镜像对称的 `wall` 组。

## 主要文件

- `run_symmetric_pack.dat`
  主 PFC 脚本。负责新建模型、生成六个 wall、调用颗粒生成器、松弛、检查、保存 `.sav`，并导出 STL。

- `symmetric_pack.py`
  颗粒生成器。顶部集中放置可调参数，包括目标孔隙率、粒径 bins、随机种子、贴壁带厚度、贴壁颗粒固体体积分数、随机颗粒侧壁安全距离等。

- `symmetric_pack_project.py`
  松弛后投影脚本。将 `wall` 颗粒重新投影为严格镜面对称；`random` 颗粒只限制在完整盒体范围内并保持侧壁安全距离。

- `symmetric_pack_check.py`
  验收脚本。检查颗粒边界、随机颗粒侧壁安全距离、`wall` 颗粒镜像对应关系和几何孔隙率。

- `export_pack_stl.py`
  STL 导出脚本。将当前 PFC 模型中的颗粒和六个壁面导出为一个 ASCII STL 文件。

- `pfc_console_bridge.ps1`
  Codex 到 PFC GUI Console 的桥接脚本。通过 Windows UIAutomation 向 PFC Console 写入命令并读取输出，方便直接识别 PFC 报错。

- `PFC_AUTOMATION.md`
  运行方式和参数修改说明。

## 当前默认参数与结果

当前默认目标孔隙率：

```text
TARGET_POROSITY = 0.40
```

PFC Console 实测验收结果：

```text
=== Wall-symmetric pack check passed ===
ball count:      477
random balls:    285
wall balls:      192 (48 mirror groups)
solid volume:    32.37729634 mm^3
porosity:        0.40042044
```

孔隙率误差在默认容差 `1e-3` 内。

## 输出文件

PFC 保存状态：

```text
E:\codexfile\pfc cyclic particle\symmetric_pack_porosity_0p40.sav
```

STL 导出文件：

```text
E:\codexfile\pfc cyclic particle\STLfile\cyc-particles-1.stl
```

STL 导出内容包括：

- 477 个球体颗粒。
- 6 个矩形 wall 面。
- ASCII STL，总三角面数为 `251868`。

## PFC Console 运行方式

在 PFC3D Console 中运行：

```text
program call 'E:/codexfile/pfc cyclic particle/run_symmetric_pack.dat'
```

Codex 侧可通过桥接脚本执行并读取 PFC Console 输出：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\pfc_console_bridge.ps1 -Command "program call 'E:/codexfile/pfc cyclic particle/run_symmetric_pack.dat'" -WaitSeconds 70 -TailChars 12000
```

## Git 保存点

当前仓库已有两个关键提交：

```text
add266b Save wall-symmetric random-interior PFC pack
94c41d5 Add STL export for PFC pack
```

其中：

- `add266b` 保存了“贴壁镜像对称 + 内部随机”的稳定颗粒模型。
- `94c41d5` 增加了颗粒和壁面 STL 导出功能。

## 后续可继续扩展

后续可以在当前基础上继续做：

- 将 inlet/outlet 从静态 wall 改成可删除、可移动或可施加边界条件的对象。
- 按实验级配调整 `RADIUS_BINS`。
- 加入循环加载、渗流或颗粒破碎等工况。
- 分别导出颗粒 STL 和壁面 STL。
- 增加孔径、连通性或优势通道的后处理分析。
