"""Application-wide Streamlit styling."""

import streamlit as st

from ui_config import FONT_SIZES, UI_COLORS


def inject_custom_styles():
    st.markdown(
        f"""
        <style>
        .stApp {{ background: radial-gradient(circle at 15% 0%, #EAF0FF 0, transparent 30rem), {UI_COLORS["canvas"]}; color: {UI_COLORS["ink"]}; font-size: {FONT_SIZES["body"]}; }}
        [data-testid="stHeader"] {{ background: rgba(245, 247, 251, 0.94) !important; border-bottom: 1px solid {UI_COLORS["border"]}; }}
        [data-testid="stToolbar"], [data-testid="stDecoration"] {{ background: transparent !important; color: {UI_COLORS["ink"]} !important; }}
        .block-container {{ max-width: 1180px; padding-top: 2.25rem; padding-bottom: 3rem; }}
        h1, h2, h3 {{ color: {UI_COLORS["ink"]} !important; letter-spacing: -0.025em; }}
        h1 {{ font-size: {FONT_SIZES["app_title"]} !important; }}
        h2, h3 {{ font-size: {FONT_SIZES["section_title"]} !important; }}
        p, label, .stMarkdown {{ color: {UI_COLORS["ink"]}; }}
        [data-testid="stCaptionContainer"] {{ color: {UI_COLORS["muted"]} !important; font-size: {FONT_SIZES["caption"]}; }}
        [data-testid="stMetric"] {{ background: {UI_COLORS["surface"]}; border: 1px solid {UI_COLORS["border"]}; border-radius: 0.85rem; padding: 0.55rem 0.85rem; box-shadow: 0 8px 22px rgba(26, 43, 82, 0.06); }}
        .stButton > button {{ min-height: 2.65rem; border: 1px solid {UI_COLORS["border"]}; border-radius: 0.65rem; background: {UI_COLORS["surface"]}; color: {UI_COLORS["ink"]}; font-weight: 600; transition: all 160ms ease; }}
        .stButton > button:hover {{ border-color: {UI_COLORS["primary"]}; color: {UI_COLORS["primary"]}; transform: translateY(-1px); box-shadow: 0 7px 16px rgba(49, 87, 213, 0.14); }}
        .stButton > button[kind="primary"] {{ background: {UI_COLORS["primary"]}; border-color: {UI_COLORS["primary"]}; color: {UI_COLORS["primary_text"]}; }}
        .stButton > button[kind="primary"] * {{ color: {UI_COLORS["primary_text"]} !important; }}
        .stButton > button[kind="primary"]:hover {{ background: {UI_COLORS["primary_hover"]}; border-color: {UI_COLORS["primary_hover"]}; color: {UI_COLORS["primary_text"]}; }}
        .stFormSubmitButton > button {{ background: {UI_COLORS["primary"]}; border-color: {UI_COLORS["primary"]}; color: {UI_COLORS["primary_text"]} !important; font-weight: 600; }}
        .stFormSubmitButton > button * {{ color: {UI_COLORS["primary_text"]} !important; }}
        .stFormSubmitButton > button:hover {{ background: {UI_COLORS["primary_hover"]}; border-color: {UI_COLORS["primary_hover"]}; color: {UI_COLORS["primary_text"]} !important; }}
        .stTextInput input, .stTextArea textarea {{ background: rgba(255, 255, 255, 0.92) !important; border: 1px solid {UI_COLORS["border"]} !important; border-radius: 0.65rem !important; color: {UI_COLORS["ink"]} !important; }}
        .stTextInput input:focus, .stTextArea textarea:focus {{ border-color: {UI_COLORS["primary"]} !important; box-shadow: 0 0 0 3px rgba(49, 87, 213, 0.12) !important; }}
        [data-testid="stExpander"] {{ background: {UI_COLORS["surface"]}; border: 1px solid {UI_COLORS["border"]}; border-radius: 0.75rem; }}
        [data-testid="stForm"] {{ border: 0; padding: 0.2rem 0 0; }}
        hr {{ border-color: {UI_COLORS["border"]}; }}
        div[role="radiogroup"] label, div[role="radio"] {{ font-size: {FONT_SIZES["radio_option"]} !important; color: {UI_COLORS["ink"]} !important; }}
        div[role="radiogroup"] {{ gap: 0.45rem; }}
        .stRadio label, .stRadio div[role="radio"] {{ font-size: {FONT_SIZES["radio_option"]} !important; }}
        [class*="st-key-question_content"] {{ font-size: {FONT_SIZES["question"]}; font-weight: 600; line-height: 1.35; color: {UI_COLORS["ink"]}; background: {UI_COLORS["surface"]}; border-left: 4px solid {UI_COLORS["primary"]} !important; border-radius: 0.7rem; margin: 0.65rem 0 1rem; }}
        .stTextArea label {{ font-size: {FONT_SIZES["text_area_label"]} !important; font-weight: 600; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
