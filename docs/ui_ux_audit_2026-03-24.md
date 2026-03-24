# MotorControlApp PySide6 UI/UX 审计报告（复审）

审计日期：2026-03-24  
审计对象：主窗口、手动控制、自动化流程、位置监控、PID 实时分析 / 参数优化、光谱采集、自定义控件与关键反馈链路  
产品上下文：面向实验/现场工程人员的多轴电机控制与光谱采集桌面工作台

## 审计方法

- 代码审查：`src/ui/**`、`src/config/constants.py`、`src/core/pid_optimizer.py`
- 视觉证据：使用项目 `.venv` 于 2026-03-24 16:37 离屏启动应用，重新生成 `docs/ui_audit_assets/00_manual.png` 至 `docs/ui_audit_assets/05_spectro.png`
- 对比度抽样：对主按钮、危险按钮、状态文字进行 WCAG 对比度计算
- 交互核对：重点检查“界面状态是否真实”“输入是否在字段级受约束”“错误是否在触发点附近反馈”

## 说明与限制

- 本次复审已完成新截图抓取，截图证据与当前代码版本一致，不再依赖旧版资产。
- 离屏 Qt 环境中的中文字体 fallback 仍不完整，新截图里存在方块字形；因此布局、层级和控件状态判断以截图为准，但字形/字体细节判断仍更多依赖代码。
- 项目中未发现 `.impeccable.md` 设计上下文文件，因此视觉判断以 README 所描述的工业/实验控制场景为准，而不是按消费级 App 标准评价。
- 本报告不做修复，只更新问题清单、优先级和后续处理建议。

## Anti-Patterns Verdict

**Verdict: Fail**

这套界面不是典型的“紫蓝渐变 + 玻璃拟态 + 指标卡片”式 AI 网页，但仍然存在明显的模板化痕迹，不像经过系统化设计的专业控制工作台：

- 几乎所有主要动作都沿用同一种高饱和蓝色实心按钮，主次关系被抹平。
- 页面大量依赖圆角 `QGroupBox` 包裹内容，形成“所有内容都被卡片框住”的单调节奏。
- `IOSSwitch` 在工业控制语境中显得过于消费级，且被重复使用在多个关键开关场景。
- 布局偏平均分块，很多区域是“左侧表单 / 右侧图表 / 底部日志”的固定拼装式结构，信息层级缺少针对任务流的重组。
- 局部组件直接写死颜色、字体和圆角，整体像一套系统，细节又像多套系统拼接。

结论：当前 UI 更像“功能完整但设计语言尚未收束的桌面工程工具”，而不是“交互可信、视觉层级明确的专业控制台”。

## Executive Summary

- 总问题数：14
- 严重级别分布：2 Critical / 6 High / 4 Medium / 2 Low
- 综合质量评分：**64 / 100**
- 当前状态：功能面覆盖明显增强，但交互可信度、信息层级、输入防错和视觉系统化程度仍有较高 UX 债务

最关键的 5 个问题：

1. 串口连接后会自动开启角度流，但“实时角度”按钮状态没有同步，界面状态与系统状态不一致。
2. PID 优化面板中的“方向”选择在单次测试流程中未被真正使用，界面控件与实际执行脱节。
3. 自定义开关、按钮和拖拽列表缺少成体系的键盘可达性与可访问语义，关键操作对非鼠标用户不友好。
4. 主按钮、危险按钮与小字号状态文字存在真实对比度不达标问题，影响识别效率。
5. 大量固定尺寸、固定列宽和固定面板宽度让高 DPI / 小屏场景风险持续偏高。

建议下一步：

1. 先修复所有“界面承诺了某个状态/控制，但系统并未兑现”的问题。
2. 再补字段级校验、反馈归一和高风险动作的触发点提示。
3. 最后统一设计 token、按钮层级和页面信息架构。

## Detailed Findings By Severity

### Critical Issues

#### C1. 串口连接会自动开启角度流，但“实时角度”按钮未同步状态

- **Location**: `src/ui/mixins/serial_mixin.py:105-115`, `src/ui/mixins/position_mixin.py:139-141`, `src/ui/mixins/position_mixin.py:314-330`
- **Severity**: Critical
- **Category**: Interaction Flow
- **Description**: 串口连接成功后会直接发送 `ANGLESTREAM_START`，但位置监控页的 `stream_btn` 没有被同步为选中态，也没有展示“已随连接自动开启”的状态提示。
- **Impact**: 用户看到的界面状态与设备真实状态不一致，容易重复点击、误判实时角度流是否已开启，直接损害控制台的可信度。
- **WCAG/Standard**: Visibility of System Status / Consistency and Standards
- **Recommendation**: 连接串口后必须同步更新 `stream_btn`、状态文案和相关禁用状态；或者取消自动开启，改成完全由用户显式触发。
- **Suggested command**: `/harden`, `/normalize`

#### C2. PID 优化面板“方向”选择在单次测试流程中失效

- **Location**: `src/ui/widgets/pid_optimizer_panel.py:167-170`, `src/ui/widgets/pid_optimizer_panel.py:348-370`, `src/ui/mixins/analysis_mixin.py:257-286`, `src/core/pid_optimizer.py:332-333`, `src/core/pid_optimizer.py:528-530`
- **Severity**: Critical
- **Category**: Interaction Flow
- **Description**: 界面提供了“正转/反转”选择，但单次测试发出的配置没有带上该字段；`_run_single_pid_test()` 又从 `config.get("direction", "F")` 读取方向，导致单次测试默认总是 `F`。
- **Impact**: 用户明确设置的方向可能被悄悄忽略，属于“UI 控件不兑现承诺”的严重问题；在电机控制场景里，这会直接影响对设备行为的判断。
- **WCAG/Standard**: Error Prevention / Match Between System and Real World
- **Recommendation**: 统一方向字段命名，确保优化流程与单次测试流程都使用同一来源；在开始测试前把最终执行参数显式显示给用户。
- **Suggested command**: `/harden`, `/clarify`

### High-Severity Issues

#### H1. 自定义开关与关键交互缺少可访问语义、焦点设计和键盘路径

- **Location**: `src/ui/widgets/ios_switch.py:6-31`, `src/ui/main_window_complete.py:409-440`, `src/ui/mixins/position_mixin.py:110-119`, `src/ui/mixins/manual_mixin.py:203-206`, `src/ui/widgets/drag_tree.py:10-22`, `src/config/constants.py:115-138`
- **Severity**: High
- **Category**: Accessibility
- **Description**: `IOSSwitch` 只是无文本的 `QCheckBox` 外观包装；项目中未发现 `setAccessibleName`、`setAccessibleDescription`、`setTabOrder`、`setBuddy`、`setShortcut` 等成体系可达性 API。按钮样式定义了 hover/pressed/disabled，但没有明确的 `QPushButton:focus` 设计；自动化步骤重排依赖鼠标拖拽，没有键盘替代路径。
- **Impact**: 键盘用户、辅助技术用户和高强度操作用户都缺少稳定的焦点感知与操作路径，关键开关的含义主要依赖旁边文字和视觉猜测。
- **WCAG/Standard**: WCAG 1.3.1, 2.1.1, 2.4.3, 2.4.7, 4.1.2
- **Recommendation**: 为所有自定义开关和关键按钮补齐 accessible name/description；为导航和高频动作建立稳定 tab 顺序与快捷键；增加清晰的 focus 样式；为步骤重排提供“上移/下移”按钮或快捷键。
- **Suggested command**: `/harden`, `/normalize`

#### H2. 主按钮、危险按钮和小字号状态文字存在真实对比度不达标问题

- **Location**: `src/config/constants.py:115-138`, `src/ui/mixins/position_mixin.py:145-174`, `src/ui/mixins/spectro_mixin.py:91-97`, `src/ui/widgets/pid_optimizer_panel.py:200-245`
- **Severity**: High
- **Category**: Accessibility
- **Description**: 抽样结果显示：`#007aff`/白约 `4.02:1`、`#ff3b30`/白约 `3.55:1`、`#ff9500`/白约 `2.20:1`、`#4CAF50`/白约 `2.78:1`、`#2196F3`/白约 `3.12:1`、`#8e8e93`/白约 `3.26:1`。这意味着主按钮、危险按钮，以及部分 11-14px 的状态/辅助文字都不能稳定满足普通文本 AA。
- **Impact**: 在高亮环境、投屏、实验台显示器和长时间使用场景中，按钮标签、状态提示和辅助信息会变得难读，尤其不利于高风险操作识别。
- **WCAG/Standard**: WCAG 1.4.3 AA
- **Recommendation**: 建立经过验证的语义色 token；对高风险按钮改用更深底色或深色文字；将 `#8e8e93`、`#888888` 一类小字号状态文字整体提升对比度。
- **Suggested command**: `/colorize`, `/normalize`

#### H3. 固定窗口、固定列宽和固定面板宽度过多，适配高 DPI / 小屏风险高

- **Location**: `src/ui/main_window_complete.py:187-188`, `src/ui/main_window_complete.py:247`, `src/ui/main_window_complete.py:265-327`, `src/ui/dialogs/motor_step_config.py:46`, `src/ui/mixins/automation_mixin.py:87-90`, `src/ui/mixins/manual_mixin.py:163`, `src/ui/widgets/pid_optimizer_panel.py:83-84`, `src/ui/mixins/spectro_mixin.py:52-56`
- **Severity**: High
- **Category**: Responsive
- **Description**: 主窗口固定在 `1280x900` 起步，侧栏宽度写死为 `220`，自动化表格列宽固定，步骤配置弹窗固定 `500x780`，PID 优化左侧面板锁在 `320-400`，光谱页初始化 splitter 尺寸固定为 `[300, 700]`。新抓取的 `02_position.png` 也确认 I2C 映射整块直接进入位置监控主工作区，进一步挤占了监控和操作区域的垂直空间。
- **Impact**: 在 1366x768、125%/150% DPI、竖屏投屏或较小工业一体机上，容易出现内容拥挤、图表被压缩、弹窗超界和信息被截断的问题。
- **WCAG/Standard**: Reflow / Responsive best practice
- **Recommendation**: 以布局伸缩、内容最小宽度和 splitter 权重替代大面积 `setFixed*`；弹窗改为可滚动或支持伸缩；表格列宽改为按容器宽度和内容权重分配。
- **Suggested command**: `/adapt`, `/arrange`

#### H4. 手动控制、定时运行和自动化步骤配置仍然依赖“提交后报错”

- **Location**: `src/ui/mixins/manual_mixin.py:120-132`, `src/ui/mixins/manual_mixin.py:255-320`, `src/ui/mixins/manual_mixin.py:335-349`, `src/ui/dialogs/motor_step_config.py:109-118`, `src/ui/dialogs/motor_step_config.py:172-260`, `src/ui/mixins/automation_mixin.py:117-122`, `src/ui/mixins/automation_mixin.py:257-270`
- **Severity**: High
- **Category**: Usability
- **Description**: 多个速度、角度、时长、循环次数字段仍使用普通 `QLineEdit`，缺少即时范围提示、字段级错误状态和禁用条件。很多错误要到点击“运行/确认”后才通过 `QMessageBox` 暴露。
- **Impact**: 用户必须先试错再修正，控制流程被打断；对于高频电机操作，晚失败会显著拖慢节奏，也更容易造成误操作。
- **WCAG/Standard**: WCAG 3.3.1, 3.3.3
- **Recommendation**: 能用 `QSpinBox` / `QDoubleSpinBox` 的地方尽量不用自由文本；为文本框补 validator、单位、合法范围和即时提示；只有在表单有效时才允许提交。
- **Suggested command**: `/harden`, `/clarify`

#### H5. 自动化页的信息层级仍然不利于“先理解、再编辑、最后执行”

- **Location**: `src/ui/mixins/automation_mixin.py:75-122`, `src/ui/mixins/automation_mixin.py:154-176`, `src/ui/mixins/automation_mixin.py:188-196`, `src/ui/widgets/drag_tree.py:10-22`
- **Severity**: High
- **Category**: Information Hierarchy
- **Description**: 页面核心区域是一张默认空白的大表，但没有空状态说明；步骤参数被压成一整串长文本；循环次数放在表格外，编辑入口依赖双击和拖拽，学习成本偏高。
- **Impact**: 新用户难以理解“第一步该做什么”，老用户也不容易快速扫读每一步的轴、方向、角度和泵设置；编辑路径不够直觉。
- **WCAG/Standard**: Recognition over Recall / Progressive Disclosure
- **Recommendation**: 为空状态增加“如何添加第一步”的说明；把参数摘要拆成结构化标签/列；把执行区、循环次数和步骤上下文组织成一个连续任务流；提供显式“编辑 / 上移 / 下移”动作。
- **Suggested command**: `/arrange`, `/onboard`

#### H6. 主次动作层级被大量蓝色实心按钮抹平

- **Location**: `src/config/constants.py:115-138`, `src/ui/main_window_complete.py:257-327`, `src/ui/mixins/manual_mixin.py:150-180`, `src/ui/mixins/automation_mixin.py:97-111`, `src/ui/mixins/position_mixin.py:177-180`
- **Severity**: High
- **Category**: Visual Design
- **Description**: 导航切换、加载/保存、刷新串口、发送指令、开始/停止、清空日志等大量动作共享同一主按钮样式。除少数红橙按钮外，视觉上很难区分“当前主任务”“次级操作”和“工具动作”。
- **Impact**: 用户扫描页面时缺少明确焦点，复杂页面显得吵，真正需要优先注意的操作不够突出。
- **WCAG/Standard**: Visual Hierarchy / Interaction Design Heuristic
- **Recommendation**: 至少建立 Primary / Secondary / Tertiary / Danger 四层按钮体系；将“刷新、加载、保存、清空日志”等工具动作降级，避免与“开始执行”竞争注意力。
- **Suggested command**: `/normalize`, `/polish`

### Medium-Severity Issues

#### M1. 反馈通道碎片化，部分无效操作只有日志、状态栏或静默回退

- **Location**: `src/ui/main_window_complete.py:443-455`, `src/ui/mixins/position_mixin.py:337-355`, `src/ui/mixins/spectro_mixin.py:219-224`, `src/ui/mixins/automation_mixin.py:124-152`, `src/ui/main_window_complete.py:872-881`
- **Severity**: Medium
- **Category**: Error Feedback
- **Description**: 有些问题走 `QMessageBox`，有些只写状态栏，有些只写日志，还有些直接静默回退。例如 PID 阈值输入越界时会被重置并写日志；设置参考电压在无数据时没有任何反馈；部分异常只留在日志面板。
- **Impact**: 用户很难建立稳定预期，不知道“这次动作失败了会在哪里看到原因”；在多任务控制场景下，反馈不统一会降低定位问题的速度。
- **WCAG/Standard**: Visibility of System Status / Error Identification
- **Recommendation**: 建立统一规则：字段错误用 inline，流程阻断用模态或页内警告，后台诊断才进入日志；避免无提示的重置或 no-op。
- **Suggested command**: `/clarify`, `/harden`

#### M2. 主题、字体和局部样式分散，维护成本高且一致性偏弱

- **Location**: `src/config/constants.py:89-93`, `src/ui/main_window_complete.py:254-379`, `src/ui/widgets/ios_switch.py:12-31`, `src/ui/mixins/position_mixin.py:94-107`, `src/ui/mixins/spectro_mixin.py:91-97`, `src/ui/widgets/pid_analysis_chart.py:451-554`, `src/ui/widgets/pid_optimizer_panel.py:200-245`
- **Severity**: Medium
- **Category**: Theming
- **Description**: 全局字体先设置为 `Times New Roman` 系列，但多个页面又局部切换到 `Microsoft YaHei`、`Menlo`、`Roboto Mono`；颜色同时存在全局 QSS 和局部 `setStyleSheet` 双轨体系；多个组件直接写死十六进制颜色。
- **Impact**: 页面观感像多套子系统拼接，后续如果要做统一品牌化、深色模式或语义色治理，成本会很高。
- **WCAG/Standard**: Design System Consistency
- **Recommendation**: 抽离语义色、状态色、字体角色和组件层级 token；减少局部 `setStyleSheet`；统一数字/代码/正文的字体角色。
- **Suggested command**: `/extract`, `/normalize`, `/typeset`

#### M3. 隐藏的旧版图表仍然持续参与更新

- **Location**: `src/ui/mixins/analysis_mixin.py:155-158`, `src/ui/main_window_complete.py:488-497`
- **Severity**: Medium
- **Category**: Performance
- **Description**: `AnalysisChart` 已被隐藏，但 `update_angles()` 仍在每 100ms 调用 `self.chart_view.chart().update_data(data)`。
- **Impact**: 在实时角度流和图表都活跃时，会产生无用户价值的 UI 更新开销，也增加后续维护复杂度。
- **WCAG/Standard**: Performance Efficiency
- **Recommendation**: 完整移除隐藏兼容图表，或至少在不可见时彻底停更。
- **Suggested command**: `/optimize`

#### M4. 底部日志面板长期占据主视区，且当前是可编辑文本框

- **Location**: `src/ui/main_window_complete.py:372-386`, `src/ui/main_window_complete.py:377-379`, `src/ui/main_window_complete.py:875-881`
- **Severity**: Medium
- **Category**: Information Hierarchy
- **Description**: 日志区在所有页面常驻，占据底部大块空间；`QTextEdit` 没有设为只读，用户理论上可以直接输入内容。
- **Impact**: 主任务区被压缩，图表和配置区的可用空间减少；“诊断信息”与“可编辑工作区”边界模糊，增加误解成本。
- **WCAG/Standard**: Progressive Disclosure / Minimalist Design
- **Recommendation**: 将日志改为可折叠 drawer、独立“诊断”页或侧边面板；默认只保留关键状态；若继续保留在主界面，至少应设为只读。
- **Suggested command**: `/arrange`, `/distill`

### Low-Severity Issues

#### L1. PID 优化面板按钮混入 emoji / glyph，风格与专业工具语境不一致

- **Location**: `src/ui/widgets/pid_optimizer_panel.py:200-236`, `src/ui/widgets/pid_optimizer_panel.py:328-343`, `src/ui/widgets/pid_optimizer_panel.py:354-378`
- **Severity**: Low
- **Category**: Visual Design
- **Description**: `▶`、`⏸`、`⏹` 与 emoji 风格文本混杂在同一组控制按钮中，不同字体环境下显示效果不稳定。
- **Impact**: 不会阻断功能，但会削弱整体专业感，也可能在不同系统字体环境中出现对齐和渲染差异。
- **WCAG/Standard**: Consistency and Standards
- **Recommendation**: 改用统一的 Qt 图标体系或纯文本标签。
- **Suggested command**: `/polish`, `/normalize`

#### L2. 复杂功能的上下文帮助仍然偏少

- **Location**: `src/ui/widgets/pid_optimizer_panel.py:162-169`, `src/ui/mixins/manual_mixin.py:120-132`, `src/ui/dialogs/motor_step_config.py:109-118`, `src/ui/mixins/spectro_mixin.py:65-117`
- **Severity**: Low
- **Category**: Usability
- **Description**: 当前项目里能看到的 tooltip 很少，很多复杂区域主要依赖占位符和用户记忆，没有把合法范围、推荐值、典型流程写在界面附近。
- **Impact**: 新用户和低频用户需要依赖 README、经验或反复试错才能顺利完成操作。
- **WCAG/Standard**: Help and Documentation
- **Recommendation**: 为高复杂度区域补充短说明、推荐值、风险提示和典型顺序；优先覆盖 PID 优化、自动化步骤配置和光谱采集。
- **Suggested command**: `/clarify`, `/onboard`

## Patterns & Systemic Issues

- **界面契约不稳定**：至少存在 2 处“控件已显示，但执行逻辑未兑现”的问题，直接影响用户信任。
- **固定尺寸使用频繁**：主窗口、导航、按钮、弹窗、图表和表格列宽都存在明显写死。
- **样式治理分散**：`constants.py`、`position_mixin.py`、`spectro_mixin.py`、`pid_optimizer_panel.py`、`pid_analysis_chart.py`、`ios_switch.py` 都在直接写颜色和局部样式。
- **反馈链路碎片化**：模态、状态栏、日志、静默重置并存，优先级和使用边界不稳定。
- **帮助与可达性基础薄弱**：未形成统一的 accessible API、快捷键、focus 规则和上下文帮助策略。

## Positive Findings

- 功能分区比上一轮更完整。手动、自动化、位置、PID 分析/优化、光谱采集的主入口已经稳定成型，任务边界清楚。
- 部分高复杂度区域已经开始使用更合适的控件类型。PID 优化页与光谱配置页大量采用 `QSpinBox`、`QDoubleSpinBox`、`QComboBox`，比纯文本输入更稳。
- 有明确的性能意识。`MotorCircle`、`_chart_update_timer`、`pid_update_timer`、批量曲线刷新都说明你已经在主动控制实时绘制成本。
- 配置持久化能力是亮点。预设、零点偏移、微泵备注和 I2C 映射都贴近真实设备使用场景，值得保留并继续完善。

## Recommendations By Priority

### 1. Immediate

1. 修复所有界面状态与真实执行状态不一致的问题，先处理 C1 和 C2。
2. 为关键开关、按钮和拖拽列表补齐键盘/焦点/可访问语义。
3. 先把主按钮、危险按钮和小字号状态文字的对比度拉到达标，再讨论视觉统一。

### 2. Short-term

1. 把手动控制、定时运行和步骤配置中的自由文本输入改为受约束输入。
2. 重新组织自动化页，让“空状态 -> 添加步骤 -> 编辑 -> 执行”成为连续流程。
3. 去掉主窗口、弹窗和关键面板的大面积固定尺寸依赖。

### 3. Medium-term

1. 统一反馈通道规则：字段错误、流程错误、后台诊断分别走不同层级。
2. 抽取设计 token，收敛字体、颜色、按钮层级和状态色。
3. 清理已隐藏但仍在更新的旧版图表与兼容逻辑。

### 4. Long-term

1. 将日志从常驻主视区中剥离，构建更专业的“执行区 / 诊断区”分层。
2. 为 PID 优化、自动化和光谱采集增加轻量 onboarding 与上下文说明。
3. 逐步把现有 UI 从“功能堆叠”演进为“操作优先的专业工作台”。

## Suggested Commands For Fixes

- `/harden`
  解决 C1、C2、H1、H4、M1 这类“状态同步、可达性、字段级防错、错误反馈”问题。
- `/normalize`
  解决 H2、H6、M2、L1 这类“按钮层级、语义色、组件规则、风格一致性”问题。
- `/adapt`
  解决 H3 的固定尺寸与高 DPI / 小屏适配问题。
- `/arrange`
  解决 H3、H5、M4 的布局与信息层级问题。
- `/clarify`
  解决 H4、M1、L2 的表单说明、错误提示和上下文帮助问题。
- `/colorize`
  重点处理 H2 的对比度与语义色问题。
- `/extract`
  抽离 M2 中散落的颜色、字体和组件规则，形成可维护 token。
- `/optimize`
  清理 M3 的隐藏图表更新与无效 UI 开销。
- `/onboard`
  处理 H5、L2 中的空状态与首次使用引导。
- `/typeset`
  统一 M2 中的字体角色和数字信息表达。
- `/polish`
  处理 H6、L1 的视觉收束与细节噪声。

## Evidence Assets

- `docs/ui_audit_assets/00_manual.png`
- `docs/ui_audit_assets/01_auto.png`
- `docs/ui_audit_assets/02_position.png`
- `docs/ui_audit_assets/03_analysis_realtime.png`
- `docs/ui_audit_assets/04_analysis_optimizer.png`
- `docs/ui_audit_assets/05_spectro.png`

## Final Assessment

这次功能更新让应用更像一套完整的工程工作台了，尤其是光谱采集、PID 优化和配置持久化能力都比之前更成体系。问题已经不再是“功能够不够”，而是“用户能不能稳定地理解系统现在在做什么、接下来该做什么、以及刚才那次操作到底有没有按预期生效”。

下一阶段最值得投入的不是单点美化，而是把三个基础问题做扎实：

1. 界面状态必须可信。
2. 输入必须尽量在字段级被约束。
3. 错误必须在触发点附近被清楚解释。

只要先把这三件事补齐，这套应用的 UI/UX 质量会明显上一个台阶。
