"""Regenerates the synthetic PB2-p2 Confluence fixture corpus. Not run by
pytest — a developer action, per S3 ("Fixtures are committed. Recording is
a developer action, replay is the default.").

Every fixture is hand-shaped to mirror structure confirmed against two real
Confluence Cloud per-page exports inspected during the PB2-p2 build session
(a "Word" export and a "PDF" export) — the real exports themselves are
never committed (CLAUDE.md § Secrets: sample corpora must be synthetic).

    uv run python tests/fixtures/confluence/generate.py
"""

from __future__ import annotations

import quopri
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).parent

_PAGE_HTML = """\
<html xmlns:o='urn:schemas-microsoft-com:office:office'
      xmlns:w='urn:schemas-microsoft-com:word'
      xmlns='urn:w3-org-ns:HTML'>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <title>Widget classification based on availability</title>
    <style>
        table { border: solid 1px; border-collapse: collapse; }
        table td, table th { border: solid 1px; padding: 5px; }
    </style>
</head>
<body>
    <h1>Widget classification based on availability</h1>
    <div class="Section1">
        <div class="table-wrap">
        <table data-table-width="760" data-layout="default" class="confluenceTable">
        <tbody>
        <tr>
        <th class="confluenceTh"><p><strong>Widget name</strong></p></th>
        <th class="confluenceTh"><p><strong>Description</strong></p></th>
        <th class="confluenceTh"><p><strong>Availability</strong></p></th>
        </tr>
        <tr>
        <td class="confluenceTd"><p>Sprocket</p></td>
        <td class="confluenceTd"><p>Turns the main gear assembly.</p></td>
        <td class="confluenceTd"><p>Generally available</p></td>
        </tr>
        <tr>
        <td class="confluenceTd"><p>Widget</p></td>
        <td class="confluenceTd"><p>Placeholder for the thing itself.</p></td>
        <td class="confluenceTd"><p>Alpha</p></td>
        </tr>
        </tbody>
        </table>
        </div>
        <h2>Definitions</h2>
        <p>Terms used in the table above are defined here.</p>
        <div class="table-wrap">
        <table data-table-width="760" data-layout="default" class="confluenceTable">
        <tbody>
        <tr>
        <th class="confluenceTh"><p><strong>Alpha</strong></p></th>
        <th class="confluenceTh"><p><strong>Generally available</strong></p></th>
        </tr>
        <tr>
        <td class="confluenceTd">
        <p>Audience - Internal teams</p>
        <p>Stability - Experimentation in progress</p>
        <p>Support - None</p>
        </td>
        <td class="confluenceTd"><p>Officially launched and used by clients.</p></td>
        </tr>
        </tbody>
        </table>
        </div>
        <h2>Notes</h2>
        <p>A second top-level heading closes out the Definitions section.</p>
    </div>
</body>
</html>
"""

_EMPTY_BODY_HTML = """\
<html><head><title>Empty page</title></head><body></body></html>
"""

_NO_BODY_HTML = """\
<html><head><title>No body tag</title></head></html>
"""


def _html_part(
    html: str, *, charset: str = "utf-8", body_bytes: bytes | None = None
) -> MIMENonMultipart:
    part = MIMENonMultipart("text", "html", charset=charset)
    part["Content-Transfer-Encoding"] = "quoted-printable"
    part["Content-Location"] = "file:///C:/exported.html"
    payload = quopri.encodestring(body_bytes if body_bytes is not None else html.encode(charset))
    part.set_payload(payload.decode("ascii"))
    return part


def _mhtml_message(part: MIMENonMultipart) -> bytes:
    msg = MIMEMultipart("related")
    msg["Date"] = "Tue, 22 Sep 2026 07:37:20 +0000 (UTC)"
    msg["Subject"] = "Exported From Confluence"
    msg.attach(part)
    return msg.as_bytes().replace(b"\n", b"\r\n").replace(b"\r\r\n", b"\r\n")


def write_page_export_doc() -> None:
    """Mirrors the real "Export to Word" output: a multipart/related MIME
    message, quoted-printable, wrapping one text/html part with Confluence's
    real markup vocabulary (confluenceTable, table-wrap)."""
    (HERE / "page_export.doc").write_bytes(_mhtml_message(_html_part(_PAGE_HTML)))


def write_empty_body_doc() -> None:
    """Valid MHTML, but the page body has no heading/paragraph/table
    content at all."""
    (HERE / "empty_body.doc").write_bytes(_mhtml_message(_html_part(_EMPTY_BODY_HTML)))


def write_no_body_doc() -> None:
    """Valid MHTML wrapping HTML with no <body> tag at all — html.parser
    (unlike lxml/html5lib) does not synthesise one."""
    (HERE / "no_body.doc").write_bytes(_mhtml_message(_html_part(_NO_BODY_HTML)))


def write_mime_no_html_part_doc() -> None:
    """A well-formed multipart/related message that never contains a
    text/html part (e.g. an export that only carried an image)."""
    msg = MIMEMultipart("related")
    msg["Subject"] = "Exported From Confluence"
    part = MIMENonMultipart("text", "plain", charset="utf-8")
    part["Content-Transfer-Encoding"] = "quoted-printable"
    part.set_payload(quopri.encodestring(b"not html").decode("ascii"))
    msg.attach(part)
    (HERE / "mime_no_html_part.doc").write_bytes(msg.as_bytes().replace(b"\n", b"\r\n"))


def write_not_mime_doc() -> None:
    """Arbitrary bytes with a .doc extension: not multipart, not HTML —
    the "this doesn't look like a Confluence export at all" case."""
    (HERE / "not_mime.doc").write_bytes(b"\x00\x01\x02random garbage, not a MIME message\xff\xfe")


def write_mime_bad_encoding_doc() -> None:
    """Declares charset=utf-8 but the quoted-printable-decoded payload is
    not valid UTF-8 (a stray Latin-1 byte)."""
    bad_bytes = "<html><body><p>bad byte: \u00e9</p></body></html>".encode("latin-1")
    (HERE / "mime_bad_encoding.doc").write_bytes(
        _mhtml_message(_html_part("", charset="utf-8", body_bytes=bad_bytes))
    )


def write_page_pdf() -> None:
    """Reproduces the real PDF export's confirmed characteristic: the
    browser's top navigation chrome is captured as literal page-1 text
    ahead of the actual content, because the export is a print of the
    whole page, not just the article body."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=10)
    pdf.add_page()
    pdf.cell(text="Home  All Spaces  Internal Functions  Add New", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(text="Widget classification based on availability", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(text="Widget name  Description  Availability", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        text="Sprocket  Turns the main gear assembly.  Generally available",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.output(str(HERE / "page.pdf"))


if __name__ == "__main__":
    write_page_export_doc()
    write_empty_body_doc()
    write_no_body_doc()
    write_mime_no_html_part_doc()
    write_not_mime_doc()
    write_mime_bad_encoding_doc()
    write_page_pdf()
