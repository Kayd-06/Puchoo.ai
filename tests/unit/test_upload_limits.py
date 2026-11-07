"""Resource limits for spreadsheet and CSV uploads."""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from apps.core.upload_limits import (
    UploadLimitError,
    UploadLimits,
    inspect_xlsx,
    read_tabular,
)


def limits(**overrides) -> UploadLimits:
    base = dict(
        xlsx_max_uncompressed_bytes=50 * 1024 * 1024,
        xlsx_max_compression_ratio=100,
        max_sheets=5,
        max_rows=100,
        max_columns=10,
        max_cells=500,
    )
    base.update(overrides)
    return UploadLimits(**base)


def xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def bomb_xlsx(uncompressed: int = 64 * 1024 * 1024) -> bytes:
    """A real workbook plus one worksheet part that inflates ~1000:1."""

    source = zipfile.ZipFile(io.BytesIO(xlsx_bytes({"data": pd.DataFrame({"a": [1]})})))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in source.infolist():
            payload = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                payload = payload + b" " * uncompressed
            archive.writestr(
                item.filename,
                payload,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return buffer.getvalue()


def test_default_limits_and_env_overrides(monkeypatch):
    defaults = UploadLimits.from_env()
    assert defaults.max_columns == 500 and defaults.xlsx_max_compression_ratio == 100
    monkeypatch.setenv("UPLOAD_MAX_ROWS", "7")
    monkeypatch.setenv("UPLOAD_MAX_SHEETS", "nonsense")
    monkeypatch.setenv("UPLOAD_MAX_CELLS", "-1")
    configured = UploadLimits.from_env()
    assert configured.max_rows == 7
    assert configured.max_sheets == defaults.max_sheets
    assert configured.max_cells == defaults.max_cells


def test_normal_files_are_read():
    frames = read_tabular("sales.csv", b"month,revenue\nJan,1\nFeb,2\n", limits())
    assert list(frames) == ["sales"] and frames["sales"].shape == (2, 2)
    frames = read_tabular(
        "book.xlsx",
        xlsx_bytes({"a": pd.DataFrame({"x": [1, 2]}), "b": pd.DataFrame({"y": [3]})}),
        limits(),
    )
    assert set(frames) == {"a", "b"}


def test_high_ratio_xlsx_is_rejected_before_parsing():
    bomb = bomb_xlsx()
    assert len(bomb) < 1024 * 1024
    with pytest.raises(UploadLimitError, match="compressed too heavily") as caught:
        read_tabular("bomb.xlsx", bomb, limits())
    assert caught.value.status_code == 413


def test_xlsx_uncompressed_total_is_capped():
    with pytest.raises(UploadLimitError, match="too large once uncompressed") as caught:
        inspect_xlsx(
            bomb_xlsx(8 * 1024 * 1024),
            limits(
                xlsx_max_uncompressed_bytes=4 * 1024 * 1024,
                xlsx_max_compression_ratio=100_000,
            ),
        )
    assert caught.value.status_code == 413


def test_sheet_count_is_capped():
    book = xlsx_bytes({f"s{i}": pd.DataFrame({"a": [i]}) for i in range(4)})
    with pytest.raises(UploadLimitError, match="4 sheets; the limit is 3"):
        read_tabular("many.xlsx", book, limits(max_sheets=3))


def test_rows_columns_and_cells_are_capped_for_csv():
    rows = b"a,b\n" + b"1,2\n" * 101
    with pytest.raises(UploadLimitError, match="more than 100 rows") as caught:
        read_tabular("rows.csv", rows, limits())
    assert caught.value.status_code == 400
    wide = (
        ",".join(f"c{i}" for i in range(11)) + "\n" + ",".join("1" * 11) + "\n"
    ).encode()
    with pytest.raises(UploadLimitError, match="11 columns; the limit is 10"):
        read_tabular("wide.csv", wide, limits())
    cells = b"a,b,c,d,e,f\n" + b"1,2,3,4,5,6\n" * 90
    with pytest.raises(UploadLimitError, match="more than 500 cells"):
        read_tabular("cells.csv", cells, limits())


def test_rows_columns_and_cells_are_capped_for_xlsx():
    with pytest.raises(UploadLimitError, match="rows"):
        read_tabular(
            "rows.xlsx", xlsx_bytes({"s": pd.DataFrame({"a": range(101)})}), limits()
        )
    with pytest.raises(UploadLimitError, match="columns"):
        read_tabular(
            "wide.xlsx",
            xlsx_bytes({"s": pd.DataFrame({f"c{i}": [1] for i in range(11)})}),
            limits(),
        )
    with pytest.raises(UploadLimitError, match="cells"):
        read_tabular(
            "cells.xlsx",
            xlsx_bytes(
                {
                    "a": pd.DataFrame({f"c{i}": range(60) for i in range(5)}),
                    "b": pd.DataFrame({f"c{i}": range(60) for i in range(5)}),
                }
            ),
            limits(),
        )


def rewrite_xlsx(book, replacements):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(book)) as source, zipfile.ZipFile(
        output, "w", zipfile.ZIP_STORED
    ) as target:
        for member in source.infolist():
            target.writestr(
                member.filename, replacements.get(member.filename, source.read(member))
            )
        for name, value in replacements.items():
            if name not in source.namelist():
                target.writestr(name, value)
    return output.getvalue()


def test_cumulative_sheet_budget_rejected_before_excel_driver_allocation(monkeypatch):
    book = xlsx_bytes(
        {
            name: pd.DataFrame({"x": range(30), "y": range(30)})
            for name in ["one", "two", "three"]
        }
    )
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *a, **k: pytest.fail("oversized workbook reached dataframe driver"),
    )
    with pytest.raises(UploadLimitError, match="cells"):
        read_tabular("cumulative.xlsx", book, limits(max_cells=100))


@pytest.mark.parametrize("coordinate", ["XFD1048576", "ZZZ9999999", "A" + "9" * 10000])
def test_sparse_or_excessive_coordinates_rejected_before_dense_allocation(
    monkeypatch, coordinate
):
    book = xlsx_bytes({"s": pd.DataFrame({"x": [1]})})
    replacement = f'<worksheet><dimension ref="A1:{coordinate}"/><sheetData/></worksheet>'.encode()
    book = rewrite_xlsx(book, {"xl/worksheets/sheet1.xml": replacement})
    monkeypatch.setattr(
        pd, "ExcelFile", lambda *a, **k: pytest.fail("sparse dimensions reached driver")
    )
    with pytest.raises(UploadLimitError):
        read_tabular("sparse.xlsx", book, limits())


def test_xml_entities_are_rejected_before_expansion(monkeypatch):
    book = xlsx_bytes({"s": pd.DataFrame({"x": [1]})})
    book = rewrite_xlsx(
        book,
        {
            "xl/worksheets/sheet1.xml": b'<!DOCTYPE worksheet [<!ENTITY secret "expanded">]><worksheet>&secret;</worksheet>'
        },
    )
    monkeypatch.setattr(
        pd, "ExcelFile", lambda *a, **k: pytest.fail("DTD reached driver")
    )
    with pytest.raises(UploadLimitError, match="entities/DTDs"):
        read_tabular("entity.xlsx", book, limits())


def test_shared_string_table_has_an_independent_preallocation_budget(monkeypatch):
    from apps.core.upload_limits import MAX_PARSE_CELLS

    book = xlsx_bytes({"s": pd.DataFrame({"x": [1]})})
    strings = (
        b"<sst>"
        + b"".join(f"<si><t>{i}</t></si>".encode() for i in range(MAX_PARSE_CELLS + 1))
        + b"</sst>"
    )
    book = rewrite_xlsx(book, {"xl/sharedStrings.xml": strings})
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *a, **k: pytest.fail("oversized shared strings reached driver"),
    )
    with pytest.raises(UploadLimitError, match="shared strings"):
        read_tabular("strings.xlsx", book, limits())


def test_legacy_xls_is_explicitly_rejected_without_any_driver(monkeypatch):
    monkeypatch.setattr(
        pd, "ExcelFile", lambda *a, **k: pytest.fail("legacy parser must not run")
    )
    with pytest.raises(UploadLimitError, match="Save as XLSX or CSV"):
        read_tabular("old.xls", b"fake legacy", limits())


def test_multiline_quoted_csv_header_cannot_hide_columns(monkeypatch):
    monkeypatch.setattr(
        pd, "read_csv", lambda *a, **k: pytest.fail("wide CSV reached dataframe parser")
    )
    with pytest.raises(UploadLimitError, match="columns"):
        read_tabular("wide.csv", b'"line1\nline2",b,c\n1,2,3\n', limits(max_columns=2))


def test_escaped_quote_text_counts_against_the_field_budget(monkeypatch):
    monkeypatch.setattr(
        pd,
        "read_csv",
        lambda *a, **k: pytest.fail("huge quote field reached dataframe parser"),
    )
    with pytest.raises(UploadLimitError, match="text exceeds"):
        read_tabular("quoted.csv", b'x\n"' + b'""' * 40000 + b'"\n', limits())


def test_quoted_commas_multiline_headers_and_values_still_parse_correctly():
    contents = b'"a,b","multi\nline"\r\n"quoted ""value""",3\r\n'
    frame = read_tabular("quoted.csv", contents, limits())["quoted"]
    assert list(frame.columns) == ["a,b", "multi\nline"]
    assert frame.iloc[0].tolist() == ['quoted "value"', 3]


def test_config_cannot_raise_unmeasured_hard_parser_ceilings(monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_CELLS", "999999999")
    monkeypatch.setenv("UPLOAD_XLSX_MAX_UNCOMPRESSED_BYTES", "999999999")
    configured = UploadLimits.from_env()
    assert configured.max_cells == 250000
    assert configured.xlsx_max_uncompressed_bytes == 32 * 1024 * 1024


def test_collection_remaining_budget_is_checked_before_parsing_next_file(
    tmp_path, monkeypatch
):
    from apps.core import workspaces

    original = pd.read_csv
    calls = []

    def tracked(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", tracked)
    monkeypatch.setattr(UploadLimits, "from_env", lambda: limits(max_cells=4))
    with pytest.raises(UploadLimitError, match="cells"):
        workspaces.create_tabular_collection_workspace(
            "combined",
            [("a.csv", b"x\n1\n2\n3\n"), ("b.csv", b"x\n4\n5\n")],
            storage_dir=tmp_path,
        )
    assert len(calls) == 1
    assert not list(tmp_path.glob("*.db"))


def test_zip_directory_is_bounded_before_zipfile_allocates_entry_objects(monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for number in range(10001):
            archive.writestr(f"part-{number}", b"")
    monkeypatch.setattr(
        zipfile,
        "ZipFile",
        lambda *a, **k: pytest.fail("excessive central directory reached ZipFile"),
    )
    with pytest.raises(UploadLimitError, match="too many internal parts"):
        read_tabular("many-parts.xlsx", buffer.getvalue(), limits())


@pytest.mark.parametrize(
    "payload",
    [
        b'<worksheet><dimension ref="A1:XFD1048576"/></worksheet>',
        b'<not-a-standard-root><row r="9999999"><c r="A9999999"/></row></not-a-standard-root>',
        b'<worksheet><row r="1">'
        + b'<c r="A1"><v>1</v></c>' * 501
        + b"</row></worksheet>",
        b"<worksheet>"
        + b'<row r="1"><c r="A1"><v>1</v></c></row>' * 102
        + b"</worksheet>",
        b"<worksheet>" + b"<nested>" * 65 + b"</nested>" * 65 + b"</worksheet>",
        b'<worksheet value="' + b"x" * 70000 + b'"/>',
    ],
)
def test_noncanonical_xml_parts_and_physical_expansion_are_preflighted(
    monkeypatch, payload
):
    book = rewrite_xlsx(
        xlsx_bytes({"s": pd.DataFrame({"x": [1]})}), {"hidden-binary-name.bin": payload}
    )
    monkeypatch.setattr(
        pd,
        "ExcelFile",
        lambda *a, **k: pytest.fail("noncanonical XML bypass reached dataframe driver"),
    )
    with pytest.raises(UploadLimitError):
        read_tabular("hidden.xlsx", book, limits())


def test_unreferenced_binary_image_does_not_break_ordinary_data_import():
    book = rewrite_xlsx(
        xlsx_bytes({"s": pd.DataFrame({"x": [1, 2]})}),
        {"xl/media/image.png": b"\x89PNG\r\n\x1a\nsynthetic-image"},
    )
    assert read_tabular("image.xlsx", book, limits())["s"]["x"].tolist() == [1, 2]


def test_style_objects_are_bounded_before_openpyxl_instantiates_them(monkeypatch):
    book = rewrite_xlsx(
        xlsx_bytes({"s": pd.DataFrame({"x": [1]})}),
        {
            "hidden-style.bin": b"<styleSheet><fonts>"
            + b"<font/>" * 10001
            + b"</fonts></styleSheet>"
        },
    )
    monkeypatch.setattr(
        pd, "ExcelFile", lambda *a, **k: pytest.fail("huge style table reached driver")
    )
    with pytest.raises(UploadLimitError, match="styles"):
        read_tabular("styles.xlsx", book, limits())


def test_xml_comment_apostrophes_do_not_hide_later_tag_boundaries():
    book = xlsx_bytes({"s": pd.DataFrame({"x": range(1000)})})
    with zipfile.ZipFile(io.BytesIO(book)) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml")
    xml = xml.replace(
        b"<worksheet ", b"<!-- author's optional comment -->\n<worksheet ", 1
    )
    book = rewrite_xlsx(book, {"xl/worksheets/sheet1.xml": xml})
    assert read_tabular("comment.xlsx", book, limits(max_rows=1000, max_cells=2000))[
        "s"
    ].shape == (1000, 1)


def test_invalid_workbook_container_returns_safe_import_error():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("unrelated.xml", b"<other/>")
    with pytest.raises(UploadLimitError, match="structure is invalid") as error:
        read_tabular("invalid.xlsx", buffer.getvalue(), limits())
    assert error.value.status_code == 400


def test_driver_decode_failure_closes_workbook_and_returns_safe_error(monkeypatch):
    book = xlsx_bytes({"s": pd.DataFrame({"x": [1]})})
    closed = []

    class FailedReader:
        sheet_names = ["s"]

        def parse(self, *args, **kwargs):
            raise KeyError("synthetic malformed sheet")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(pd, "ExcelFile", lambda *a, **k: FailedReader())
    with pytest.raises(UploadLimitError, match="sheet structure"):
        read_tabular("broken.xlsx", book, limits())
    assert closed == [True]
