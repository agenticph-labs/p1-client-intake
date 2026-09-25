# Client Intake & Project Scoping Pipeline

[![Status: Live](https://img.shields.io/badge/status-live-22c55e.svg)](https://github.com/agenticph-labs/p1-client-intake)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An **n8n-like workflow automation** built in pure Python that simulates a consulting company's client intake and project scoping process. The pipeline ingests client inquiries, validates them, classifies the need, generates structured project scope documents, and outputs formatted reports — all in a single, auditable pass.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   CLIENT INTAKE PIPELINE                         │
├──────────┬──────────┬──────────┬───────────┬─────────────────────┤
│  STAGE 1 │ STAGE 2  │ STAGE 3  │  STAGE 4  │      STAGE 5        │
│  INGEST  │ VALIDATE │ CLASSIFY │   SCOPE   │      OUTPUT         │
├──────────┼──────────┼──────────┼───────────┼─────────────────────┤
│  JSON    │ Required │  Rule-   │ Template- │  Markdown Report    │
│  CSV     │ fields   │  based   │ based     │  + Summary Index    │
│  Dir     │ quality  │  keyword │ generation│                     │
│  walk    │ checks   │  matching│           │                     │
└──────────┴──────────┴──────────┴───────────┴─────────────────────┘
       │          │          │           │              │
       ▼          ▼          ▼           ▼              ▼
   Raw data   Clean     Category +  Full scope     ./output/
   records    records   confidence  document        *.md files
```

### Pipeline Stages

| Stage | Module | What It Does |
|-------|--------|-------------|
| **1. INGEST** | `client_intake_pipeline.ingest()` | Reads client records from JSON or CSV files. Auto-detects format by extension. Can accept a single file or a directory (walks recursively). |
| **2. VALIDATE** | `client_intake_pipeline.validate()` | Checks every record for 5 required fields (`id`, `name`, `industry`, `size`, `need`). Produces a clean/dirty split with error logging. |
| **3. CLASSIFY** | `client_intake_pipeline.classify()` | Applies a configurable keyword-based rule engine against the `need` and `research_notes` fields. Returns category, sub-category, confidence score (0–1), and estimated complexity (Low/Medium/High). |
| **4. SCOPE** | `client_intake_pipeline.generate_scopes()` | Fills a template engine with classification results to produce a structured project scope: objective, deliverables, tech stack, timeline, budget range, risk factors, and next steps. Templates exist for 8 service categories + a general fallback. |
| **5. OUTPUT** | `client_intake_pipeline.output()` | Renders each scope as a formatted Markdown file and writes a summary `_index.md` that links all reports. |

### Classification Categories

The system classifies client needs into these categories (configurable in `CLASSIFICATION_RULES`):

| Category | Example Sub-Categories |
|----------|----------------------|
| Digital Transformation | Supply Chain Digitization, Legacy Modernization |
| Healthcare IT | Patient Portal, Appointment Scheduling |
| Web Development | Booking Websites, Corporate Sites |
| CRM & Sales | CRM Implementation, Pipeline Automation |
| Compliance & KYC | KYC/AML Automation, Client Onboarding |
| E-commerce | Online Storefront, Payment Integration |
| SaaS / MVP | MVP Development, Platform Build |
| Retail Technology | POS Unification, Menu Management |
| Process Automation | General Workflow Automation |
| General Consulting | (fallback for unmatched needs) |

---

## Quick Start

### Prerequisites

- Python 3.10+
- No external dependencies (stdlib only)

### Usage (CLI)

```bash
# Process the bundled sample data (JSON + CSV = 7 clients)
python client_intake_pipeline.py

# Process a specific file
python client_intake_pipeline.py intake_data/sample_client.json

# Process all files in a directory
python client_intake_pipeline.py intake_data/

# Process multiple sources
python client_intake_pipeline.py my_clients.json my_clients.csv
```

### Usage (Web UI)

```bash
# Launch the Streamlit web dashboard
pip install -r requirements.txt
streamlit run streamlit_ui.py
```

### Sample Data

Two sample files are included:

- `intake_data/sample_client.json` — 5 clients covering Manufacturing, Healthcare, Landscaping, Finance, and Retail
- `intake_data/sample_client.csv` — 2 clients covering SaaS and Food & Beverage

---

## Output Structure

```
output/
├── _index.md                              # Summary index linking all scope reports
├── SCOPE-CLT-001_20250925_acme_manufacturing_corp.md
├── SCOPE-CLT-002_20250925_brightpath_healthcare.md
├── SCOPE-CLT-003_20250925_greenleaf_landscaping.md
├── SCOPE-CLT-004_20250925_pinnacle_financial_group.md
├── SCOPE-CLT-005_20250925_tidepool_retail.md
├── SCOPE-CLT-006_20250925_novatech_solutions.md
└── SCOPE-CLT-007_20250925_heritage_restaurant_group.md
```

Each report contains:
1. Client Information (table)
2. Need Classification (category, confidence, complexity)
3. Original Need Statement
4. Research Notes
5. Project Objective
6. Deliverables (8 structured items)
7. Recommended Technology Stack
8. Timeline & Budget Estimates
9. Risk Factors
10. Recommended Next Steps

---

## Programmatic API

```python
from client_intake_pipeline import run_pipeline, ingest, classify, generate_scopes, output

# Run the full pipeline on custom data
processed, errors = run_pipeline(["my_intake.json"])

# Or use individual stages
records = ingest("intake_data/sample_client.json")
valid, errs = validate(records)
classifications = classify(valid)
scopes = generate_scopes(valid, classifications)
files = output(scopes)
```

---

## Extending the System

### Adding Classification Rules

Edit `CLASSIFICATION_RULES` in `client_intake_pipeline.py`:

```python
CLASSIFICATION_RULES.append((
    "Cybersecurity",           # category
    "Security Audit",          # sub-category
    ["penetration test",       # trigger keywords
     "security audit",
     "vulnerability assessment"]
))
```

### Adding Scope Templates

Add an entry to `_SCOPE_TEMPLATES` with the same structure:

```python
_SCOPE_TEMPLATES["Cybersecurity"] = {
    "template_objective": "Conduct a comprehensive {sub_category} for {name}...",
    "tech_stack": [...],
    "duration_map": {"Low": "X", "Medium": "Y", "High": "Z"},
    "budget_map": {"Low": "$X", "Medium": "$Y", "High": "$Z"},
}
```

### Adding New Output Formats

Extend the `output()` function with format flags (`--pdf`, `--html`) using libraries like `reportlab` or `weasyprint`.

---

## Testing

```bash
# Run unit tests
python -m pytest tests/ -v

# Run integration test (processes all sample data)
python -m tests.test_integration
```

---

## Project Structure

```
p1-client-intake/
├── client_intake_pipeline.py   # Main pipeline (all stages)
├── intake_data/
│   ├── sample_client.json      # 5 sample clients (JSON)
│   └── sample_client.csv       # 2 sample clients (CSV)
├── output/                     # Generated reports (gitignored)
├── tests/
│   ├── test_pipeline.py        # Unit tests
│   └── test_integration.py     # Integration test
├── requirements.txt            # Dependencies (stdlib-only)
└── README.md                   # This file
```

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built as Portfolio Project 1 for Business Automation — [AgenticPH Labs](https://agenticph-labs.github.io/portfolio)*
