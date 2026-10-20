"""Structured content for a wholly fictional Chinese demonstration thesis."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .figures import Figure
from .study import (
    DEFAULT_SCALE_INPUTS,
    SIMULATED_OBSERVATIONS,
    calculate_reported_statistics,
    leave_one_layer_out,
    sensitivity_envelope,
)


@dataclass(frozen=True, slots=True)
class Paragraph:
    text: str
    role: str = "body"


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    paragraphs: tuple[Paragraph, ...] = ()


@dataclass(frozen=True, slots=True)
class Chapter:
    title: str
    sections: tuple[Section, ...] = ()
    paragraphs: tuple[Paragraph, ...] = ()
    number: int = 0


@dataclass(frozen=True, slots=True)
class Table:
    number: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    caption: str = ""
    note: str = "注：全部数值均为模拟数据。"


@dataclass(frozen=True, slots=True)
class Reference:
    number: int
    author: str
    title: str
    year: int
    publication: str


@dataclass(frozen=True, slots=True)
class Appendix:
    title: str
    paragraphs: tuple[Paragraph, ...] = ()
    tables: tuple[Table, ...] = ()


@dataclass(frozen=True, slots=True)
class Thesis:
    title_zh: str
    title_en: str
    abstract_zh: str
    abstract_en: str
    keywords_zh: tuple[str, ...]
    keywords_en: tuple[str, ...]
    chapters: tuple[Chapter, ...]
    figures: tuple[Figure, ...]
    tables: tuple[Table, ...]
    references: tuple[Reference, ...]
    appendix: Appendix
    acknowledgements: str
    data_disclosure: str

    @property
    def paired_keywords(self) -> tuple[tuple[str, str], ...]:
        return tuple(zip(self.keywords_zh, self.keywords_en, strict=True))


_DISCLOSURE = (
    "数据声明：本文的树体、叶片、样方、观测记录、统计结果和误差指标均为为演示论文排版而构造的模拟数据，"
    "不代表任何真实果园、真实机构、真实人员或实际科研结论，不得用于生产决策。"
)


def _paragraphs(*texts: str) -> tuple[Paragraph, ...]:
    return tuple(Paragraph(text) for text in texts)


def _compact_demo_content(
    chapters: tuple[Chapter, ...],
    appendix: Appendix,
) -> tuple[tuple[Chapter, ...], Appendix]:
    compact_chapters = []
    for chapter in chapters:
        sections = []
        for section in chapter.sections:
            if chapter.number == 4 and section.title == "演示价值与改进方向":
                paragraphs = section.paragraphs[1:2]
            elif chapter.number == 4 and section.title == "主要结论":
                paragraphs = section.paragraphs[:1]
            elif (
                chapter.number == 3
                and section.title == "不确定性与敏感性分析"
            ):
                paragraphs = section.paragraphs
            else:
                paragraphs = section.paragraphs[:2]
            sections.append(replace(section, paragraphs=paragraphs))
        compact_chapters.append(
            replace(
                chapter,
                sections=tuple(sections),
                paragraphs=() if chapter.number == 4 else chapter.paragraphs[:1],
            )
        )
    return tuple(compact_chapters), replace(
        appendix,
        paragraphs=appendix.paragraphs[:3],
    )


def build_demo_thesis() -> Thesis:
    """Build the internally consistent fictional apple-leaf demonstration thesis."""

    statistics = calculate_reported_statistics(
        SIMULATED_OBSERVATIONS, DEFAULT_SCALE_INPUTS
    )
    sensitivity = sensitivity_envelope(
        SIMULATED_OBSERVATIONS, DEFAULT_SCALE_INPUTS
    )
    layer_omissions = leave_one_layer_out(
        SIMULATED_OBSERVATIONS, DEFAULT_SCALE_INPUTS
    )
    simple = statistics["simple"]
    stratified = statistics["stratified"]
    corrected = statistics["corrected"]

    abstract_zh = (
        "准确了解单株苹果树的叶片数量，有助于描述树冠生长状态并演示从局部观测推断总体规模的基本过程。"
        "本研究以一株虚构的盛果期苹果树为对象，提出一种结合树冠分层、方位样方、可见面积校正和重复抽样的叶片数量估算方法。"
        "研究首先将树冠划分为上、中、下三层，再在不同方位设置固定面积样方，对样方内完整叶片、边界叶片和被遮挡叶片分别记录；"
        "随后依据模拟摄影得到的可见面积比例修正局部计数，并按各层表面积权重进行外推。为检验方法稳定性，本文设置三轮重复观测，"
        "比较简单均值外推、分层加权外推与遮挡校正外推三种结果，同时通过留一层分析和确定性扰动计算敏感性区间。"
        "模拟结果表明，分层与遮挡校正可以降低树冠中层叶片密集造成的系统性低估；在设定的模拟条件下，推荐估计值为4286片，"
        "相对模拟真值4320片的偏差为-0.79%，重复观测变异系数为3.1%。研究还给出样方布设图、估算流程图、记录表和可复算公式，"
        "使演示数据能够沿着“原始记录—校正计数—分层外推—整树合计”的链条被核对。本文强调，所有树体参数、叶片计数、"
        "图表和结论均为模拟数据，仅服务于论文结构、图表、引文、附录和无障碍说明的完整演示，不代表任何真实试验或生产建议。"
        "该方法的意义在于提供一个逻辑闭合、步骤透明且适合教学复核的案例，而不是证明某种真实苹果树管理技术的优劣。"
    ) + _DISCLOSURE
    abstract_en = (
        "Estimating the number of leaves on an individual apple tree provides a "
        "clear demonstration of how local observations can be expanded into a "
        "whole-crown estimate. This fictional study develops a transparent method "
        "that combines crown stratification, directional quadrats, visible-area "
        "correction, and repeated observations. The crown is divided into upper, "
        "middle, and lower layers. Fixed-area quadrats are then assigned to "
        "different directions, where complete, boundary, and occluded leaves are "
        "recorded separately. Local counts are corrected with simulated visible-area "
        "ratios and expanded using layer-specific surface weights. Three observation "
        "rounds compare simple mean expansion, stratified weighting, and occlusion-"
        "corrected expansion. A leave-one-layer-out check and deterministic parameter "
        "perturbations describe sensitivity and uncertainty. Under the stated "
        "simulated conditions, the recommended estimate is 4,286 leaves, compared "
        "with a simulated truth of 4,320 leaves, producing a bias of minus 0.79 "
        "percent and a repeat-observation coefficient of variation of 3.1 percent. "
        "The thesis supplies a sampling schematic, an estimation workflow, complete "
        "tables, reproducible formulas, and an appendix record sheet so that every "
        "reported value can be traced from a local count to the final total. All "
        "trees, measurements, images, calculations, references, and findings are "
        "simulated data created solely for a thesis-formatting demonstration. They "
        "do not describe a real orchard, institution, person, experiment, or "
        "agricultural recommendation. The contribution is therefore a coherent and "
        "auditable teaching example rather than an empirical claim about apple "
        "production."
    )

    figures = (
        Figure(
            "图 2-1",
            "build/demo-assets/crown-layer-sampling.png",
            "模拟苹果树树冠被划分为上中下三层，并在不同方位设置六个编号样方。",
            "树冠分层与方位抽样示意图（模拟）",
        ),
        Figure(
            "图 3-1",
            "build/demo-assets/leaf-count-estimation-workflow.png",
            "模拟叶片数量由分层编号、样方计数、可见面积校正、分层外推进入误差评估的完整流程。",
            "单株叶片数量估算流程（模拟）",
        ),
    )

    tables = (
        Table(
            "表 2-1",
            ("树冠层", "样方数", "单样方面积/m²", "表面积权重", "可见比例"),
            (
                ("上层", "2", "0.25", "0.24", "0.91"),
                ("中层", "2", "0.25", "0.46", "0.82"),
                ("下层", "2", "0.25", "0.30", "0.88"),
            ),
            "模拟树冠分层与抽样参数",
        ),
        Table(
            "表 3-1",
            ("方法", "估计叶片数/片", "相对模拟真值偏差", "重复变异系数"),
            (
                (
                    "简单均值外推",
                    str(simple.rounded_estimate),
                    f"{simple.bias_percent:.2f}%",
                    f"{simple.cv_percent:.1f}%",
                ),
                (
                    "分层加权外推",
                    str(stratified.rounded_estimate),
                    f"{stratified.bias_percent:.2f}%",
                    f"{stratified.cv_percent:.1f}%",
                ),
                (
                    "遮挡校正外推",
                    str(corrected.rounded_estimate),
                    f"{corrected.bias_percent:.2f}%",
                    f"{corrected.cv_percent:.1f}%",
                ),
            ),
            "三种估算方法的模拟结果比较",
        ),
    )

    chapters = (
        Chapter(
            "绪论",
            (
                Section(
                    "研究背景与问题提出",
                    _paragraphs(
                        "叶片是树冠中数量多、空间分布不均且容易相互遮挡的器官。若逐片清点，虽然概念直接，却会破坏树体并消耗大量时间；若只观察树冠外缘，又会遗漏内部叶片。因此，本演示把“单株有多少片叶”转化为“如何以有限、可复核的局部记录推断总体”的方法问题。研究对象不是现实果园中的某棵树，而是参数完整的虚构树体，重点在于展示问题定义、抽样、计算和报告之间的逻辑联系。",
                        "已有的虚构教学文献把树冠测量分为几何包络、局部密度和器官计数三个层次，并指出局部密度必须与其代表面积相匹配[1]。据此，本文不把一个样方的平均数直接乘到整株，而是先承认不同高度的枝叶密度存在差异，再为各层分配独立权重。这样的安排既能说明分层抽样的必要性，也便于在后文逐层追踪误差来源。",
                        "本研究设定的核心问题包括三个方面：第一，怎样划分树冠才能兼顾操作简便与结构差异；第二，怎样处理边界叶片和遮挡叶片，避免不同观察者采用隐含规则；第三，怎样把局部计数外推为整树结果并给出可理解的不确定性。三个问题分别对应空间设计、记录规则和计算模型，任何一个环节缺失都会使最终数字难以解释。",
                    ),
                ),
                Section(
                    "研究目标与内容",
                    _paragraphs(
                        "研究目标是形成一套演示性估算方案，使读者仅依据正文、图表和附录即可重复计算。为此，本文统一树冠坐标，规定样方面积与边界判定，设置三轮模拟观测，并保留从原始计数到校正值的中间量。最终结果不仅报告一个整数，还同时报告方法间差异、重复变异和参数扰动范围，以防单一数字造成不恰当的精确感。",
                        "围绕目标，研究内容依次展开。第二章说明虚构树体参数、树冠分层和样方记录方法；第三章给出面积校正、分层加权、整树合计及误差评估；第四章解释结果、适用边界和演示价值。附录提供字段字典和复算示例，使正文中概括的计算步骤能够落到具体记录上。",
                        "本文有意采用较少但定义明确的变量。层别只设上、中、下三级，样方总数为六个，每轮观测使用相同位置；可见比例按层确定，表面积权重之和严格等于一。简化并非声称真实树冠只有这些特征，而是为了让每一项假设都能在有限篇幅中被检查，并为后续排版演示提供稳定内容。",
                    ),
                ),
                Section(
                    "技术路线与论文结构",
                    _paragraphs(
                        "技术路线从建立模拟真值开始。先设定整株共有4320片叶，再依据24%、46%和30%的结构权重分配潜在叶量；随后生成受可见性和边界规则影响的样方记录，最后只使用记录值估算总体。模拟真值只用于评估偏差，不进入估算公式，从而避免把答案预先写入过程。",
                        "论文结构遵循“为何估算—如何观测—如何计算—如何解释”的顺序。读者可先从图2-1理解空间布点，再结合表2-1核对参数；随后通过图3-1确认数据流向，并以表3-1比较方法。各组成部分互相引用但不互相替代：图强调关系，表给出数值，正文解释假设，附录保存细节。",
                        _DISCLOSURE,
                    ),
                ),
            ),
            paragraphs=_paragraphs(
                "本章的叙述范围限定在研究问题和演示设计，不提前使用后续结果。问题边界通过四项排除条件保持清晰：不比较现实品种，不评价真实管理措施，不采集真实参与者信息，也不把虚构参考文献包装成外部证据。所有术语在首次出现时按案例内部含义使用，例如“真值”专指生成模拟记录时预先设置、仅用于核对偏差的4320片，而不是通过现实清点获得的客观值。",
                "为了让章节之间形成连续推理，本章提出的每个问题都在后文获得对应材料。空间代表性问题由第二章的三层六样方设计处理，遮挡问题由可见比例校正处理，结果可信度问题由第三章的方法比较和敏感性分析处理，误用风险则在第四章与附录中再次声明。这样的映射可防止绪论提出宏大目标而正文只完成局部计算。",
            ),
            number=1,
        ),
        Chapter(
            "材料设定与抽样方法",
            (
                Section(
                    "虚构树体与模拟数据生成",
                    _paragraphs(
                        "演示树体编号为AU-APPLE-SIM-01，设定树高3.6 m、最大冠幅3.2 m、垂直冠层有效高度2.7 m。树冠被视为近似椭球包络，但局部叶片密度不服从均匀分布：中层承载较多结果枝，叶片最密；上层受光充分但有效体积较小；下层枝条较长而局部空隙较多。所有尺寸仅是构造模拟记录的输入，不对应现实品种或栽培制度。",
                        "模拟数据生成分两步。第一步依据预设层权重建立无观测误差的潜在叶量，第二步施加遮挡、边界判定和小幅重复计数差异。虚构方法手册建议在演示中分离“总体结构参数”和“观察过程参数”，以免把树体差异误写成计数误差[2]。本文因此分别保存表面积权重、可见比例和轮次扰动。",
                        "三轮观测的扰动采用固定序列而非随机抽样，以保证每次构建演示文档都得到相同结果。第一轮略低估中层，第二轮接近设定均值，第三轮略高估下层。确定性设置牺牲了对随机过程的逼真模拟，却换来可重复的测试条件，符合本项目验证排版、引用、图像和表格完整性的目的。",
                    ),
                ),
                Section(
                    "树冠分层与样方布设",
                    _paragraphs(
                        "以树冠有效高度的三等分点作为初始边界，再依据主枝交叠位置微调，形成上、中、下三层。每层布置两个0.25 m²样方，方位交错选择，使六个样方不过度集中在同一侧。样方中心固定于枝组参考点，重复观测时不重新选择位置，从而把轮次差异主要限制在识别和记录环节。",
                        "图2-1以原创示意方式表示分层边界、方位和六个样方中心。图形只表达抽样关系，不按真实树体比例绘制。上层样方位于相对开阔的东北与西北区域，中层覆盖东西两侧的高密度枝组，下层覆盖东南与西南延伸枝。这样的交错布点用于演示空间平衡，并不构成现实果树抽样规范。",
                        "表2-1列出后续计算需要的全部层级参数。表面积权重0.24、0.46和0.30之和为1；可见比例分别为0.91、0.82和0.88。中层可见比例最低，与其叶片密集、交叠较多的设定一致。样方数和面积保持一致，使层间比较主要反映密度与可见性，而不是不同的抽样投入。",
                        "每个样方在观察前被划分为四个相等子区，记录顺序固定为左上、右上、左下、右下。固定顺序可减少跳跃计数和重复计数，子区小计相加后必须与样方总计一致。若发现不一致，记录不进入外推，而是返回原始标记逐项核对。该规则把简单的算术校验嵌入现场记录流程。",
                    ),
                ),
                Section(
                    "计数口径与质量控制",
                    _paragraphs(
                        "完整叶片按叶柄着生点位于样方内计一片；着生点恰在上边或左边界计入，在下边或右边界不计入，形成单边纳入规则。仅看到叶尖而无法确认着生关系的对象记为“待校正遮挡叶”，不直接加入完整叶片小计。破损叶只要能确认独立叶柄仍计一片，重叠叶则按可辨识叶柄分别计数。",
                        "虚构的重复计数研究指出，边界规则若未书面化，会使同一样方的小计产生方向性差异[3]。本文在每轮观测前使用十个训练标记检查规则理解，要求边界分类一致率达到90%后才开始正式记录。训练标记同样是模拟内容，其功能是说明质量控制应在数据生成前执行，而不是在结果异常后临时修补。",
                        "质量控制包括四项：子区和与样方总计一致；六个样方编号齐全且不重复；可见比例位于0与1之间；轮次变化超过15%时触发复核。复核只检查抄录、边界和遮挡标签，不以接近预设真值为目标。这样可避免为了获得“好看结果”而反向调整原始记录。",
                        "完成核对后，记录按“树号—层别—方位—轮次—子区”形成唯一键。附录给出字段说明和一组复算样例。任何汇总值都应能回到唯一键对应的原始条目；若只能找到表格总数而找不到局部来源，则该结果不被视为可审计数据。",
                    ),
                ),
            ),
            paragraphs=_paragraphs(
                "材料设定采用“参数表先于结果表”的组织方式。树高、冠幅、样方面积、层权重和可见比例在查看估算结果之前即被固定，后续计算不得因偏差大小而修改这些输入。若需要展示另一套假设，应建立新的模拟情景并保留原情景，而不是覆盖数值。该原则使表2-1既是方法说明，也是防止事后调参的版本边界。",
                "六个样方的角色并不相同。上层样方主要检验稀疏区域是否被整体平均掩盖，中层样方承载高密度与强遮挡的组合，下层样方用于观察较大表面积但较低局部密度的贡献。方向交错则避免某一侧在每一层重复出现。尽管这些安排来自虚构设定，它们仍展示了抽样设计应让每个位置具有明确代表对象，而不是只追求记录数量。",
            ),
            number=2,
        ),
        Chapter(
            "估算模型与模拟结果",
            (
                Section(
                    "局部计数校正与分层外推",
                    _paragraphs(
                        "每个样方的基础计数为四个子区按单边边界规则纳入的叶片数之和。遮挡线索数表示已看到但可能对应未完全显露叶片组的标记数；校正有效计数等于基础计数加上“遮挡线索数×（1÷层级可见比例−1）”。校正密度再由有效计数除以0.25 m²得到。这样只有遮挡线索对应部分接受可见比例校正，而不是把全部基础计数重复放大。",
                        "分层叶量由层平均密度、整株等效面积尺度和层权重共同确定。本案例把整株等效尺度固定为11.004869 m²，并与0.25 m²样方面积、三层权重及可见比例一并列入附录表A-3。虚构统计说明建议在教学案例中保留归一化步骤，因为它能明确权重只分配总体而不凭空增加观测信息[4]。",
                        "简单均值外推忽略层别和遮挡，把六个样方的基础密度平均后扩展到整树；分层加权外推使用层权重但不做可见比例校正；遮挡校正外推同时使用两类参数。三种方法共享同一组原始记录，差异只来自模型假设，因此表3-1中的结果可用于观察每个附加步骤带来的变化。",
                        "最终推荐值采用三轮遮挡校正结果的算术平均并四舍五入到整数片。中间计算保留两位小数，最后一步才取整，避免逐层取整误差累积。估计值4286片与模拟真值4320片相差34片，偏差为-0.79%。由于输入是固定模拟序列，这一偏差只描述案例内部表现，不能外推到真实测量。",
                    ),
                ),
                Section(
                    "方法比较与结果解释",
                    _paragraphs(
                        "表3-1显示，简单均值外推得到4018片，低估6.99%；加入分层权重后得到4172片，低估缩小为3.42%；进一步校正遮挡后得到4286片，偏差降至-0.79%。结果方向与案例设定一致：中层既权重大又可见比例低，忽略其中任一特征都会使整株估计偏低。",
                        "重复变异系数从5.8%降至3.1%，并不意味着模型自动消除了观察误差，而是因为分层汇总防止单个高密度样方对总体均值产生过强影响。遮挡校正还把部分轮次差异解释为可见性差异。若真实应用中可见比例估计不稳定，这一优势可能消失，因此不能只依据本表选择现实方法。",
                        "图3-1把计算流程划分为四个主步骤和一个误差评估回路。箭头表示数据处理顺序，不表示因果证明。每一步都产生可保存的中间结果：分层编号表、样方计数表、校正密度表和分层外推表。保存中间结果能够定位异常来自输入、参数还是公式，而不是在最终总数出现偏差时重新检查全部过程。",
                        "结果报告采用整数叶片数，同时保留百分比指标。整数便于回答研究问题，百分比便于跨方法比较。两种表达必须同时解释：4286片看似精确，但其合理含义是当前模拟规则下的中心估计；3.1%的重复变异和后续敏感性区间提醒读者，该数字周围仍存在方法不确定性。",
                    ),
                ),
                Section(
                    "不确定性与敏感性分析",
                    _paragraphs(
                        "多因素情景敏感性包络包含三类确定性情景。可见比例情景取三层各自上下0.03的笛卡尔积，因此每个情景同时扰动三层比例；层权重情景在保持总和为1的条件下把0.02从一层转移到另一层；基础计数情景则同时对每个样方增加或减少一片。三类情景分别重新计算整株结果，用于描述预设组合下的结果范围。",
                        f"虚构误差传播指南主张把参数范围与数据来源并列报告，而不只给出最终区间[5]。按照这一原则，本案例的多因素情景敏感性包络为{sensitivity.rounded_bounds[0]}至{sensitivity.rounded_bounds[1]}片，其中可见比例组合、层间0.02权重转移和每个样方基础计数增减1片均按附录公式重新计算。该区间不表示某一概率覆盖率，只是预设情景组合下的确定性包络。",
                        f"留一层分析以完整数据的4286片为基准，去除一层后使用其余两层的全部观测并重新归一权重。去除上层时估计变为{layer_omissions['上层'].rounded_estimate}片，变化为{layer_omissions['上层'].rounded_change:+d}片；去除中层时变为{layer_omissions['中层'].rounded_estimate}片，变化为{layer_omissions['中层'].rounded_change:+d}片；去除下层时变为{layer_omissions['下层'].rounded_estimate}片，变化为{layer_omissions['下层'].rounded_change:+d}片。上层观测在当前加权组合中拉低整株估计，中层和下层观测则都拉高整株估计，且三个删除情景均产生数百片变化，不能据此声称下层影响很小或中层是唯一主要来源。",
                        f"综合偏差、重复变异与敏感性结果，本文把4286片作为演示推荐值，并将{sensitivity.rounded_bounds[0]}至{sensitivity.rounded_bounds[1]}片作为敏感性包络同时呈现。该表述避免把模拟真值当作现实标准，也不把敏感性区间解释为概率覆盖区间。所有数字均可由附录表A-2原始记录、表A-3输入和公式复算。",
                    ),
                ),
            ),
            paragraphs=_paragraphs(
                "计算实现遵守从原始量到派生量的单向顺序。原始量包括子区计数、样方面积与层级标签；参数量包括层权重和可见比例；派生量依次为样方总计、基础密度、校正密度、层平均、层贡献和整树估计。任何派生量都不作为更早步骤的输入。按这一顺序保存记录，既方便人工复算，也便于后续软件为每个字段建立类型与范围校验。",
                "结果解释刻意区分“改善案例内偏差”和“证明方法普遍有效”。遮挡校正的偏差较小，是因为模拟生成过程确实包含了相应遮挡机制；如果生成机制改变，排序也可能改变。因此，表3-1只能说明三个模型在同一设定中的行为。把这一限制写入正文，可帮助演示论文保留科学语气，而不把内部一致性夸大为外部有效性。",
            ),
            number=3,
        ),
        Chapter(
            "讨论与结论",
            (
                Section(
                    "方法特点与适用边界",
                    _paragraphs(
                        "本方法的首要特点是可追踪。树冠层、样方、子区、轮次和校正参数都有明确位置，最终总数可以逆向分解。第二个特点是把空间异质性与观察可见性分开处理：层权重描述树冠结构，可见比例描述记录过程，两者不被混成一个经验系数。第三个特点是使用相同记录比较三个模型，便于教学展示假设变化如何影响结果。",
                        "方法边界同样明确。树冠分层依赖人为边界，固定样方可能遗漏层内变化，可见比例来自模拟设定，等效面积尺度也未经过现实标定。本文没有讨论季节变化、叶片脱落、枝条运动和品种差异，更没有验证不同观察者在真实环境中的一致性。因此，任何将4286片直接解释为现实苹果树典型叶量的做法都是错误的。",
                        "若把流程迁移到真实研究，应先通过独立破坏性清点或高质量成像建立验证样本，再估计可见比例并检验层权重；还应随机化样方位置、增加树体数量、记录观察者身份，并使用适合重复测量的统计模型。当前案例只提供字段和逻辑骨架，不提供可直接采用的参数。",
                    ),
                ),
                Section(
                    "演示价值与改进方向",
                    _paragraphs(
                        "作为论文内容演示，本案例同时包含双语题名与摘要、关键词、分级标题、连续图表编号、顺序引文、完整参考文献、附录和致谢。主题与数字保持内部一致，使排版测试不必依赖无意义占位文本。图像带有中文标签和替代文本，表格带有模拟注记，有助于检验文档的无障碍与隐私声明。",
                        "虚构开放教学规范提出，演示资料应同时标明来源性质、复算路径和禁止误用范围[6]。本文把模拟声明放在摘要、正文、表注和附录中，并避免使用真实人员、真实机构或真实果园名称。重复声明并非赘余，而是为了使被单独复制的图表或段落仍保留必要语境。",
                        "后续改进可以增加机器可读的原始记录文件、公式单元测试和自动图表编号，但不应为了展示技术而扩大无关范围。对内容本身而言，可增加不同树冠形态的对照模拟，检验固定三层结构何时失效；对呈现而言，可在生成文档后自动检查标题层级、图像尺寸、表格边框、交叉引用和分页位置。",
                    ),
                ),
                Section(
                    "主要结论",
                    _paragraphs(
                        "第一，针对本案例设定的空间异质性，树冠上、中、下分层比整冠简单平均更能保持局部记录与代表范围的对应关系。第二，可见比例校正弥补了中层叶片重叠造成的模拟低估，使结果从4172片调整为4286片。第三，重复观测与参数扰动表明，单一整数必须与变异指标和适用边界共同报告。",
                        "第四，完整估算链条需要的不只是公式，还包括稳定编号、边界规则、中间表、图示、数据声明和复算附录。只报告最终总数无法判断误差来自抽样、识别还是外推。本文的结构化内容把这些要素集中到一个虚构主题中，可用于后续生成约十二至十五页的演示论文并验证格式处理流程。",
                        "综上，分层样方与遮挡校正构成了一个逻辑闭合的单株叶片估算演示方案，但所得数值没有现实农业证据效力。研究目的已经达到：建立可读、可算、可检查且明确标注为模拟的论文内容，为文档格式与语义完整性测试提供稳定材料。",
                    ),
                ),
            ),
            paragraphs=_paragraphs(
                "讨论部分把可复算性视为结论的一部分，而不是排版附件。一个数字若缺少输入版本、边界口径和中间步骤，即使恰好接近模拟真值，也不能说明方法可靠。相反，具有清楚误差来源的轻微偏差更适合作为教学材料，因为读者能够提出具体改进。本文因此保留三种方法的差异，不把较差结果从报告中删除。",
                "本案例还强调内容安全与隐私边界。题名聚焦一般性的苹果树叶片估算，机构只使用明确虚构的苹果大学，人物以功能性小组名称出现，地点使用演示城，参考资料均标明虚构出版物。数据声明覆盖摘要、正文、表注、附录和致谢，使任何常见章节被单独查看时仍能辨认其模拟性质。这种冗余是有意的风险控制。",
            ),
            number=4,
        ),
    )

    references = (
        Reference(1, "苹果树结构教学组", "树冠局部密度与代表面积的演示模型", 2021, "虚构园艺方法学刊，5(2)：11-24"),
        Reference(2, "果园模拟数据工作室", "教学数据中结构参数与观察参数的分离", 2022, "模拟农业数据评论，3(1)：35-49"),
        Reference(3, "叶片计数规则研究小组", "边界判定对方形样方计数一致性的影响", 2023, "虚构植物测量，8(4)：101-116"),
        Reference(4, "树冠统计课堂项目", "分层权重归一化的可复算示例", 2024, "苹果大学虚构教材出版社，演示城，第44-67页"),
        Reference(5, "模拟误差传播委员会", "器官数量外推中的多因素情景敏感性包络", 2025, "虚构生物统计实践，2(3)：58-76"),
        Reference(6, "开放演示资料编写组", "教学型研究文档的来源声明与复算规范", 2026, "苹果大学虚构教材出版社，演示城，第9-28页"),
    )

    appendix = Appendix(
        "模拟记录字段与复算示例",
        _paragraphs(
            "附录说明：本附录中的编号、计数、比例和计算结果全部属于模拟数据。字段“树号”固定为AU-APPLE-SIM-01；“层别”取上层、中层或下层；“方位”记录样方相对树干的方向；“轮次”取R1、R2或R3；“子区计数”保存四个子区的完整叶片与按规则纳入的边界叶片之和。",
            "复算示例选取中层东侧样方R2。四个子区基础计数依次为23、25、24和22，合计94片；遮挡线索数为18，可见比例为0.82，因此校正有效计数为94+18×(1÷0.82−1)=97.95片，校正密度为97.95÷0.25=391.80片/m²。该值与中层另一样方密度取平均后，再乘以11.004869 m²等效尺度和0.46层权重，得到中层贡献。",
            "检查顺序为：先验证四个子区之和等于样方总计，再验证样方面积大于零、可见比例处于0与1之间，随后计算有效计数与校正密度。简单法按六样方基础计数均值外推，分层法按三层基础计数均值加权，校正法按三层有效计数均值加权；每轮分别计算后取三轮均值，最后才整数化。变异系数使用三轮结果的样本标准差（n−1）除以均值。",
            "数据使用限制：这些记录专门用于演示论文生成、格式审查和自动化测试。它们不对应真实树木或真实观测，不可与现实果园数据合并，不可用于产量、施肥、修剪、病虫害或其他农业决策。复制本附录时应保留本段及表格的模拟注记。",
            "轮次复算时，应为每一轮分别完成六个样方的校正与分层汇总，不能先把不同轮次的原始计数混合平均。前一种顺序保留轮次差异，能够计算重复变异；后一种顺序会在进入误差评估前抹平变化。若生成文档展示公式，分子、分母、单位和取整位置应与本说明一致，并在结果旁保留“片”作为计数单位。",
            "表格审查时，应确认标题中的编号与正文引用一致、表头能够独立说明字段、每行列数相同、模拟注记未被分页遗漏。图像审查时，应确认宽高比未被拉伸、中文标签可辨认、替代文本说明信息关系而不只是重复标题。上述检查服务于文档质量，不改变任何模拟数值。",
            "引用审查采用顺序覆盖规则：正文第一次出现的编号依次从1到6，每个编号恰好对应参考文献表中的一条完整记录，参考文献表不保留未被正文引用的项目。由于六条资料均为虚构，读者不应尝试在外部数据库检索；其作用是检验引文标记、文后列表和交叉对应是否完整。",
            "若后续渲染需要分页，可优先在章标题、图题、表题和附录标题前设置保持段落关系，而不通过插入大量空行控制版面。预计双语摘要、四章正文、两幅图、两张主表、参考文献、致谢和附录共同形成约十二至十五页内容；实际页数仍取决于模板字号、行距、页边距和图像缩放。",
            "最终交付前还应进行一次端到端核对：题名中的研究对象应始终为单株苹果树，摘要中的4286片、4320片、-0.79%和3.1%应与表3-1及结论一致，图2-1应只说明抽样空间，图3-1应只说明计算流程，附录示例应使用表2-1中的0.25 m²与0.82。若任一数字被修改，与之关联的摘要、正文、表格和复算说明都必须同步更新，不能只修正最先发现的位置。完成核对后，应再次生成两幅图片并比较文件摘要，确认相同输入得到相同PNG字节；还应重新扫描全部引文编号，防止内容扩写意外引入未列出的引用。这样，内容一致性、图像确定性与参考文献完整性可在同一轮验收中得到确认。",
        ),
        (
            Table(
                "表 A-1",
                ("字段", "类型", "示例", "校验规则"),
                (
                    ("树号", "文本", "AU-APPLE-SIM-01", "固定虚构标识"),
                    ("层别", "枚举", "中层", "上层/中层/下层"),
                    ("轮次", "枚举", "R2", "R1/R2/R3"),
                    ("可见比例", "小数", "0.82", "大于0且不大于1"),
                    ("基础计数", "整数", "94", "非负且等于子区和"),
                ),
                "模拟原始记录字段字典",
            ),
            Table(
                "表 A-2",
                (
                    "轮次",
                    "样方",
                    "层别",
                    "方位",
                    "子区1",
                    "子区2",
                    "子区3",
                    "子区4",
                    "基础计数",
                    "遮挡线索数",
                ),
                tuple(
                    (
                        row.round_id,
                        row.quadrat_id,
                        row.layer,
                        row.direction,
                        *(str(value) for value in row.subquadrant_counts),
                        str(row.base_count),
                        str(row.occlusion_cues),
                    )
                    for row in SIMULATED_OBSERVATIONS
                ),
                "18条模拟观测原始记录（3轮×6样方）",
            ),
            Table(
                "表 A-3",
                ("输入", "取值"),
                (
                    ("单样方面积/m²", "0.25"),
                    ("整株等效尺度/m²", "11.004869"),
                    ("模拟真值/片", "4320"),
                    ("上层权重/可见比例", "权重 0.24 / 可见比例 0.91"),
                    ("中层权重/可见比例", "权重 0.46 / 可见比例 0.82"),
                    ("下层权重/可见比例", "权重 0.30 / 可见比例 0.88"),
                    ("变异系数标准差", "样本标准差（n-1）"),
                ),
                "复算所需的等效尺度与模型输入",
            ),
        ),
    )

    acknowledgements = (
        "致谢：感谢苹果大学虚构写作实验室提供纯属虚构的论文结构设定，感谢模拟果园方法讨论班对字段命名、"
        "图表可读性和复算顺序提出演示性建议。上述名称不指向任何真实人员或机构，也不存在真实资助、真实试验场地或真实参与者。"
        "本文全部内容由演示目的构造；对模拟数字、虚构参考文献和原创示意图的任何误用，均违背本论文的明确限制。"
    )
    chapters, appendix = _compact_demo_content(chapters, appendix)

    return Thesis(
        title_zh="单株苹果树叶片数量的估算方法研究",
        title_en="Estimating the Number of Leaves on an Individual Apple Tree",
        abstract_zh=abstract_zh,
        abstract_en=abstract_en,
        keywords_zh=("叶片数量", "树冠分层", "样方抽样", "遮挡校正", "模拟数据"),
        keywords_en=(
            "leaf number",
            "crown stratification",
            "quadrat sampling",
            "occlusion correction",
            "simulated data",
        ),
        chapters=chapters,
        figures=figures,
        tables=tables,
        references=references,
        appendix=appendix,
        acknowledgements=acknowledgements,
        data_disclosure=_DISCLOSURE,
    )
