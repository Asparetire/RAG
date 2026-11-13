# 试审报告——13c8e91b3467（图像分割论文）

- 候选题 12 道；请逐题在末行标 `通过` / `修改(说明)` / `弃用(原因)`
- 通过后我按你的标记定稿并放量出全量题

## 第 1 题 [text] synthesis

**题目**：既然 Kapur 和 Otsu 方法在双阈值图像分割中已被证明是有效的，论文为什么还要提出一种混合仿生学习算法？该混合算法在设计上如何通过不同组件的分工来同时兼顾优化精度与求解速度？

**参考答案**：原因在于：这两种经典方法虽然适合双阈值分割，但一旦推广到多阈值情形，其计算开销会随阈值个数的增加而呈指数级增长，从而制约了多阈值分割的实际应用；因此论文提出混合仿生学习算法，其目标是在求解多阈值问题时最大化 Kapur 与 Otsu 的目标函数。在设计上，该算法把细菌觅食（BF）的搜索准确性与和声搜索（HS）的求解速度结合起来以共同满足目标函数，并由学习自动机（LA）充当智能决策部分，依据问题当前的状态在两种算法之间选择其一，从而实现对目标函数的满意优化。

**gold [13c8e91b3467:0015]**（text p5）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 2.2 Otsu method
\mu_ {j} = \sum_ {i = t _ {j}} ^ {t _ {j + 1} - 1} \frac {i p _ {i}}{\omega_ {j}}. \mu_ {m} = \sum_ {i = t _ {m}} ^ {L - 1} \frac {i p _ {i}}{\omega_ {m}}. \end{array}\tag{8}
The optimal multilevel thresholding is configured by maximizing the objective function using Eq. (9):
\left| \lef

**gold [13c8e91b3467:0016]**（text p6）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 3 Brief explanations of the algorithms in the study
Optimization is the process of making something better than the previous form. Over the last decade, the aggregate intelligent behavior of insect or animal groups in the natural world for example flocks of birds, colonies of ants, schools of fish, swar

**审核**：

---

## 第 2 题 [text] synthesis

**题目**：细菌觅食优化算法与和声搜索算法各自的灵感来源是什么？撇开灵感来源不谈，这两个算法在探索解空间时采用了怎样的共同搜索策略？

**参考答案**：细菌觅食算法的灵感来自大肠杆菌等细菌（如 E.coli 和 M.xanthus）的群体觅食行为，尤其是细菌感知环境中化学梯度并朝向或远离特定信号的趋化行为；和声搜索的灵感则来自爵士乐手即兴演奏、通过不断变化迅速打磨出优美和声的过程。两者的共同点在于都以随机方式探索解空间：细菌觅食算法让一群模拟细胞随机且集体地涌向理想状态（借助趋化、繁殖、消除-扩散三个过程）；和声搜索则逐步随机生成候选解，每个分量要么从高质量解的记忆中随机抽取，要么在优质解基础上调整，要么在问题取值范围内随机赋值，并且只有当目标值有改进时才按贪心准则接受新解以替换现有成员。

**gold [13c8e91b3467:0017]**（text p7）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 3.1 Bacterial foraging optimization algorithm
The Bacterial Foraging Optimization Algorithm (BF) [3] is inspired by the group foraging behavior of bacteria such as E.coli and M.xanthus. Specifically, the BF is inspired by the chemotaxis behavior of bacteria that will perceive chemical gradients in the e

**gold [13c8e91b3467:0019]**（text p7）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 3.2 Harmony search algorithm
Harmony Search [3] was inspired by the improvisation of Jazz musicians. Specifically, the process in which the musicians (who may have never played together before) rapidly refine their individual improvisation through variation resulting in an aesthetic harmony.
The informa

**审核**：

---

## 第 3 题 [table] direct

**题目**：根据 Table 1（BFHS 初始参数），Bacterial Foraging (BF) 部分中取值最大的参数和 Harmony Search (HS) 部分中取值最大的参数分别是什么？各自的取值是多少？

**参考答案**：BF 部分取值最大的参数是 Number of bacterium (s)，取值为 20；HS 部分取值最大的参数是 Number of improvisations (NI)，取值为 250。

**gold [13c8e91b3467:0028]**（table p10）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 4 Implementation of the Hybrid Method
【表注】Table 1 Initial parameters of BFHS
【列】Method Parameter / Value
【行】Bacterial Foraging (BF) Number of bacterium (s) / Number of chemotactic steps (Nc) / Swimming length (N<sub>s</sub>) / Number of reproduction steps (Nre) / Number of elimination of dispersal event

**审核**：

---

## 第 4 题 [figure] direct

**题目**：在图1中，(a)列与(b)至(f)列的图像在视觉上的主要区别是什么？请以Skydiver（跳伞者）一行为例说明不同列之间绿色边界标注的差异。

**参考答案**：(a)列是原始图像，图像上没有任何边界叠加；(b)至(f)列则在图像上用绿色线条叠加了不同标注者手工生成的区域边界。以Skydiver一行为例，各列的绿色边界并不完全一致：如(d)列将降落伞连同伞绳一起用绿色标出为一个区域，而(e)、(f)列只勾勒出跳伞者身体部分的小区域，说明不同人工分割结果之间存在明显差异。

**gold [13c8e91b3467:0005]**（image p?）：

> 

**gold [13c8e91b3467:0004]**（caption p3）：

> Fig. 1 Berkeley segmentation benchmark [14] (a) original images, and (b) to (f) region boundaries of multiple manually generated segmentations overlaid on the images

**审核**：

---

## 第 5 题 [figure] direct

**题目**：根据图 2(b) 所示的互联自动机（Interconnected automata）结构：虚线框内共有几个 Learning Automaton？各自动机的输出信号汇入求和节点后形成的向量 X 是什么？从框外馈入各自动机的反馈信号是什么？

**参考答案**：图 2(b) 的虚线框内共有 3 个 Learning Automaton（学习自动机），三者分别输出信号 x₁、x₂、x₃，这些信号汇入图中圆圈所示的求和节点后，组成向量 X = (x₁, x₂, x₃) 向外输出；从框外右侧输入并分支连接到三个学习自动机的反馈信号为 β。

**gold [13c8e91b3467:0023]**（image p?）：

> 

**gold [13c8e91b3467:0022]**（caption p8）：

> Fig. 2 (a) Reinforcement learning system and (b) Interconnected automata

**审核**：

---

## 第 6 题 [figure] direct

**题目**：根据图 3（Thresholding points determination），阈值点 T_i 在图中是如何确定的？它在横轴上处于什么位置？

**参考答案**：图中画出了两条概率密度曲线 p_i(x) 和 p_{i+1}(x)，阈值点 T_i 取在两条曲线的交点处（交点用小圆圈标出），该交点在横轴上位于两个均值 μ_i 与 μ_{i+1} 之间。

**gold [13c8e91b3467:0033]**（image p?）：

> 

**gold [13c8e91b3467:0032]**（caption p11）：

> Fig. 3 Thresholding points determination

**审核**：

---

## 第 7 题 [figure] direct

**题目**：图中展示的图像内容是什么？从视觉上判断，该图像是彩色图像还是灰度图像？

**参考答案**：图中是一张人像照片：一位留着长发的女性头戴装饰有羽毛的宽边帽，侧身回望镜头。整幅图像仅呈现黑白灰层次，是一张灰度（黑白）图像，而非彩色图像。

**gold [13c8e91b3467:0038]**（image p?）：

> 

**审核**：

---

## 第 8 题 [figure] direct

**题目**：该图像是彩色还是灰度图像？图中可以辨认出哪两类形状明显不同的辣椒，它们分别位于画面的什么位置？

**参考答案**：图像为灰度（黑白）图像。图中可辨认出两类形状明显不同的辣椒：一类是体积较大、顶部带蒂、果身分瓣的灯笼椒（甜椒/柿子椒），其中一个位于画面中央偏下、十分醒目，其后上方还有一个更大的；另一类是细长、顶端尖突的长辣椒（尖椒），竖直位于画面左侧。背景中还堆叠着许多大小不一的其他辣椒。

**gold [13c8e91b3467:0039]**（image p?）：

> 

**审核**：

---

## 第 9 题 [figure] direct

**题目**：图中照片的主体是什么动物？该图像是彩色还是黑白（灰度）？请列举至少两处可从画面中直接确认的面部特征。

**参考答案**：主体是一只山魈（mandrill，一种灵长类动物）的面部正面特写；图像为黑白（灰度）照片。画面中可直接确认的特征包括：双眼直视镜头、鼻梁狭长突出、两侧脸颊有对称的纵向褶皱状须毛、下巴与嘴周长有浓密的胡须。

**gold [13c8e91b3467:0040]**（image p?）：

> 

**审核**：

---

## 第 10 题 [noise] direct

**题目**：在该混合图像分割算法中，为什么引入学习自动机（Learning Automata, LA）？它在算法中起什么作用？

**参考答案**：因为软计算类算法最大的问题是容易陷入局部最优。为解决这一关键问题，论文引入LA作为控制器，在两种优化方法（细菌觅食BF与和声搜索HS）之间进行切换。

**gold [13c8e91b3467:0000]**（text p1）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding
Mohammad Mahdi Dehshibi <sup>1</sup> & Mohamad Sourizaei <sup>2</sup> & Mahmood Fazlali <sup>3</sup> & Omid Talaee <sup>4</sup> & Hossein Samadyar <sup>1</sup> & Jamshid Shanbehzadeh<sup>5</sup>
Received: 26 September 2015 /Revised: 10 August 2016 /Accepted: 22 August 2016 / Published online: 21 September

**审核**：

---

## 第 11 题 [noise] direct

**题目**：论文提出的混合算法（BFHS）将哪两种优化算法结合在一起？这两种算法各自为该方法贡献了什么优势？

**参考答案**：该混合算法结合了细菌觅食算法与和声搜索算法。其中 BF 贡献的是精度，HS 贡献的是收敛速度，二者结合用于应对局部最优问题，从而实现鲁棒的多级阈值分割。

**gold [13c8e91b3467:0009]**（text p3）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 1 Introduction
Yang and Deb [26] formulated a new meta-heuristic algorithm, called cuckoo search algorithm which is based on the interesting breeding behavior such as brood parasitism of particular species of Cuckoos, and the preliminary studies show that it is very promising and could outperform the ex

**gold [13c8e91b3467:0010]**（text p3）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 1 Introduction
Quantitative results are defined by peak signal-to-noise ratio (PSNR), structural similarity index (SSIM) and feature similarity index (FSIM). The performance improvement of the proposed algorithm, so-called BFHS, based segmentation approach is measured regarding PSNR, SSIM, and FSIM, in 

**审核**：

---

## 第 12 题 [noise] direct

**题目**：细菌觅食优化算法（BF）通过哪三个过程实现其信息处理策略？

**参考答案**：通过在模拟细胞种群上执行三个过程实现：1) 趋化（Chemotaxis），细胞在操纵后的代价面上逐一移动，是算法的主要工作量；2) 繁殖（Reproduction），只有生命周期中表现良好的细胞才能贡献下一代；3) 消除-扩散（Elimination-dispersal），以较低概率丢弃细胞并插入新的随机样本。

**gold [13c8e91b3467:0017]**（text p7）：

> A hybrid bio-inspired learning algorithm for image segmentation using multilevel thresholding / 3.1 Bacterial foraging optimization algorithm
The Bacterial Foraging Optimization Algorithm (BF) [3] is inspired by the group foraging behavior of bacteria such as E.coli and M.xanthus. Specifically, the BF is inspired by the chemotaxis behavior of bacteria that will perceive chemical gradients in the e

**审核**：

---

