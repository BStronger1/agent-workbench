"""Apply model-proposed literal edits; never infer a fix or change the contract."""

import hashlib
from .models import Code, CodeEdits


class PatchError(ValueError):
    pass


def apply_edits(html, reply):
    edits = CodeEdits.model_validate(reply).edits
    spans = []
    for edit in edits:
        if edit.old == edit.new:
            raise PatchError("No-op edit")
        if html.count(edit.old) != 1:
            raise PatchError("Edit anchor must occur exactly once in original HTML")
        start = html.index(edit.old)
        end = start + len(edit.old)
        if any(start < b and end > a for a, b, _ in spans):
            raise PatchError("Edit anchors overlap")
        spans.append((start, end, edit.new))
    result = html
    for start, end, replacement in sorted(spans, reverse=True):
        result = result[:start] + replacement + result[end:]
    Code.model_validate({"html": result})
    if not result.lower().startswith(
        "<!doctype html"
    ) or not result.lower().rstrip().endswith("</html>"):
        raise PatchError("Edits must preserve a complete HTML document")
    return result


def html_hash(html):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()
