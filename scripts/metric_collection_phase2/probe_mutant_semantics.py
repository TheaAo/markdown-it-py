"""Compare frozen source and one exact catalog patch; differences are review witnesses."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.mutation_common import sut_hash


def patch_source(source: str, diff: str, absolute_line: int | None = None) -> str:
    """Apply verified function-relative hunks with the original class indentation."""
    lines = source.splitlines()
    old: list[tuple[int, str]] = []
    blocks: list[tuple[int, int, list[str]]] = []
    position: int | None = None
    pending: tuple[int, int, list[str]] | None = None
    for line in diff.splitlines():
        header = re.match(r"^@@ -(\d+)(?:,\d+)? \+", line)
        if header:
            if pending is not None:
                blocks.append(pending)
                pending = None
            position = int(header[1])
        elif position is not None:
            if line.startswith(("-", "+")):
                if pending is None:
                    pending = (position, 0, [])
                if line.startswith("-"):
                    old.append((position, line[1:]))
                    pending = (pending[0], pending[1] + 1, pending[2])
                    position += 1
                else:
                    pending[2].append(line[1:])
            elif line == "" or line.startswith(" "):
                if pending is not None:
                    blocks.append(pending)
                    pending = None
                old.append((position, line[1:]))
                position += 1
    if pending is not None:
        blocks.append(pending)
    offsets = [
        offset
        for offset in range(len(lines))
        if all(
            0 <= offset + relative - 1 < len(lines)
            and lines[offset + relative - 1].lstrip() == text.lstrip()
            for relative, text in old
        )
    ]
    if absolute_line is not None:
        offsets = [
            offset for offset in offsets if offset + blocks[0][0] == absolute_line
        ]
    if len(offsets) != 1:
        raise ValueError("Patch old-side context does not uniquely match frozen source")
    offset = offsets[0]
    for start, count, added in reversed(blocks):
        index = offset + start - 1
        relative, text = next(
            (relative, text)
            for relative, text in old
            if start <= relative < start + count and text.strip()
        )
        actual = lines[offset + relative - 1]
        indentation = (len(actual) - len(actual.lstrip())) - (
            len(text) - len(text.lstrip())
        )
        if indentation < 0:
            raise ValueError("Unexpected negative class indentation")
        lines[index : index + count] = [
            " " * indentation + line if line else "" for line in added
        ]
    patched = "\n".join(lines) + "\n"
    ast.parse(patched)
    return patched


def run_probe(
    python: Path, script: Path, workspace: Path, materials: Path
) -> dict[str, Any]:
    result = subprocess.run(
        [str(python), "-B", str(script), "--materials", str(materials)],
        cwd=workspace,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        return {"process_exit": result.returncode, "stderr": result.stderr}
    return {"observations": json.loads(result.stdout)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mutant-id", action="append")
    parser.add_argument("--sample", type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    if sut_hash(args.source.resolve() / "markdown_it") != catalog["sut_hash"]:
        raise ValueError("Semantic witness source differs from frozen SUT")
    selected = set(args.mutant_id or [])
    if args.sample:
        import csv

        with args.sample.open(newline="") as stream:
            selected.update(row["mutant_id"] for row in csv.DictReader(stream))
    if not selected:
        raise ValueError("Select explicit mutant IDs or a frozen review sample")
    script = Path(__file__).with_name("semantic_probe_workload.py").resolve()
    evidence: dict[str, Any] = {
        "catalog_hash": catalog["catalog_hash"],
        "sut_hash": catalog["sut_hash"],
        "probe_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "purpose": "Researcher semantic counterexamples only; excluded from participant scores",
        "records": {},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase2-semantic-review-") as tmp:
        workspace = Path(tmp)
        shutil.copytree(
            args.source.resolve() / "markdown_it",
            workspace / "markdown_it",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        baseline = run_probe(
            args.python.absolute(), script, workspace, args.materials.resolve()
        )
        if "observations" not in baseline:
            raise ValueError(f"Pristine semantic workload failed: {baseline}")
        evidence["baseline_sha256"] = hashlib.sha256(
            json.dumps(baseline, sort_keys=True).encode()
        ).hexdigest()
        for mutant in catalog["mutants"]:
            if mutant["mutant_id"] not in selected:
                continue
            path = workspace / mutant["module"]
            source = path.read_text()
            try:
                path.write_text(
                    patch_source(source, mutant["diff"], mutant["source_line"])
                )
                result = run_probe(
                    args.python.absolute(), script, workspace, args.materials.resolve()
                )
            finally:
                path.write_text(source)
            record: dict[str, Any] = {
                "diff_sha256": hashlib.sha256(mutant["diff"].encode()).hexdigest(),
                "different": result != baseline,
            }
            if "observations" in result:
                for original, changed in zip(
                    baseline["observations"], result["observations"], strict=True
                ):
                    if original != changed:
                        record["first_difference"] = {
                            "baseline": original,
                            "mutant": changed,
                        }
                        break
            else:
                record["first_difference"] = result
            evidence["records"][mutant["mutant_id"]] = record
            args.output.write_text(json.dumps(evidence, indent=2) + "\n")
            print(
                mutant["mutant_id"],
                "witness" if record["different"] else "source review needed",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
