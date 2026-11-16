from __future__ import annotations

from pathlib import Path

from roadops.data_lineage import (
    normalized_leaf_paths,
    validate_lineage_spec,
    validate_path_coverage,
    validate_tabular_field_coverage,
)


def test_normalized_leaf_paths_merges_list_item_schemas():
    payload = {
        "rows": [
            {"id": "a", "metrics": {"score": 1}},
            {"id": "b", "metrics": {"lower": 0}},
        ],
        "empty": [],
    }

    assert normalized_leaf_paths(payload) == {
        "rows[].id",
        "rows[].metrics.score",
        "rows[].metrics.lower",
        "empty[]",
    }


def test_path_coverage_supports_exact_and_prefix_rules():
    result = validate_path_coverage(
        {"status", "rows[].id", "rows[].metrics.score"},
        [
            {"path": "status", "match": "exact", "transform": "copied"},
            {"path": "rows", "match": "prefix", "transform": "projected"},
        ],
    )

    assert result["status"] == "pass"
    assert result["covered_path_count"] == 3


def test_path_coverage_reports_uncovered_and_unused_rules():
    result = validate_path_coverage(
        {"status", "rows[].id"},
        [
            {"path": "status", "match": "exact", "transform": "copied"},
            {"path": "missing", "match": "prefix", "transform": "not observed"},
        ],
    )

    assert result["status"] == "fail"
    assert result["uncovered_paths"] == ["rows[].id"]
    assert result["unused_rules"] == ["missing"]


def test_tabular_coverage_requires_exact_columns_once():
    passed = validate_tabular_field_coverage(
        ["id", "score", "status"],
        [
            {
                "group_id": "identity",
                "fields": ["id", "status"],
                "transform": "copied",
            },
            {
                "group_id": "metric",
                "fields": ["score"],
                "transform": "calculated",
            },
        ],
    )
    assert passed["status"] == "pass"

    failed = validate_tabular_field_coverage(
        ["id", "score"],
        [
            {
                "group_id": "bad",
                "fields": ["id", "id", "extra"],
                "transform": "copied",
            }
        ],
    )
    assert failed["status"] == "fail"
    assert failed["missing_columns"] == ["score"]
    assert failed["extra_columns"] == ["extra"]
    assert failed["duplicate_columns"] == ["id"]


def test_lineage_spec_validates_sources_references_and_code(tmp_path: Path):
    source_file = tmp_path / "pipeline.py"
    source_file.write_text("pass\n", encoding="utf-8")
    payload = {
        "lineage_id": "test",
        "sources": [
            {
                "source_id": "raw",
                "usage_status": "used_in_decision",
                "role": "input",
                "redistribution_status": "not_packaged",
            }
        ],
        "datasets": [
            {
                "dataset_id": "derived",
                "grain": "one row",
                "source_ids": ["raw"],
                "input_dataset_ids": [],
                "code_refs": ["pipeline.py:1"],
            }
        ],
        "final_outputs": [
            {
                "output_id": "result",
                "input_dataset_ids": ["derived"],
                "code_refs": ["pipeline.py:1"],
                "coverage_rules": [
                    {"path": "rows", "match": "prefix", "transform": "copy"}
                ],
            }
        ],
    }

    result = validate_lineage_spec(
        tmp_path, payload, configured_source_ids=["raw"]
    )

    assert result["status"] == "pass"
    assert result["source_count"] == 1


def test_lineage_spec_rejects_missing_configured_source_and_code(tmp_path: Path):
    payload = {
        "sources": [
            {
                "source_id": "raw",
                "usage_status": "unknown",
                "role": "input",
                "redistribution_status": "unknown",
            }
        ],
        "datasets": [
            {
                "dataset_id": "derived",
                "grain": "one row",
                "source_ids": ["missing"],
                "input_dataset_ids": [],
                "code_refs": ["missing.py:1"],
            }
        ],
        "final_outputs": [],
    }

    result = validate_lineage_spec(
        tmp_path, payload, configured_source_ids=["configured"]
    )

    assert result["status"] == "fail"
    assert result["missing_configured_sources"] == ["configured"]
    assert "lineage_code_references_missing" in result["failures"]
