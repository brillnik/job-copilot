"""The last gate before submit. Returns problems; ANY problem means: do not submit."""

from app.apply.fields import ALLOWED_SOURCES, ApprovedFile, FormField, Planned, ReadBack


def presubmit_check(
    fields: list[FormField],
    plan: list[Planned],
    readback: dict[str, ReadBack],
    approved: ApprovedFile,
) -> list[str]:
    problems: list[str] = []
    by_key = {p.key: p for p in plan}
    for f in fields:
        p, rb = by_key.get(f.key), readback.get(f.key, ReadBack())
        if f.kind == "file":
            if rb.files and not (
                len(rb.files) == 1 and rb.files[0] == (approved.name, approved.size)
            ):
                problems.append(f"file_not_approved:{f.key}")
            if p and p.value is not None and not rb.files:
                problems.append(f"file_not_attached:{f.key}")
            if p and p.value is not None and p.source != "approved_pdf":
                problems.append(f"file_not_approved:{f.key}")
        if p and p.value is not None and p.source not in ALLOWED_SOURCES:
            problems.append(f"source_not_allowed:{f.key}")
        if not f.required:
            continue
        if p is None or p.value is None:
            problems.append(f"required_missing:{f.key}")
            continue
        if f.kind == "file":
            if not rb.files:
                problems.append(f"required_empty:{f.key}")
        elif f.kind in ("checkbox", "radio"):
            if not rb.checked:
                problems.append(f"required_empty:{f.key}")
        elif not rb.value.strip():
            problems.append(f"required_empty:{f.key}")
    return problems
