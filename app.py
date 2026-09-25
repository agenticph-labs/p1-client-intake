#!/usr/bin/env python3
"""streamlit_ui.py — Web UI for the Client Intake & Project Scoping Pipeline.

Usage:
    streamlit run streamlit_ui.py
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ── Reuse the pipeline module ──────────────────────────────────────────
from client_intake_pipeline import (
    ClientRecord,
    ingest,
    validate,
    classify,
    generate_scopes,
    output,
    _render_markdown,
    OUTPUT_DIR,
)

st.set_page_config(
    page_title="Client Intake & Scoping",
    page_icon="📋",
    layout="wide",
)

# ── Helpers ────────────────────────────────────────────────────────────


def _run_pipeline_on_single(record: ClientRecord) -> str:
    """Run the full pipeline on a single ClientRecord and return the
    rendered markdown scope document."""
    records = [record]
    valid, errors = validate(records)
    if not valid:
        return f"**Validation error:** {errors[0]['error'] if errors else 'Unknown'}"
    classifications = classify(valid)
    scopes = generate_scopes(valid, classifications)
    # Write to disk so the output/ directory stays in sync
    written = output(scopes)
    return _render_markdown(scopes[0])


# ── Industry / Size pick-lists ────────────────────────────────────────

INDUSTRIES = [
    "Manufacturing",
    "Healthcare",
    "Finance / Insurance",
    "Retail / E-commerce",
    "Technology / SaaS",
    "Services / Consulting",
    "Education",
    "Real Estate / Construction",
    "Food & Beverage",
    "Non-profit",
    "Other",
]

SIZES = [
    "Solo (1 employee)",
    "Small (2–10 employees)",
    "Small (10–50 employees)",
    "Mid-size (50–100 employees)",
    "Mid-size (100–500 employees)",
    "Enterprise (500+ employees)",
]

# ── UI ─────────────────────────────────────────────────────────────────

st.title("📋 Client Intake & Project Scoping")
st.markdown("Enter client information below and generate a structured project scope document.")

with st.form("intake_form"):
    col1, col2 = st.columns(2)

    with col1:
        name = st.text_input("Client Name *", placeholder="e.g. Acme Manufacturing Corp")
        industry = st.selectbox("Industry *", options=[""] + INDUSTRIES)
        size = st.selectbox("Company Size *", options=[""] + SIZES)
        location = st.text_input("Location", placeholder="e.g. Chicago, IL")

    with col2:
        website = st.text_input("Website", placeholder="https://...")
        need = st.text_area(
            "Client Need *",
            placeholder="Describe the client's problem statement...",
            height=100,
        )
        research_notes = st.text_area(
            "Research Notes",
            placeholder="Background, budget, competitors, timeline...",
            height=100,
        )

    submitted = st.form_submit_button("🚀 Generate Scope Document", type="primary", use_container_width=True)

if submitted:
    missing = []
    if not name.strip():
        missing.append("Name")
    if not industry.strip():
        missing.append("Industry")
    if not size.strip():
        missing.append("Size")
    if not need.strip():
        missing.append("Need")

    if missing:
        st.error(f"Please fill in the following required field(s): {', '.join(missing)}")
    else:
        client_id = f"CLT-{uuid.uuid4().hex[:4].upper()}"
        record = ClientRecord(
            id=client_id,
            name=name.strip(),
            industry=industry.strip(),
            size=size.strip(),
            location=location.strip() or "TBD",
            website=website.strip() or "",
            need=need.strip(),
            research_notes=research_notes.strip() or "No research notes provided.",
        )

        with st.spinner("Running pipeline (ingest → validate → classify → scope → output)..."):
            markdown = _run_pipeline_on_single(record)

        st.success(f"Scope document generated! (Client ID: {client_id})")
        st.markdown("---")
        st.markdown(markdown)

        # ── Download button ──
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", record.name.lower().replace(" ", "_"))
        filename = f"{record.id}_{safe_name}.md"
        st.download_button(
            label="📥 Download Scope Document (.md)",
            data=markdown,
            file_name=filename,
            mime="text/markdown",
            use_container_width=True,
        )
