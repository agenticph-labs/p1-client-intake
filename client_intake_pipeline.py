"""
client_intake_pipeline.py — Client Intake & Project Scoping Pipeline
====================================================================

An n8n-like workflow automation that processes consulting client inquiries
through five pipeline stages:

  1. INGEST   →  Read client data from JSON or CSV files
  2. VALIDATE →  Ensure required fields and data quality
  3. CLASSIFY →  Categorize the client's need into a service type
  4. SCOPE    →  Generate a structured project scope document
  5. OUTPUT   →  Write formatted markdown report to disk

Usage:
    python client_intake_pipeline.py                         # processes both sample files
    python client_intake_pipeline.py intake_data/foo.json    # single file
    python client_intake_pipeline.py intake_data/            # whole directory

Author: Hermes Agent / AgenticPH Labs
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class ClientRecord:
    """A single client intake record — raw data from the form."""
    id: str
    name: str
    industry: str
    size: str
    location: str
    website: str
    need: str
    research_notes: str


@dataclass
class ClassifiedNeed:
    """The result of classifying a client's stated need."""
    category: str               # e.g. "Digital Transformation"
    sub_category: str           # e.g. "Supply Chain Digitization"
    confidence: float           # 0.0 – 1.0
    keywords: List[str]         # Trigger phrases that drove classification
    estimated_complexity: str   # Low / Medium / High


@dataclass
class ProjectScope:
    """A full project scope document generated from a classified need."""
    client: ClientRecord
    classification: ClassifiedNeed
    scope_id: str
    generated_at: str
    project_objective: str
    deliverables: List[str]
    tech_stack_suggestions: List[str]
    estimated_duration: str
    estimated_budget_range: str
    risk_factors: List[str]
    next_steps: List[str]


# ---------------------------------------------------------------------------
# 1. INGEST — Read client records from JSON or CSV sources
# ---------------------------------------------------------------------------

def ingest(source: str) -> List[ClientRecord]:
    """
    Load client records from a file or directory.

    Supported formats:
        - .json  →  expects a top-level key "clients" containing an array
        - .csv   →  header row maps to ClientRecord fields
        - directory →  recursively finds and processes all .json/.csv files
    """
    path = Path(source)

    if path.is_dir():
        records: List[ClientRecord] = []
        for child in sorted(path.iterdir()):
            if child.suffix.lower() in (".json", ".csv"):
                records.extend(ingest(str(child)))
        print(f"  [INGEST]  Loaded {len(records)} record(s) from directory '{source}'")
        return records

    if path.suffix.lower() == ".json":
        return _ingest_json(path)

    if path.suffix.lower() == ".csv":
        return _ingest_csv(path)

    raise ValueError(f"Unsupported file format: {path.suffix} (supported: .json, .csv)")


def _ingest_json(path: Path) -> List[ClientRecord]:
    with open(path, "r") as f:
        data = json.load(f)

    raw_records = data.get("clients", []) if isinstance(data, dict) else data
    records = [ClientRecord(**r) for r in raw_records]
    print(f"  [INGEST]  Loaded {len(records)} record(s) from '{path.name}'")
    return records


def _ingest_csv(path: Path) -> List[ClientRecord]:
    records: List[ClientRecord] = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(ClientRecord(**{k.strip(): v.strip() for k, v in row.items()}))
    print(f"  [INGEST]  Loaded {len(records)} record(s) from '{path.name}'")
    return records


# ---------------------------------------------------------------------------
# 2. VALIDATE — Data quality checks
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ["id", "name", "industry", "size", "need"]


def validate(records: List[ClientRecord]) -> Tuple[List[ClientRecord], List[Dict[str, Any]]]:
    """
    Check every record for missing required fields and basic quality.

    Returns (valid_records, error_log).
    """
    valid: List[ClientRecord] = []
    errors: List[Dict[str, Any]] = []

    for rec in records:
        missing = [f for f in REQUIRED_FIELDS if not getattr(rec, f, "").strip()]
        if missing:
            errors.append({
                "record_id": rec.id,
                "error": f"Missing required field(s): {', '.join(missing)}",
            })
            print(f"  [VALIDATE] ✗ {rec.id}: MISSING {missing}")
            continue
        valid.append(rec)
        print(f"  [VALIDATE] ✓ {rec.id}")

    print(f"  [VALIDATE] {len(valid)} passed, {len(errors)} failed\n")
    return valid, errors


# ---------------------------------------------------------------------------
# 3. CLASSIFY — Rule-based need categorisation
# ---------------------------------------------------------------------------

# Keyword-to-category mapping used by the classifier.
# Each entry: (category, sub_category, [keywords])
CLASSIFICATION_RULES: List[Tuple[str, str, List[str]]] = [
    ("Digital Transformation", "Supply Chain Digitization",    ["supply chain", "inventory", "purchase order", "logistics", "warehouse"]),
    ("Digital Transformation", "Legacy System Modernization",  ["legacy", "mainframe", "digitize", "paper form", "manual process"]),
    ("Healthcare IT",          "Patient Portal & Scheduling",  ["patient portal", "appointment", "ehr", "hipaa", "healthcare", "clinical"]),
    ("Web Development",        "Website with Booking",         ["website", "booking", "landing page", "web presence"]),
    ("CRM & Sales",            "CRM Implementation",           ["crm", "customer relationship", "lead tracking", "sales pipeline"]),
    ("Compliance & KYC",       "KYC/AML Automation",           ["kyc", "aml", "compliance", "onboarding", "identity verification", "know your customer"]),
    ("E-commerce",             "E-commerce Platform",          ["e-commerce", "ecommerce", "online store", "shopify", "payment processing", "shipping"]),
    ("SaaS / MVP",             "MVP Development",              ["mvp", "minimum viable", "saas platform", "prototype", "wireframes"]),
    ("Retail Technology",      "POS Unification",              ["pos", "point of sale", "menu", "restaurant", "centralized management"]),
    ("Process Automation",     "General Workflow Automation",  ["automate", "workflow", "integration", "api", "notification"]),
]


def _classify_single(record: ClientRecord) -> ClassifiedNeed:
    """Classify one client's need using keyword rules."""
    text = (record.need + " " + record.research_notes).lower()

    best_match: Optional[Tuple[str, str, float, List[str]]] = None

    for category, sub_category, keywords in CLASSIFICATION_RULES:
        found = [kw for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", text)]
        if found:
            score = len(found) / len(keywords)  # proportion of keywords matched
            if best_match is None or score > best_match[2]:
                best_match = (category, sub_category, score, found)

    if best_match is None:
        return ClassifiedNeed(
            category="General Consulting",
            sub_category="Uncategorised",
            confidence=0.3,
            keywords=[],
            estimated_complexity="Medium",
        )

    # Map confidence and complexity from score
    category, sub_category, score, keywords = best_match
    confidence = min(1.0, score + 0.2)  # Add a floor so a single keyword match isn't too low
    complexity = (
        "High" if confidence > 0.7 or "enterprise" in text or "hipaa" in text or "compliance" in text
        else "Low" if confidence < 0.4
        else "Medium"
    )

    return ClassifiedNeed(
        category=category,
        sub_category=sub_category,
        confidence=round(confidence, 2),
        keywords=keywords,
        estimated_complexity=complexity,
    )


def classify(records: List[ClientRecord]) -> List[ClassifiedNeed]:
    """Run classification on every valid client record."""
    results = [_classify_single(r) for r in records]
    for rec, cls in zip(records, results):
        print(
            f"  [CLASSIFY] {rec.id} → {cls.category} / {cls.sub_category}"
            f"  (confidence={cls.confidence}, complexity={cls.estimated_complexity})"
        )
    print(f"  [CLASSIFY] {len(results)} classified\n")
    return results


# ---------------------------------------------------------------------------
# 4. SCOPE — Generate a structured project scope for each client
# ---------------------------------------------------------------------------

_SCOPE_TEMPLATES = {
    "Digital Transformation": {
        "template_objective": (
            "Design and implement a {sub_category} solution for {name}, transitioning from "
            "manual or legacy processes to a modern digital platform that improves efficiency, "
            "data visibility, and operational control."
        ),
        "tech_stack": [
            "Cloud platform: AWS / Azure / GCP",
            "ERP / SCM platform: Odoo, SAP Business One, or NetSuite",
            "Integration layer: Apache Camel / MuleSoft / custom APIs",
            "Database: PostgreSQL with TimescaleDB for time-series inventory data",
            "BI dashboard: Metabase or Power BI",
        ],
        "duration_map": {
            "Low": "3–5 months",
            "Medium": "5–9 months",
            "High": "9–15 months",
        },
        "budget_map": {
            "Low": "$30K – $80K",
            "Medium": "$80K – $200K",
            "High": "$200K – $500K+",
        },
    },
    "Healthcare IT": {
        "template_objective": (
            "Develop a HIPAA-compliant {sub_category} for {name}, enabling secure patient "
            "self-service, streamlined scheduling, and seamless EHR integration while maintaining "
            "full regulatory compliance."
        ),
        "tech_stack": [
            "Framework: React / React Native (mobile)",
            "Backend: Node.js + FastAPI with HIPAA-compliant hosting",
            "EHR integration: FHIR / HL7 API connectors",
            "Auth: Auth0 or AWS Cognito with MFA",
            "Compliance: AWS HIPAA-eligible environment + annual audit",
            "Database: PostgreSQL (encrypted at rest)",
        ],
        "duration_map": {
            "Low": "4–6 months",
            "Medium": "6–10 months",
            "High": "10–16 months",
        },
        "budget_map": {
            "Low": "$50K – $100K",
            "Medium": "$100K – $300K",
            "High": "$300K – $600K",
        },
    },
    "Web Development": {
        "template_objective": (
            "Design, build, and launch a {sub_category} for {name}, incorporating modern "
            "design, responsive layouts, SEO optimisation, and integrated booking functionality."
        ),
        "tech_stack": [
            "Frontend: Next.js + Tailwind CSS",
            "CMS / backend: Sanity / Strapi headless CMS",
            "Booking engine: Cal.com embedded or custom Calendly API integration",
            "Hosting: Vercel or Netlify with CI/CD",
            "Analytics: Plausible + Google Search Console",
        ],
        "duration_map": {
            "Low": "4–8 weeks",
            "Medium": "2–4 months",
            "High": "4–6 months",
        },
        "budget_map": {
            "Low": "$10K – $25K",
            "Medium": "$25K – $50K",
            "High": "$50K – $100K",
        },
    },
    "CRM & Sales": {
        "template_objective": (
            "Implement and configure a {sub_category} system for {name}, tailored to their "
            "sales workflow, to centralise lead tracking, automate follow-ups, and provide "
            "actionable pipeline analytics."
        ),
        "tech_stack": [
            "CRM platform: Salesforce / HubSpot / Zoho (or Odoo CRM for self-hosted)",
            "Integration: Zapier or n8n for cross-app workflows",
            "Email automation: SendGrid / Mailgun + CRM native",
            "Reporting: Embedded BI (Metabase / Looker Studio)",
        ],
        "duration_map": {
            "Low": "1–2 months",
            "Medium": "2–4 months",
            "High": "4–8 months",
        },
        "budget_map": {
            "Low": "$15K – $40K",
            "Medium": "$40K – $100K",
            "High": "$100K – $200K",
        },
    },
    "Compliance & KYC": {
        "template_objective": (
            "Design and deploy an automated {sub_category} pipeline for {name}, reducing "
            "client onboarding time from weeks to hours while maintaining full SEC/FINRA "
            "regulatory compliance."
        ),
        "tech_stack": [
            "Identity verification: Onfido / Persona / Clear",
            "Document management: DocuSign + document OCR (AWS Textract / Tesseract)",
            "Backend: Python (FastAPI) with audit logging",
            "Database: PostgreSQL with column-level encryption",
            "Reporting: Automated suspicious activity reports (SARs)",
            "Infrastructure: AWS GovCloud or dedicated SOC 2 environment",
        ],
        "duration_map": {
            "Low": "3–5 months",
            "Medium": "5–8 months",
            "High": "8–14 months",
        },
        "budget_map": {
            "Low": "$60K – $120K",
            "Medium": "$120K – $300K",
            "High": "$300K – $700K",
        },
    },
    "E-commerce": {
        "template_objective": (
            "Launch a full-featured {sub_category} for {name}, migrating from existing "
            "marketplace channels to an owned storefront with inventory management, secure "
            "payments, and automated shipping workflows."
        ),
        "tech_stack": [
            "Platform: Shopify Plus (headless) or WooCommerce + custom theme",
            "Payment: Stripe / PayPal / local gateways",
            "Inventory: Stocky or TradeGecko integration",
            "Shipping: Shippo / ShipStation with real-time rates",
            "Marketing: Klaviyo email flows + Google Merchant Center",
        ],
        "duration_map": {
            "Low": "2–3 months",
            "Medium": "3–6 months",
            "High": "6–10 months",
        },
        "budget_map": {
            "Low": "$20K – $50K",
            "Medium": "$50K – $100K",
            "High": "$100K – $250K",
        },
    },
    "SaaS / MVP": {
        "template_objective": (
            "Engineer and ship a {sub_category} for {name}, converting wireframes and "
            "product specifications into a working SaaS platform with core features, "
            "auth, billing, and deployment infrastructure ready for beta users."
        ),
        "tech_stack": [
            "Frontend: Next.js + Tailwind CSS + shadcn/ui",
            "Backend: FastAPI or Node.js (Express)",
            "Database: PostgreSQL + Drizzle ORM or SQLAlchemy",
            "Auth: Clerk or Supabase Auth",
            "Payments: Stripe (subscription billing)",
            "AI/ML: OpenAI API or Anthropic Claude for task estimation",
            "Deployment: Docker + AWS ECS or Railway / Fly.io",
            "CI/CD: GitHub Actions + Sentry error tracking",
        ],
        "duration_map": {
            "Low": "2–4 months",
            "Medium": "4–6 months",
            "High": "6–10 months",
        },
        "budget_map": {
            "Low": "$40K – $80K",
            "Medium": "$80K – $150K",
            "High": "$150K – $300K",
        },
    },
    "Retail Technology": {
        "template_objective": (
            "Deploy a unified {sub_category} solution for {name}, consolidating multiple "
            "POS systems into a single platform with centralised inventory, menu management, "
            "and real-time analytics across all locations."
        ),
        "tech_stack": [
            "POS platform: Toast / Square for Restaurants / Lightspeed",
            "Central management: Custom dashboard (React + Node.js)",
            "Analytics: Google Looker Studio or Sigma Computing",
            "Integration: API connectors for each existing POS",
            "Cloud infrastructure: AWS or GCP",
        ],
        "duration_map": {
            "Low": "3–5 months",
            "Medium": "5–8 months",
            "High": "8–12 months",
        },
        "budget_map": {
            "Low": "$50K – $100K",
            "Medium": "$100K – $200K",
            "High": "$200K – $400K",
        },
    },
}

_GENERAL_TEMPLATE = {
    "template_objective": (
        "Provide strategic consulting and solution delivery for {name} based on their need: "
        "\"{need}\". Scope to be refined during discovery workshop."
    ),
    "tech_stack": [
        "To be determined during discovery phase",
    ],
    "duration_map": {
        "Low": "2–6 weeks",
        "Medium": "1–3 months",
        "High": "3–6 months",
    },
    "budget_map": {
        "Low": "$5K – $20K",
        "Medium": "$20K – $60K",
        "High": "$60K – $150K",
    },
}


def _generate_scope(record: ClientRecord, cls: ClassifiedNeed, idx: int) -> ProjectScope:
    """Create a ProjectScope for a single classified record."""
    template = _SCOPE_TEMPLATES.get(cls.category, _GENERAL_TEMPLATE)
    sub = cls.sub_category

    objective = template["template_objective"].format(
        name=record.name, sub_category=sub, need=record.need[:80]
    )

    duration = template["duration_map"].get(cls.estimated_complexity, "TBD")
    budget = template["budget_map"].get(cls.estimated_complexity, "TBD")

    # Generate tailored deliverables based on classification
    deliverables = [
        f"Project kick-off workshop and requirements gathering ({cls.estimated_complexity} engagement)",
        f"{sub} architecture design document",
        f"Implementation of {sub} solution",
        "Integration testing and quality assurance",
        "User acceptance testing (UAT) support",
        "Deployment and go-live support",
        f"Training materials and {record.size.lower()} team training sessions",
        "30-day post-launch support and knowledge transfer",
    ]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    scope_id = f"SCOPE-{record.id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    return ProjectScope(
        client=record,
        classification=cls,
        scope_id=scope_id,
        generated_at=now,
        project_objective=objective,
        deliverables=deliverables,
        tech_stack_suggestions=template["tech_stack"],
        estimated_duration=duration,
        estimated_budget_range=budget,
        risk_factors=[
            "Data migration complexity — legacy data quality must be assessed early",
            f"Stakeholder alignment across {record.location.split(',')[0]} operations",
            "Integration dependencies with existing third-party systems",
            "Resource availability — verify team capacity before kick-off",
            "Change management adoption rate among end users",
        ],
        next_steps=[
            "Schedule 90-minute discovery call to validate scope assumptions",
            "Share this scope document with the client for feedback",
            "Prepare formal proposal with pricing options (fixed-price vs. T&M)",
            "Identify 2–3 reference clients with similar engagements",
        ],
    )


def generate_scopes(
    records: List[ClientRecord], classifications: List[ClassifiedNeed]
) -> List[ProjectScope]:
    """Generate project scope documents for each classified client."""
    scopes = [_generate_scope(r, c, i) for i, (r, c) in enumerate(zip(records, classifications))]
    print(f"  [SCOPE]   {len(scopes)} scope document(s) generated\n")
    return scopes


# ---------------------------------------------------------------------------
# 5. OUTPUT — Write formatted markdown reports
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(os.path.join(os.path.dirname(__file__), "output"))


def _render_markdown(scope: ProjectScope) -> str:
    """Render a single scope document as a Markdown string."""
    c = scope.client
    cl = scope.classification

    lines = [
        f"# Project Scope: {c.name}",
        "",
        f"**Scope ID:** {scope.scope_id}  \n",
        f"**Generated:** {scope.generated_at}  \n",
        "",
        "---",
        "",
        "## 1. Client Information",
        "",
        f"| Field         | Value",
        f"|---------------|-------",
        f"| **Client ID** | {c.id}",
        f"| **Name**      | {c.name}",
        f"| **Industry**  | {c.industry}",
        f"| **Size**      | {c.size}",
        f"| **Location**  | {c.location}",
        f"| **Website**   | {c.website or 'N/A'}",
        "",
        "## 2. Need Classification",
        "",
        f"| Field                | Value",
        f"|----------------------|-------",
        f"| **Category**         | {cl.category}",
        f"| **Sub-category**     | {cl.sub_category}",
        f"| **Confidence**       | {cl.confidence:.0%}",
        f"| **Estimated Complexity** | {cl.estimated_complexity}",
        f"| **Trigger Keywords** | {', '.join(cl.keywords) if cl.keywords else 'General inquiry'}",
        "",
        "## 3. Original Need Statement",
        "",
        f"> {c.need}",
        "",
        "## 4. Research Notes",
        "",
        f"{c.research_notes}",
        "",
        "## 5. Project Objective",
        "",
        f"{scope.project_objective}",
        "",
        "## 6. Deliverables",
        "",
    ]
    for i, d in enumerate(scope.deliverables, 1):
        lines.append(f"  {i}. {d}")
    lines.extend([
        "",
        "## 7. Recommended Technology Stack",
        "",
    ])
    for t in scope.tech_stack_suggestions:
        lines.append(f"  - {t}")
    lines.extend([
        "",
        "## 8. Timeline & Budget",
        "",
        f"| Dimension | Estimate",
        f"|-----------|--------",
        f"| **Estimated Duration** | {scope.estimated_duration}",
        f"| **Estimated Budget**  | {scope.estimated_budget_range}",
        "",
        "## 9. Risk Factors",
        "",
    ])
    for r in scope.risk_factors:
        lines.append(f"  - {r}")
    lines.extend([
        "",
        "## 10. Recommended Next Steps",
        "",
    ])
    for n in scope.next_steps:
        lines.append(f"  - [ ] {n}")
    lines.extend([
        "",
        "---",
        "",
        f"*Report generated by the Client Intake & Project Scoping Pipeline*",
        "",
    ])
    return "\n".join(lines)


def output(scopes: List[ProjectScope], output_dir: str = "") -> List[Path]:
    """Write each scope to a markdown file. Returns list of file paths written."""
    out_dir = Path(output_dir or OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for scope in scopes:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", scope.client.name.lower().replace(" ", "_"))
        filename = f"{scope.scope_id}_{safe_name}.md"
        filepath = out_dir / filename
        content = _render_markdown(scope)
        with open(filepath, "w") as f:
            f.write(content)
        written.append(filepath)
        print(f"  [OUTPUT]  Wrote {filepath}")

    # Also write a summary index
    index_path = out_dir / "_index.md"
    with open(index_path, "w") as f:
        f.write(_render_index(scopes))
    written.append(index_path)
    print(f"  [OUTPUT]  Wrote summary index: {index_path}")

    print(f"  [OUTPUT]  {len(scopes)} report(s) + summary index written to '{out_dir}/'\n")
    return written


def _render_index(scopes: List[ProjectScope]) -> str:
    """Render a summary index markdown file linking all scopes."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Client Intake Pipeline — Scope Summary Index",
        "",
        f"**Generated:** {now}  \n",
        f"**Total Scopes:** {len(scopes)}  \n",
        "",
        "| # | Client | Industry | Category | Budget | Duration | File",
        "|---|--------|----------|----------|--------|----------|-----",
    ]
    for i, s in enumerate(scopes, 1):
        filename = f"{s.scope_id}_{s.client.name.lower().replace(' ', '_')}.md"
        # Sanitise for markdown link
        filename_sanitised = filename.replace(" ", "_").replace("(", "").replace(")", "")
        lines.append(
            f"| {i} | {s.client.name} | {s.client.industry} "
            f"| {s.classification.category} | {s.estimated_budget_range} "
            f"| {s.estimated_duration} | [{filename_sanitised}]({filename_sanitised})"
        )
    lines.extend([
        "",
        "---",
        "",
        f"*Generated by the Client Intake & Project Scoping Pipeline*",
    ])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(sources: List[str], output_dir: str = "") -> Tuple[int, int]:
    """
    Execute the full pipeline for one or more intake sources.

    Returns (total_processed, total_errors).
    """
    print("\n" + "=" * 70)
    print("  CLIENT INTAKE & PROJECT SCOPING PIPELINE")
    print("=" * 70)

    # --- Stage 1: Ingestion ---
    print("\n─── Stage 1: INGEST ────────────────────────────────")
    all_records: List[ClientRecord] = []
    for src in sources:
        all_records.extend(ingest(src))

    if not all_records:
        print("  [PIPELINE] ⚠ No records found. Exiting.")
        return 0, 0

    print(f"\n  Total raw records loaded: {len(all_records)}")

    # --- Stage 2: Validation ---
    print("\n─── Stage 2: VALIDATE ──────────────────────────────")
    valid_records, errors = validate(all_records)

    if not valid_records:
        print("  [PIPELINE] ⚠ No valid records remain. Exiting.")
        return 0, len(errors)

    # --- Stage 3: Classification ---
    print("\n─── Stage 3: CLASSIFY ──────────────────────────────")
    classifications = classify(valid_records)

    # --- Stage 4: Scope Generation ---
    print("\n─── Stage 4: SCOPE GENERATION ──────────────────────")
    scopes = generate_scopes(valid_records, classifications)

    # --- Stage 5: Output ---
    print("\n─── Stage 5: OUTPUT ────────────────────────────────")
    written = output(scopes, output_dir)

    print("=" * 70)
    print(f"  PIPELINE COMPLETE: {len(scopes)} scope(s) generated, {len(errors)} error(s)")
    print(f"  Output directory: {Path(output_dir or OUTPUT_DIR).resolve()}")
    print("=" * 70 + "\n")

    return len(scopes), len(errors)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    """Parse command-line arguments and run the pipeline."""
    # Default sources: the bundled sample data
    script_dir = Path(__file__).parent
    default_sources = [
        str(script_dir / "intake_data" / "sample_client.json"),
        str(script_dir / "intake_data" / "sample_client.csv"),
    ]

    # Use CLI args if provided, otherwise defaults
    sources = sys.argv[1:] if len(sys.argv) > 1 else default_sources

    output_dir = str(OUTPUT_DIR)
    run_pipeline(sources, output_dir)


if __name__ == "__main__":
    main()
