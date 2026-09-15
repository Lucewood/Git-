"""行业知识库：行业大类 → 薪资基准 / 学历门槛 / 核心技能 / 典型岗位 / 产业名录。

用途：
1. 数据管道（scripts/crawl_industry.py）据此生成可爬取的支柱产业页面内容，
   并为每个城市派生「就业占比 / 平均月薪 / 需求景气指数 / 岗位年增速」；
2. 就业推荐引擎（career.py）据此给出「典型岗位方向」与「技能供需缺口」；
3. 前端（streamlit_app.py）据此渲染技能标签选择器与行业大类筛选器。

口径说明：薪资基准为 2024 年一线 / 新一线城市中位水平的演示口径（元/月），
其余城市按城市年收入水平线性缩放（见 industry_seed.seed_records），
仅为教学演示，非官方统计口径。

本模块仅依赖 stdlib，可被 pytest 与离线批处理脚本直接导入。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryMeta:
    """单个行业大类的元数据（薪资基准、学历门槛、景气区间、技能与岗位）。"""

    base_salary: float                  # 中位月薪基准（元/月，参考城市口径）
    education: str                      # 典型学历门槛
    demand_range: tuple[float, float]   # 人才需求景气指数区间（0-100）
    growth_range: tuple[float, float]   # 岗位年增速区间（%）
    skills: tuple[str, ...]             # 核心技能候选池（生成时抽取 4 项）
    industries: tuple[str, ...]         # 对应的具体支柱产业名录（生成时择一）
    occupations: tuple[str, ...]        # 典型岗位方向（推荐结果展示用）


# ---------------------------------------------------------------------------
# 16 个行业大类（覆盖全国 248 城支柱产业结构）
# ---------------------------------------------------------------------------
CATEGORY_META: dict[str, CategoryMeta] = {
    "信息技术": CategoryMeta(
        base_salary=16000,
        education="本科及以上",
        demand_range=(68.0, 92.0),
        growth_range=(2.5, 8.5),
        skills=("Python", "Java", "数据分析", "机器学习", "云计算", "系统架构"),
        industries=(
            "软件开发与信息服务", "互联网平台运营",
            "云计算与大数据服务", "人工智能与算法服务",
        ),
        occupations=(
            "软件开发工程师", "算法/数据工程师", "数据分析师", "云原生运维工程师",
        ),
    ),
    "半导体电子": CategoryMeta(
        base_salary=15500,
        education="本科及以上",
        demand_range=(66.0, 90.0),
        growth_range=(3.0, 9.5),
        skills=("微电子", "电路设计", "半导体工艺", "嵌入式C", "版图设计", "测试验证"),
        industries=(
            "集成电路设计与制造", "电子元器件制造",
            "光电显示器件制造", "智能终端组装制造",
        ),
        occupations=(
            "IC 设计工程师", "晶圆工艺工程师", "封装测试工程师", "硬件电路工程师",
        ),
    ),
    "高端装备制造": CategoryMeta(
        base_salary=10500,
        education="大专及以上",
        demand_range=(55.0, 80.0),
        growth_range=(0.5, 6.0),
        skills=("机械设计", "CAD/CAM", "PLC控制", "精益生产", "数控编程", "设备调试"),
        industries=(
            "通用设备制造", "工业机器人与自动化",
            "精密机械加工", "轨道交通装备制造",
        ),
        occupations=(
            "机械设计工程师", "工艺工程师", "数控编程工程师", "设备运维工程师",
        ),
    ),
    "汽车与新能源": CategoryMeta(
        base_salary=12500,
        education="本科及以上",
        demand_range=(65.0, 88.0),
        growth_range=(2.0, 9.0),
        skills=("三电系统", "嵌入式开发", "电池技术", "CAN总线", "自动驾驶", "整车标定"),
        industries=(
            "新能源汽车整车制造", "动力电池与储能",
            "汽车零部件制造", "智能网联汽车",
        ),
        occupations=(
            "整车研发工程师", "电池系统工程师", "智能驾驶工程师", "质量工程师",
        ),
    ),
    "能源化工": CategoryMeta(
        base_salary=10000,
        education="大专及以上",
        demand_range=(45.0, 70.0),
        growth_range=(-2.0, 3.0),
        skills=("化工工艺", "DCS控制", "电气自动化", "安全环保管理", "冶金工艺", "设备维护"),
        industries=(
            "石油化工与炼化", "煤化工与焦化",
            "电力与热力生产", "有色金属冶炼加工",
        ),
        occupations=(
            "化工工艺工程师", "电气自动化工程师", "安全管理工程师", "冶金工艺工程师",
        ),
    ),
    "生物医药": CategoryMeta(
        base_salary=11500,
        education="硕士及以上",
        demand_range=(60.0, 85.0),
        growth_range=(1.5, 7.0),
        skills=("药学", "分子生物学", "GMP规范", "临床研究", "实验室操作", "注册法规"),
        industries=(
            "化学药与生物药制造", "医疗器械制造",
            "医药研发外包(CRO)", "中药与健康产品",
        ),
        occupations=(
            "药物研发研究员", "临床试验监查员", "注册申报专员", "医药代表",
        ),
    ),
    "金融商务": CategoryMeta(
        base_salary=14500,
        education="本科及以上",
        demand_range=(50.0, 78.0),
        growth_range=(-1.0, 4.5),
        skills=("财务分析", "风险控制", "会计实务", "数据建模", "投资研究", "商务谈判"),
        industries=(
            "银行与保险服务", "证券与基金服务",
            "会计审计与咨询", "供应链金融与风控",
        ),
        occupations=("风险管理岗", "投资研究岗", "会计/审计师", "对公客户经理"),
    ),
    "现代物流": CategoryMeta(
        base_salary=8500,
        education="大专及以上",
        demand_range=(58.0, 82.0),
        growth_range=(0.5, 5.5),
        skills=("供应链管理", "仓储运营", "国际货代", "路径优化", "WMS系统", "关务合规"),
        industries=(
            "港口航运与货代", "仓储与供应链管理",
            "航空物流与快递", "冷链物流",
        ),
        occupations=(
            "供应链计划专员", "仓储运营主管", "国际货代操作", "物流方案工程师",
        ),
    ),
    "商贸零售": CategoryMeta(
        base_salary=8000,
        education="大专及以上",
        demand_range=(50.0, 75.0),
        growth_range=(-0.5, 4.5),
        skills=("电商运营", "用户增长", "直播营销", "商品采购", "客户关系管理", "跨境贸易"),
        industries=(
            "批发零售与商贸流通", "电子商务运营",
            "跨境贸易与出海", "专业市场与展会服务",
        ),
        occupations=(
            "电商运营专员", "品类采购经理", "跨境电商运营", "直播营销策划",
        ),
    ),
    "文化传媒": CategoryMeta(
        base_salary=9000,
        education="本科及以上",
        demand_range=(45.0, 72.0),
        growth_range=(-0.5, 5.0),
        skills=("内容策划", "短视频剪辑", "新媒体运营", "文案写作", "视觉设计", "数据分析"),
        industries=(
            "影视与短视频内容", "广告与品牌营销",
            "出版与数字媒体", "动漫游戏制作",
        ),
        occupations=("内容策划/编导", "短视频剪辑师", "新媒体运营", "品牌策划"),
    ),
    "文化旅游": CategoryMeta(
        base_salary=7500,
        education="大专及以上",
        demand_range=(40.0, 68.0),
        growth_range=(-1.5, 4.5),
        skills=("旅游产品设计", "酒店运营", "客户服务", "目的地营销", "外语能力", "活动策划"),
        industries=(
            "景区与主题公园运营", "酒店与民宿服务",
            "旅行社与旅游产品", "康养与休闲度假",
        ),
        occupations=(
            "景区运营管理", "酒店前厅/客房管理", "旅游产品策划", "导游/领队",
        ),
    ),
    "建筑地产": CategoryMeta(
        base_salary=9800,
        education="大专及以上",
        demand_range=(35.0, 60.0),
        growth_range=(-4.0, 1.5),
        skills=("结构设计", "BIM建模", "工程造价", "施工管理", "项目管理", "招投标"),
        industries=(
            "房屋建筑与市政工程", "房地产开发经营",
            "装饰装修与建材", "工程造价与咨询",
        ),
        occupations=("结构设计工程师", "工程造价师", "施工项目经理", "BIM 工程师"),
    ),
    "农业食品": CategoryMeta(
        base_salary=7800,
        education="大专及以上",
        demand_range=(42.0, 68.0),
        growth_range=(0.0, 4.0),
        skills=("食品工艺", "质量检测", "农业技术推广", "食品安全法规", "供应链管理", "品牌营销"),
        industries=(
            "食品加工与饮料制造", "特色农产品种植加工",
            "畜牧与水产养殖", "白酒与酿造",
        ),
        occupations=(
            "食品研发工程师", "品质管控(QA/QC)", "农业技术推广员", "供应链专员",
        ),
    ),
    "公共服务": CategoryMeta(
        base_salary=9500,
        education="本科及以上",
        demand_range=(48.0, 72.0),
        growth_range=(0.0, 4.0),
        skills=("公文写作", "行政能力", "医疗护理技能", "教育教学法", "心理咨询", "社区服务"),
        industries=(
            "医疗卫生服务", "教育与科研机构",
            "公务员与事业编", "社会保障与社区服务",
        ),
        occupations=("医师/护理岗", "中小学教师", "公务员/事业编", "社区工作者"),
    ),
    "教育培训": CategoryMeta(
        base_salary=8800,
        education="本科及以上",
        demand_range=(42.0, 66.0),
        growth_range=(-2.5, 3.0),
        skills=("教学设计", "课程研发", "演讲表达", "教育心理学", "教材编写", "学生管理"),
        industries=(
            "K12与素质教育", "职业与技能培训",
            "教育科技与内容", "留学与国际教育",
        ),
        occupations=("学科教师", "课程研发/教研", "职业技能培训师", "课程顾问"),
    ),
    "新材料与环保": CategoryMeta(
        base_salary=11000,
        education="硕士及以上",
        demand_range=(52.0, 78.0),
        growth_range=(1.0, 6.5),
        skills=("材料表征", "环境工程", "检测认证", "工艺优化", "实验室管理", "碳中和核算"),
        industries=(
            "新材料研发制造", "节能环保工程",
            "再生资源利用", "检验检测与认证",
        ),
        occupations=(
            "材料研发工程师", "环保工程师", "检测认证工程师", "工艺优化工程师",
        ),
    ),
}


# 行业大类列表（前端筛选项与图表分类轴共用，顺序与 CATEGORY_META 一致）
CATEGORIES: tuple[str, ...] = tuple(CATEGORY_META)

# 技能标签全集（前端技能选择器用；按行业大类顺序去重，保持稳定顺序）
SKILL_TAGS: tuple[str, ...] = tuple(
    dict.fromkeys(tag for meta in CATEGORY_META.values() for tag in meta.skills)
)

# 学历层次（由低到高）与序号映射，用于学历门槛匹配
EDUCATION_LEVELS: tuple[str, ...] = ("高中及以下", "大专", "本科", "硕士", "博士")
# 默认学历（前端表单初值与画像默认值）
DEFAULT_EDUCATION = "本科"
EDUCATION_ORDINAL: dict[str, int] = {
    level: idx for idx, level in enumerate(EDUCATION_LEVELS)
}


def normalize_education(education: str) -> str:
    """将学历文本归一化到 EDUCATION_LEVELS 中的一档。

    支持「本科及以上」这类门槛文本；无法识别时回退为「大专」。
    """
    text = str(education or "").strip()
    if not text:
        return "大专"
    if text in EDUCATION_ORDINAL:
        return text
    # 门槛文本（如「硕士及以上」）取其中出现的最高层次
    hits = [lvl for lvl in EDUCATION_LEVELS if lvl in text]
    if hits:
        return max(hits, key=lambda lvl: EDUCATION_ORDINAL[lvl])
    return "大专"


def education_gap(required: str, owned: str) -> int:
    """学历门槛差值：>0 表示用户学历低于门槛要求（需要提升的档数）。"""
    return (
        EDUCATION_ORDINAL[normalize_education(required)]
        - EDUCATION_ORDINAL[normalize_education(owned)]
    )


def occupations_for(category: str) -> tuple[str, ...]:
    """返回行业大类对应的典型岗位方向（未知大类返回空元组）。"""
    meta = CATEGORY_META.get(str(category).strip())
    return meta.occupations if meta else ()


def skills_for(category: str) -> tuple[str, ...]:
    """返回行业大类的核心技能候选池（未知大类返回空元组）。"""
    meta = CATEGORY_META.get(str(category).strip())
    return meta.skills if meta else ()

