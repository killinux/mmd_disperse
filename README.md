# mmd_disperse

Blender 插件：用几何节点给 MMD 模型做「纳米战衣」式变身／换装。

技术来自 B 站视频 [【中文配音】一秒换装？用blender几何节点制作蜘蛛侠变身动画](https://www.bilibili.com/video/BV1Yd4y1X7eR/)
（李先生的元宇宙 配音，原作 Hell FX Learn，YouTube `-nAK7OidJFo`）。插件把视频里手搭的节点树用 Python 自动生成，并针对 MMD 模型做了适配。

## 视频步骤 → 插件实现

| 视频里的做法 | 插件里的对应 |
| --- | --- |
| 球形空物体当遮罩，`Object Info` 取位置和缩放 | `MMD Disperse Mask` 空物体，缩放 = 显现半径，自动打关键帧 |
| `Position → Distance → Compare(大于) → Delete Geometry`（0 保留 / 1 删除） | 节点组 `MMDDisperse Target`：删除球外的新服装 |
| 「Displacing Edge」：噪波纹理 + 混合 RGB 扭曲球形边界 | 节点组 `MMDDisperse Field`：噪波扰动距离场 |
| `Map Range` 做边缘梯度，乘 `Normal` 后接 `Set Position` | 「边缘外推」：边缘沿法线鼓起 |
| 第二层：两个遮罩求出边缘带 → `Triangulate` → `Dual Mesh`（六边形）→ `Mesh to Curve` → `Curve to Mesh`（`Curve Circle` 截面） | 「线框层」，和战衣在同一个修改器里用 `Join Geometry` 合并 |
| `Set Curve Radius` 用梯度控制线粗 | 线在边界处最粗，向两侧变细 |
| 输出属性 `gradient`，材质里用 `Attribute` 节点做发光 | 属性 `disperse_edge` → 线框材质 + 新服装边缘发光 |
| 原模型：`Less Than or Equal` + `Set Position(-Normal)` 收缩，再删除内部 | 节点组 `MMDDisperse Base`（旧服装处理） |
| 头部另外处理（形态键缩小塞进头盔） | 「保留共用部分」：按材质名锁定脸、头发等，始终用旧模型的 |

## 针对 MMD 的改进

- 自动识别 mmd_tools 模型（根空物体 / 骨架 / 网格都能选），跳过刚体和关节。
- 新服装绑定到旧模型骨架，两套模型跟着同一套动作走（骨骼名对不上时自动跳过并警告）。
- 默认在静止姿态（`rest_position`）里测距离，跳舞时变身波纹贴在身体上，不会因为手脚进出球体而闪烁。
- 按模型身高自动换算所有尺寸（MMD 模型常常有 20 个单位高）。
- 新服装边缘发光注入到原有材质（乘贴图 alpha，镂空处不发光）；线框不投射阴影。
- 一键 Bloom：EEVEE 4.2+ 没有内置辉光，插件在合成器里加 Glare 节点（兼容 5.x 的新合成器）。
- 一键移除，修改器、骨架绑定、材质、属性、模型位置全部还原。
- 效果本身只有几何节点、关键帧和材质，保存后的 .blend 不装插件也能渲染。

## 安装

支持 Blender 3.6 及以上，已在 3.6.15、4.5.10、5.1.2 上测试。两种安装包（zip 不进 git）：

- **Blender 4.2 及以上**：扩展包 `dist/mmd_disperse-1.0.0.zip`，
  用 `blender --command extension build --source-dir mmd_disperse --output-dir dist` 生成。
  安装：编辑 > 偏好设置 > 获取扩展 > 右上角下拉 > 从磁盘安装。
- **Blender 3.6 ~ 4.1**：传统插件包 `dist/mmd_disperse-1.0.0-legacy.zip`（zip 里是 `mmd_disperse/` 文件夹），
  用 `python -c "import shutil; shutil.make_archive('dist/mmd_disperse-1.0.0-legacy', 'zip', '.', 'mmd_disperse')"` 生成。
  安装：编辑 > 偏好设置 > 插件 > 安装，选这个 zip 后勾选启用。

## 使用

一步步的教程见 [docs/tutorial.md](docs/tutorial.md)，下面是简要步骤。

3D 视图按 `N`，打开「MMD Disperse」标签页：

1. **旧服装**：变身前的模型；**新服装**：变身后的模型。吸管按钮可以直接用当前选中的物体。
   旧服装可以留空，那样新服装会从无到有地「长」出来。
2. **起点**：骨骼（默认自动选「上半身2」）、3D 游标或模型中心。**测量空间**推荐用「静止姿态」。
3. 设置开始帧、结束帧和方向（穿上 / 脱下）。
4. 点 **生成变身效果**，拖动时间轴预览。
5. 下面的参数改了立即生效：
   - 边缘：噪波缩放 / 细节 / 强度、边缘渐变宽度、边缘外推、边缘发光
   - 线框层：六边形开关、边缘前后范围、线粗、抬升、颜色、发光强度、添加辉光
   - 旧服装处理：向内收缩、边缘后删除距离、保留共用部分（材质名通配符，用 `;` 分隔，改完需重新生成）
6. 点垃圾桶按钮移除效果并还原模型。

线框层是最重的部分：边界扫过高面数区域时，单帧求值约 0.9 秒（4.5）；3.6 的几何节点更慢，测试里每帧 1.6～2.6 秒
（同时也在算两套模型的刚体物理）。在视口里调动画时可以先关掉线框层，渲染前再打开。

Blender 3.6 的区别：辉光用 EEVEE 自带的泛光（Bloom），线框用材质的「阴影模式：无」不投阴影；4.2 以后用合成器 Glare 节点。

## 高清演示渲染

`demo/render_hd.py` 把模型的 MMD 卡通材质换成 PBR 材质（Principled BSDF），用上模型自带、但 PMX 材质用不到的
法线 / 粗糙度 / 金属度贴图：皮肤加次表面散射，乳胶战衣用光泽 + 清漆，头发用带 alpha 的 PNG。
再加上工作室 HDRI 反射、主光 + 青色轮廓光、反光地面和缓慢环绕的镜头，渲染 1080×1920、200 帧（第 10～185 帧变身）。

```bash
blender -b --factory-startup "$D/Tifa Gantz 18 V2.blend" --python demo/render_hd.py -- \
  --target-blend "$D/Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2" \
  --out test_output/demo_hd/frames --anim 1:200 --save test_output/demo_hd/tifa_suitup_hd.blend
```

材质的对应关系是按贴图文件名猜的（`xxx_tex` → `xxx_rough` / `xxx_met`，球面贴图槽里放的是法线贴图），只针对这个模型调过。

## 测试（Tifa Gantz 18）

测试场景：`Tifa Gantz 18 V2.blend`（镂空款，旧服装）→ 追加 `Tifa Gantz 18 V1.blend`（全包款，新服装）。
两个模型骨架相同（342 根骨骼），脸、头发、眼睛的网格完全一致，所以把脸、头发等设为共用部分。

```bash
D="E:/Downloads/tifa_good/Tifa Gantz 18"
# 功能测试：生成 / 重建 / 实时同步 / 脱下 / 只有新服装 / 动画姿态 / 辉光 / 移除还原 / 面板绘制
blender -b --factory-startup "$D/Tifa Gantz 18 V2.blend" --python tests/test_api.py -- \
  --target-blend "$D/Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2"
# 渲染测试（--motion 给旧模型骨架加一段摆动动画；--anim 1:100:1 输出序列帧；--save 保存演示场景）
blender -b --factory-startup "$D/Tifa Gantz 18 V2.blend" --python tests/test_tifa.py -- \
  --target-blend "$D/Tifa Gantz 18 V1.blend" --target-root "Tifa Gantz 18 V1" --base-root "Tifa Gantz 18 V2" \
  --lock --bloom --frames 1,25,50,75,100 --close-frames 20,25 --out test_output/run
# Blender 3.6：用 mmd_tools 直接导入 PMX（--toon-dir 指向 MMD 共享 toon 贴图目录，
# 只在 --factory-startup 下 mmd_tools 找不到 toon01.bmp 时需要）
blender -b --factory-startup --python tests/test_api.py -- --pmx "$D/Tifa Gantz 18 V2.pmx" "$D/Tifa Gantz 18 V1.pmx"
```

结果：`test_api.py` 在 Blender 3.6.15（导入 PMX）、4.5.10、5.1.2 上全部通过；两种安装包在各自版本的独立配置目录里都能安装、启用。
渲染结果（`test_output/`，不进 git）：从胸口开始，发光的六边形线框带着全包战衣扫过躯干、手臂、腿，到第 75 帧左右覆盖到脚。
