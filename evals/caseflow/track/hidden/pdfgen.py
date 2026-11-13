"""Builds the small PDFs request 4 describes (and its published sample pack)."""

import base64
import zlib


def pdf_escape(text: str) -> bytes:
    out = bytearray()
    for byte in text.encode("latin-1"):
        ch = chr(byte)
        if ch in "()\\":
            out += b"\\" + ch.encode()
        elif byte < 32 or byte > 126:
            out += b"\\%03o" % byte
        else:
            out.append(byte)
    return bytes(out)


def content_for(lines, style="tj") -> bytes:
    ops = [b"BT", b"/F1 12 Tf", b"72 720 Td"]
    for index, line in enumerate(lines):
        if index and style != "quote":
            ops.append(b"0 -16 Td")
        if style == "tj":
            ops.append(b"(" + pdf_escape(line) + b") Tj")
        elif style == "hex":
            ops.append(b"<" + line.encode("latin-1").hex().upper().encode() + b"> Tj")
        elif style == "TJ":
            words = line.split(" ")
            parts = b" -250 ".join(
                b"(" + pdf_escape(w + (" " if i < len(words) - 1 else "")) + b")"
                for i, w in enumerate(words)
            )
            ops.append(b"[" + parts + b"] TJ")
        elif style == "quote":
            ops.append(b"(" + pdf_escape(line) + b") '")
    ops.append(b"ET")
    return b"\n".join(ops) + b"\n"


def _stream(data: bytes, compress=False, filter_name=None) -> bytes:
    if compress:
        data = zlib.compress(data)
        filter_name = filter_name or "FlateDecode"
    extra = b" /Filter /" + filter_name.encode() if filter_name else b""
    return b"<< /Length %d" % len(data) + extra + b" >>\nstream\n" + data + b"\nendstream"


def build(
    pages,
    *,
    compress=False,
    shuffle=False,
    style="tj",
    image_only=False,
    xref=True,
    nested=False,
    streams=None,
    filter_name=None,
    encrypt=False,
    catalog=True,
):
    """`pages`: list of lists of lines. `streams`: optional list (per page) of lists of raw
    content-stream bytes used instead of generated text."""
    objects = {}
    n_pages = len(pages) if streams is None else len(streams)
    page_ids = [4 + 3 * i for i in range(n_pages)]
    content_ids = [5 + 3 * i for i in range(n_pages)]
    extra_ids = [6 + 3 * i for i in range(n_pages)]
    image_id = 4 + 3 * n_pages
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>" if catalog else b"<< /Type /Outline >>"
    kids = b" ".join(b"%d 0 R" % p for p in page_ids)
    objects[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n_pages
    parent = 2
    if nested:
        mid = 100
        objects[2] = b"<< /Type /Pages /Kids [%d 0 R] /Count %d >>" % (mid, n_pages)
        objects[mid] = b"<< /Type /Pages /Parent 2 0 R /Kids [" + kids + b"] /Count %d >>" % n_pages
        parent = mid
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for index, (pid, cid, xid) in enumerate(zip(page_ids, content_ids, extra_ids)):
        resources = b"<< /Font << /F1 3 0 R >> >>"
        if image_only:
            resources = b"<< /XObject << /Im1 %d 0 R >> >>" % image_id
            datas = [b"q 612 0 0 792 0 0 cm /Im1 Do Q\n"]
        elif streams is not None:
            datas = streams[index]
        else:
            datas = [content_for(pages[index], style)]
        if len(datas) == 1:
            contents = b"%d 0 R" % cid
            objects[cid] = _stream(datas[0], compress, filter_name)
        else:
            contents = b"[%d 0 R %d 0 R]" % (cid, xid)
            objects[cid] = _stream(datas[0], compress, filter_name)
            objects[xid] = _stream(datas[1], compress, filter_name)
        objects[pid] = (
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources " % parent
            + resources
            + b" /Contents "
            + contents
            + b" >>"
        )
    if image_only:
        hexed = (bytes(range(0, 256, 16)) * 4).hex().encode() + b">"
        objects[image_id] = (
            b"<< /Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceGray "
            b"/BitsPerComponent 8 /Filter /ASCIIHexDecode /Length %d >>\nstream\n" % len(hexed)
            + hexed
            + b"\nendstream"
        )
    if encrypt:
        objects[99] = b"<< /Filter /Standard /V 1 /R 2 /O <00> /U <00> /P -4 >>"
    order = sorted(objects)
    if shuffle:
        order = list(reversed(order))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in order:
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objects[num] + b"\nendobj\n"
    xref_at = len(out)
    size = max(objects) + 1
    if xref:
        out += b"xref\n0 %d\n0000000000 65535 f \n" % size
        for num in range(1, size):
            out += b"%010d 00000 n \n" % offsets.get(num, 0)
    trailer = b"<< /Size %d /Root 1 0 R" % size + (b" /Encrypt 99 0 R" if encrypt else b"") + b" >>"
    out += b"trailer\n" + trailer + b"\n"
    out += b"startxref\n%d\n%%%%EOF\n" % (xref_at if xref else 0)
    return bytes(out)


def sample_pack() -> dict[str, bytes]:
    """The four files published with request 4."""
    notes = build(
        [["Meeting notes"], ["Budget  approved", "Next review: 2026-06-01"]],
        compress=True,
        shuffle=True,
        style="TJ",
    )
    return {
        "lease.pdf": build(
            [["Lease agreement", "Tenant: Ana Lima", "Rent: 1 200 EUR (monthly)"],
             ["Signed in Tromsø, café"]]  # fmt: skip
        ),
        "notes.pdf": notes,
        "scan.pdf": build([["x"]], image_only=True),
        "broken.pdf": notes[:300],
    }


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
