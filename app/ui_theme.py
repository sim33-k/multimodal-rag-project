"""Custom CSS for the Streamlit frontend.

Streamlit's default palette is a saturated red that reads as an error state and
makes every project built with it look identical. This replaces it with an
ocean-teal and terracotta scheme drawn from the subject matter, and restyles the
components the app actually uses: tabs, buttons, inputs and the result cards.
"""

import streamlit as st

PALETTE = {
    "teal_deep": "#073B3A",
    "teal": "#0E7C7B",
    "teal_bright": "#14A0A0",
    "terracotta": "#C75B39",
    "terracotta_soft": "#E2825B",
    "sand": "#F7F2EA",
    "ink": "#1C2321",
    "muted": "#5C6B68",
    "border": "#DED5C7",
}

CSS = f"""
<style>
:root {{
    --teal-deep: {PALETTE['teal_deep']};
    --teal: {PALETTE['teal']};
    --teal-bright: {PALETTE['teal_bright']};
    --terracotta: {PALETTE['terracotta']};
    --sand: {PALETTE['sand']};
    --ink: {PALETTE['ink']};
    --muted: {PALETTE['muted']};
    --border: {PALETTE['border']};
}}

.stApp {{
    background: linear-gradient(180deg, var(--sand) 0%, #FFFFFF 320px);
}}

/* Page header block */
.hero {{
    background: linear-gradient(120deg, var(--teal-deep) 0%, var(--teal) 65%,
                var(--teal-bright) 100%);
    padding: 1.6rem 1.9rem;
    border-radius: 14px;
    margin-bottom: 1.4rem;
    color: #FFFFFF;
}}
.hero h1 {{
    margin: 0;
    font-size: 1.85rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #FFFFFF;
}}
.hero p {{
    margin: 0.35rem 0 0;
    opacity: 0.88;
    font-size: 0.95rem;
}}

/* Result cards */
.card {{
    background: #FFFFFF;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin-bottom: 0.9rem;
    box-shadow: 0 1px 3px rgba(7, 59, 58, 0.06);
}}
.card h3 {{
    margin: 0 0 0.15rem;
    font-size: 1.08rem;
    color: var(--teal-deep);
}}
.card .sub {{
    color: var(--muted);
    font-size: 0.85rem;
    margin-bottom: 0.6rem;
}}
.card .blurb {{
    font-size: 0.9rem;
    color: var(--ink);
    line-height: 1.5;
}}

/* Category and metadata chips */
.chip {{
    display: inline-block;
    padding: 0.16rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    margin: 0 0.3rem 0.3rem 0;
    background: rgba(14, 124, 123, 0.10);
    color: var(--teal);
    border: 1px solid rgba(14, 124, 123, 0.22);
}}
.chip.accent {{
    background: rgba(199, 91, 57, 0.10);
    color: var(--terracotta);
    border-color: rgba(199, 91, 57, 0.24);
}}

/* The generated answer panel */
.answer {{
    background: #FFFFFF;
    border-left: 4px solid var(--terracotta);
    border-radius: 0 12px 12px 0;
    padding: 1.1rem 1.3rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 1px 3px rgba(7, 59, 58, 0.06);
    line-height: 1.65;
    font-size: 0.94rem;
}}
.answer .label {{
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--terracotta);
    margin-bottom: 0.5rem;
}}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0.4rem;
    border-bottom: 1px solid var(--border);
}}
.stTabs [data-baseweb="tab"] {{
    height: 2.6rem;
    padding: 0 1.05rem;
    background: transparent;
    border-radius: 8px 8px 0 0;
    font-weight: 600;
    color: var(--muted);
}}
.stTabs [aria-selected="true"] {{
    background: rgba(14, 124, 123, 0.09);
    color: var(--teal) !important;
}}

/* Buttons and inputs */
.stButton > button {{
    background: var(--teal);
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1.15rem;
    font-weight: 600;
    transition: background 0.15s ease;
}}
.stButton > button:hover {{
    background: var(--teal-deep);
    color: #FFFFFF;
}}
.stTextInput input, .stTextArea textarea {{
    border-radius: 8px;
    border: 1px solid var(--border);
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
    border-color: var(--teal-bright);
    box-shadow: 0 0 0 2px rgba(20, 160, 160, 0.15);
}}

section[data-testid="stSidebar"] {{
    background: #FFFFFF;
    border-right: 1px solid var(--border);
}}

/* Retrieval evidence block */
.evidence {{
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
    font-size: 0.78rem;
    line-height: 1.5;
    white-space: pre-wrap;
    background: #FBF8F3;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.85rem 1rem;
    max-height: 380px;
    overflow-y: auto;
}}

#MainMenu, footer {{visibility: hidden;}}
</style>
"""


def apply_theme() -> None:
    """Inject the stylesheet. Call once, immediately after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )
