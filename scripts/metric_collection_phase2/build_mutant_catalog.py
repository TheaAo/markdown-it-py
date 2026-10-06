"""Reuse the Phase 1 catalog engine with Phase 2 paths and reference workloads."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import shutil
import sys
from typing import Any
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1 import build_mutant_catalog as engine
from scripts.metric_collection_phase1.mutation_common import labeled_files_hash
from scripts.metric_collection_phase2.collect_coverage import export_snapshot

WORKLOAD_DEPENDENCIES = (
    "mutation_specified_workload.py",
    "mutation_extended_workload.py",
    "mutation_workload_common.py",
    "phase1_reference_specified.py",
    "phase1_reference_extended.py",
)
TRACEABILITY = (
    *tuple(
        row
        for row in engine.TRACEABILITY
        if row["requirement"]
        not in {"ruler_after", "non_utf8_cli_file", "cli_encoding_boundaries"}
    ),
    {
        "requirement": "core_after_normalize_order",
        "layer": "specified",
        "source": "Phase 2 assignment",
        "test": "test_core_after_normalize_order",
        "rationale": "Core rule executes after normalization.",
    },
    {
        "requirement": "non_utf8_decode_failure",
        "layer": "specified",
        "source": "Phase 2 assignment",
        "test": "test_non_utf8_exits_with_decode_message",
        "rationale": "Exit code 1 and UTF-8 decode error message.",
    },
    {
        "requirement": "fence_after_and_at",
        "layer": "specified",
        "source": "Phase 2 assignment",
        "test": "test_make_fence_after_keeps_default;test_make_fence_at_replaces_default",
        "rationale": "Colon fence contents and default-fence preservation/replacement.",
    },
    {
        "requirement": "fence_encoding_boundaries",
        "layer": "extended_only",
        "source": "Phase 2 boundary analysis",
        "test": "test_non_utf8_classes;test_colon_closing_length;test_default_factory_markers;test_colon_minimum_and_unclosed",
        "rationale": "Invalid encodings and configurable fence boundaries.",
    },
)


def prepare_workspace(
    repo: Path, baseline: str, workspace: Path, only_mutate: Sequence[str]
) -> None:
    export_snapshot(repo, baseline, workspace)
    shutil.copytree(
        workspace / "tests/task/phase1/materials", workspace / "mutation_materials"
    )
    phase1 = Path(engine.__file__).parent
    for original, destination in (
        ("mutation_specified_workload.py", "phase1_reference_specified.py"),
        ("mutation_extended_workload.py", "phase1_reference_extended.py"),
        ("mutation_workload_common.py", "mutation_workload_common.py"),
    ):
        shutil.copy2(phase1 / original, workspace / destination)
    for filename in engine.WORKLOAD_FILES.values():
        shutil.copy2(Path(__file__).with_name(filename), workspace / filename)
    selection = "\n".join(f"    {name}" for name in engine.WORKLOAD_FILES.values())
    copies = "\n".join(f"    {name}" for name in WORKLOAD_DEPENDENCIES)
    filter_text = (
        "only_mutate=\n" + "\n".join(f"    {name}" for name in only_mutate) + "\n"
        if only_mutate
        else ""
    )
    (workspace / "setup.cfg").write_text(
        "[mutmut]\nsource_paths=markdown_it/\n"
        + filter_text
        + f"pytest_add_cli_args_test_selection=\n{selection}\nalso_copy=\n{copies}\n    mutation_materials/\n"
        "use_setproctitle=false\ntrack_dependencies=false\n"
    )


def workload_hashes(workspace: Path) -> dict[str, str]:
    return {
        name: labeled_files_hash([(name, workspace / name)])
        for name in WORKLOAD_DEPENDENCIES
    }


def build_catalog(args: Any) -> dict[str, Any]:
    """Scope compatibility hooks to this invocation; original engine remains unchanged."""
    with (
        patch.object(engine, "_prepare_workspace", prepare_workspace),
        patch.object(engine, "_workspace_workload_hashes", workload_hashes),
        patch.object(engine, "TRACEABILITY", TRACEABILITY),
    ):
        return engine.build_catalog(args)


def main(argv: list[str] | None = None) -> int:
    parser = engine._parser()
    parser.set_defaults(
        baseline_ref="origin/experiment-base-phase2",
        output_dir=Path("results/phase2/mutation_score/catalog"),
    )
    args = parser.parse_args(argv)
    build_catalog(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
