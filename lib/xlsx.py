"""Minimal stdlib-only XLSX read/write.

Supports:
  - Multiple sheets (one per CSV/TSV/JSON-records "table")
  - String and number cells (booleans/None coerced to strings)
  - Reading data via worksheet `<c>`/`<v>`/`<is>` elements and shared strings

Limitations:
  - No formulas, styles, merged cells, dates, or formatting.
  - All values are read back as strings, then coerced like CSV cells.
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_xlsx_bytes(blob):
    """Return a dict mapping sheet name -> rows (list[list[str]])."""
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        shared = _read_shared_strings(zf)
        sheets = _list_sheets(zf)
        result = {}
        for name, target in sheets:
            xml_path = _resolve_sheet_path(target)
            try:
                with zf.open(xml_path) as fp:
                    rows = _parse_sheet(fp.read(), shared)
            except KeyError:
                rows = []
            result[name] = rows
        return result


def _read_shared_strings(zf):
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    out = []
    for si in root.findall("main:si", NS):
        # Either a single <t> or a sequence of rich-text <r><t> nodes.
        t = si.find("main:t", NS)
        if t is not None and t.text is not None:
            out.append(t.text)
            continue
        parts = []
        for r in si.findall("main:r", NS):
            rt = r.find("main:t", NS)
            if rt is not None and rt.text is not None:
                parts.append(rt.text)
        out.append("".join(parts))
    return out


def _list_sheets(zf):
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_data = zf.read("xl/_rels/workbook.xml.rels")
    rels = ET.fromstring(rels_data)
    rel_map = {}
    rels_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    for rel in rels.findall(rels_ns + "Relationship"):
        rel_map[rel.get("Id")] = rel.get("Target")
    sheets = []
    for sh in wb.find("main:sheets", NS).findall("main:sheet", NS):
        rid = sh.get("{" + NS["r"] + "}id")
        sheets.append((sh.get("name"), rel_map.get(rid, "")))
    return sheets


def _resolve_sheet_path(target):
    if target.startswith("/"):
        return target.lstrip("/")
    return "xl/" + target.lstrip("./")


_COL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(ref):
    m = _COL_RE.match(ref or "")
    if not m:
        return 0
    letters = m.group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _parse_sheet(data, shared):
    root = ET.fromstring(data)
    sheet_data = root.find("main:sheetData", NS)
    if sheet_data is None:
        return []
    rows_out = []
    for row in sheet_data.findall("main:row", NS):
        cells = []
        for c in row.findall("main:c", NS):
            idx = _col_index(c.get("r", ""))
            while len(cells) <= idx:
                cells.append("")
            ctype = c.get("t")
            if ctype == "s":
                v = c.find("main:v", NS)
                if v is not None and v.text is not None:
                    try:
                        cells[idx] = shared[int(v.text)]
                    except (ValueError, IndexError):
                        cells[idx] = ""
            elif ctype == "inlineStr":
                t = c.find("main:is/main:t", NS)
                cells[idx] = t.text if (t is not None and t.text) else ""
            elif ctype == "b":
                v = c.find("main:v", NS)
                cells[idx] = "true" if (v is not None and v.text == "1") else "false"
            else:
                v = c.find("main:v", NS)
                cells[idx] = v.text if (v is not None and v.text is not None) else ""
        rows_out.append(cells)
    return rows_out


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_xlsx_bytes(sheets):
    """Build an XLSX byte-string from a dict[name -> rows].

    Cells that look like numbers are written as numeric; everything else is
    written as a shared string.
    """
    if not sheets:
        sheets = {"Sheet1": [[]]}

    shared = []
    shared_index = {}

    def share(text):
        if text not in shared_index:
            shared_index[text] = len(shared)
            shared.append(text)
        return shared_index[text]

    sheet_xmls = []
    for sheet_name, rows in sheets.items():
        sheet_xmls.append((sheet_name, _build_sheet_xml(rows, share)))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml(len(sheet_xmls)))
        zf.writestr("_rels/.rels", _root_rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml(sheet_xmls))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheet_xmls)))
        zf.writestr("xl/sharedStrings.xml", _shared_strings_xml(shared))
        zf.writestr("xl/styles.xml", _styles_xml())
        for i, (_, xml) in enumerate(sheet_xmls, start=1):
            zf.writestr("xl/worksheets/sheet{0}.xml".format(i), xml)
    return buf.getvalue()


def _col_letter(n):
    """1-indexed -> 'A', 'B', ..., 'AA', ..."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


_NUM_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")


def _build_sheet_xml(rows, share):
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, start=1):
        out.append('<row r="{0}">'.format(r_idx))
        for c_idx, value in enumerate(row, start=1):
            ref = "{0}{1}".format(_col_letter(c_idx), r_idx)
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                out.append(
                    '<c r="{0}" t="b"><v>{1}</v></c>'.format(ref, 1 if value else 0)
                )
            elif isinstance(value, (int, float)):
                out.append('<c r="{0}"><v>{1}</v></c>'.format(ref, value))
            else:
                s = str(value)
                if _NUM_RE.match(s):
                    out.append('<c r="{0}"><v>{1}</v></c>'.format(ref, s))
                else:
                    out.append(
                        '<c r="{0}" t="s"><v>{1}</v></c>'.format(ref, share(s))
                    )
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def _content_types_xml(n_sheets):
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>',
    ]
    for i in range(1, n_sheets + 1):
        parts.append(
            '<Override PartName="/xl/worksheets/sheet{0}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(i)
        )
    parts.append("</Types>")
    return "".join(parts)


def _root_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _workbook_xml(sheet_xmls):
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"',
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        "<sheets>",
    ]
    for i, (name, _) in enumerate(sheet_xmls, start=1):
        parts.append(
            '<sheet name="{0}" sheetId="{1}" r:id="rId{1}"/>'.format(
                _escape_xml(name), i
            )
        )
    parts.append("</sheets></workbook>")
    return "".join(parts)


def _workbook_rels_xml(n_sheets):
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for i in range(1, n_sheets + 1):
        parts.append(
            '<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{0}.xml"/>'.format(i)
        )
    parts.append(
        '<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'.format(n_sheets + 1)
    )
    parts.append(
        '<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'.format(n_sheets + 2)
    )
    parts.append("</Relationships>")
    return "".join(parts)


def _shared_strings_xml(strings):
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' count="{0}" uniqueCount="{0}">'.format(len(strings)),
    ]
    for s in strings:
        parts.append("<si><t xml:space=\"preserve\">{0}</t></si>".format(_escape_xml(s)))
    parts.append("</sst>")
    return "".join(parts)


def _styles_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf/></cellXfs>'
        '</styleSheet>'
    )


def _escape_xml(s):
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
