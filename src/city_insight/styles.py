"""页面自定义 CSS 样式（由 streamlit_app 以 unsafe_allow_html 注入）。"""

from __future__ import annotations

CUSTOM_CSS = """
<style>
    .main-header {
        font-size: 2.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px;
        padding: 1.3rem;
        color: white;
        text-align: center;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.25);
        height: 100%;
    }
    .metric-card h3 {
        font-size: 0.95rem;
        opacity: 0.9;
        margin-bottom: 0.4rem;
    }
    .metric-card h1 {
        font-size: 1.9rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .metric-card .sub {
        font-size: 0.75rem;
        opacity: 0.85;
        margin-top: 0.2rem;
    }
    .section-title {
        font-size: 1.6rem;
        font-weight: 600;
        color: #1a1a2e;
        border-left: 5px solid #667eea;
        padding-left: 1rem;
        margin: 2rem 0 1rem 0;
    }
    .insight-box {
        background: #f8f9ff;
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #e0e5ff;
        margin: 1rem 0;
    }
    .info-badge {
        display: inline-block;
        background: #eef2ff;
        color: #4f46e5;
        border-radius: 999px;
        padding: 0.25rem 0.9rem;
        font-size: 0.8rem;
        margin-right: 0.5rem;
    }
    .footer {
        text-align: center;
        padding: 2rem;
        color: #999;
        font-size: 0.85rem;
    }
    [data-testid="stSidebar"] .sidebar-version {
        font-size: 0.75rem;
        color: #999;
        text-align: center;
        padding-top: 1rem;
    }
</style>
"""
