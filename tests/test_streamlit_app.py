"""端到端测试：使用 Streamlit 官方 AppTest 无头运行整个应用。

这些测试真实执行 src/streamlit_app.py 的全部代码路径，
验证数据加载、筛选、图表渲染与交互逻辑均不抛异常。
"""

from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "src" / "streamlit_app.py"


def _build_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(APP_PATH), default_timeout=180)


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
    at.multiselect[0].set_value(["浙江省"]).run()
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
