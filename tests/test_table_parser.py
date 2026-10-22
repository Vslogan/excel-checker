"""Tests for table_parser module."""
import pytest
from src.core.table_parser import TableData


def test_empty_text():
    table = TableData.from_text("")
    assert table.rows == 0
    assert table.cols == 0
    assert table.get_cell(0, 0) == ""


def test_plain_text_1x1():
    # User requirement: "注意部分复制软件会把1x1的表格复制为纯文本，软件为了兼容将普通文本一律视为1x1表格"
    table = TableData.from_text("12345")
    assert table.rows == 1
    assert table.cols == 1
    assert table.get_cell(0, 0) == "12345"
    assert table.matches_size(1, 1)


def test_plain_text_with_trailing_newline():
    table = TableData.from_text("12345\r\n")
    assert table.rows == 1
    assert table.cols == 1
    assert table.get_cell(0, 0) == "12345"
    assert table.matches_size(1, 1)


def test_excel_tsv_2x2():
    raw = "A1\tB1\r\nA2\tB2\r\n"
    table = TableData.from_text(raw)
    assert table.rows == 2
    assert table.cols == 2
    assert table.get_cell(0, 0) == "A1"
    assert table.get_cell(0, 1) == "B1"
    assert table.get_cell(1, 0) == "A2"
    assert table.get_cell(1, 1) == "B2"
    assert table.matches_size(2, 2)
    assert not table.matches_size(1, 1)


def test_ragged_table():
    raw = "A1\tB1\tC1\r\nA2\tB2\r\n"
    table = TableData.from_text(raw)
    assert table.rows == 2
    assert table.cols == 3
    assert table.get_cell(1, 2) == ""


def test_csv_to_tsv():
    csv_str = "col1,col2\nval1,val2"
    table = TableData.from_csv_string(csv_str)
    assert table.rows == 2
    assert table.cols == 2
    tsv = table.to_tsv()
    assert tsv == "col1\tcol2\r\nval1\tval2"
