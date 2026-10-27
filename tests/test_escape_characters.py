"""Tests for escape character support in variables, expressions, and clipboard writing."""
import io
import pytest

from src.core.actions.compute import ComputeAction
from src.core.actions.write_clipboard import WriteClipboardAction
from src.core.context import ExecutionContext, HeadlessUIDelegate
from src.core.engine import WorkflowEngine
from src.core.expression import decode_escape_sequences, evaluate_expression
from src.core.table_parser import TableData


def test_expression_double_quoted_escapes():
    """Verify that double-quoted string literals in expressions correctly parse escape sequences."""
    # 1. Tab and newline
    assert evaluate_expression(r'"hello\tworld\n"') == "hello\tworld\n"

    # 2. Carriage return and newline
    assert evaluate_expression(r'"line1\r\nline2"') == "line1\r\nline2"

    # 3. Escaped double quote
    assert evaluate_expression(r'"say \"hello\""') == 'say "hello"'

    # 4. Escaped backslash
    assert evaluate_expression(r'"C:\\path\\file.txt"') == "C:\\path\\file.txt"

    # 5. Null, backspace, formfeed
    assert evaluate_expression(r'"a\0b\bc"') == "a\0b\bc"

    # 6. Unicode \uXXXX and \xXX
    assert evaluate_expression(r'"\u0041\x42"') == "AB"


def test_expression_single_quoted_escapes():
    """Verify that single-quoted string literals also parse escape sequences."""
    assert evaluate_expression(r"'first\tsecond\nthird'") == "first\tsecond\nthird"
    assert evaluate_expression(r"'it\'s fine'") == "it's fine"


def test_expression_builtin_functions_with_escapes():
    """Verify built-in functions with escape characters in string literals."""
    # strcat with tab and newline separators
    res = evaluate_expression(r'strcat("Col1", "\t", "Col2", "\n", "Row2")')
    assert res == "Col1\tCol2\nRow2"

    # substr with escape characters
    res2 = evaluate_expression(r'substr("A\tB\tC", 0, 3)')
    assert res2 == "A\tB"

    # string comparison with escape characters
    res3 = evaluate_expression(r'"\t" == "\t"')
    assert res3 == "1"
    res4 = evaluate_expression(r'"\t" == "\n"')
    assert res4 == "0"

    # ternary operator with escape sequences
    res5 = evaluate_expression(r'1 ? "has\ttab" : "no\ttab"')
    assert res5 == "has\ttab"


def test_variable_storing_and_using_escape_characters():
    """Verify that variables correctly store and manipulate values with escape characters."""
    ctx = ExecutionContext()
    delegate = HeadlessUIDelegate()

    # 1. Compute block storing escape characters into variable
    act1 = ComputeAction({
        "target_var": "delim",
        "expression": r'"\t"'
    })
    r1 = act1.execute(ctx, delegate)
    assert r1.success
    assert ctx.get_var("delim") == "\t"

    # 2. Compute block creating a newline variable
    act2 = ComputeAction({
        "target_var": "newline",
        "expression": r'"\r\n"'
    })
    r2 = act2.execute(ctx, delegate)
    assert r2.success
    assert ctx.get_var("newline") == "\r\n"

    # 3. Concatenate using variable names directly in expression
    act3 = ComputeAction({
        "target_var": "row_data",
        "expression": 'strcat("ID01", delim, "ItemA", newline, "ID02", delim, "ItemB")'
    })
    r3 = act3.execute(ctx, delegate)
    assert r3.success
    assert ctx.get_var("row_data") == "ID01\tItemA\r\nID02\tItemB"

    # 4. Context template interpolation with variables holding escape characters
    rendered = ctx.render_template("Header:\n{{row_data}}")
    assert rendered == "Header:\nID01\tItemA\r\nID02\tItemB"


def test_write_clipboard_text_mode_with_escapes():
    """Verify write_clipboard in text mode properly decodes escape sequences."""
    ctx = ExecutionContext()
    ctx.set_var("username", "admin")
    delegate = HeadlessUIDelegate()

    # Literal \t and \n in data template
    act = WriteClipboardAction({
        "type": "text",
        "data": r"User: {{username}}\nRole:\tAdministrator\nStatus:\tActive"
    })
    res = act.execute(ctx, delegate)
    assert res.success

    clip = delegate.get_clipboard()
    assert clip == "User: admin\nRole:\tAdministrator\nStatus:\tActive"
    # Ensure real tab and newline are present
    assert "\t" in clip
    assert "\n" in clip
    assert "\\t" not in clip
    assert "\\n" not in clip


def test_write_clipboard_table_mode_tsv():
    """Verify write_clipboard in table mode converts tab-separated text to Excel native TSV."""
    ctx = ExecutionContext()
    ctx.set_var("v1", "100")
    ctx.set_var("v2", "200")
    delegate = HeadlessUIDelegate()

    act = WriteClipboardAction({
        "type": "table",
        "data": r"COL_A\tCOL_B\n{{v1}}\t{{v2}}\n300\t400"
    })
    res = act.execute(ctx, delegate)
    assert res.success

    clip = delegate.get_clipboard()
    # Excel TSV expects \t between columns and \r\n between rows
    assert clip == "COL_A\tCOL_B\r\n100\t200\r\n300\t400"


def test_write_clipboard_table_mode_csv_conversion():
    """Verify write_clipboard in table mode converts comma-separated text with \n to Excel native TSV."""
    ctx = ExecutionContext()
    ctx.set_var("order_id", "ORD-999")
    delegate = HeadlessUIDelegate()

    act = WriteClipboardAction({
        "type": "table",
        "data": r"ID,Status,Amount\n{{order_id}},Paid,199.9\nORD-1000,Pending,50.0"
    })
    res = act.execute(ctx, delegate)
    assert res.success

    clip = delegate.get_clipboard()
    assert clip == "ID\tStatus\tAmount\r\nORD-999\tPaid\t199.9\r\nORD-1000\tPending\t50.0"


def test_write_clipboard_with_computed_escape_variable():
    """End-to-end test: compute variable with tabs/newlines and write to clipboard."""
    ctx = ExecutionContext()
    delegate = HeadlessUIDelegate()

    # Step 1: Compute formatted line
    c_act = ComputeAction({
        "target_var": "tsv_content",
        "expression": r'strcat("Header1", "\t", "Header2", "\n", "Data1", "\t", "Data2")'
    })
    c_act.execute(ctx, delegate)
    assert ctx.get_var("tsv_content") == "Header1\tHeader2\nData1\tData2"

    # Step 2: Write to clipboard in table mode
    w_act = WriteClipboardAction({
        "type": "table",
        "data": "{{tsv_content}}"
    })
    w_act.execute(ctx, delegate)

    clip = delegate.get_clipboard()
    assert clip == "Header1\tHeader2\r\nData1\tData2"


def test_decode_escape_sequences_edge_cases():
    """Verify decode_escape_sequences edge cases."""
    # Preserves non-escapes
    assert decode_escape_sequences("plain text") == "plain text"

    # Preserves already real tabs and newlines
    assert decode_escape_sequences("real\ttab\nand\r\nnewline") == "real\ttab\nand\r\nnewline"

    # Escaped backslash followed by t is literal \t, not tab
    assert decode_escape_sequences(r"\\t is not tab") == r"\t is not tab"

    # Windows path with backslash
    assert decode_escape_sequences(r"C:\\Windows\\System32") == r"C:\Windows\System32"
