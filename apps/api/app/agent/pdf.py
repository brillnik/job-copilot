"""Minimal PDF renderer (stub).

Produces a valid single-font text PDF so the review flow can be built and tested end
to end. The real templates (classic/compact) replace `render` later; nothing else
should depend on how this lays text out.
"""

import re
import textwrap

from app.schemas.profile import ProfileData
from app.schemas.run import Pages, TailoredResume

LINES_PER_PAGE = 48
WIDTH = 92


def _esc(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def layout(profile: ProfileData, tailored: TailoredResume) -> list[str]:
    lines = [profile.contact.name or "", ""]
    if tailored.summary:
        lines += [*textwrap.wrap(tailored.summary, WIDTH), ""]
    if tailored.skills_order:
        lines += [
            *textwrap.wrap("Skills: " + ", ".join(tailored.skills_order), WIDTH),
            "",
        ]
    for b in tailored.bullets:
        lines += textwrap.wrap("- " + b.text, WIDTH, subsequent_indent="  ")
    return lines


def measure(lines: list[str]) -> Pages:
    count = max(1, -(-len(lines) // LINES_PER_PAGE))
    rest = len(lines) - (count - 1) * LINES_PER_PAGE
    return Pages(count=count, last_page_fill=round(max(0, rest) / LINES_PER_PAGE, 2))


def render(profile: ProfileData, tailored: TailoredResume) -> tuple[bytes, Pages]:
    lines = layout(profile, tailored)
    pages = measure(lines)
    chunks = [
        lines[i : i + LINES_PER_PAGE]
        for i in range(0, max(len(lines), 1), LINES_PER_PAGE)
    ]
    objs: list[bytes] = []
    n = len(chunks)
    page_ids = [4 + 2 * i for i in range(n)]
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, chunk in enumerate(chunks):
        body = (
            "BT /F1 10 Tf 14 TL 50 790 Td\n"
            + "\n".join(f"({_esc(line)}) '" for line in chunk)
            + "\nET"
        )
        pid = page_ids[i]
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {pid + 1} 0 R >>".encode()
        )
        data = body.encode("latin-1", "replace")
        objs.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out), pages


def slug(text: str | None, *, keep_case: bool = False, default: str = "company") -> str:
    text = text or ""
    text = re.sub(r"[^A-Za-z0-9]+", "-", text if keep_case else text.lower()).strip("-")
    return text or default
