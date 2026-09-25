"""
Tests for the Client Intake & Project Scoping Pipeline.
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

# Ensure the project root is on sys.path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client_intake_pipeline import (
    ClientRecord,
    ClassifiedNeed,
    ProjectScope,
    ingest,
    validate,
    classify,
    generate_scopes,
    output,
    _classify_single,
    _render_markdown,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_records() -> list:
    return [
        ClientRecord(
            id="CLT-T01",
            name="TestCorp",
            industry="Manufacturing",
            size="Mid-size (50–200)",
            location="Detroit, MI",
            website="https://testcorp.example.com",
            need="We need to digitize our supply chain tracking with real-time inventory visibility.",
            research_notes="Competitors have adopted ERP. Budget $100K.",
        ),
        ClientRecord(
            id="CLT-T02",
            name="IncompleteCo",
            industry="",
            size="Small (10–50)",
            location="Nowhere",
            website="",
            need="",
            research_notes="Missing fields.",
        ),
    ]


@pytest.fixture
def valid_record() -> ClientRecord:
    return ClientRecord(
        id="CLT-V01",
        name="ValidCorp",
        industry="Healthcare",
        size="Mid-size (100–500)",
        location="Boston, MA",
        website="https://valid.example.com",
        need="Need a HIPAA-compliant patient portal with appointment scheduling.",
        research_notes="Uses Athenahealth. IT team of 5.",
    )


# ── Tests: Data Model ────────────────────────────────────────────────────

class TestClientRecord:
    def test_creation(self):
        r = ClientRecord("A", "B", "C", "D", "E", "F", "G", "H")
        assert r.id == "A"
        assert r.name == "B"
        assert r.industry == "C"
        assert r.size == "D"
        assert r.location == "E"
        assert r.website == "F"
        assert r.need == "G"
        assert r.research_notes == "H"


# ── Tests: INGEST Stage ──────────────────────────────────────────────────

class TestIngest:
    def test_ingest_json(self):
        """Load sample JSON file."""
        path = os.path.join(os.path.dirname(__file__), "..", "intake_data", "sample_client.json")
        records = ingest(path)
        assert len(records) == 5
        assert all(isinstance(r, ClientRecord) for r in records)
        assert records[0].id == "CLT-001"

    def test_ingest_csv(self):
        """Load sample CSV file."""
        path = os.path.join(os.path.dirname(__file__), "..", "intake_data", "sample_client.csv")
        records = ingest(path)
        assert len(records) == 2
        assert all(isinstance(r, ClientRecord) for r in records)
        assert records[0].id == "CLT-006"

    def test_ingest_invalid_extension(self):
        with pytest.raises(ValueError, match="Unsupported file format"):
            ingest("data.txt")

    def test_ingest_directory(self):
        """Ingesting a directory should walk and combine all supported files."""
        path = os.path.join(os.path.dirname(__file__), "..", "intake_data")
        records = ingest(path)
        assert len(records) == 7  # 5 from JSON + 2 from CSV


# ── Tests: VALIDATE Stage ────────────────────────────────────────────────

class TestValidate:
    def test_all_valid(self, sample_records):
        valid, errors = validate(sample_records[:1])
        assert len(valid) == 1
        assert len(errors) == 0

    def test_missing_fields(self, sample_records):
        valid, errors = validate(sample_records)
        assert len(valid) == 1  # only CLT-T01 passes
        assert len(errors) == 1  # CLT-T02 fails
        assert errors[0]["record_id"] == "CLT-T02"
        assert "industry" in errors[0]["error"]
        assert "need" in errors[0]["error"]


# ── Tests: CLASSIFY Stage ────────────────────────────────────────────────

class TestClassify:
    def test_supply_chain(self):
        """Supply-chain keywords should map to Digital Transformation."""
        r = ClientRecord("T", "C", "Mfg", "S", "L", "", "Need supply chain digitization", "")
        cls = _classify_single(r)
        assert cls.category == "Digital Transformation"
        assert "supply chain" in cls.keywords

    def test_healthcare_hipaa(self):
        """HIPAA keywords should map to Healthcare IT."""
        r = ClientRecord("T", "C", "Health", "M", "L", "", "Need HIPAA-compliant patient portal", "")
        cls = _classify_single(r)
        assert cls.category == "Healthcare IT"
        assert "hipaa" in cls.keywords

    def test_ecommerce(self):
        """E-commerce keywords."""
        r = ClientRecord("T", "C", "Retail", "S", "L", "", "Need e-commerce with payment processing", "")
        cls = _classify_single(r)
        assert cls.category == "E-commerce"

    def test_mvp(self):
        """SaaS/MVP keywords."""
        r = ClientRecord("T", "C", "Tech", "S", "L", "", "Building an MVP for a SaaS platform", "")
        cls = _classify_single(r)
        assert cls.category == "SaaS / MVP"

    def test_general_fallback(self):
        """Unmatched needs should get General Consulting."""
        r = ClientRecord("T", "C", "Other", "S", "L", "", "I need a business plan written", "")
        cls = _classify_single(r)
        assert cls.category == "General Consulting"

    def test_batch_classify(self, sample_records):
        """Batch classify returns same count."""
        valid, _ = validate(sample_records)
        results = classify(valid)
        assert len(results) == len(valid)


# ── Tests: SCOPE Generation Stage ────────────────────────────────────────

class TestScopeGeneration:
    def test_scope_creation(self, valid_record):
        cls = _classify_single(valid_record)
        scopes = generate_scopes([valid_record], [cls])
        assert len(scopes) == 1
        scope = scopes[0]
        assert scope.client.id == "CLT-V01"
        assert scope.scope_id.startswith("SCOPE-")
        assert scope.estimated_duration != ""
        assert scope.estimated_budget_range != ""
        assert len(scope.deliverables) == 8
        assert len(scope.tech_stack_suggestions) >= 1
        assert len(scope.risk_factors) == 5
        assert len(scope.next_steps) == 4

    def test_duration_and_budget_vary_by_complexity(self, valid_record):
        """Complexity should drive different duration/budget values."""
        cls_low = ClassifiedNeed("Healthcare IT", "Portal", 0.3, ["portal"], "Low")
        cls_high = ClassifiedNeed("Healthcare IT", "Portal", 0.9, ["portal", "hipaa"], "High")
        s_low = generate_scopes([valid_record], [cls_low])[0]
        s_high = generate_scopes([valid_record], [cls_high])[0]
        assert s_low != s_high  # different budget/duration


# ── Tests: OUTPUT Stage ──────────────────────────────────────────────────

class TestOutput:
    def test_output_creates_files(self, valid_record):
        cls = _classify_single(valid_record)
        scopes = generate_scopes([valid_record], [cls])

        with tempfile.TemporaryDirectory() as tmp:
            paths = output(scopes, tmp)
            assert len(paths) == 2  # scope report + index
            for p in paths:
                assert os.path.exists(p)

            # Check content of the scope report
            report = [p for p in paths if p.name != "_index.md"][0]
            content = Path(report).read_text()
            assert "Project Scope: ValidCorp" in content
            assert "## 1. Client Information" in content
            assert "## 10. Recommended Next Steps" in content

    def test_render_markdown_has_all_sections(self, valid_record):
        cls = _classify_single(valid_record)
        scopes = generate_scopes([valid_record], [cls])
        md = _render_markdown(scopes[0])
        sections = [
            "Project Scope:",
            "## 1. Client Information",
            "## 2. Need Classification",
            "## 3. Original Need Statement",
            "## 4. Research Notes",
            "## 5. Project Objective",
            "## 6. Deliverables",
            "## 7. Recommended Technology Stack",
            "## 8. Timeline & Budget",
            "## 9. Risk Factors",
            "## 10. Recommended Next Steps",
        ]
        for sec in sections:
            assert sec in md


# ── Tests: Full Pipeline Integration ─────────────────────────────────────

class TestFullPipeline:
    def test_run_pipeline_with_json(self):
        """Run the full pipeline end-to-end with the sample JSON file."""
        from client_intake_pipeline import run_pipeline

        json_path = os.path.join(os.path.dirname(__file__), "..", "intake_data", "sample_client.json")
        with tempfile.TemporaryDirectory() as tmp:
            processed, errors = run_pipeline([json_path], output_dir=tmp)
            assert processed == 5
            assert errors == 0

            # Verify output files were created
            files = list(Path(tmp).glob("*.md"))
            assert len(files) == 6  # 5 reports + 1 index

    def test_run_pipeline_with_csv(self):
        """Run the full pipeline end-to-end with the sample CSV file."""
        from client_intake_pipeline import run_pipeline

        csv_path = os.path.join(os.path.dirname(__file__), "..", "intake_data", "sample_client.csv")
        with tempfile.TemporaryDirectory() as tmp:
            processed, errors = run_pipeline([csv_path], output_dir=tmp)
            assert processed == 2
            assert errors == 0
            files = list(Path(tmp).glob("*.md"))
            assert len(files) == 3  # 2 reports + 1 index
