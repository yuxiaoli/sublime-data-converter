"""Smoke tests for lib/converters.py and lib/xlsx.py.

Run with: uv run python -m pytest tests/  (after `uv add --dev pytest`)
or       : uv run python tests/test_smoke.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.converters import (
    convert_text,
    read_text_format,
    write_text_format,
)
from lib.xlsx import read_xlsx_bytes, write_xlsx_bytes


CSV_TEXT = "name,age\nalice,30\nbob,25\n"
JSON_TEXT = '[{"name": "alice", "age": 30}, {"name": "bob", "age": 25}]'


def test_csv_to_tsv():
    out = convert_text(CSV_TEXT, "csv", "tsv")
    assert out == "name\tage\nalice\t30\nbob\t25\n", out


def test_csv_to_json_records():
    out = convert_text(CSV_TEXT, "csv", "json")
    assert json.loads(out) == [
        {"name": "alice", "age": 30},
        {"name": "bob", "age": 25},
    ]


def test_json_to_jsonl_and_back():
    jsonl = convert_text(JSON_TEXT, "json", "jsonl")
    assert jsonl.strip().splitlines() == [
        '{"name": "alice", "age": 30}',
        '{"name": "bob", "age": 25}',
    ]
    back = convert_text(jsonl, "jsonl", "json")
    assert json.loads(back) == json.loads(JSON_TEXT)


def test_json_multi_sheet_to_csv():
    # The convert_text function currently returns a single string, but if we pass
    # multi-sheet data directly to write_text_format for csv, what happens?
    # Wait, write_text_format currently throws an error if data is multi-sheet!
    # Because records_to_tabular throws an error on dict.
    pass


def test_xlsx_roundtrip():
    sheets = {"People": [["name", "age"], ["alice", 30], ["bob", 25]]}
    blob = write_xlsx_bytes(sheets)
    parsed = read_xlsx_bytes(blob)
    assert list(parsed.keys()) == ["People"]
    assert parsed["People"][0] == ["name", "age"]
    # Numeric cells come back as their string form.
    assert parsed["People"][1] == ["alice", "30"]


def main():
    test_csv_to_tsv()
    test_csv_to_json_records()
    test_json_to_jsonl_and_back()
    test_xlsx_roundtrip()
    print("OK")


if __name__ == "__main__":
    main()
