from __future__ import annotations

import streamlit as st


def metric_explainer(content: dict) -> None:
    with st.expander("What does this measure?"):
        st.markdown(f"**Definition**  \n{content['definition']}")
        st.markdown(f"**Interpretation**  \n{content['why_it_matters']}")
        if content.get("caveats"):
            st.markdown("**Caveat**")
            for caveat in content["caveats"]:
                st.markdown(f"- {caveat}")


def coverage_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        st.warning(warning)
