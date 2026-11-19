"""Validate RoadOps source-to-result data lineage specifications.

원천 데이터에서 Agent·지도 결과까지의 필드 계보를 검증합니다.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping


LINEAGE_VALIDATION_VERSION = "roadops-data-lineage-v0.1"
ALLOWED_SOURCE_STATUSES = {
    "used_in_decision",
    "used_in_quality_gate",
    "context_only",
    "configured_not_used",
    "blocked_not_used",
    "operator_input",
}
ALLOWED_MATCH_MODES = {"exact", "prefix"}


def normalized_leaf_paths(value: Any, prefix: str = "") -> set[str]:
    """Return deterministic dotted leaf paths, normalizing every list as []."""

    paths: set[str] = set()
    if isinstance(value, Mapping):
        if not value:
            paths.add(prefix or "<root>")
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.update(normalized_leaf_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        list_prefix = f"{prefix}[]"
        if not value:
            paths.add(list_prefix)
        for child in value:
            paths.update(normalized_leaf_paths(child, list_prefix))
        return paths
    paths.add(prefix or "<root>")
    return paths


def csv_columns(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _rule_matches(path: str, rule: Mapping[str, Any]) -> bool:
    declared = str(rule.get("path") or "")
    mode = str(rule.get("match") or "")
    if mode == "exact":
        return path == declared
    if mode == "prefix":
        return (
            path == declared
            or path.startswith(f"{declared}.")
            or path.startswith(f"{declared}[]")
        )
    return False


def validate_path_coverage(
    observed_paths: Iterable[str],
    rules: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check that every observed leaf path has at least one lineage rule."""

    observed = sorted(set(str(path) for path in observed_paths))
    rule_rows = [dict(rule) for rule in rules]
    uncovered = [
        path for path in observed if not any(_rule_matches(path, rule) for rule in rule_rows)
    ]
    unused_rules = [
        str(rule.get("path") or "")
        for rule in rule_rows
        if not any(_rule_matches(path, rule) for path in observed)
    ]
    invalid_rules = [
        str(rule.get("path") or "<missing>")
        for rule in rule_rows
        if not str(rule.get("path") or "")
        or rule.get("match") not in ALLOWED_MATCH_MODES
        or not str(rule.get("transform") or "").strip()
    ]
    failures: list[str] = []
    if uncovered:
        failures.append("observed_paths_without_lineage")
    if unused_rules:
        failures.append("lineage_rules_without_observed_paths")
    if invalid_rules:
        failures.append("invalid_lineage_rules")
    return {
        "status": "pass" if not failures else "fail",
        "observed_path_count": len(observed),
        "covered_path_count": len(observed) - len(uncovered),
        "rule_count": len(rule_rows),
        "uncovered_paths": uncovered,
        "unused_rules": unused_rules,
        "invalid_rules": invalid_rules,
        "failures": failures,
    }


def validate_tabular_field_coverage(
    observed_columns: Iterable[str],
    field_groups: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate exact column coverage by documented field groups."""

    observed = list(observed_columns)
    groups = [dict(group) for group in field_groups]
    declared: list[str] = []
    invalid_groups: list[str] = []
    for index, group in enumerate(groups, start=1):
        fields = group.get("fields")
        if (
            not str(group.get("group_id") or "").strip()
            or not isinstance(fields, list)
            or not fields
            or not str(group.get("transform") or "").strip()
        ):
            invalid_groups.append(str(group.get("group_id") or index))
            continue
        declared.extend(str(field) for field in fields)
    observed_set = set(observed)
    declared_set = set(declared)
    missing = sorted(observed_set - declared_set)
    extra = sorted(declared_set - observed_set)
    duplicates = sorted({field for field in declared if declared.count(field) > 1})
    failures: list[str] = []
    if missing:
        failures.append("observed_columns_without_lineage")
    if extra:
        failures.append("declared_columns_not_observed")
    if duplicates:
        failures.append("columns_declared_multiple_times")
    if invalid_groups:
        failures.append("invalid_field_groups")
    return {
        "status": "pass" if not failures else "fail",
        "observed_column_count": len(observed),
        "covered_column_count": len(observed_set & declared_set),
        "field_group_count": len(groups),
        "missing_columns": missing,
        "extra_columns": extra,
        "duplicate_columns": duplicates,
        "invalid_groups": invalid_groups,
        "failures": failures,
    }


def validate_lineage_spec(
    project_root: Path,
    payload: Mapping[str, Any],
    *,
    configured_source_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate references, code locations, and source-use declarations."""

    failures: list[str] = []
    sources = payload.get("sources")
    datasets = payload.get("datasets")
    final_outputs = payload.get("final_outputs")
    if not isinstance(sources, list):
        sources = []
        failures.append("sources_missing")
    if not isinstance(datasets, list):
        datasets = []
        failures.append("datasets_missing")
    if not isinstance(final_outputs, list):
        final_outputs = []
        failures.append("final_outputs_missing")

    source_ids = [str(row.get("source_id") or "") for row in sources if isinstance(row, Mapping)]
    dataset_ids = [str(row.get("dataset_id") or "") for row in datasets if isinstance(row, Mapping)]
    output_ids = [str(row.get("output_id") or "") for row in final_outputs if isinstance(row, Mapping)]
    duplicate_source_ids = sorted({value for value in source_ids if source_ids.count(value) > 1})
    duplicate_dataset_ids = sorted({value for value in dataset_ids if dataset_ids.count(value) > 1})
    duplicate_output_ids = sorted({value for value in output_ids if output_ids.count(value) > 1})
    if not all(source_ids) or duplicate_source_ids:
        failures.append("source_ids_invalid")
    if not all(dataset_ids) or duplicate_dataset_ids:
        failures.append("dataset_ids_invalid")
    if not all(output_ids) or duplicate_output_ids:
        failures.append("output_ids_invalid")

    invalid_source_statuses = sorted(
        source_id
        for source_id, row in zip(source_ids, sources)
        if not isinstance(row, Mapping)
        or row.get("usage_status") not in ALLOWED_SOURCE_STATUSES
        or not str(row.get("role") or "").strip()
        or not str(row.get("redistribution_status") or "").strip()
    )
    if invalid_source_statuses:
        failures.append("source_usage_declarations_invalid")
    missing_configured_sources = sorted(set(configured_source_ids) - set(source_ids))
    if missing_configured_sources:
        failures.append("configured_sources_missing_from_lineage")

    invalid_references: list[str] = []
    missing_code_refs: list[str] = []
    for dataset in datasets:
        if not isinstance(dataset, Mapping):
            continue
        dataset_id = str(dataset.get("dataset_id") or "")
        for source_id in dataset.get("source_ids", []):
            if source_id not in source_ids:
                invalid_references.append(f"{dataset_id}:source:{source_id}")
        for input_id in dataset.get("input_dataset_ids", []):
            if input_id not in dataset_ids:
                invalid_references.append(f"{dataset_id}:dataset:{input_id}")
        for code_ref in dataset.get("code_refs", []):
            relative = str(code_ref).split(":", 1)[0]
            if not (project_root / relative).is_file():
                missing_code_refs.append(f"{dataset_id}:{code_ref}")
        if not str(dataset.get("grain") or "").strip():
            invalid_references.append(f"{dataset_id}:grain")

    for output in final_outputs:
        if not isinstance(output, Mapping):
            continue
        output_id = str(output.get("output_id") or "")
        for input_id in output.get("input_dataset_ids", []):
            if input_id not in dataset_ids:
                invalid_references.append(f"{output_id}:dataset:{input_id}")
        for code_ref in output.get("code_refs", []):
            relative = str(code_ref).split(":", 1)[0]
            if not (project_root / relative).is_file():
                missing_code_refs.append(f"{output_id}:{code_ref}")
        rules = output.get("coverage_rules")
        if not isinstance(rules, list) or not rules:
            invalid_references.append(f"{output_id}:coverage_rules")

    if invalid_references:
        failures.append("lineage_references_invalid")
    if missing_code_refs:
        failures.append("lineage_code_references_missing")
    return {
        "status": "pass" if not failures else "fail",
        "lineage_id": payload.get("lineage_id"),
        "source_count": len(source_ids),
        "dataset_count": len(dataset_ids),
        "final_output_count": len(output_ids),
        "duplicate_source_ids": duplicate_source_ids,
        "duplicate_dataset_ids": duplicate_dataset_ids,
        "duplicate_output_ids": duplicate_output_ids,
        "invalid_source_statuses": invalid_source_statuses,
        "missing_configured_sources": missing_configured_sources,
        "invalid_references": sorted(invalid_references),
        "missing_code_refs": sorted(missing_code_refs),
        "failures": failures,
    }
