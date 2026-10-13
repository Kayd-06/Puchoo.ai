"""Resource limits for spreadsheet and CSV uploads.

An uploaded file is bounded in bytes by the router, but a small XLSX (a zip
archive) can inflate to gigabytes, and a CSV can hold millions of tiny cells.
These checks run before and while pandas parses the file so one upload cannot
exhaust the server's memory or disk. Every limit is configurable by env var.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass

import pandas as pd


class UploadLimitError(ValueError):
    """An upload exceeded a resource limit. ``message`` is safe to show users."""

    def __init__(self, message: str, *, status_code: int = 413) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class UploadLimits:
    xlsx_max_uncompressed_bytes: int
    xlsx_max_compression_ratio: int
    max_sheets: int
    max_rows: int
    max_columns: int
    max_cells: int

    @classmethod
    def from_env(cls) -> "UploadLimits":
        return cls(
            xlsx_max_uncompressed_bytes=_env_int("UPLOAD_XLSX_MAX_UNCOMPRESSED_BYTES", 200 * 1024 * 1024),
            xlsx_max_compression_ratio=_env_int("UPLOAD_XLSX_MAX_COMPRESSION_RATIO", 100),
            max_sheets=_env_int("UPLOAD_MAX_SHEETS", 50),
            max_rows=_env_int("UPLOAD_MAX_ROWS", 1_000_000),
            max_columns=_env_int("UPLOAD_MAX_COLUMNS", 500),
            max_cells=_env_int("UPLOAD_MAX_CELLS", 10_000_000),
        )


_SHEET_ENTRY = re.compile(r"^xl/worksheets/[^/]+\.xml$", re.IGNORECASE)
_MIN_RATIO_BYTES = 1024 * 1024  # tiny members may compress extremely well; ignore below 1 MiB


def inspect_xlsx(contents: bytes, limits: UploadLimits) -> None:
    """Check the zip's declared sizes before any XML is decompressed."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise UploadLimitError("The Excel file is not a valid XLSX archive.", status_code=400) from exc
    with archive:
        members = archive.infolist()
        if len(members) > 10_000:
            raise UploadLimitError("The Excel file contains too many internal parts.")
        total = 0
        compressed_total = 0
        sheets = 0
        for member in members:
            total += member.file_size
            compressed_total += member.compress_size
            if _SHEET_ENTRY.match(member.filename):
                sheets += 1
            if member.file_size > _MIN_RATIO_BYTES and (
                member.file_size > limits.xlsx_max_compression_ratio * max(member.compress_size, 1)
            ):
                raise UploadLimitError(
                    "The Excel file is compressed too heavily to import safely "
                    f"(over {limits.xlsx_max_compression_ratio}:1)."
                )
        if total > limits.xlsx_max_uncompressed_bytes:
            raise UploadLimitError(
                "The Excel file is too large once uncompressed "
                f"(limit {limits.xlsx_max_uncompressed_bytes // (1024 * 1024)} MB)."
            )
        if total > _MIN_RATIO_BYTES and total > limits.xlsx_max_compression_ratio * max(compressed_total, 1):
            raise UploadLimitError(
                "The Excel file is compressed too heavily to import safely "
                f"(over {limits.xlsx_max_compression_ratio}:1)."
            )
        if sheets > limits.max_sheets:
            raise UploadLimitError(
                f"The Excel file has {sheets} sheets; the limit is {limits.max_sheets}.", status_code=400
            )


def _csv_header_columns(contents: bytes) -> int:
    first_line = contents.split(b"\n", 1)[0][: 1024 * 1024].decode("utf-8", errors="replace")
    try:
        return len(next(csv.reader([first_line]), []))
    except csv.Error:
        return 0


def check_frame(frame: pd.DataFrame, label: str, limits: UploadLimits) -> None:
    rows, columns = frame.shape
    if rows > limits.max_rows:
        raise UploadLimitError(f"{label} has more than {limits.max_rows:,} rows.", status_code=400)
    if columns > limits.max_columns:
        raise UploadLimitError(f"{label} has {columns:,} columns; the limit is {limits.max_columns:,}.", status_code=400)


def _check_cells(frames: dict, limits: UploadLimits) -> None:
    cells = sum(frame.shape[0] * frame.shape[1] for frame in frames.values())
    if cells > limits.max_cells:
        raise UploadLimitError(f"The upload has more than {limits.max_cells:,} cells.", status_code=400)


def read_tabular(filename: str, contents: bytes, limits: UploadLimits | None = None) -> dict[str, pd.DataFrame]:
    """Parse a CSV/XLSX/XLS upload into named frames, enforcing every limit."""

    limits = limits or UploadLimits.from_env()
    suffix = os.path.splitext(filename)[1].lower()
    stem = os.path.splitext(os.path.basename(filename))[0]
    # Read one row past the cap so "too many rows" is detected without loading the rest.
    nrows = limits.max_rows + 1
    if suffix == ".csv":
        header_columns = _csv_header_columns(contents)
        if header_columns > limits.max_columns:
            raise UploadLimitError(
                f"{filename} has {header_columns:,} columns; the limit is {limits.max_columns:,}.", status_code=400
            )
        frames = {stem: pd.read_csv(io.BytesIO(contents), nrows=nrows)}
    elif suffix in {".xlsx", ".xls"}:
        if suffix == ".xlsx":
            inspect_xlsx(contents, limits)
        excel = pd.ExcelFile(io.BytesIO(contents))
        if len(excel.sheet_names) > limits.max_sheets:
            raise UploadLimitError(
                f"The Excel file has {len(excel.sheet_names)} sheets; the limit is {limits.max_sheets}.",
                status_code=400,
            )
        frames = {name: excel.parse(name, nrows=nrows) for name in excel.sheet_names}
    else:
        raise ValueError("Upload a CSV, XLSX, or XLS file.")
    for name, frame in frames.items():
        check_frame(frame, f"{filename} ({name})" if suffix != ".csv" else filename, limits)
    _check_cells(frames, limits)
    return frames


__all__ = ["UploadLimitError", "UploadLimits", "check_frame", "inspect_xlsx", "read_tabular"]
