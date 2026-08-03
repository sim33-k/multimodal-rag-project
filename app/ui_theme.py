"""Custom styling for the Streamlit frontend.

Deliberately narrow in scope. The base palette - widgets, sidebar, tabs, inputs -
is set in .streamlit/config.toml, which is the mechanism Streamlit provides for
theming and the only one that reliably covers its own components. This file adds
styling for the handful of custom elements the app renders itself: the page
header, result cards, the answer panel and the retrieval evidence block.

Every rule here sets an explicit colour rather than inheriting one. An earlier
version left text colours to Streamlit, which made the whole page unreadable on a
machine set to dark mode: light body text on a light custom background.
"""

import streamlit as st

PALETTE = {
    "teal_deep": "#073B3A",
    "teal": "#0E7C7B",
    "teal_bright": "#14A0A0",
    "terracotta": "#C75B39",
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

/* Page header */
.hero {{
    background: linear-gradient(120deg, var(--teal-deep) 0%, var(--teal) 65%,
                var(--teal-bright) 100%);
    padding: 1.5rem 1.8rem;
    border-radius: 12px;
    margin-bottom: 1.4rem;
}}
.hero h1 {{
    margin: 0;
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #FFFFFF;
}}
.hero p {{
    margin: 0.35rem 0 0;
    font-size: 0.95rem;
    color: rgba(255, 255, 255, 0.9);
}}

/* Result cards */
.card {{
    background: #FFFFFF;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.9rem 1.05rem;
    margin-bottom: 0.85rem;
}}
.card h3 {{
    margin: 0 0 0.15rem;
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--teal-deep);
}}
.card .sub {{
    font-size: 0.85rem;
    color: var(--muted);
    margin-bottom: 0.55rem;
}}
.card .blurb {{
    font-size: 0.88rem;
    line-height: 1.55;
    color: var(--ink);
}}
.card .blurb b {{
    color: var(--teal-deep);
}}

/* Metadata chips */
.chip {{
    display: inline-block;
    padding: 0.15rem 0.58rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    margin: 0 0.3rem 0.35rem 0;
    background: #E4F0F0;
    color: #0B5F5E;
    border: 1px solid #BFDCDB;
}}
.chip.accent {{
    background: #F7E4DC;
    color: #A6472A;
    border-color: #E6C4B6;
}}

/* Generated answer panel */
.answer {{
    background: #FFFFFF;
    border: 1px solid var(--border);
    border-left: 4px solid var(--terracotta);
    border-radius: 0 10px 10px 0;
    padding: 1rem 1.2rem;
    margin-bottom: 1.1rem;
}}
.answer .label {{
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--terracotta);
    margin-bottom: 0.45rem;
}}
.answer p {{
    font-size: 0.93rem;
    line-height: 1.65;
    color: var(--ink);
    margin: 0 0 0.7rem;
}}
.answer p:last-child {{
    margin-bottom: 0;
}}

/* Retrieval evidence block */
.evidence {{
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
    font-size: 0.78rem;
    line-height: 1.5;
    white-space: pre-wrap;
    background: #FBF8F3;
    color: var(--ink);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.85rem 1rem;
    max-height: 380px;
    overflow-y: auto;
}}

/* Selected tab, which config.toml alone leaves fairly subtle */
.stTabs [aria-selected="true"] {{
    color: var(--teal) !important;
    font-weight: 700;
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
