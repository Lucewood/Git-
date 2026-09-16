"""端到端测试：使用 Streamlit 官方 AppTest 无头运行整个应用。

这些测试真实执行 src/streamlit_app.py 的全部代码路径，
验证数据加载、筛选、图表渲染与交互逻辑均不抛异常。
"""

from __future__ import annotations

import re
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "src" / "streamlit_app.py"


def _build_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(APP_PATH), default_timeout=180)


def _card_value(at, title: str) -> str:
    """读取指标卡片（HTML）中的数值文本，用于断言推荐结果随筛选联动。"""
    for block in at.markdown:
        if f"<h3>{title}</h3>" in block.value:
            match = re.search(r"<h1>(.*?)</h1>", block.value)
            return match.group(1).strip() if match else ""
    return ""


def test_app_runs_without_exception():
    """应用默认状态应正常渲染。"""
    at = _build_app()
    at.run()
    assert not at.exception, f"应用抛出了异常: {at.exception}"
    assert len(at.title) > 0 or len(at.markdown) > 0


def test_province_filter_works():
    """选择浙江省后应用仍正常，且明细数据表仍存在。"""
    at = _build_app()
    at.run()
    province = next(ms for ms in at.multiselect if "选择省份" in ms.label)
    province.set_value(["浙江省"]).run()
    assert not at.exception, f"省份筛选后抛出了异常: {at.exception}"


def test_theme_switch_works():
    """切换图表主题后应用仍正常。"""
    at = _build_app()
    at.run()
    theme_box = next(sb for sb in at.selectbox if sb.label == "图表配色主题")
    theme_box.set_value("暖橙").run()
    assert not at.exception


def test_keyword_filter_empty_shows_warning():
    """关键词过滤到空结果时应显示警告而非崩溃。"""
    at = _build_app()
    at.run()
    at.text_input[0].set_value("不存在的城市名称xyz").run()
    assert not at.exception, f"空筛选状态抛出了异常: {at.exception}"
    assert len(at.warning) > 0


def test_ranking_direction_switch():
    """切换排名方向（Top/Bottom）后应用仍正常。"""
    at = _build_app()
    at.run()
    ranking_box = next(rb for rb in at.radio if rb.label == "查看方向")
    ranking_box.set_value("Bottom N（最低）").run()
    assert not at.exception


def test_keyword_regex_special_char_no_crash():
    """含正则特殊字符的关键词应按字面匹配，不得触发正则解析异常。"""
    at = _build_app()
    at.run()
    at.text_input[0].set_value("[").run()
    assert not at.exception, f"正则特殊字符关键词抛出了异常: {at.exception}"
    # 特殊字符没有匹配到任何城市，应显示空筛选警告而非崩溃
    assert len(at.warning) > 0


def test_forecast_section_city_and_horizon_interaction():
    """房价预测区块：切换城市并调整预测年数后页面仍正常渲染。"""
    at = _build_app()
    at.run()

    city_box = next(sb for sb in at.selectbox if "选择要预测的城市" in sb.label)
    city_box.set_value("成都").run()
    assert not at.exception, f"切换预测城市后抛出了异常: {at.exception}"

    at.run()
    horizon = next(sl for sl in at.slider if "预测年数" in sl.label)
    horizon.set_value(8).run()
    assert not at.exception, f"调整预测年数后抛出了异常: {at.exception}"


# ---------------------------------------------------------------------------
# 就业指导与产业推荐（爬虫数据 + 推荐引擎）
# ---------------------------------------------------------------------------
def test_career_section_skills_and_education_interaction():
    """就业指导区块：切换技能标签 / 学历 / 期望行业大类后页面仍正常。"""
    at = _build_app()
    at.run()

    skills = next(ms for ms in at.multiselect if "技能标签" in ms.label)
    skills.set_value(["Python", "数据分析", "机器学习"]).run()
    assert not at.exception, f"切换技能标签后抛出了异常: {at.exception}"

    education = next(sb for sb in at.selectbox if sb.label == "最高学历")
    education.set_value("硕士").run()
    assert not at.exception, f"切换学历后抛出了异常: {at.exception}"

    category = next(ms for ms in at.multiselect if "期望行业大类" in ms.label)
    category.set_value(["信息技术"]).run()
    assert not at.exception, f"限定行业大类后抛出了异常: {at.exception}"


def test_career_section_weight_and_cost_preference():
    """就业指导区块：调整偏好权重与低生活成本开关后页面仍正常。"""
    at = _build_app()
    at.run()

    salary_weight = next(sl for sl in at.slider if sl.label == "薪资待遇")
    salary_weight.set_value(5).run()
    assert not at.exception, f"调整偏好权重后抛出了异常: {at.exception}"

    toggle = next(tg for tg in at.toggle if "优先考虑低生活成本" in tg.label)
    toggle.set_value(True).run()
    assert not at.exception, f"切换低生活成本偏好后抛出了异常: {at.exception}"


def test_career_section_empty_skills_is_stable():
    """清空技能标签后应用仍正常（技能权重自动并入其余维度的分支）。"""
    at = _build_app()
    at.run()

    skills = next(ms for ms in at.multiselect if "技能标签" in ms.label)
    skills.set_value([]).run()
    assert not at.exception, f"清空技能标签后抛出了异常: {at.exception}"


def test_career_section_industry_panorama_selector():
    """城市产业全景：切换行业大类下拉框后页面仍正常。"""
    at = _build_app()
    at.run()

    picker = next(
        sb for sb in at.selectbox if "选择行业大类查看城市排名" in sb.label
    )
    options = list(picker.options)
    assert options, "行业大类下拉框不应为空"
    picker.set_value(options[-1]).run()
    assert not at.exception, f"切换行业大类后抛出了异常: {at.exception}"


def test_career_section_detail_view_switch():
    """推荐明细的多维视图（总览 / 五维得分 / 技能与岗位）均可切换。"""
    at = _build_app()
    at.run()

    views = next(r for r in at.radio if r.label == "明细视图")
    assert len(views.options) == 3, "推荐明细应提供三种视图"

    for option in list(views.options)[1:]:
        views.set_value(option).run()
        assert not at.exception, f"切换到「{option}」视图后抛出了异常: {at.exception}"
        views = next(r for r in at.radio if r.label == "明细视图")
        assert views.value == option


def test_career_section_city_structure_drilldown():
    """单城市产业结构：切换城市下拉框后页面仍正常。"""
    at = _build_app()
    at.run()

    drill = next(sb for sb in at.selectbox if "支柱产业构成" in sb.label)
    assert len(drill.options) > 0, "单城市产业结构下拉框不应为空"

    drill.set_value("三亚").run()
    assert not at.exception, f"切换单城市产业结构后抛出了异常: {at.exception}"
    picker = next(sb for sb in at.selectbox if "支柱产业构成" in sb.label)
    assert picker.value == "三亚"


def test_career_recommendation_follows_sidebar_filter():
    """就业推荐范围应随侧边栏省份筛选联动（缓存键包含筛选后的城市集）。"""
    at = _build_app()
    at.run()
    assert _card_value(at, "🎯 首选城市"), "默认应给出首选城市推荐"

    province = next(ms for ms in at.multiselect if "选择省份" in ms.label)
    province.set_value(["海南省"]).run()
    assert not at.exception, f"切换到海南省后抛出了异常: {at.exception}"

    assert _card_value(at, "📋 城市总数") == "3"
    assert _card_value(at, "🎯 首选城市") in {"海口", "三亚", "儋州"}


def test_career_section_blocks_render_once():
    """就业指导区块的说明面板、明细表与导出按钮不应重复渲染。"""
    at = _build_app()
    at.run()

    expanders = [item.label for item in at.expander]
    assert sum("数据来源、爬虫口径" in label for label in expanders) == 1
    assert sum("逐条推荐理由" in label for label in expanders) == 1

    tabs = [tab.label for tab in at.tabs]
    for expected in ("🎯 个性化推荐", "🏙️ 城市产业全景", "🧩 技能需求图谱"):
        assert tabs.count(expected) == 1, f"「{expected}」Tab 应且仅应出现一次"

    buttons = [button.label for button in at.get("download_button")]
    for expected in ("下载推荐结果", "下载城市级推荐", "下载技能需求榜"):
        assert sum(expected in label for label in buttons) == 1
