"""Resource limits for spreadsheet and CSV uploads.

An uploaded file is bounded in bytes by the router, but a small XLSX (a zip
archive) can inflate to gigabytes, and a CSV can hold millions of tiny cells.
Streaming preflight bounds logical expansion before pandas/openpyxl materializes
frames. Configuration can LOWER the documented hard ceilings. This is not an
absolute whole-server RSS guarantee; deployment/concurrency sizing is separate.
"""

from __future__ import annotations

import io
import os
import posixpath
import re
import struct
import zipfile
from xml.parsers import expat
from dataclasses import dataclass, replace

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
        return bounded_limits(
            cls(
                xlsx_max_uncompressed_bytes=_env_int(
                    "UPLOAD_XLSX_MAX_UNCOMPRESSED_BYTES", 32 * 1024 * 1024
                ),
                xlsx_max_compression_ratio=_env_int(
                    "UPLOAD_XLSX_MAX_COMPRESSION_RATIO", 100
                ),
                max_sheets=_env_int("UPLOAD_MAX_SHEETS", 50),
                max_rows=_env_int("UPLOAD_MAX_ROWS", 1_000_000),
                max_columns=_env_int("UPLOAD_MAX_COLUMNS", 500),
                max_cells=_env_int("UPLOAD_MAX_CELLS", 250_000),
            )
        )


# Hard parser ceilings cannot be raised through configuration. Lower limits are
# honored. These bound input and logical expansion BEFORE pandas/openpyxl allocates.
MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_XML_PART_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024 * 1024
MAX_FIELD_BYTES = 32_768
MAX_PARSE_CELLS = 250_000
MAX_XML_ELEMENTS = 1_000_000


def bounded_limits(limits):
    return replace(
        limits,
        max_cells=min(limits.max_cells, MAX_PARSE_CELLS),
        max_columns=min(limits.max_columns, 500),
        max_rows=min(limits.max_rows, 1_000_000),
        max_sheets=min(limits.max_sheets, 50),
        xlsx_max_uncompressed_bytes=min(
            limits.xlsx_max_uncompressed_bytes, MAX_XML_BYTES
        ),
    )


_SHEET_ENTRY = re.compile(r"^xl/worksheets/[^/]+\.xml$", re.IGNORECASE)
_MIN_RATIO_BYTES = (
    1024 * 1024
)  # tiny members may compress extremely well; ignore below 1 MiB


def _zip_directory_budget(contents):
    # ZipFile constructs its entire entry list before infolist() can be checked.
    # Bound/scan the central directory ourselves first, without entry objects.
    end = contents.rfind(b"PK\x05\x06", max(0, len(contents) - 65557))
    if end < 0 or end + 22 > len(contents):
        raise UploadLimitError("Invalid XLSX ZIP directory.", status_code=400)
    disk, directory_disk, disk_count, count, size, offset, comment = struct.unpack_from(
        "<4H2IH", contents, end + 4
    )
    if (
        disk
        or directory_disk
        or disk_count != count
        or count == 65535
        or size == 0xFFFFFFFF
        or offset == 0xFFFFFFFF
        or end + 22 + comment != len(contents)
        or offset + size != end
    ):
        raise UploadLimitError(
            "ZIP64, multipart or irregular XLSX archives are unsupported.",
            status_code=400,
        )
    if count > 10000 or size > 4 * 1024 * 1024:
        raise UploadLimitError(
            "The Excel file contains too many internal parts or directory metadata."
        )
    position, seen = offset, 0
    while position < offset + size:
        if (
            position + 46 > offset + size
            or contents[position : position + 4] != b"PK\x01\x02"
        ):
            raise UploadLimitError("Invalid XLSX ZIP directory.", status_code=400)
        lengths = struct.unpack_from("<3H", contents, position + 28)
        compressed, expanded = struct.unpack_from("<2I", contents, position + 20)
        method = struct.unpack_from("<H", contents, position + 10)[0]
        if (
            lengths[0] > 1024
            or compressed == 0xFFFFFFFF
            or expanded == 0xFFFFFFFF
            or method not in (0, 8)
        ):
            raise UploadLimitError("Unsupported or excessive XLSX ZIP metadata.")
        position += 46 + sum(lengths)
        seen += 1
        if seen > 10000 or position > offset + size:
            raise UploadLimitError("The Excel ZIP directory exceeds its parser budget.")
    if seen != count:
        raise UploadLimitError("Inconsistent XLSX ZIP entry count.", status_code=400)


def inspect_xlsx(contents: bytes, limits: UploadLimits) -> None:
    """Check the zip's declared sizes before any XML is decompressed."""

    limits = bounded_limits(limits)
    if len(contents) > MAX_INPUT_BYTES:
        raise UploadLimitError("Upload exceeds the 25 MiB hard parser input budget.")
    _zip_directory_budget(contents)
    try:
        archive = zipfile.ZipFile(io.BytesIO(contents))
    except zipfile.BadZipFile as exc:
        raise UploadLimitError(
            "The Excel file is not a valid XLSX archive.", status_code=400
        ) from exc
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
                member.file_size
                > limits.xlsx_max_compression_ratio * max(member.compress_size, 1)
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
        if (
            total > _MIN_RATIO_BYTES
            and total > limits.xlsx_max_compression_ratio * max(compressed_total, 1)
        ):
            raise UploadLimitError(
                "The Excel file is compressed too heavily to import safely "
                f"(over {limits.xlsx_max_compression_ratio}:1)."
            )
        if sheets > limits.max_sheets:
            raise UploadLimitError(
                f"The Excel file has {sheets} sheets; the limit is {limits.max_sheets}.",
                status_code=400,
            )


def _preflight_csv(contents, limits, label):
    # RFC4180-style quoting, including multiline headers/escaped quotes. No row
    # list is constructed here, so millions of delimiters cannot allocate fields.
    state, columns, header, rows, field_bytes, total_text = "start", 1, None, 0, 0, 0
    record, previous_cr = False, False

    def finish_record():
        nonlocal columns, header, rows, field_bytes, record
        if record:
            if header is None:
                header = columns
            else:
                rows += 1
                if columns > header:
                    raise UploadLimitError(
                        "CSV row has more fields than its header.", status_code=400
                    )
                if rows > limits.max_rows:
                    raise UploadLimitError(
                        f"{label} has more than {limits.max_rows:,} rows.",
                        status_code=400,
                    )
                if rows * header > limits.max_cells:
                    raise UploadLimitError(
                        f"The upload has more than {limits.max_cells:,} cells.",
                        status_code=400,
                    )
        columns, field_bytes, record = 1, 0, False

    for byte in contents.removeprefix(b"\xef\xbb\xbf"):
        if previous_cr and byte == 10 and state != "quoted":
            previous_cr = False
            continue
        previous_cr = False
        if state == "quoted":
            if byte == 34:
                state = "after_quote"
            else:
                field_bytes += 1
                total_text += 1
        elif byte == 34 and state in {"start", "after_quote"}:
            if state == "after_quote":
                field_bytes += 1
                total_text += 1
            state = "quoted"
            record = True
        elif byte == 44:
            columns += 1
            field_bytes = 0
            record = True
            state = "start"
            if columns > limits.max_columns:
                raise UploadLimitError(
                    f"The CSV has {columns:,} columns; the limit is {limits.max_columns:,}.",
                    status_code=400,
                )
        elif byte in (10, 13):
            finish_record()
            state = "start"
            previous_cr = byte == 13
        elif state == "after_quote":
            raise UploadLimitError(
                "Invalid CSV quoting after a closing quote.", status_code=400
            )
        else:
            if byte == 34:
                raise UploadLimitError("Invalid CSV quoting.", status_code=400)
            state = "unquoted"
            field_bytes += 1
            total_text += 1
            record = True
        if field_bytes > MAX_FIELD_BYTES or total_text > MAX_TEXT_BYTES:
            raise UploadLimitError("CSV text exceeds the safe parser budget.")
    if state == "quoted":
        raise UploadLimitError("Unclosed CSV quoted field.", status_code=400)
    finish_record()


def _preflight_xml(archive, limits):
    total_cells, total_text, strings, elements, observed_sheets, style_nodes = (
        0,
        0,
        0,
        0,
        0,
        0,
    )
    coordinate = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})\Z")
    for member in archive.infolist():
        if member.is_dir():
            continue
        if member.file_size > MAX_XML_PART_BYTES:
            raise UploadLimitError(
                "An Excel internal part exceeds the safe parser budget."
            )
        worksheet, shared, root_seen = False, False, False
        workbook_part, sheet_references, worksheet_targets = False, set(), set()
        max_row, max_column, current_row, current_column, field_size = 0, 0, 0, 0, 0
        physical_rows, physical_columns, depth = 0, 0, 0
        tag_bytes, in_tag, quote = 0, False, None
        tag_prefix, tag_tail, tag_mode = b"", b"", None

        def fail_dtd(*args):
            raise UploadLimitError(
                "Excel XML entities/DTDs are not supported.", status_code=400
            )

        def bound(row, column):
            nonlocal max_row, max_column
            max_row, max_column = max(max_row, row), max(max_column, column)
            if max_row > limits.max_rows + 1:
                raise UploadLimitError(
                    f"The Excel sheet has more than {limits.max_rows:,} rows.",
                    status_code=400,
                )
            if max_column > limits.max_columns:
                raise UploadLimitError(
                    f"The Excel sheet has {max_column:,} columns; the limit is {limits.max_columns:,}.",
                    status_code=400,
                )
            if (
                total_cells + max(0, max_row - 1) * max(1, max_column)
                > limits.max_cells
            ):
                raise UploadLimitError(
                    f"The upload has more than {limits.max_cells:,} cells.",
                    status_code=400,
                )

        def position(value):
            match = coordinate.fullmatch(value)
            if not match:
                raise UploadLimitError(
                    "Invalid or excessive Excel cell coordinates.", status_code=400
                )
            column = 0
            for character in match[1].upper():
                column = column * 26 + ord(character) - 64
            return int(match[2]), column

        def start(name, attrs):
            nonlocal elements, strings, current_row, current_column, field_size
            nonlocal worksheet, shared, root_seen, observed_sheets, physical_rows, physical_columns, depth
            nonlocal style_nodes, workbook_part
            root_seen = True
            depth += 1
            if depth > 64 or len(attrs) > 64:
                raise UploadLimitError(
                    "Excel XML nesting/attributes exceed the safe parser budget."
                )
            elements += 1
            if elements > MAX_XML_ELEMENTS:
                raise UploadLimitError(
                    "Excel XML complexity exceeds the safe parser budget."
                )
            tag = name.rsplit("}", 1)[-1]
            if tag == "workbook":
                workbook_part = True
            if workbook_part and tag == "sheet":
                reference = next(
                    (v for k, v in attrs.items() if k.endswith("}id")), None
                )
                if reference is None or reference in sheet_references:
                    raise UploadLimitError(
                        "Repeated or invalid worksheet references are unsupported.",
                        status_code=400,
                    )
                sheet_references.add(reference)
                if len(sheet_references) > limits.max_sheets:
                    raise UploadLimitError(
                        "The workbook exceeds the sheet budget.", status_code=400
                    )
            if tag == "Relationship" and attrs.get("Type", "").endswith("/worksheet"):
                target = attrs.get("Target", "")
                # Relative worksheet targets resolve beside the workbook, not beside its .rels.
                base = posixpath.dirname(posixpath.dirname(member.filename))
                canonical = posixpath.normpath(
                    target.lstrip("/")
                    if target.startswith("/")
                    else posixpath.join(base, target)
                )
                if (
                    not target
                    or attrs.get("TargetMode") == "External"
                    or canonical in worksheet_targets
                ):
                    raise UploadLimitError(
                        "Repeated or external worksheet targets are unsupported.",
                        status_code=400,
                    )
                worksheet_targets.add(canonical)
            if tag in {"font", "fill", "border", "xf", "numFmt", "cellStyle"}:
                style_nodes += 1
                if style_nodes > 10000:
                    raise UploadLimitError(
                        "Excel styles exceed the safe parser budget."
                    )
            if tag in {"worksheet", "row", "c", "dimension"} and not worksheet:
                worksheet = True
                observed_sheets += 1
                if observed_sheets > limits.max_sheets:
                    raise UploadLimitError(
                        "Excel worksheet parts exceed the sheet budget.",
                        status_code=400,
                    )
            if tag in {"sst", "si"}:
                shared = True
            if tag == "si":
                strings += 1
                field_size = 0
                if strings > MAX_PARSE_CELLS:
                    raise UploadLimitError(
                        "Excel shared strings exceed the safe parser budget."
                    )
            if worksheet:
                if tag == "dimension" and "ref" in attrs:
                    bound(*position(attrs["ref"].split(":")[-1]))
                elif tag == "row":
                    value = attrs.get("r", str(current_row + 1))
                    if not re.fullmatch(r"[1-9][0-9]{0,6}", value):
                        raise UploadLimitError(
                            "Invalid Excel row coordinate.", status_code=400
                        )
                    current_row, current_column = int(value), 0
                    physical_rows += 1
                    physical_columns = 0
                    bound(max(current_row, physical_rows), max_column)
                elif tag == "c":
                    row, column = (
                        position(attrs["r"])
                        if "r" in attrs
                        else (current_row, current_column + 1)
                    )
                    current_column = column
                    physical_columns += 1
                    field_size = 0
                    bound(max(row, physical_rows), max(column, physical_columns))

        def text(value):
            nonlocal total_text, field_size
            size = len(value.encode("utf-8"))
            total_text += size
            field_size += size
            if (
                total_text > MAX_TEXT_BYTES
                or (worksheet or shared)
                and field_size > MAX_FIELD_BYTES
            ):
                raise UploadLimitError("Excel text exceeds the safe parser budget.")

        parser = expat.ParserCreate(namespace_separator="}")
        parser.StartDoctypeDeclHandler = fail_dtd
        parser.ExternalEntityRefHandler = fail_dtd

        def end(_name):
            nonlocal depth
            depth -= 1

        def token_budget(chunk):
            nonlocal in_tag, quote, tag_bytes, tag_prefix, tag_tail, tag_mode
            for byte in chunk:
                if not in_tag:
                    if byte == 60:
                        in_tag, tag_bytes, quote = True, 1, None
                        tag_prefix, tag_tail, tag_mode = b"<", b"", None
                    continue
                tag_bytes += 1
                if tag_bytes > 65536:
                    raise UploadLimitError(
                        "Excel XML token exceeds the safe parser budget."
                    )
                if tag_mode is None:
                    if byte != 0:
                        tag_prefix += bytes((byte,))
                    if tag_prefix == b"<!--":
                        tag_mode = "comment"
                    elif tag_prefix == b"<![CDATA[":
                        tag_mode = "cdata"
                    elif tag_prefix == b"<?":
                        tag_mode = "pi"
                    elif len(tag_prefix) >= 2 and tag_prefix[1:2] != b"!":
                        tag_mode = "tag"
                    elif len(tag_prefix) >= 3 and tag_prefix[2:3] not in (b"-", b"["):
                        tag_mode = "tag"
                if tag_mode in {"comment", "cdata", "pi"}:
                    if byte != 0:
                        tag_tail = (tag_tail + bytes((byte,)))[-3:]
                    ending = {"comment": b"-->", "cdata": b"]]>", "pi": b"?>"}[tag_mode]
                    if tag_tail.endswith(ending):
                        in_tag = False
                elif quote is not None:
                    if byte == quote:
                        quote = None
                elif byte in (34, 39):
                    quote = byte
                elif byte == 62:
                    in_tag = False

        parser.StartElementHandler, parser.CharacterDataHandler = start, text
        parser.EndElementHandler = end
        try:
            with archive.open(member) as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    token_budget(chunk)
                    parser.Parse(chunk, False)
                parser.Parse(b"", True)
        except (expat.ExpatError, zipfile.BadZipFile) as exc:
            if (
                isinstance(exc, expat.ExpatError)
                and not root_seen
                and not member.filename.lower().endswith((".xml", ".rels"))
            ):
                continue  # Ordinary binary images/print settings are not XML and not inflated by pandas.
            raise UploadLimitError(
                "Invalid Excel XML content.", status_code=400
            ) from exc
        if worksheet:
            total_cells += max(0, max_row - 1) * max(1, max_column)


def check_frame(frame: pd.DataFrame, label: str, limits: UploadLimits) -> None:
    rows, columns = frame.shape
    if rows > limits.max_rows:
        raise UploadLimitError(
            f"{label} has more than {limits.max_rows:,} rows.", status_code=400
        )
    if columns > limits.max_columns:
        raise UploadLimitError(
            f"{label} has {columns:,} columns; the limit is {limits.max_columns:,}.",
            status_code=400,
        )


def _check_cells(frames: dict, limits: UploadLimits) -> None:
    cells = sum(frame.shape[0] * frame.shape[1] for frame in frames.values())
    if cells > limits.max_cells:
        raise UploadLimitError(
            f"The upload has more than {limits.max_cells:,} cells.", status_code=400
        )


def read_tabular(
    filename: str, contents: bytes, limits: UploadLimits | None = None
) -> dict[str, pd.DataFrame]:
    """Preflight and parse supported CSV/XLSX uploads into bounded named frames."""

    limits = bounded_limits(limits or UploadLimits.from_env())
    if len(contents) > MAX_INPUT_BYTES:
        raise UploadLimitError("Upload exceeds the 25 MiB hard parser input budget.")
    suffix = os.path.splitext(filename)[1].lower()
    stem = os.path.splitext(os.path.basename(filename))[0]
    # Read one row past the cap so "too many rows" is detected without loading the rest.
    nrows = limits.max_rows + 1
    if suffix == ".csv":
        _preflight_csv(contents, limits, filename)
        frames = {stem: pd.read_csv(io.BytesIO(contents), nrows=nrows)}
    elif suffix == ".xls":
        raise UploadLimitError(
            "Legacy XLS cannot be imported within the safe parser bounds. Save as XLSX or CSV first.",
            status_code=400,
        )
    elif suffix == ".xlsx":
        inspect_xlsx(contents, limits)
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            if len({part.filename for part in archive.infolist()}) != len(
                archive.infolist()
            ) or any(part.flag_bits & 1 for part in archive.infolist()):
                raise UploadLimitError(
                    "Duplicate or encrypted Excel parts are not supported.",
                    status_code=400,
                )
            _preflight_xml(archive, limits)
        try:
            excel = pd.ExcelFile(io.BytesIO(contents))
        except Exception as exc:
            raise UploadLimitError(
                "The XLSX workbook structure is invalid or unsupported.",
                status_code=400,
            ) from exc
        try:
            if len(excel.sheet_names) > limits.max_sheets:
                raise UploadLimitError(
                    f"The Excel file has {len(excel.sheet_names)} sheets; the limit is {limits.max_sheets}.",
                    status_code=400,
                )
            frames = {}
            cells = 0
            for name in excel.sheet_names:
                frame = excel.parse(name, nrows=nrows)
                check_frame(frame, f"{filename} ({name})", limits)
                cells += frame.shape[0] * frame.shape[1]
                if cells > limits.max_cells:
                    raise UploadLimitError(
                        f"The upload has more than {limits.max_cells:,} cells.",
                        status_code=400,
                    )
                frames[name] = frame
        except UploadLimitError:
            raise
        except Exception as exc:
            raise UploadLimitError(
                "The XLSX sheet structure is invalid or unsupported.", status_code=400
            ) from exc
        finally:
            excel.close()
    else:
        raise ValueError("Upload a CSV or XLSX file.")
    for name, frame in frames.items():
        check_frame(
            frame, f"{filename} ({name})" if suffix != ".csv" else filename, limits
        )
    _check_cells(frames, limits)
    return frames


__all__ = [
    "UploadLimitError",
    "UploadLimits",
    "check_frame",
    "inspect_xlsx",
    "read_tabular",
]
