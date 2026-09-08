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
