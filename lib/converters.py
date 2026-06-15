"""Conversion functions between data formats.

Conversion graph (per docs/conversions.txt):

    CSV <--> TSV
      |
      | many files, each file = one sheet/tab
      v
    XLSX
      |
      | always possible
      | JSON may be too flexible to convert back to tabular data (validate first)
      v
    JSON <--> JSONL <--> YAML <--> TOML

All conversions go through one of two intermediate forms:
  - tabular: list[list[str]] (rows of cells), with a header row
  - structured: any JSON-compatible value (dict / list / scalars)

`tabular` and `structured` are interconvertible when `structured` is a
list of flat dicts.
"""

import csv
import io
import json


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

TEXT_FORMATS = ("csv", "tsv", "json", "jsonl", "yaml", "toml")
ALL_FORMATS = TEXT_FORMATS + ("xlsx",)

EXT_MAP = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xlsx": "xlsx",
}


def detect_format(filename, default="json"):
    if not filename:
        return default
    lower = filename.lower()
    for ext, fmt in EXT_MAP.items():
        if lower.endswith(ext):
            return fmt
    return default


# ---------------------------------------------------------------------------
# Tabular helpers
# ---------------------------------------------------------------------------

def read_csv_tsv(text, delimiter):
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader]


def write_csv_tsv(rows, delimiter):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def tabular_to_records(rows):
    """Convert [[header...], [row...], ...] to list[dict] with type coercion."""
    if not rows:
        return []
    header = rows[0]
    records = []
    for raw in rows[1:]:
        rec = {}
        for i, key in enumerate(header):
            val = raw[i] if i < len(raw) else ""
            rec[key] = _coerce_scalar(val)
        records.append(rec)
    return records


def records_to_tabular(records):
    """Convert list[dict] to [[header...], [row...], ...]. Errors if not flat."""
    if not isinstance(records, list):
        raise ValueError(
            "Cannot convert to tabular: expected a list of objects, got "
            + type(records).__name__
        )
    if not records:
        return [[]]
    headers = []
    seen = set()
    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError(
                "Cannot convert to tabular: every item must be an object."
            )
        for k in rec.keys():
            if k not in seen:
                seen.add(k)
                headers.append(k)
    rows = [list(headers)]
    for rec in records:
        rows.append([_stringify(rec.get(h, "")) for h in headers])
    return rows


def _coerce_scalar(s):
    if s is None:
        return None
    if not isinstance(s, str):
        return s
    if s == "":
        return ""
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    try:
        if "." in s or "e" in low:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _stringify(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


# ---------------------------------------------------------------------------
# Structured (JSON-compatible) <-> serialized
# ---------------------------------------------------------------------------

def parse_json(text):
    return json.loads(text)


def dump_json(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_jsonl(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def dump_jsonl(data):
    if not isinstance(data, list):
        raise ValueError("JSONL requires a list of records.")
    return "\n".join(json.dumps(item, ensure_ascii=False) for item in data) + "\n"


def parse_yaml(text):
    import yaml  # provided by Package Control dependency `pyyaml`
    return yaml.safe_load(text)


def dump_yaml(data):
    import yaml
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _import_toml():
    """Return the `toml` module (uiri/toml).

    Tries the externally installed package first, then falls back to the
    copy vendored under ``lib/_vendor/toml``.
    """
    try:
        import toml
        return toml
    except ImportError:
        from ._vendor import toml  # Vendored fallback
        return toml


def parse_toml(text):
    return _import_toml().loads(text)


def dump_toml(data):
    if not isinstance(data, dict):
        raise ValueError(
            "TOML requires the top-level value to be an object/table."
        )
    return _import_toml().dumps(data)


# ---------------------------------------------------------------------------
# High-level read/write dispatch
# ---------------------------------------------------------------------------

def read_text_format(text, fmt):
    """Parse a text payload of the given format and return a `structured` value
    (dict / list of dict / list / scalar).
    """
    if fmt == "csv":
        return tabular_to_records(read_csv_tsv(text, ","))
    if fmt == "tsv":
        return tabular_to_records(read_csv_tsv(text, "\t"))
    if fmt == "json":
        return parse_json(text)
    if fmt == "jsonl":
        return parse_jsonl(text)
    if fmt == "yaml":
        return parse_yaml(text)
    if fmt == "toml":
        return parse_toml(text)
    raise ValueError("Unknown text format: " + fmt)


def write_text_format(data, fmt):
    """Serialize a `structured` value to the given text format."""
    if fmt == "csv":
        return write_csv_tsv(records_to_tabular(data), ",")
    if fmt == "tsv":
        return write_csv_tsv(records_to_tabular(data), "\t")
    if fmt == "json":
        return dump_json(data)
    if fmt == "jsonl":
        if isinstance(data, dict):
            data = [data]
        return dump_jsonl(data)
    if fmt == "yaml":
        return dump_yaml(data)
    if fmt == "toml":
        # TOML expects a top-level table; wrap a list of records under "rows".
        if isinstance(data, list):
            data = {"rows": data}
        return dump_toml(data)
    raise ValueError("Unknown text format: " + fmt)


def convert_text(text, src_fmt, dst_fmt):
    """Convert a text payload from src_fmt to dst_fmt.

    Both formats must be in TEXT_FORMATS. XLSX is handled separately because
    it is a binary format and can hold multiple sheets.
    """
    if src_fmt not in TEXT_FORMATS:
        raise ValueError("Unsupported source text format: " + src_fmt)
    if dst_fmt not in TEXT_FORMATS:
        raise ValueError("Unsupported destination text format: " + dst_fmt)
    data = read_text_format(text, src_fmt)
    return write_text_format(data, dst_fmt)
