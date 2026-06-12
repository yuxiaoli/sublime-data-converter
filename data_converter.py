"""Sublime Text plugin: convert between data formats.

Commands provided:
  - data_converter_convert       (args: to_format=<fmt>, [from_format=<fmt>])
  - data_converter_pick_format   (interactive quick panel)

Supported formats: csv, tsv, json, jsonl, yaml, toml, xlsx.

Output policy: a new view is opened and named "{input_filename}.{to_format}".
Binary outputs (xlsx) are written to a temporary file (next to the source
when possible) and that file is opened.
"""

import os
import tempfile
import traceback

import sublime
import sublime_plugin

# Sublime loads this module as `Packages.<PackageName>.data_converter`, so use
# relative imports for the bundled `lib` subpackage.
from .lib import xlsx as xlsx_mod
from .lib.converters import (
    ALL_FORMATS,
    TEXT_FORMATS,
    convert_text,
    detect_format,
    read_text_format,
    records_to_tabular,
    tabular_to_records,
    write_text_format,
)


def _input_basename(view):
    name = view.file_name()
    if name:
        base = os.path.basename(name)
        stem, _ = os.path.splitext(base)
        return stem or base
    name = view.name()
    if name:
        return name
    return "untitled"


def _output_view_name(view, to_format):
    return "{0}.{1}".format(_input_basename(view), to_format)


def _show_error(message):
    sublime.error_message("Data Converter: " + message)


def _open_text_in_new_view(window, text, name):
    new_view = window.new_file()
    new_view.set_name(name)
    new_view.set_scratch(True)
    new_view.run_command("append", {"characters": text})
    return new_view


# ---------------------------------------------------------------------------
# XLSX integration
# ---------------------------------------------------------------------------

def _records_for_xlsx_sheets(data):
    """Normalize structured data into a dict[sheet_name -> rows]."""
    if isinstance(data, dict):
        # Treat each top-level key as a sheet if its value is a list of dicts;
        # otherwise put the whole dict in a single sheet "Sheet1".
        is_multi = (
            data
            and all(
                isinstance(v, list)
                and v
                and all(isinstance(x, dict) for x in v)
                for v in data.values()
            )
        )
        if is_multi:
            return {name: records_to_tabular(rows) for name, rows in data.items()}
        return {"Sheet1": records_to_tabular([data])}
    if isinstance(data, list):
        return {"Sheet1": records_to_tabular(data)}
    raise ValueError(
        "Cannot convert this value to XLSX: expected an object or array of objects."
    )


def _xlsx_to_structured(sheets):
    """Convert the dict[sheet_name -> rows] returned by xlsx into structured.

    - Single sheet -> list[dict]
    - Multiple sheets -> dict[sheet_name -> list[dict]]
    """
    if len(sheets) == 1:
        rows = next(iter(sheets.values()))
        return tabular_to_records(rows)
    return {name: tabular_to_records(rows) for name, rows in sheets.items()}


def _read_view_as_structured(view, src_fmt):
    """Read the active view's content (or file) and return structured data."""
    if src_fmt == "xlsx":
        path = view.file_name()
        if not path or not os.path.isfile(path):
            raise ValueError(
                "XLSX input requires a saved file on disk."
            )
        with open(path, "rb") as fp:
            blob = fp.read()
        sheets = xlsx_mod.read_xlsx_bytes(blob)
        return _xlsx_to_structured(sheets)
    text = view.substr(sublime.Region(0, view.size()))
    return read_text_format(text, src_fmt)


def _write_structured_for_view(window, view, data, dst_fmt):
    """Serialize and present the result according to dst_fmt."""
    out_name = _output_view_name(view, dst_fmt)
    if dst_fmt == "xlsx":
        sheets = _records_for_xlsx_sheets(data)
        blob = xlsx_mod.write_xlsx_bytes(sheets)
        # Write to a real file so Sublime can open it.
        src_path = view.file_name()
        if src_path:
            out_path = os.path.join(os.path.dirname(src_path), out_name)
        else:
            out_path = os.path.join(tempfile.gettempdir(), out_name)
        with open(out_path, "wb") as fp:
            fp.write(blob)
        sublime.status_message("Data Converter: wrote " + out_path)
        window.open_file(out_path)
        return
    text = write_text_format(data, dst_fmt)
    _open_text_in_new_view(window, text, out_name)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

class DataConverterConvertCommand(sublime_plugin.TextCommand):
    """Convert the current view to a target format.

    Args:
        to_format: one of csv, tsv, json, jsonl, yaml, toml, xlsx.
        from_format: optional override; otherwise detected from file extension.
    """

    def run(self, edit, to_format=None, from_format=None):
        if not to_format or to_format not in ALL_FORMATS:
            _show_error(
                "Missing or invalid 'to_format'. Supported: "
                + ", ".join(ALL_FORMATS)
            )
            return

        view = self.view
        window = view.window() or sublime.active_window()
        if window is None:
            _show_error("No active window.")
            return

        src_fmt = from_format or detect_format(view.file_name() or view.name())
        if src_fmt not in ALL_FORMATS:
            _show_error(
                "Could not detect source format. Pass 'from_format' explicitly."
            )
            return
        if src_fmt == to_format:
            _show_error("Source and target formats are the same: " + src_fmt)
            return

        try:
            if src_fmt in TEXT_FORMATS and to_format in TEXT_FORMATS:
                text = view.substr(sublime.Region(0, view.size()))
                out = convert_text(text, src_fmt, to_format)
                _open_text_in_new_view(
                    window, out, _output_view_name(view, to_format)
                )
                return

            data = _read_view_as_structured(view, src_fmt)
            _write_structured_for_view(window, view, data, to_format)
        except ImportError as e:
            _show_error(
                "Missing dependency: {0}. Install via Package Control "
                "(pyyaml / tomli / tomli_w).".format(e)
            )
        except Exception as e:
            traceback.print_exc()
            _show_error("{0}: {1}".format(type(e).__name__, e))


class DataConverterPickFormatCommand(sublime_plugin.TextCommand):
    """Show a quick panel with candidate target formats."""

    def run(self, edit, from_format=None):
        view = self.view
        window = view.window() or sublime.active_window()
        if window is None:
            _show_error("No active window.")
            return

        src_fmt = from_format or detect_format(view.file_name() or view.name())
        targets = [f for f in ALL_FORMATS if f != src_fmt]
        if not targets:
            _show_error("No target formats available.")
            return

        labels = [
            ["Convert to {0}".format(f.upper()), "from {0}".format(src_fmt)]
            for f in targets
        ]

        def on_done(idx):
            if idx < 0:
                return
            view.run_command(
                "data_converter_convert",
                {"to_format": targets[idx], "from_format": src_fmt},
            )

        window.show_quick_panel(labels, on_done)
