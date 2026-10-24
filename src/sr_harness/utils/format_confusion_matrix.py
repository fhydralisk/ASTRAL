from __future__ import annotations

from typing import Mapping, Optional

__all__ = ["format_confusion_matrix"]


def color_by_error_rate(text: str, error_rate: float) -> str:
    """Wrap ``text`` in an ANSI color tag ranging from green (low error) to red (high error).

    Args:
        text: String to colorize.
        error_rate: Error rate in ``[0.0, 1.0]``.

    Returns:
        str: Tagged string ready for :func:`tag2ansi`.
    """
    if error_rate >= 0.30:
        return f"[red]{text}[reset]"
    if error_rate >= 0.10:
        return f"[orange]{text}[reset]"
    if error_rate > 0.00:
        return f"[yellow]{text}[reset]"
    return f"[green]{text}[reset]"


def format_confusion_matrix(
    matrix: Mapping[str, Mapping[str, int]] | None,
    *,
    max_size: int = 12,
    topk: int = 10,
) -> Optional[str]:
    """Format a nested confusion or co-occurrence count mapping as an aligned ASCII table.

    Args:
        matrix: Nested mapping ``{row_label: {col_label: count}}``.
        max_size: Maximum number of rows/columns to display.
        topk: Number of top off-diagonal pairs to highlight.

    Returns:
        Optional[str]: Formatted table string, or ``None`` if ``matrix`` is empty.
    """
    if not matrix:
        return "(no confusion matrix data)"

    labels = list(matrix)
    seen_labels = set(labels)
    for row in matrix.values():
        for label in row:
            if label not in seen_labels:
                labels.append(label)
                seen_labels.add(label)

    row_totals = {
        gt_label: sum(matrix.get(gt_label, {}).values())
        for gt_label in labels
    }

    if len(labels) <= max_size:
        short_labels = [label[:8] for label in labels]
        width = max(5, min(8, max(len(label) for label in short_labels)))
        lines = ["Confusion Matrix (GT rows x Pred cols)"]
        lines.append(" " * (width + 1) + " ".join(f"{label:>{width}}" for label in short_labels))
        for gt_label, short_label in zip(labels, short_labels):
            row = matrix.get(gt_label, {})
            row_total = row_totals[gt_label]
            cells = []
            for pred_label in labels:
                count = row.get(pred_label, 0)
                if gt_label == pred_label:
                    cells.append(f"[green]{count:>{width}}[reset]")
                else:
                    error_rate = 0.0 if row_total == 0 else count / row_total
                    cells.append(color_by_error_rate(f"{count:>{width}}", error_rate))
            lines.append(f"{short_label:>{width}} " + " ".join(cells))
        return "\n".join(lines)

    errors = []
    for gt_label, row in matrix.items():
        row_total = row_totals[gt_label]
        if row_total == 0:
            continue
        for pred_label, count in row.items():
            if gt_label != pred_label and count > 0:
                errors.append((count / row_total, count, gt_label, pred_label, row_total))
    errors.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not errors:
        return "Top Confusion Errors: none"

    lines = [f"Top {min(topk, len(errors))} Confusion Errors"]
    for error_rate, count, gt_label, pred_label, row_total in errors[:topk]:
        text = f"{gt_label} -> {pred_label}: {count}/{row_total} ({error_rate:.1%})"
        lines.append(color_by_error_rate(text, error_rate))
    return "\n".join(lines)
