"""Resource limits for spreadsheet and CSV uploads."""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from apps.core.upload_limits import UploadLimitError, UploadLimits, inspect_xlsx, read_tabular


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
            archive.writestr(item.filename, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
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
    frames = read_tabular("book.xlsx", xlsx_bytes({"a": pd.DataFrame({"x": [1, 2]}), "b": pd.DataFrame({"y": [3]})}), limits())
    assert set(frames) == {"a", "b"}


def test_high_ratio_xlsx_is_rejected_before_parsing():
    bomb = bomb_xlsx()
    assert len(bomb) < 1024 * 1024
    with pytest.raises(UploadLimitError, match="compressed too heavily") as caught:
        read_tabular("bomb.xlsx", bomb, limits())
    assert caught.value.status_code == 413


def test_xlsx_uncompressed_total_is_capped():
    with pytest.raises(UploadLimitError, match="too large once uncompressed") as caught:
        inspect_xlsx(bomb_xlsx(8 * 1024 * 1024), limits(xlsx_max_uncompressed_bytes=4 * 1024 * 1024, xlsx_max_compression_ratio=100_000))
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
    wide = (",".join(f"c{i}" for i in range(11)) + "\n" + ",".join("1" * 11) + "\n").encode()
    with pytest.raises(UploadLimitError, match="11 columns; the limit is 10"):
        read_tabular("wide.csv", wide, limits())
    cells = b"a,b,c,d,e,f\n" + b"1,2,3,4,5,6\n" * 90
    with pytest.raises(UploadLimitError, match="more than 500 cells"):
        read_tabular("cells.csv", cells, limits())


def test_rows_columns_and_cells_are_capped_for_xlsx():
    with pytest.raises(UploadLimitError, match="rows"):
        read_tabular("rows.xlsx", xlsx_bytes({"s": pd.DataFrame({"a": range(101)})}), limits())
    with pytest.raises(UploadLimitError, match="columns"):
        read_tabular("wide.xlsx", xlsx_bytes({"s": pd.DataFrame({f"c{i}": [1] for i in range(11)})}), limits())
    with pytest.raises(UploadLimitError, match="cells"):
        read_tabular(
            "cells.xlsx",
            xlsx_bytes({"a": pd.DataFrame({f"c{i}": range(60) for i in range(5)}), "b": pd.DataFrame({f"c{i}": range(60) for i in range(5)})}),
            limits(),
        )
