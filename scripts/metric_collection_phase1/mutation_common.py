from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

RAW_STATUSES = frozenset(
    {"killed", "survived", "no_tests", "timeout", "suspicious", "skipped", "segfault"}
)
REVIEW_STATUSES = frozenset(
    {
        "unreviewed",
        "non_equivalent",
        "confirmed_equivalent",
        "duplicate",
        "unresolved",
    }
)
WORKLOAD_LAYERS = frozenset({"specified", "extended_only"})
RAW_WORKLOAD_LAYERS = frozenset({"specified", "extended_only", "out_of_scope"})
RESULT_PATTERN = re.compile(r"^\s*(?P<name>.+?): (?P<status>[a-z_ ]+)$")
HUNK_PATTERN = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", re.MULTILINE)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_mutant_id(module: str, mutant_name: str, source_line: int, diff: str) -> str:
    identity = [module, mutant_name, source_line, normalize_diff(diff)]
    digest = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    return f"M{digest[:16]}"


def normalize_diff(diff: str) -> str:
    lines = [line.rstrip() for line in diff.strip().splitlines()]
    return "\n".join(lines) + ("\n" if lines else "")


def source_line_from_diff(diff: str) -> int:
    match = HUNK_PATTERN.search(diff)
    if match is None:
        raise ValueError("mutant diff does not contain a unified-diff hunk")
    return int(match.group(1))


def changed_line_from_diff(diff: str) -> int:
    return changed_lines_from_diff(diff)[0]


def changed_lines_from_diff(diff: str) -> tuple[int, ...]:
    changed: list[int] = []
    lines = diff.splitlines()
    index = 0
    while index < len(lines):
        match = HUNK_PATTERN.match(lines[index])
        if match is None:
            index += 1
            continue
        old_line = int(match.group(1))
        index += 1
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if line.startswith("-") and not line.startswith("---"):
                changed.append(old_line)
                old_line += 1
            elif not line.startswith("+"):
                old_line += 1
            index += 1
    if not changed:
        raise ValueError("mutant diff does not contain a removed source line")
    return tuple(dict.fromkeys(changed))


def changed_code(diff: str) -> tuple[str, str]:
    original: list[str] = []
    mutated: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("-"):
            original.append(line[1:])
        elif line.startswith("+"):
            mutated.append(line[1:])
    return "\n".join(original), "\n".join(mutated)


def diff_fingerprint(diff: str) -> str:
    module = ""
    for line in diff.splitlines():
        if line.startswith("--- ") and "mutation diff" not in line:
            module = line[4:].strip()
            if module.startswith("a/"):
                module = module[2:]
            break
    original, mutated = changed_code(diff)
    return canonical_json([module, original, mutated])


def function_from_mutant_name(mutant_name: str) -> str:
    marker = "ǁ"
    parts = mutant_name.split(marker)
    if len(parts) >= 2:
        return parts[-1].split("__mutmut_", 1)[0]
    return "<module>"


def parse_mutmut_results(output: str) -> dict[str, str]:
    results: dict[str, str] = {}
    for line in output.splitlines():
        match = RESULT_PATTERN.match(line)
        if match is None:
            continue
        status = match.group("status").strip().replace(" ", "_")
        if status not in RAW_STATUSES:
            continue
        results[match.group("name").strip()] = status
    return results


def catalog_hash(mutants: Sequence[dict[str, Any]]) -> str:
    catalog_fields = []
    for item in sorted(mutants, key=lambda row: row["mutant_id"]):
        fields = {
            "mutant_id": item["mutant_id"],
            "mutant_name": item["mutant_name"],
            "module": item["module"],
            "function": item["function"],
            "source_line": item["source_line"],
            "workload_layer": item.get("workload_layer", "specified"),
            "diff": normalize_diff(item["diff"]),
        }
        if item.get("identity_schema") == 3:
            fields.update(
                {
                    "identity_schema": 3,
                    "changed_source_lines": item["changed_source_lines"],
                    "coverage_source_lines": item["coverage_source_lines"],
                    "operator_family": item["operator_family"],
                    "covered_by_specified": item["covered_by_specified"],
                    "covered_by_extended": item["covered_by_extended"],
                    "mapping_status": item["mapping_status"],
                }
            )
        catalog_fields.append(fields)
    return hashlib.sha256(canonical_json(catalog_fields).encode()).hexdigest()


def semantic_artifact_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def collection_policy_hash(policy: dict[str, Any]) -> str:
    return semantic_artifact_hash(policy)


def build_collection_policy(
    catalog: dict[str, Any],
    *,
    python_version: str,
    test_timeout: float,
    execution_timeout: float | None,
    timeout_multiplier: float,
    timeout_constant: float,
    confirm_kills: bool,
    confirmation_max_children: int,
    exclude_duplicates: bool,
) -> dict[str, Any]:
    if timeout_multiplier <= 0:
        raise ValueError("timeout multiplier must be positive")
    if timeout_constant < 0:
        raise ValueError("timeout constant must be non-negative")
    return {
        "schema_version": 1,
        "catalog_hash": catalog["catalog_hash"],
        "baseline_commit": catalog["baseline_commit"],
        "sut_hash": catalog["sut_hash"],
        "workload_hashes": catalog.get("workload_hashes"),
        "material_hashes": catalog.get("material_hashes"),
        "tool_version": catalog["tool_version"],
        "python_version": python_version,
        "valid_only_protocol": "isolated_expanded_cases_v1",
        "test_timeout_seconds": test_timeout,
        "execution_timeout_seconds": execution_timeout,
        "mutant_timeout": {
            "formula": "(estimated_test_time + constant) * multiplier",
            "multiplier": timeout_multiplier,
            "constant": timeout_constant,
        },
        "timeout_retry": {
            "attempts": 1,
            "max_children": 1,
            "timeout_multiplier": timeout_multiplier,
            "timeout_constant": timeout_constant,
        },
        "global_kill_confirmation": {
            "enabled": confirm_kills,
            "protocol": "independent_second_execution_v2",
            "max_children": confirmation_max_children,
        },
        "exclude_duplicates": exclude_duplicates,
    }


def sut_hash(source_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(source_root.rglob("*.py")):
        digest.update(path.relative_to(source_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def files_hash(paths: Sequence[Path], root: Path | None = None) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        label = path.relative_to(root).as_posix() if root else path.name
        digest.update(label.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def labeled_files_hash(files: Sequence[tuple[str, Path]]) -> str:
    digest = hashlib.sha256()
    for label, path in sorted(files):
        digest.update(label.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("mutants"), list):
        raise ValueError("catalog must be an object containing a mutants array")
    mutants = payload["mutants"]
    if payload.get("catalog_hash") != catalog_hash(mutants):
        raise ValueError("catalog hash does not match catalog contents")
    seen: set[str] = set()
    for mutant in mutants:
        if not isinstance(mutant, dict):
            raise ValueError("catalog mutant must be an object")
        mutant_id = mutant.get("mutant_id")
        review_status = mutant.get("review_status")
        workload_layer = mutant.get("workload_layer", "specified")
        if not isinstance(mutant_id, str) or mutant_id in seen:
            raise ValueError("catalog mutant IDs must be unique strings")
        if review_status not in REVIEW_STATUSES:
            raise ValueError(f"invalid review status for {mutant_id}")
        allowed_layers = (
            RAW_WORKLOAD_LAYERS
            if payload.get("catalog_kind") == "full_sut_raw"
            else WORKLOAD_LAYERS
        )
        if workload_layer not in allowed_layers:
            raise ValueError(f"invalid workload layer for {mutant_id}")
        seen.add(mutant_id)
    return payload


def mutation_summary(
    mutants: Sequence[dict[str, Any]], *, exclude_duplicates: bool = False
) -> dict[str, Any]:
    raw_counts = Counter(item["status"] for item in mutants)
    confirmed_equivalent = sum(
        item.get("review_status") == "confirmed_equivalent"
        and item["status"] in {"killed", "survived", "no_tests"}
        for item in mutants
    )
    excluded_duplicates = sum(
        exclude_duplicates
        and item.get("review_status") == "duplicate"
        and item["status"] in {"killed", "survived", "no_tests"}
        for item in mutants
    )
    killed = raw_counts["killed"]
    survived = raw_counts["survived"]
    no_tests = raw_counts["no_tests"]
    timeout = raw_counts["timeout"]
    eligible_killed = sum(
        item["status"] == "killed"
        and item.get("review_status") != "confirmed_equivalent"
        and not (exclude_duplicates and item.get("review_status") == "duplicate")
        for item in mutants
    )
    eligible = killed + survived + no_tests - confirmed_equivalent - excluded_duplicates
    if eligible < 0:
        raise ValueError("confirmed equivalent count exceeds scoreable mutants")
    return {
        "catalog_total": len(mutants),
        "killed": killed,
        "survived": survived,
        "no_tests": no_tests,
        "timeout": timeout,
        "other": len(mutants) - killed - survived - no_tests - timeout,
        "confirmed_equivalent": confirmed_equivalent,
        "excluded_duplicates": excluded_duplicates,
        "eligible_mutants": eligible,
        "eligible_killed": eligible_killed,
        "mutation_score": eligible_killed / eligible if eligible else 0.0,
    }


def layered_mutation_summary(
    mutants: Sequence[dict[str, Any]], *, exclude_duplicates: bool = False
) -> dict[str, dict[str, Any]]:
    specified = [item for item in mutants if item.get("workload_layer") == "specified"]
    extended = [
        item for item in mutants if item.get("workload_layer") == "extended_only"
    ]
    return {
        "specified": mutation_summary(specified, exclude_duplicates=exclude_duplicates),
        "extended": mutation_summary(extended, exclude_duplicates=exclude_duplicates),
        "combined": mutation_summary(mutants, exclude_duplicates=exclude_duplicates),
    }


def weighted_mutation_summary(
    mutants: Sequence[dict[str, Any]], *, exclude_duplicates: bool = False
) -> dict[str, Any]:
    raw = mutation_summary(mutants, exclude_duplicates=exclude_duplicates)
    eligible_rows = [
        item
        for item in mutants
        if item["status"] in {"killed", "survived", "no_tests"}
        and item.get("review_status") != "confirmed_equivalent"
        and not (exclude_duplicates and item.get("review_status") == "duplicate")
    ]
    estimated_killed = sum(
        float(item.get("sampling_weight", 1.0))
        for item in eligible_rows
        if item["status"] == "killed"
    )
    estimated_eligible = sum(
        float(item.get("sampling_weight", 1.0)) for item in eligible_rows
    )
    estimate = estimated_killed / estimated_eligible if estimated_eligible else 0.0

    strata: dict[str, list[dict[str, Any]]] = {}
    for item in eligible_rows:
        strata.setdefault(str(item.get("sampling_stratum", "ALL")), []).append(item)
    variance = 0.0
    insufficient_variance_data = False
    if estimated_eligible:
        for rows in strata.values():
            sampled_count = len(rows)
            population = int(rows[0].get("stratum_population", sampled_count))
            if sampled_count == 1 and population > 1:
                insufficient_variance_data = True
            if sampled_count <= 1 or population <= 1:
                continue
            killed_count = sum(item["status"] == "killed" for item in rows)
            proportion = killed_count / sampled_count
            finite_correction = max(0.0, 1.0 - sampled_count / population)
            stratum_weight = population / estimated_eligible
            variance += (
                stratum_weight**2
                * finite_correction
                * proportion
                * (1.0 - proportion)
                / (sampled_count - 1)
            )
    margin = 1.96 * math.sqrt(max(0.0, variance))
    return {
        **raw,
        "estimated_killed": estimated_killed,
        "estimated_eligible_mutants": estimated_eligible,
        "estimated_mutation_score": estimate,
        "estimated_ci95_lower": (
            0.0 if insufficient_variance_data else max(0.0, estimate - margin)
        ),
        "estimated_ci95_upper": (
            1.0 if insufficient_variance_data else min(1.0, estimate + margin)
        ),
        "ci_method": (
            "conservative_bounds_singleton_stratum"
            if insufficient_variance_data
            else "stratified_normal_finite_population"
        ),
    }


def layered_weighted_mutation_summary(
    mutants: Sequence[dict[str, Any]], *, exclude_duplicates: bool = False
) -> dict[str, dict[str, Any]]:
    specified = [item for item in mutants if item.get("workload_layer") == "specified"]
    extended = [
        item for item in mutants if item.get("workload_layer") == "extended_only"
    ]
    return {
        "specified": weighted_mutation_summary(
            specified, exclude_duplicates=exclude_duplicates
        ),
        "extended": weighted_mutation_summary(
            extended, exclude_duplicates=exclude_duplicates
        ),
        "combined": weighted_mutation_summary(
            mutants, exclude_duplicates=exclude_duplicates
        ),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def write_csv(
    path: Path, columns: Sequence[str], rows: Iterable[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
