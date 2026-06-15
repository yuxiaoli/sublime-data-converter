# data-converter (Sublime Text plugin)

Convert the active buffer between data formats per
[`docs/conversions.txt`](docs/conversions.txt):

```
CSV <--> TSV
  |
  | many files, each file = one sheet/tab
  v
XLSX
  |
  v
JSON <--> JSONL <--> YAML <--> TOML
```

## Commands

Open the Command Palette and search for:

- `Data Converter: Convert...` - pick the target via quick panel.
- `Data Converter: Convert to CSV / TSV / JSON / JSONL / YAML / TOML / XLSX`
- `Data Converter: Shorten Data` - Shorten a JSON object (if a value is a list, it gets shortened to its first element).

The source format is detected from the file extension. The result opens in a
new tab named `{input_filename}.{to_format}`. For multi-sheet structures (like a JSON dictionary containing lists of records) converted to CSV/TSV, it generates multiple tabs named `{input_filename}.{sheet}.{to_format}`. XLSX output is written to a real
file (next to the input when possible) and that file is opened.

## Dependencies

Declared in [`dependencies.json`](dependencies.json) and installed by
Package Control:

- `pyyaml` (YAML)

TOML support is provided by a vendored copy of `uiri/toml` to ensure compatibility across Sublime Text Python plugin hosts.

XLSX is handled with the Python standard library only (no `openpyxl`).
Supported XLSX cell types are strings and numbers; styles, formulas, and
dates are not preserved.

## Layout

- `data_converter.py` - Sublime command implementations.
- `lib/converters.py` - format detection, parse/dump, conversion graph.
- `lib/xlsx.py` - stdlib-only XLSX read/write.
- `Default.sublime-commands` - command palette entries.
- `dependencies.json` - Package Control dependency declaration.
