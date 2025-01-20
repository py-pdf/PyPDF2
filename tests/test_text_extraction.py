"""
Testing the text-extraction submodule and ensuring the quality of text extraction.

The tested code might be in _page.py.
"""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from pypdf import PdfReader, mult
from pypdf._text_extraction import set_custom_rtl
from pypdf.errors import ParseError, PdfReadError

from . import get_data_from_url

TESTS_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
RESOURCE_ROOT = PROJECT_ROOT / "resources"
SAMPLE_ROOT = PROJECT_ROOT / "sample-files"


@pytest.mark.samples
@pytest.mark.parametrize(("visitor_text"), [None, lambda a, b, c, d, e: None])
def test_multi_language(visitor_text):
    reader = PdfReader(RESOURCE_ROOT / "multilang.pdf")
    txt = reader.pages[0].extract_text(visitor_text=visitor_text)
    assert "Hello World" in txt, "English not correctly extracted"
    # iss #1296
    assert "مرحبا بالعالم" in txt, "Arabic not correctly extracted"
    assert "Привет, мир" in txt, "Russian not correctly extracted"
    assert "你好世界" in txt, "Chinese not correctly extracted"
    assert "สวัสดีชาวโลก" in txt, "Thai not correctly extracted"
    assert "こんにちは世界" in txt, "Japanese not correctly extracted"
    # check customizations
    set_custom_rtl(None, None, "Russian:")
    assert ":naissuR" in reader.pages[0].extract_text(
        visitor_text=visitor_text
    ), "(1) CUSTOM_RTL_SPECIAL_CHARS failed"
    set_custom_rtl(None, None, [ord(x) for x in "Russian:"])
    assert ":naissuR" in reader.pages[0].extract_text(
        visitor_text=visitor_text
    ), "(2) CUSTOM_RTL_SPECIAL_CHARS failed"
    set_custom_rtl(0, 255, None)
    assert ":hsilgnE" in reader.pages[0].extract_text(
        visitor_text=visitor_text
    ), "CUSTOM_RTL_MIN/MAX failed"
    set_custom_rtl("A", "z", [])
    assert ":hsilgnE" in reader.pages[0].extract_text(
        visitor_text=visitor_text
    ), "CUSTOM_RTL_MIN/MAX failed"
    set_custom_rtl(-1, -1, [])  # to prevent further errors

    reader = PdfReader(SAMPLE_ROOT / "015-arabic/habibi-rotated.pdf")
    assert "habibi" in reader.pages[0].extract_text(visitor_text=visitor_text)
    assert "حَبيبي" in reader.pages[0].extract_text(visitor_text=visitor_text)
    assert "habibi" in reader.pages[1].extract_text(visitor_text=visitor_text)
    assert "حَبيبي" in reader.pages[1].extract_text(visitor_text=visitor_text)
    assert "habibi" in reader.pages[2].extract_text(visitor_text=visitor_text)
    assert "حَبيبي" in reader.pages[2].extract_text(visitor_text=visitor_text)
    assert "habibi" in reader.pages[3].extract_text(visitor_text=visitor_text)
    assert "حَبيبي" in reader.pages[3].extract_text(visitor_text=visitor_text)


@pytest.mark.parametrize(
    ("file_name", "constraints"),
    [
        (
            "inkscape-abc.pdf",
            {
                "A": lambda x, y: 0 < x < 94 and 189 < y < 283,  # In upper left
                "B": lambda x, y: 94 < x < 189 and 94 < y < 189,  # In the center
                "C": lambda x, y: 189 < x < 283 and 0 < y < 94,
            },  # In lower right
        )
    ],
)
def test_visitor_text_matrices(file_name, constraints):
    """
    Checks if the matrices given to the visitor_text function when calling
    `extract_text` on the first page of `file_name` match some given constraints.
    `constraints` is a dictionary mapping a line of text to a constraint that should
    evaluate to `True` on its expected x,y-coordinates.
    """
    reader = PdfReader(RESOURCE_ROOT / file_name)

    lines = []

    def visitor_text(text, cm, tm, font_dict, font_size) -> None:
        ctm = mult(tm, cm)
        x = ctm[4]  # used to tm[4] * cm[0] + tm[5] * cm[2] + cm[4]  # mult(tm, cm)[4]
        y = ctm[
            5
        ]  # used to be tm[4] * cm[1] + tm[5] * cm[3] + cm[5]  # mult(tm, cm)[5]
        lines.append({"text": text, "x": x, "y": y})

    reader.pages[0].extract_text(visitor_text=visitor_text)

    for text, constraint in constraints.items():
        matches = [li for li in lines if li["text"].strip() == text]
        assert len(matches) <= 1, f"Multiple lines match {text}"
        assert len(matches) >= 1, f"No lines match {text}"

        x = matches[0]["x"]
        y = matches[0]["y"]
        assert constraint(x, y), f'Line "{text}" is wrong at x:{x}, y:{y}'


@pytest.mark.xfail(reason="known whitespace issue #2336")
@pytest.mark.enable_socket
def test_issue_2336():
    name = "Pesquisa-de-Precos-Combustiveis-novembro-2023.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(name=name)))
    page = reader.pages[0]
    actual_text = page.extract_text()
    assert "Beira Rio" in actual_text


def test_layout_mode_font_class_to_dict():
    from pypdf._text_extraction._layout_mode._font import Font

    font = Font("foo", space_width=8, encoding="utf-8", char_map={}, font_dictionary={})
    assert Font.to_dict(font) == {
        "char_map": {},
        "encoding": "utf-8",
        "font_dictionary": {},
        "space_width": 8,
        "subtype": "foo",
        "width_map": {},
    }


@pytest.mark.enable_socket
def test_layout_mode_epic_page_fonts():
    url = "https://github.com/py-pdf/pypdf/files/13836944/Epic.Page.PDF"
    name = "Epic Page.PDF"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    expected = (RESOURCE_ROOT / "Epic.Page.layout.txt").read_text(encoding="utf-8")
    assert expected == reader.pages[0].extract_text(extraction_mode="layout")


def test_layout_mode_uncommon_operators():
    # coverage for layout mode Tc, Tz, Ts, ', ", TD, TL, and Tw
    reader = PdfReader(RESOURCE_ROOT / "toy.pdf")
    expected = (RESOURCE_ROOT / "toy.layout.txt").read_text(encoding="utf-8")
    assert expected == reader.pages[0].extract_text(extraction_mode="layout")


@pytest.mark.enable_socket
def test_layout_mode_type0_font_widths():
    # Cover both the 'int int int' and 'int [int int ...]' formats for Type0
    # /DescendantFonts /W array entries.
    url = "https://github.com/py-pdf/pypdf/files/13533204/Claim.Maker.Alerts.Guide_pg2.PDF"
    name = "Claim Maker Alerts Guide_pg2.PDF"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    expected = (RESOURCE_ROOT / "Claim Maker Alerts Guide_pg2.layout.txt").read_text(
        encoding="utf-8"
    )
    assert expected == reader.pages[0].extract_text(extraction_mode="layout")


@pytest.mark.enable_socket
def test_layout_mode_indirect_sequence_font_widths():
    # Cover the situation where the sequence for font widths is an IndirectObject
    # ref https://github.com/py-pdf/pypdf/pull/2788
    url = "https://github.com/user-attachments/files/16491621/2788_example.pdf"
    name = "2788_example.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert reader.pages[0].extract_text(extraction_mode="layout") == ""
    url = "https://github.com/user-attachments/files/16491619/2788_example_malformed.pdf"
    name = "2788_example_malformed.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    with pytest.raises(ParseError) as exc:
        reader.pages[0].extract_text(extraction_mode="layout")
        assert str(exc.value).startswith("Invalid font width definition")


def dummy_visitor_text(text, ctm, tm, fd, fs):
    pass


@patch("pypdf._page.logger_warning")
def test_layout_mode_warnings(mock_logger_warning):
    # Check that a warning is issued when an argument is ignored
    reader = PdfReader(RESOURCE_ROOT / "hello-world.pdf")
    page = reader.pages[0]
    page.extract_text(extraction_mode="plain", visitor_text=dummy_visitor_text)
    mock_logger_warning.assert_not_called()
    page.extract_text(extraction_mode="layout", visitor_text=dummy_visitor_text)
    mock_logger_warning.assert_called_with(
        "Argument visitor_text is ignored in layout mode", "pypdf._page"
    )


@pytest.mark.enable_socket
def test_space_with_one_unit_smaller_than_font_width():
    """Tests for #1328"""
    url = "https://github.com/py-pdf/pypdf/files/9498481/0004.pdf"
    name = "iss1328.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    page = reader.pages[0]
    extracted = page.extract_text()
    assert "Reporting crude oil leak.\n" in extracted


@pytest.mark.enable_socket
def test_space_position_calculation():
    """Tests for #1153"""
    url = "https://github.com/py-pdf/pypdf/files/9164743/file-0.pdf"
    name = "iss1153.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    page = reader.pages[3]
    extracted = page.extract_text()
    assert "Shortly after the Geneva BOF session, the" in extracted


def test_text_leading_height_unit():
    """Tests for #2262"""
    reader = PdfReader(RESOURCE_ROOT / "toy.pdf")
    page = reader.pages[0]
    extracted = page.extract_text()
    assert "Something[cited]\n" in extracted


def test_layout_mode_space_vertically_font_height_weight():
    """Tests layout mode with vertical space and font height weight (issue #2915)"""
    with open(RESOURCE_ROOT / "crazyones.pdf", "rb") as inputfile:
        # Load PDF file from file
        reader = PdfReader(inputfile)
        page = reader.pages[0]

        # Normal behaviour
        with open(RESOURCE_ROOT / "crazyones_layout_vertical_space.txt", "rb") as pdftext_file:
            pdftext = pdftext_file.read()

        text = page.extract_text(extraction_mode="layout", layout_mode_space_vertically=True).encode("utf-8")

        # Compare the text of the PDF to a known source
        for expected_line, actual_line in zip(text.splitlines(), pdftext.splitlines()):
            assert expected_line == actual_line

        pdftext = pdftext.replace(b"\r\n", b"\n")  # fix for windows
        assert text == pdftext, (
            "PDF extracted text differs from expected value.\n\n"
            "Expected:\n\n%r\n\nExtracted:\n\n%r\n\n" % (pdftext, text)
        )

        # Blank lines are added to truly separate paragraphs
        with open(RESOURCE_ROOT / "crazyones_layout_vertical_space_font_height_weight.txt", "rb") as pdftext_file:
            pdftext = pdftext_file.read()

        text = page.extract_text(extraction_mode="layout", layout_mode_space_vertically=True,
                                 layout_mode_font_height_weight=0.85).encode("utf-8")

        # Compare the text of the PDF to a known source
        for expected_line, actual_line in zip(text.splitlines(), pdftext.splitlines()):
            assert expected_line == actual_line

        pdftext = pdftext.replace(b"\r\n", b"\n")  # fix for windows
        assert text == pdftext, (
                "PDF extracted text differs from expected value.\n\n"
                "Expected:\n\n%r\n\nExtracted:\n\n%r\n\n" % (pdftext, text)
        )


@pytest.mark.enable_socket
def test_infinite_loop_arrays():
    """Tests for #2928"""
    url = "https://github.com/user-attachments/files/17576546/arrayabruptending.pdf"
    name = "arrayabruptending.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))

    page = reader.pages[0]
    extracted = page.extract_text()
    assert "RNA structure comparison" in extracted


@pytest.mark.enable_socket
def test_content_stream_is_dictionary_object(caplog):
    """Tests for #2995."""
    url = "https://github.com/user-attachments/files/18049322/6fa5fd46-5f98-4a67-800d-5e2362b0164f.pdf"
    name = "iss2995.pdf"
    data = get_data_from_url(url, name=name)

    reader = PdfReader(BytesIO(data))
    page = reader.pages[0]
    assert "\nYours faithfully   \n" in page.extract_text()
    assert "Expected StreamObject, got DictionaryObject instead. Data might be wrong." in caplog.text
    caplog.clear()

    reader = PdfReader(BytesIO(data), strict=True)
    page = reader.pages[0]
    with pytest.raises(PdfReadError) as exception:
        page.extract_text()
    assert (
        "Invalid Elementary Object starting with b\\'\\\\x18\\' @3557: b\\'ateDecode/Length 629\\\\x18ck["
        in exception.value.args[0]
    )


@pytest.mark.enable_socket
def test_tz_with_no_operands():
    """Tests for #2975"""
    url = "https://github.com/user-attachments/files/17974120/9E5E080E-C8DB-4A6B-822B-9A67DC04E526-120438.pdf"
    name = "iss2975.pdf"
    data = get_data_from_url(url, name=name)

    reader = PdfReader(BytesIO(data))
    page = reader.pages[1]
    assert "\nThankyouforyourattentiontothismatter.\n" in page.extract_text()
