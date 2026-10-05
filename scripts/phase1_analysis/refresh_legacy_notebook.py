"""Synchronize legacy notebook presentation after the 2026-10-05 review.

This is a mechanical source-cell update. Run the notebook afterwards to refresh
its results and plots. Repeated runs do not duplicate the review or plot rule.
"""

from __future__ import annotations

from pathlib import Path

import nbformat


def refresh() -> None:
    """Apply the resolved assertion and plot-only participant exclusion notes."""
    path = Path(__file__).with_name("phase1_analysis.ipynb")
    notebook = nbformat.read(path, as_version=4)
    note = (
        "\n\n2026-10-05 review: participant 8's test_file assertion is non-trivial "
        "(score 1, uncertain count 0). Participant 6 is hidden only from individual "
        "plots; their group means/medians use the displayed subset. Statistical "
        "tables and interval plots retain the full sample, and surveys retain all responses."
    )
    if "2026-10-05 review:" not in notebook.cells[0].source:
        notebook.cells[0].source += note
    if "plot_participants =" not in notebook.cells[4].source:
        notebook.cells[4].source = notebook.cells[4].source.replace(
            "participants = participating_data(master)",
            "participants = participating_data(master)\n"
            "plot_participants = participants.loc[participants['participant_number'].ne(6)].copy()",
        )
    for index in (9, 15, 17, 19, 23):
        source = notebook.cells[index].source
        source = source.replace("participant_dot_panel(ax, participants,", "participant_dot_panel(ax, plot_participants,")
        source = source.replace("participants.loc[", "plot_participants.loc[") if "plot_participants.loc[" not in source else source
        source = source.replace("smell_totals = participants[list(smell_columns)]", "smell_totals = plot_participants[list(smell_columns)]")
        notebook.cells[index].source = source
    notebook.cells[20].source = notebook.cells[20].source.replace(
        "lower/upper handling of participant 8's unresolved assertion; ", ""
    )
    # Legacy primary interval plot gets the same numerical annotations as Analysis.
    source = notebook.cells[11].source
    if "number = lambda" not in source:
        source = source.replace(
            "    ax.set_yticks([])",
            "    number = lambda value: f'{value:.3g}' if 0 < abs(value) < 0.01 else f'{value:.2f}'\n"
            "    for value, label, offset in [(estimate, 'Estimate', 14), (lower, 'Lower', -20), (upper, 'Upper', -20)]:\n"
            "        ax.annotate(f'{label}: {number(value)}', (value, 0), xytext=(0, offset),\n"
            "                    textcoords='offset points', ha='center', fontsize=8,\n"
            "                    va='bottom' if offset > 0 else 'top',\n"
            "                    bbox=dict(facecolor='white', edgecolor='none', alpha=0.9, pad=1))\n"
            "    ax.set_ylim(-1, 1)\n"
            "    ax.margins(x=0.18)\n"
            "    ax.set_yticks([])",
        )
    notebook.cells[11].source = source
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    nbformat.write(notebook, path)


if __name__ == "__main__":
    refresh()
