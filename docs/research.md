# 业内变身效果调研

调研时间：2026-10-02。目的：找出纳米战衣以外还有哪些好看的变身方式，看哪些能加进插件。

## 结论

业内的变身效果拆开看，都是四件事的组合：

1. **前沿怎么走**：从哪里开始、沿什么路线推进；
2. **旧衣服怎么退场**：收缩、碎掉、飞走；
3. **新衣服怎么登场**：直接长出、全息先行、零件飞入；
4. **前沿上加什么装饰**：线框、光环、电弧、粒子。

插件现在是「球形扩散 × 收缩删除 × 直接长出 × 六边形线框」。补上两块底层能力，大部分效果都能做成预设：

- **到达时间场**：决定前沿怎么走；
- **碎片运动**：决定旧衣服怎么退场。

两块都能在 Blender 3.6 里实现。

## 一、业内常见的变身方式

### 1. 纳米 / 科技战衣（插件现在做的这类）

- **钢铁侠 Mark 50**（《复仇者联盟3》，特效 Framestore）：
  - 概念设计师 Phil Saunders 的设计：纳米从胸口主反应堆和身上几个副反应堆同时流出。
  - 按人体结构分层：先铺神经和血管状的线路，再长肌肉纹理，最后堆出肌肉块和外骨骼，层与层像波浪一样叠着推进。
- **黑豹**（Method Studios）：纳米粒子从项链里生成，沿身体向下展开。
- **和插件的差距**：只有一个球形起点，没有多起点、沿体表流动和多层叠加。

### 2. 消散 / 碎裂

- **灭霸响指**（Weta）：
  - 身体化成碎屑被风吹走，碰撞体逐帧更新，让风绕着身体打旋。
  - 先散哪里由导演定，比如蜘蛛侠「手先散，脸要留到最后」。
- **《创：战纪》derez**：碎成成千上万个立方体素，像碎玻璃一样散落。
- **《头号玩家》**：角色被击败时爆成金币。
- **二次元和仙侠常见的变体**：化成花瓣、蝴蝶或羽毛散去；燃烧成灰；冰晶长满后碎裂。

### 3. 扫描 / 全息 / 打印

- **全息实体化**（科幻片和游戏，比如《命运2》的传送登场）：先出现发光线框和扫描线，再变成实体。
- **《西部世界》片头**（Elastic）：用 3D 打印的方式逐层打印出骨骼、肌腱和肌肉。
- **假面骑士 Ex-Aid**：角色选择面板从身体穿过去，穿过的地方就变身完成。

### 4. 装甲组装（特摄 / 机甲）

- **假面骑士 Kabuto 的「Cast Off」**：外层厚装甲炸开飞走，露出里面的轻装。
- **假面骑士 Build**：前后两半装甲从身前身后夹合。
- **假面骑士 Zero-One**：机械蝗虫拆成装甲片扣到身上。
- **假面骑士 Decade**：几个全息残影汇聚到身上。

### 5. 有机 / 液体

- **毒液**（DNEG）：触手爬满全身。做法是先做一个能动画的团块绑定，伸出触手，再在上面叠多层特效模拟。
- **T-1000 液态金属**（《终结者2》）。
- **魔形女**（《X战警》）：鳞片像波浪一样翻过来，鳞片两面是不同的材质。Blender 市场上已有几何节点版本（Mystique Scales Effect，支持 3.6–5.2）。

### 6. 动画 / 风格化

- **魔法少女变身**：
  - 身体变成纯色发光的剪影，光带缠绕手脚，变出手套和靴子。
  - 按部位依次换装，周围有闪光粒子，最后定格摆姿势。
  - 《美少女战士 Crystal》第一季的变身用 3DCG 制作，观众反响一般，后来改回了手绘。
- **《蜘蛛侠：平行宇宙》的「故障」**：把画面切成格子，每格用不同相机和不同风格渲染，再拼起来。
- **闪白遮挡**：用一道强光盖住换装的瞬间。动画里最常用，也最省事。

### 同类 Blender 产品

Superhive（原 Blender Market）上的同类产品都是单个物体消散，没有搜到做「两套服装互换 + MMD 骨架绑定」的：

| 产品 | 价格 | 做法 |
| --- | --- | --- |
| Disintegration FXs | $4.9 | 模拟节点，8 种消散，粒子带贴图颜色 |
| Dissolution | | 几何节点，网格散成粒子 |
| Disintegrate Objects | | 几何节点修改器 |

## 二、映射到插件：两块底层能力

### ① 到达时间场：决定前沿怎么走

现在的 Field 节点组用的是「静止姿态里到球心的距离」。

- 这个距离是在静止姿态里量的，所以不会随动作变化。生成时可以用 Python 给每个顶点预先算好「前沿走多远才到这里」，存成顶点属性。
- 节点组读这个属性代替球形距离。遮罩空物体的缩放继续当进度条，关键帧、缓动、实时调参都不用改，播放时几乎不增加计算。

预计算可以支持这些走法：

| 走法 | 效果 | 对应 |
| --- | --- | --- |
| 球形 | 现在这种 | 蜘蛛侠教程 |
| 平面扫描 | 从脚到头或从头到脚 | 扫描、3D 打印 |
| 多起点 | 胸口、两只手腕、两只脚踝同时出发 | 钢铁侠的副反应堆 |
| 沿体表流动 | 从项链或胸口出发，贴着身体表面走，手臂交叉时不会直接跳到手上 | 黑豹 |
| 按部位 | 手脚先，躯干后，脸最后 | 灭霸响指、魔法少女 |

**沿体表的难点**：MMD 模型是很多不相连的零件。PMX 会按 UV 接缝把网格拆开，测试用的 Tifa 一个网格就有 6250 个零件岛，没法直接在网格上求最短路。

**办法**：把两套服装一起体素化，在体素网格上求最短路，再插值回每个顶点。新旧服装在同一个位置拿到的到达时间一致，生成时只算一次。

### ② 碎片运动：决定旧衣服怎么退场

- **做法**：把前沿扫过的面拆开（Split Edges），缩成碎片（Scale Elements）。碎片的位置只取决于「前沿扫过这里多久了」：先弹出，再顺风漂，再加噪波扰动，最后缩小消失。
- **无状态**：随便拖时间轴都对，不需要烘焙，3.6 也能用。如果要「风绕着身体打旋」这种真实感，再加模拟节点（Simulation Zone）做可选项。
  （1.3 里跳舞时让碎片留在原地，没有用模拟节点，而是生成时记录每个顶点脱落那一刻的位置，见下面的「1.3 跟进」；
  1.4 扩展到装甲大块和整个模型的移动，见「1.4 跟进」。）
- **贴图颜色白送**：碎片保留原来的 UV 和材质，颜色天然就是衣服的贴图颜色。别家把「粒子带贴图颜色」当卖点。
- **换成实例**：碎片换成实例，就是花瓣、蝴蝶、立方体素、金币，都是同一套运动。
- **按零件飞**：用 Mesh Island 找零件、用 Accumulate Field 求零件中心，就能做装甲飞入，或者 Kabuto 那种 Cast Off。

### 节点核对

在 3.6.15、4.5.10、5.1.2 里逐个创建节点确认过。

| | 3.6 | 4.5 / 5.1 |
| --- | --- | --- |
| Simulation Zone、Shortest Edge Paths、Edge Paths to Curves | 有 | 有 |
| Split Edges、Scale Elements、Mesh Island、Accumulate Field | 有 | 有 |
| Blur Attribute、Curve Spiral、Points/Mesh to Volume、Sample Nearest Surface | 有 | 有 |
| Repeat / For Each 循环、Bake 节点、Index / Menu Switch、Sort Elements | 没有 | 有 |

所以设计里不用循环，保持 3.6 兼容。

## 三、推荐路线

| # | 效果 | 怎么做 | 工作量 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 到达时间场：平面扫描 / 多起点 / 沿体表 / 按部位 | 底层能力①，做完就有钢铁侠、黑豹那种「流出来」的感觉 | 小～中 | 1.1 已完成（按部位用「只从手脚」出发实现） |
| 2 | 灰飞烟灭、化成花瓣或蝴蝶 | 底层能力②，用于旧服装退场 | 中 | 1.1 已完成 |
| 3 | 全息先行 + 扫描/打印光环 | 前沿前方一段先显示全息材质，切口边界转成曲线发光 | 小 | 1.2 已完成（光环画在材质里，没用曲线） |
| 4 | 装甲飞入 / Cast Off | ②按零件飞的版本 | 中 | 1.2 已完成（零件用 Voronoi 切分，不用网格自带的岛） |
| 5 | 魔法少女预设 | 组合 1–4，再加光剪影材质、螺旋光带、闪光粒子、闪白 | 大 | 1.2 已完成（另加了 7 个一键预设）；闪白在 1.3 做成「收尾闪光」，1.4 加了光扫和合成器全屏闪白 |
| 6 | 故障风切换 | 按横条随机切换新旧服装并错位，合成器里加 RGB 分离，可以卡音乐节拍 | 小 | 1.2 已完成 |

### 1.3 跟进

| 项目 | 做法 | 状态 |
| --- | --- | --- |
| 收尾闪光 | 新服装完整出现后（遮罩半径过了 wave），整身按「快升慢降」的包络发光，同时从全身表面迸出星星；时长按变身时长的比例算 | 已完成 |
| 跳舞时碎片留在原地 | 不用模拟区域：生成时播一遍动画，探针修改器复用 Field 节点组求每个顶点的年龄，变号那一刻（两帧间插值）记下位置，碎片和粒子从那里飞出。拖时间轴仍然随时正确 | 已完成（装甲大块仍跟着身体） |
| 按物体缩放换算尺寸 | 距离类输入除以物体缩放，噪波频率乘缩放，粒子密度乘缩放的平方；缩小一半的模型结果逐顶点一致 | 已完成 |
| 其他模型、真实舞蹈 | Purifier Inase / Reika / Tifa AC / Tifa Remake 跑完整功能测试；回レ！雪月花 VMD 下渲染检查 | 已完成；Tifa AC 新服装多出布料骨骼，改为「复制姿态」跟随 |

### 1.4 跟进

| 项目 | 做法 | 状态 |
| --- | --- | --- |
| 装甲大块留在原地 | 一块装甲在「块内顶点的平均年龄」变正时整块脱落，所以整块要在同一时刻记录。切口上的顶点属于两块，两块脱落时间不同，所以按面角（corner）存位置。探针修改器按 Base 组的切法切一次块，记下每个面角属于哪一块；播放时用 numpy 的 bincount 求每块的平均年龄，变号那一刻整块插值 | 已完成 |
| 整体移动模型时留在原地 | 位置改成按世界坐标记录。一个隐藏空物体记下录制时网格物体每帧的世界矩阵，节点里经由它（Object Info + 反向旋转 + 除以缩放）把世界坐标转回物体坐标。根物体做移动、转圈动画时碎片留在原地；生成后再整体挪动模型（每帧同样的偏移），碎片跟着挪 | 已完成；顺带让新服装用「复制变换」约束跟随旧模型的整体移动（之前只在生成时对齐一次，物体动画带不动新服装） |
| 收尾光扫 | Field 组多输出一个不带噪波的路径距离；光带位置 = 收尾进度 ÷ 0.7 ×（wave + 光带宽度），沿变身路径从起点扫过全身，剩下 30% 的时间留给最后迸出的星星。星星在光带经过时各自出生 | 已完成 |
| 全屏闪白 | 合成器里加一个混合节点，把画面混向高亮的白色（场景线性 6.0，经过视图变换后是纯白）。混合系数用驱动器按遮罩缩放算，和收尾闪光同一个时间轴；亮起、退掉的快慢按遮罩那一刻每帧的增量换算成约 1 帧 / 6 帧，收尾再短也不会漏帧。只用简单表达式，不装插件、不开 Python 自动运行也能渲染 | 已完成 |

另外修了一处：留在原地把碎片挪到脱落位置以后，「动画姿态」测量空间下的距离会按新位置重算，碎片的飞行时间会乱。现在年龄先在身体上算好存成属性，碎片、装甲和粒子都用它，只改位置不改时间。

两个顺手的小改进：

- **背面发光**：只有新服装时，从切口能看到模型内部，显得空心。游戏的溶解特效常把背面渲染成发光色来遮掩。
- **多层叠加**：模仿 Mark 50，在最终战衣前面先长一层深色内衬。

暂不推荐：

- **魔形女鳞片**：鳞片一面要显示旧衣服的贴图，另一面显示新衣服的贴图，两套网格对不上，要做贴图对位采样。
- **毒液触手**：曲线很难在不相连的零件之间连续爬行。
- **液态金属、黑烟**：要每帧把点转成体积，MMD 这种面数下会很慢。

## 参考资料

- 纳米战衣
  - [Phil Saunders – Mark 50 变身设计](https://philsaunders.artstation.com/projects/aR0NQL?album_id=262875)
  - [Gizmodo – Framestore 的 Mark 50](https://gizmodo.com/how-vfx-artists-created-the-nanotech-powered-iron-man-s-1828342127)
  - [黑豹纳米战衣（Method Studios）](https://www.motionpictures.org/2018/05/how-black-panthers-visual-effects-team-infused-the-panther-suits-with-vibranium-technology/)
- 消散
  - [AWN – Weta 的响指消散](https://www.awn.com/vfxworld/weta-and-thanos-come-full-circle-avengers-endgame)
  - [Yahoo – 响指消散的设计](https://www.yahoo.com/entertainment/secret-snap-avengers-infinity-war-effects-team-turned-mcu-dust-140029675.html)
  - [Tron Derez](https://tron.fandom.com/wiki/Derez)
- 扫描、有机、风格化
  - [IndieWire – 西部世界片头](https://www.indiewire.com/2017/06/westworld-main-title-design-emmy-1201840709/)
  - [AWN – DNEG 的毒液](https://www.awn.com/vfxworld/its-much-more-horseplay-dneg-venom-last-dance-vfx)
  - [CG Channel – X2 魔形女](https://www.cgchannel.com/2003/05/interview-with-daniel-roizman/)
  - [fxguide – 第一战魔形女](https://www.fxguide.com/fxfeatured/making-mutants-for-x-men-first-class/)
  - [SideFX – 平行宇宙的故障效果](https://www.sidefx.com/community/spider-man-into-the-spider-verse/)
  - [CBR – 美少女战士 Crystal 变身](https://www.cbr.com/sailor-moon-crystal-every-sailor-guardian-transformation-ranked/)
- Blender 产品
  - [Mystique Scales Effect](https://superhivemarket.com/products/mystique-scales-effect)
  - [Disintegration FXs](https://superhivemarket.com/products/disintegration-fxs)
  - [Dissolution](https://superhivemarket.com/products/dissolution---dissolve-mesh-into-particles-with-geometry-nodes)
- 引擎与教程
  - [Unreal Niagara 消散与重组教程](https://forums.unrealengine.com/t/community-tutorial-unreal-niagara-dissolve-disintegrate-reintegrate/2253288)
  - [Fab – Materialize VFX](https://www.fab.com/listings/718707d3-5e80-49a2-9b2a-fdfbd9cf8d7d)
  - [几何节点长毒液触手](https://www.youtube.com/watch?v=F2f1mj4oy-U)
  - [Shortest Edge Paths 做表面闪电](https://blenderartists.org/t/lightning-effect-with-shortest-edge-path-nodes-of-geometry-nodes-in-blender-detailed-tutorial/1404273)
