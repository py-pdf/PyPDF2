"""Test the pypdf._writer module."""
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from pypdf import (
    ImageType,
    ObjectDeletionFlag,
    PageObject,
    PdfMerger,
    PdfReader,
    PdfWriter,
    Transformation,
)
from pypdf.errors import DeprecationError, PageSizeNotDefinedError, PyPdfError
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    Fit,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    RectangleObject,
    StreamObject,
    TextStringObject,
)

from . import get_data_from_url, is_sublist
from .test_images import image_similarity

TESTS_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
RESOURCE_ROOT = PROJECT_ROOT / "resources"
SAMPLE_ROOT = Path(PROJECT_ROOT) / "sample-files"
GHOSTSCRIPT_BINARY = shutil.which("gs")


def test_writer_exception_non_binary(tmp_path, caplog):
    src = RESOURCE_ROOT / "pdflatex-outline.pdf"

    reader = PdfReader(src)
    writer = PdfWriter()
    writer.add_page(reader.pages[0])

    with open(tmp_path / "out.txt", "w") as fp, pytest.raises(TypeError):
        writer.write_stream(fp)
    ending = "to write to is not in binary mode. It may not be written to correctly.\n"
    assert caplog.text.endswith(ending)


def test_writer_clone():
    src = RESOURCE_ROOT / "pdflatex-outline.pdf"

    reader = PdfReader(src)
    writer = PdfWriter(clone_from=reader)
    assert len(writer.pages) == 4
    assert "PageObject" in str(type(writer.pages[0]))

    writer = PdfWriter(clone_from=src)
    assert len(writer.pages) == 4
    assert "PageObject" in str(type(writer.pages[0]))


def test_writer_clone_bookmarks():
    # Arrange
    src = RESOURCE_ROOT / "Seige_of_Vicksburg_Sample_OCR-crazyones-merged.pdf"
    reader = PdfReader(src)
    writer = PdfWriter()

    # Act + test cat
    cat = ""

    def cat1(p) -> None:
        nonlocal cat
        cat += p.__repr__()

    writer.clone_document_from_reader(reader, cat1)
    assert "/Page" in cat
    assert writer.pages[0].raw_get("/Parent") == writer._pages
    writer.add_outline_item("Page 1", 0)
    writer.add_outline_item("Page 2", 1)

    # Assert
    bytes_stream = BytesIO()
    writer.write(bytes_stream)
    bytes_stream.seek(0)
    reader2 = PdfReader(bytes_stream)
    assert len(reader2.pages) == len(reader.pages)
    assert len(reader2.outline) == 2

    # test with append
    writer = PdfWriter()
    writer.append(reader)
    writer.add_outline_item("Page 1", 0)
    writer.add_outline_item("Page 2", 1)

    # Assert
    bytes_stream = BytesIO()
    writer.write(bytes_stream)
    bytes_stream.seek(0)
    reader2 = PdfReader(bytes_stream)
    assert len(reader2.pages) == len(reader.pages)
    assert len(reader2.outline) == 2


def writer_operate(writer: PdfWriter) -> None:
    """
    To test the writer that initialized by each of the four usages.

    Args:
        writer: A PdfWriter object
    """
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    pdf_outline_path = RESOURCE_ROOT / "pdflatex-outline.pdf"

    reader = PdfReader(pdf_path)
    reader_outline = PdfReader(pdf_outline_path)

    page = reader.pages[0]
    with pytest.raises(PageSizeNotDefinedError) as exc:
        writer.add_blank_page()
    assert exc.value.args == ()
    writer.insert_page(page, 1)
    writer.insert_page(reader_outline.pages[0], 0)
    writer.add_outline_item_destination(page)
    writer.remove_links()
    writer.add_outline_item_destination(page)
    oi = writer.add_outline_item(
        "An outline item", 0, None, (255, 0, 15), True, True, Fit.fit_box_vertically(10)
    )
    writer.add_outline_item(
        "The XYZ fit", 0, oi, (255, 0, 15), True, True, Fit.xyz(left=10, top=20, zoom=3)
    )
    writer.add_outline_item(
        "The XYZ fit no args", 0, oi, (255, 0, 15), True, True, Fit.xyz()
    )
    writer.add_outline_item(
        "The FitH fit", 0, oi, (255, 0, 15), True, True, Fit.fit_horizontally(top=10)
    )
    writer.add_outline_item(
        "The FitV fit", 0, oi, (255, 0, 15), True, True, Fit.fit_vertically(left=10)
    )
    writer.add_outline_item(
        "The FitR fit",
        0,
        oi,
        (255, 0, 15),
        True,
        True,
        Fit.fit_rectangle(left=10, bottom=20, right=30, top=40),
    )
    writer.add_outline_item(
        "The FitB fit", 0, oi, (255, 0, 15), True, True, Fit.fit_box()
    )
    writer.add_outline_item(
        "The FitBH fit",
        0,
        oi,
        (255, 0, 15),
        True,
        True,
        Fit.fit_box_horizontally(top=10),
    )
    writer.add_outline_item(
        "The FitBV fit",
        0,
        oi,
        (255, 0, 15),
        True,
        True,
        Fit.fit_box_vertically(left=10),
    )
    writer.add_blank_page()
    writer.add_uri(2, "https://example.com", RectangleObject([0, 0, 100, 100]))
    with pytest.warns(
        DeprecationWarning, match="'pagenum' argument of add_uri is deprecated"
    ):
        writer.add_uri(
            2, "https://example.com", RectangleObject([0, 0, 100, 100]), pagenum=2
        )
    with pytest.raises(DeprecationError):
        writer.add_link(2, 1, RectangleObject([0, 0, 100, 100]))
    assert writer._get_page_layout() is None
    writer.page_layout = "broken"
    assert writer.page_layout == "broken"
    writer.page_layout = NameObject("/SinglePage")
    assert writer._get_page_layout() == "/SinglePage"
    assert writer._get_page_mode() is None
    writer.set_page_mode("/UseNone")
    assert writer._get_page_mode() == "/UseNone"
    writer.set_page_mode(NameObject("/UseOC"))
    assert writer._get_page_mode() == "/UseOC"
    writer.insert_blank_page(width=100, height=100)
    writer.insert_blank_page()  # without parameters

    writer.remove_images()

    writer.add_metadata(reader.metadata)
    writer.add_metadata({"/Author": "Martin Thoma"})
    writer.add_metadata({"/MyCustom": 1234})

    writer.add_attachment("foobar.gif", b"foobarcontent")

    # Check that every key in _idnum_hash is correct
    objects_hash = [o.hash_value() for o in writer._objects]
    for k, v in writer._idnum_hash.items():
        assert v.pdf == writer
        assert k in objects_hash, f"Missing {v}"


tmp_path = "dont_commit_writer.pdf"


@pytest.mark.parametrize(
    ("write_data_here", "needs_cleanup"),
    [
        ("dont_commit_writer.pdf", True),
        (Path("dont_commit_writer.pdf"), True),
        (BytesIO(), False),
    ],
)
def test_writer_operations_by_traditional_usage(write_data_here, needs_cleanup):
    writer = PdfWriter()

    writer_operate(writer)

    # finally, write "output" to pypdf-output.pdf
    if needs_cleanup:
        with open(write_data_here, "wb") as output_stream:
            writer.write(output_stream)
    else:
        output_stream = write_data_here
        writer.write(output_stream)

    if needs_cleanup:
        Path(write_data_here).unlink()


@pytest.mark.parametrize(
    ("write_data_here", "needs_cleanup"),
    [
        ("dont_commit_writer.pdf", True),
        (Path("dont_commit_writer.pdf"), True),
        (BytesIO(), False),
    ],
)
def test_writer_operations_by_semi_traditional_usage(write_data_here, needs_cleanup):
    with PdfWriter() as writer:
        writer_operate(writer)

        # finally, write "output" to pypdf-output.pdf
        if needs_cleanup:
            with open(write_data_here, "wb") as output_stream:
                writer.write(output_stream)
        else:
            output_stream = write_data_here
            writer.write(output_stream)

    if needs_cleanup:
        Path(write_data_here).unlink()


@pytest.mark.parametrize(
    ("write_data_here", "needs_cleanup"),
    [
        ("dont_commit_writer.pdf", True),
        (Path("dont_commit_writer.pdf"), True),
        (BytesIO(), False),
    ],
)
def test_writer_operations_by_semi_new_traditional_usage(
    write_data_here, needs_cleanup
):
    with PdfWriter() as writer:
        writer_operate(writer)

        # finally, write "output" to pypdf-output.pdf
        writer.write(write_data_here)

    if needs_cleanup:
        Path(write_data_here).unlink()


@pytest.mark.parametrize(
    ("write_data_here", "needs_cleanup"),
    [
        ("dont_commit_writer.pdf", True),
        (Path("dont_commit_writer.pdf"), True),
        (BytesIO(), False),
    ],
)
def test_writer_operation_by_new_usage(write_data_here, needs_cleanup):
    # This includes write "output" to pypdf-output.pdf
    with PdfWriter(write_data_here) as writer:
        writer_operate(writer)

    if needs_cleanup:
        Path(write_data_here).unlink()


@pytest.mark.parametrize(
    "input_path",
    [
        "side-by-side-subfig.pdf",
        "reportlab-inline-image.pdf",
    ],
)
def test_remove_images(pdf_file_path, input_path):
    pdf_path = RESOURCE_ROOT / input_path

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    page = reader.pages[0]
    writer.insert_page(page, 0)
    writer.remove_images()
    page_contents_stream = writer.pages[0]["/Contents"]._data
    assert len(page_contents_stream.strip())

    # finally, write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)

    with open(pdf_file_path, "rb") as input_stream:
        reader = PdfReader(input_stream)
        if input_path == "side-by-side-subfig.pdf":
            extracted_text = reader.pages[0].extract_text()
            assert extracted_text
            assert "Lorem ipsum dolor sit amet" in extracted_text


@pytest.mark.enable_socket()
def test_remove_images_sub_level():
    """Cf #2035"""
    url = "https://github.com/py-pdf/pypdf/files/12394781/2210.03142-1.pdf"
    name = "iss2103.pdf"
    writer = PdfWriter(clone_from=BytesIO(get_data_from_url(url, name=name)))
    writer.remove_images()
    assert (
        len(
            [
                o.get_object()
                for o in writer.pages[0]["/Resources"]["/XObject"]["/Fm1"][
                    "/Resources"
                ]["/XObject"]["/Im1"]["/Resources"]["/XObject"].values()
                if not isinstance(o.get_object(), NullObject)
            ]
        )
        == 0
    )


@pytest.mark.parametrize(
    "input_path",
    [
        "side-by-side-subfig.pdf",
        "reportlab-inline-image.pdf",
    ],
)
def test_remove_text(input_path, pdf_file_path):
    pdf_path = RESOURCE_ROOT / input_path

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    page = reader.pages[0]
    writer.insert_page(page, 0)
    writer.remove_text()

    # finally, write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_remove_text_all_operators(pdf_file_path):
    stream = (
        b"BT "
        b"/F0 36 Tf "
        b"50 706 Td "
        b"36 TL "
        b"(The Tj operator) Tj "
        b'1 2 (The double quote operator) " '
        b"(The single quote operator) ' "
        b"ET"
    )
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [5 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Length %d >>\n"
        b"stream\n" + (b"%s\n" % stream) + b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Contents 4 0 R /CropBox [0.0 0.0 2550.0 3508.0]\n"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"6 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 6\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << /Root 6 0 R /Size 6 >>\n"
        b"startxref\n%d\n"
        b"%%%%EOF"
    )
    startx_correction = -1
    pdf_data = pdf_data % (
        len(stream),
        pdf_data.find(b"1 0 obj") + startx_correction,
        pdf_data.find(b"2 0 obj") + startx_correction,
        pdf_data.find(b"3 0 obj") + startx_correction,
        pdf_data.find(b"4 0 obj") + startx_correction,
        pdf_data.find(b"5 0 obj") + startx_correction,
        pdf_data.find(b"6 0 obj") + startx_correction,
        # startx_correction should be -1 due to double % at the beginning
        # inducing an error on startxref computation
        pdf_data.find(b"xref"),
    )
    pdf_stream = BytesIO(pdf_data)

    reader = PdfReader(pdf_stream, strict=False)
    writer = PdfWriter()

    page = reader.pages[0]
    writer.insert_page(page, 0)
    writer.remove_text()

    # finally, write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_write_metadata(pdf_file_path):
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    writer.add_page(reader.pages[0])
    for page in reader.pages:
        writer.add_page(page)

    metadata = reader.metadata
    writer.add_metadata(metadata)

    writer.add_metadata({"/Title": "The Crazy Ones"})

    # finally, write data to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)

    # Check if the title was set
    reader = PdfReader(pdf_file_path)
    metadata = reader.metadata
    assert metadata.get("/Title") == "The Crazy Ones"


def test_fill_form(pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "form.pdf")
    writer = PdfWriter()

    writer.append(reader, [0])
    writer.append(RESOURCE_ROOT / "crazyones.pdf", [0])

    writer.update_page_form_field_values(
        writer.pages[0], {"foo": "some filled in text"}, flags=1
    )

    # check if no fields to fill in the page
    writer.update_page_form_field_values(
        writer.pages[1], {"foo": "some filled in text"}, flags=1
    )

    writer.update_page_form_field_values(
        writer.pages[0], {"foo": "some filled in text"}
    )

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_fill_form_with_qualified():
    reader = PdfReader(RESOURCE_ROOT / "form.pdf")
    reader.add_form_topname("top")

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_page(reader.pages[0])
    writer.update_page_form_field_values(
        writer.pages[0], {"top.foo": "filling"}, flags=1
    )
    b = BytesIO()
    writer.write(b)

    reader2 = PdfReader(b)
    fields = reader2.get_fields()
    assert fields["top.foo"]["/V"] == "filling"


@pytest.mark.parametrize(
    ("use_128bit", "user_password", "owner_password"),
    [(True, "userpwd", "ownerpwd"), (False, "userpwd", "ownerpwd")],
)
def test_encrypt(use_128bit, user_password, owner_password, pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "form.pdf")
    writer = PdfWriter()

    page = reader.pages[0]
    orig_text = page.extract_text()

    writer.add_page(page)

    with pytest.raises(ValueError, match="owner_pwd of encrypt is deprecated."):
        writer.encrypt(
            owner_pwd=user_password,
            owner_password=owner_password,
            user_password=user_password,
            use_128bit=use_128bit,
        )
    with pytest.raises(ValueError, match="'user_pwd' argument is deprecated"):
        writer.encrypt(
            owner_password=owner_password,
            user_password=user_password,
            user_pwd=user_password,
            use_128bit=use_128bit,
        )
    writer.encrypt(
        user_password=user_password,
        owner_password=owner_password,
        use_128bit=use_128bit,
    )

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)

    # Test that the data is not there in clear text
    with open(pdf_file_path, "rb") as input_stream:
        data = input_stream.read()
    assert b"foo" not in data

    # Test the user password (str):
    reader = PdfReader(pdf_file_path, password="userpwd")
    new_text = reader.pages[0].extract_text()
    assert reader.metadata.get("/Producer") == "pypdf"
    assert new_text == orig_text

    # Test the owner password (str):
    reader = PdfReader(pdf_file_path, password="ownerpwd")
    new_text = reader.pages[0].extract_text()
    assert reader.metadata.get("/Producer") == "pypdf"
    assert new_text == orig_text

    # Test the user password (bytes):
    reader = PdfReader(pdf_file_path, password=b"userpwd")
    new_text = reader.pages[0].extract_text()
    assert reader.metadata.get("/Producer") == "pypdf"
    assert new_text == orig_text

    # Test the owner password (stbytesr):
    reader = PdfReader(pdf_file_path, password=b"ownerpwd")
    new_text = reader.pages[0].extract_text()
    assert reader.metadata.get("/Producer") == "pypdf"
    assert new_text == orig_text


def test_add_outline_item(pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "pdflatex-outline.pdf")
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    outline_item = writer.add_outline_item(
        "An outline item",
        1,
        None,
        (255, 0, 15),
        True,
        True,
        Fit.fit(),
        is_open=False,
    )
    _o2a = writer.add_outline_item(
        "Another", 2, outline_item, None, False, False, Fit.fit()
    )
    _o2b = writer.add_outline_item(
        "Another bis", 2, outline_item, None, False, False, Fit.fit()
    )
    outline_item2 = writer.add_outline_item(
        "An outline item 2",
        1,
        None,
        (255, 0, 15),
        True,
        True,
        Fit.fit(),
        is_open=True,
    )
    _o3a = writer.add_outline_item(
        "Another 2", 2, outline_item2, None, False, False, Fit.fit()
    )
    _o3b = writer.add_outline_item(
        "Another 2bis", 2, outline_item2, None, False, False, Fit.fit()
    )

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "w+b") as output_stream:
        writer.write(output_stream)
        output_stream.seek(0)
        reader = PdfReader(output_stream)
        assert reader.trailer["/Root"]["/Outlines"]["/Count"] == 3
        assert reader.outline[0]["/Count"] == -2
        assert reader.outline[0]["/%is_open%"] == False  # noqa
        assert reader.outline[2]["/Count"] == 2
        assert reader.outline[2]["/%is_open%"] == True  # noqa
        assert reader.outline[1][0]["/Count"] == 0


def test_add_named_destination(pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "pdflatex-outline.pdf")
    writer = PdfWriter()
    assert writer.get_named_dest_root() == []

    for page in reader.pages:
        writer.add_page(page)

    assert writer.get_named_dest_root() == []

    writer.add_named_destination(TextStringObject("A named dest"), 2)
    writer.add_named_destination(TextStringObject("A named dest2"), 2)

    with pytest.warns(DeprecationWarning, match="pagenum is deprecated as an argument"):
        writer.add_named_destination(TextStringObject("A named dest3"), pagenum=2)

    with pytest.raises(ValueError):
        writer.add_named_destination(
            TextStringObject("A named dest3"), pagenum=2, page_number=2
        )

    root = writer.get_named_dest_root()
    assert root[0] == "A named dest"
    assert root[1].pdf == writer
    assert root[1].get_object()["/S"] == NameObject("/GoTo")
    assert root[1].get_object()["/D"][0] == writer.pages[2].indirect_reference
    assert root[2] == "A named dest2"
    assert root[3].pdf == writer
    assert root[3].get_object()["/S"] == NameObject("/GoTo")
    assert root[3].get_object()["/D"][0] == writer.pages[2].indirect_reference
    assert root[4] == "A named dest3"

    # test get_object

    assert writer.get_object(root[1].idnum) == writer.get_object(root[1])
    with pytest.raises(ValueError) as exc:
        writer.get_object(reader.pages[0].indirect_reference)
    assert exc.value.args[0] == "pdf must be self"

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_add_named_destination_sort_order(pdf_file_path):
    """
    Issue #1927 does not appear.

    add_named_destination() maintains the named destination list sort order
    """
    writer = PdfWriter()

    assert writer.get_named_dest_root() == []

    writer.add_blank_page(200, 200)
    writer.add_named_destination("b", 0)
    # "a" should be moved before "b" on insert
    writer.add_named_destination("a", 0)

    root = writer.get_named_dest_root()

    assert len(root) == 4
    assert (
        root[0] == "a"
    ), '"a" was not inserted before "b" in the named destination root'
    assert root[2] == "b"

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_add_uri(pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "pdflatex-outline.pdf")
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    writer.add_uri(
        1,
        "http://www.example.com",
        RectangleObject([0, 0, 100, 100]),
        border=[1, 2, 3, [4]],
    )
    writer.add_uri(
        2,
        "https://pypdf.readthedocs.io/en/latest/",
        RectangleObject([20, 30, 50, 80]),
        border=[1, 2, 3],
    )
    writer.add_uri(
        3,
        "https://pypdf.readthedocs.io/en/latest/user/adding-pdf-annotations.html",
        "[ 200 300 250 350 ]",
        border=[0, 0, 0],
    )
    writer.add_uri(
        3,
        "https://pypdf.readthedocs.io/en/latest/user/adding-pdf-annotations.html",
        [100, 200, 150, 250],
        border=[0, 0, 0],
    )

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_add_link(pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "pdflatex-outline.pdf")
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    with pytest.raises(
        DeprecationError,
        match=(
            re.escape(
                "add_link is deprecated and was removed in pypdf 3.0.0. "
                "Use add_annotation(pypdf.annotations.Link(...)) instead."
            )
        ),
    ):
        writer.add_link(
            1,
            2,
            RectangleObject([0, 0, 100, 100]),
            border=[1, 2, 3, [4]],
            fit="/Fit",
        )
        writer.add_link(
            2, 3, RectangleObject([20, 30, 50, 80]), [1, 2, 3], "/FitH", None
        )
        writer.add_link(
            3,
            0,
            "[ 200 300 250 350 ]",
            [0, 0, 0],
            "/XYZ",
            0,
            0,
            2,
        )
        writer.add_link(
            3,
            0,
            [100, 200, 150, 250],
            border=[0, 0, 0],
        )

    # write "output" to pypdf-output.pdf
    with open(pdf_file_path, "wb") as output_stream:
        writer.write(output_stream)


def test_io_streams():
    """This is the example from the docs ("Streaming data")."""
    filepath = RESOURCE_ROOT / "pdflatex-outline.pdf"
    with open(filepath, "rb") as fh:
        bytes_stream = BytesIO(fh.read())

    # Read from bytes stream
    reader = PdfReader(bytes_stream)
    assert len(reader.pages) == 4

    # Write to bytes stream
    writer = PdfWriter()
    with BytesIO() as output_stream:
        writer.write(output_stream)


def test_regression_issue670(pdf_file_path):
    filepath = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(filepath, strict=False)
    for _ in range(2):
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        with open(pdf_file_path, "wb") as f_pdf:
            writer.write(f_pdf)


def test_issue301():
    """Test with invalid stream length object."""
    with open(RESOURCE_ROOT / "issue-301.pdf", "rb") as f:
        reader = PdfReader(f)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        b = BytesIO()
        writer.write(b)


def test_append_pages_from_reader_append():
    """Use append_pages_from_reader with a callable."""
    with open(RESOURCE_ROOT / "issue-301.pdf", "rb") as f:
        reader = PdfReader(f)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader, callable)
        b = BytesIO()
        writer.write(b)


@pytest.mark.enable_socket()
@pytest.mark.slow()
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_sweep_indirect_references_nullobject_exception(pdf_file_path):
    # TODO: Check this more closely... this looks weird
    url = "https://corpora.tika.apache.org/base/docs/govdocs1/924/924666.pdf"
    name = "tika-924666.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    merger = PdfMerger()
    merger.append(reader)
    merger.write(pdf_file_path)


@pytest.mark.enable_socket()
@pytest.mark.slow()
@pytest.mark.parametrize(
    ("url", "name"),
    [
        (
            "https://corpora.tika.apache.org/base/docs/govdocs1/924/924666.pdf",
            "test_sweep_indirect_references_nullobject_exception.pdf",
        ),
        (
            "https://corpora.tika.apache.org/base/docs/govdocs1/922/922840.pdf",
            "test_write_outline_item_on_page_fitv.pdf",
        ),
        ("https://github.com/py-pdf/pypdf/files/10715624/test.pdf", "iss1627.pdf"),
    ],
)
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_some_appends(pdf_file_path, url, name):
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    # PdfMerger
    merger = PdfMerger()
    merger.append(reader)
    merger.write(pdf_file_path)
    # PdfWriter
    merger = PdfWriter()
    merger.append(reader)
    merger.write(pdf_file_path)


def test_pdf_header():
    writer = PdfWriter()
    assert writer.pdf_header == b"%PDF-1.3"

    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    writer.add_page(reader.pages[0])
    assert writer.pdf_header == b"%PDF-1.5"

    writer.pdf_header = b"%PDF-1.6"
    assert writer.pdf_header == b"%PDF-1.6"


def test_write_dict_stream_object(pdf_file_path):
    stream = (
        b"BT "
        b"/F0 36 Tf "
        b"50 706 Td "
        b"36 TL "
        b"(The Tj operator) Tj "
        b'1 2 (The double quote operator) " '
        b"(The single quote operator) ' "
        b"ET"
    )

    stream_object = StreamObject()
    stream_object[NameObject("/Type")] = NameObject("/Text")
    stream_object._data = stream

    writer = PdfWriter()

    page_object = PageObject.create_blank_page(writer, 1000, 1000)
    # Construct dictionary object (PageObject) with stream object
    # Writer will replace this stream object with indirect object
    page_object[NameObject("/Test")] = stream_object

    page_object = writer.add_page(page_object)
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)

    for k, v in page_object.items():
        if k == "/Test":
            assert str(v) != str(stream_object)
            assert isinstance(v, IndirectObject)
            assert str(v.get_object()) == str(stream_object)
            break
    else:
        pytest.fail("/Test not found")

    # Check that every key in _idnum_hash is correct
    objects_hash = [o.hash_value() for o in writer._objects]
    for k, v in writer._idnum_hash.items():
        assert v.pdf == writer
        assert k in objects_hash, "Missing %s" % v


def test_add_single_annotation(pdf_file_path):
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    annot_dict = {
        "/Type": "/Annot",
        "/Subtype": "/Text",
        "/Rect": [270.75, 596.25, 294.75, 620.25],
        "/Contents": "Note in second paragraph",
        "/C": [1, 1, 0],
        "/M": "D:20220406191858+02'00",
        "/Popup": {
            "/Type": "/Annot",
            "/Subtype": "/Popup",
            "/Rect": [294.75, 446.25, 494.75, 596.25],
            "/M": "D:20220406191847+02'00",
        },
        "/T": "moose",
    }
    writer.add_annotation(0, annot_dict)

    # Inspect manually by adding 'assert False' and viewing the PDF
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_deprecation_bookmark_decorator():
    reader = PdfReader(RESOURCE_ROOT / "outlines-with-invalid-destinations.pdf")
    page = reader.pages[0]
    outline_item = reader.outline[0]
    writer = PdfWriter()
    writer.add_page(page)
    with pytest.raises(
        DeprecationError,
        match="bookmark is deprecated as an argument. Use outline_item instead",
    ):
        writer.add_outline_item_dict(bookmark=outline_item)


@pytest.mark.samples()
def test_colors_in_outline_item(pdf_file_path):
    reader = PdfReader(SAMPLE_ROOT / "004-pdflatex-4-pages/pdflatex-4-pages.pdf")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    purple_rgb = (0.5019607843137255, 0.0, 0.5019607843137255)
    writer.add_outline_item("First Outline Item", page_number=2, color="800080")
    writer.add_outline_item("Second Outline Item", page_number=3, color="#800080")
    writer.add_outline_item("Third Outline Item", page_number=4, color=purple_rgb)

    with open(pdf_file_path, "wb") as f:
        writer.write(f)

    reader2 = PdfReader(pdf_file_path)
    for outline_item in reader2.outline:
        # convert float to string because of mutability
        assert ["%.5f" % c for c in outline_item.color] == [
            "%.5f" % p for p in purple_rgb
        ]


@pytest.mark.samples()
def test_write_empty_stream():
    reader = PdfReader(SAMPLE_ROOT / "004-pdflatex-4-pages/pdflatex-4-pages.pdf")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    with pytest.raises(ValueError) as exc:
        writer.write("")
    assert exc.value.args[0] == "Output(stream=) is empty."


def test_startup_dest():
    pdf_file_writer = PdfWriter()
    pdf_file_writer.append_pages_from_reader(PdfReader(RESOURCE_ROOT / "issue-604.pdf"))

    assert pdf_file_writer.open_destination is None
    pdf_file_writer.open_destination = pdf_file_writer.pages[9]
    # checked also using Acrobrat to verify the good page is opened
    op = pdf_file_writer._root_object["/OpenAction"]
    assert op[0] == pdf_file_writer.pages[9].indirect_reference
    assert op[1] == "/Fit"
    op = pdf_file_writer.open_destination
    assert op.raw_get("/Page") == pdf_file_writer.pages[9].indirect_reference
    assert op["/Type"] == "/Fit"
    pdf_file_writer.open_destination = op
    assert pdf_file_writer.open_destination == op

    # irrelevant, just for coverage
    pdf_file_writer._root_object[NameObject("/OpenAction")][0] = NumberObject(0)
    pdf_file_writer.open_destination
    with pytest.raises(Exception) as exc:
        del pdf_file_writer._root_object[NameObject("/OpenAction")][0]
        pdf_file_writer.open_destination
    assert "Invalid Destination" in str(exc.value)

    pdf_file_writer.open_destination = "Test"
    # checked also using Acrobrat to verify open_destination
    op = pdf_file_writer._root_object["/OpenAction"]
    assert isinstance(op, TextStringObject)
    assert op == "Test"
    op = pdf_file_writer.open_destination
    assert isinstance(op, TextStringObject)
    assert op == "Test"

    # irrelevant, this is just for coverage
    pdf_file_writer._root_object[NameObject("/OpenAction")] = NumberObject(0)
    assert pdf_file_writer.open_destination is None
    pdf_file_writer.open_destination = None
    assert "/OpenAction" not in pdf_file_writer._root_object
    pdf_file_writer.open_destination = None


@pytest.mark.enable_socket()
def test_iss471():
    url = "https://github.com/py-pdf/pypdf/files/9139245/book.pdf"
    name = "book_471.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))

    writer = PdfWriter()
    writer.append(reader, excluded_fields=[])
    assert isinstance(
        writer.pages[0]["/Annots"][0].get_object()["/Dest"], TextStringObject
    )


@pytest.mark.enable_socket()
def test_reset_translation():
    url = "https://corpora.tika.apache.org/base/docs/govdocs1/924/924666.pdf"
    name = "tika-924666.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader, (0, 10))
    nb = len(writer._objects)
    writer.append(reader, (0, 10))
    assert (
        len(writer._objects) == nb + 11
    )  # +10 (pages) +1 because of the added outline
    nb += 1
    writer.reset_translation(reader)
    writer.append(reader, (0, 10))
    assert len(writer._objects) >= nb + 200
    nb = len(writer._objects)
    writer.reset_translation(reader.pages[0].indirect_reference)
    writer.append(reader, (0, 10))
    assert len(writer._objects) >= nb + 200
    nb = len(writer._objects)
    writer.reset_translation()
    writer.append(reader, (0, 10))
    assert len(writer._objects) >= nb + 200
    nb = len(writer.pages)
    writer.append(reader, [reader.pages[0], reader.pages[0]])
    assert len(writer.pages) == nb + 2


def test_threads_empty():
    writer = PdfWriter()
    thr = writer.threads
    assert isinstance(thr, ArrayObject)
    assert len(thr) == 0
    thr2 = writer.threads
    assert thr == thr2


@pytest.mark.enable_socket()
def test_append_without_annots_and_articles():
    url = "https://corpora.tika.apache.org/base/docs/govdocs1/924/924666.pdf"
    name = "tika-924666.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader, None, (0, 10), True, ["/B"])
    writer.reset_translation()
    writer.append(reader, (0, 10), True, ["/B"])
    assert writer.threads == []
    writer = PdfWriter()
    writer.append(reader, None, (0, 10), True, ["/Annots"])
    assert "/Annots" not in writer.pages[5]
    writer = PdfWriter()
    writer.append(reader, None, (0, 10), True, [])
    assert "/Annots" in writer.pages[5]
    assert len(writer.threads) >= 1


@pytest.mark.enable_socket()
def test_append_multiple():
    url = "https://corpora.tika.apache.org/base/docs/govdocs1/924/924666.pdf"
    name = "tika-924666.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(
        reader, [0, 0, 0]
    )  # to demonstre multiple insertion of same page at once
    writer.append(reader, [0, 0, 0])  # second pack
    pages = writer._root_object["/Pages"]["/Kids"]
    assert pages[0] not in pages[1:]  # page not repeated
    assert pages[-1] not in pages[0:-1]  # page not repeated


@pytest.mark.samples()
def test_set_page_label(pdf_file_path):
    src = RESOURCE_ROOT / "GeoBase_NHNC1_Data_Model_UML_EN.pdf"  # File without labels
    reader = PdfReader(src)

    expected = [
        "i",
        "ii",
        "1",
        "2",
        "A",
        "B",
        "1",
        "2",
        "3",
        "4",
        "A",
        "i",
        "I",
        "II",
        "1",
        "2",
        "3",
        "I",
        "II",
    ]

    # Tests full lenght with labels assigned at first and last elements
    # Tests different labels assigned to consecutive ranges
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.set_page_label(0, 1, "/r")
    writer.set_page_label(4, 5, "/A")
    writer.set_page_label(10, 10, "/A")
    writer.set_page_label(11, 11, "/r")
    writer.set_page_label(12, 13, "/R")
    writer.set_page_label(17, 18, "/R")
    writer.write(pdf_file_path)
    assert PdfReader(pdf_file_path).page_labels == expected

    writer = PdfWriter()  # Same labels, different set order
    writer.clone_document_from_reader(reader)
    writer.set_page_label(17, 18, "/R")
    writer.set_page_label(4, 5, "/A")
    writer.set_page_label(10, 10, "/A")
    writer.set_page_label(0, 1, "/r")
    writer.set_page_label(12, 13, "/R")
    writer.set_page_label(11, 11, "/r")
    writer.write(pdf_file_path)
    assert PdfReader(pdf_file_path).page_labels == expected

    # Tests labels assigned only in the middle
    # Tests label assigned to a range already containing labled ranges
    expected = ["1", "2", "i", "ii", "iii", "iv", "v", "1"]
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.set_page_label(3, 4, "/a")
    writer.set_page_label(5, 5, "/A")
    writer.set_page_label(2, 6, "/r")
    writer.write(pdf_file_path)
    assert PdfReader(pdf_file_path).page_labels[: len(expected)] == expected

    # Tests labels assigned inside a previously existing range
    expected = ["1", "2", "i", "a", "b", "A", "1", "1", "2"]
    # Ones repeat because user didnt cover the entire original range
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.set_page_label(2, 6, "/r")
    writer.set_page_label(3, 4, "/a")
    writer.set_page_label(5, 5, "/A")
    writer.write(pdf_file_path)
    assert PdfReader(pdf_file_path).page_labels[: len(expected)] == expected

    # Tests invalid user input
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    with pytest.raises(
        ValueError, match="at least one between style and prefix must be given"
    ):
        writer.set_page_label(0, 5, start=2)
    with pytest.raises(
        ValueError, match="page_index_from must be equal or greater then 0"
    ):
        writer.set_page_label(-1, 5, "/r")
    with pytest.raises(
        ValueError, match="page_index_to must be equal or greater then page_index_from"
    ):
        writer.set_page_label(5, 0, "/r")
    with pytest.raises(ValueError, match="page_index_to exceeds number of pages"):
        writer.set_page_label(0, 19, "/r")
    with pytest.raises(
        ValueError, match="if given, start must be equal or greater than one"
    ):
        writer.set_page_label(0, 5, "/r", start=-1)

    pdf_file_path.unlink()

    src = (
        SAMPLE_ROOT / "009-pdflatex-geotopo/GeoTopo.pdf"
    )  # File with pre existing labels
    reader = PdfReader(src)

    # Tests adding labels to existing ones
    expected = ["i", "ii", "A", "B", "1"]
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.set_page_label(2, 3, "/A")
    writer.write(pdf_file_path)
    assert PdfReader(pdf_file_path).page_labels[: len(expected)] == expected

    # Tests replacing existing lables
    expected = ["A", "B", "1", "1", "2"]
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.set_page_label(0, 1, "/A")
    writer.write(pdf_file_path)
    assert PdfReader(pdf_file_path).page_labels[: len(expected)] == expected

    pdf_file_path.unlink()

    # Tests prefix and start.
    src = RESOURCE_ROOT / "issue-604.pdf"  # File without page labels
    reader = PdfReader(src)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    writer.set_page_label(0, 0, prefix="FRONT")
    writer.set_page_label(1, 2, "/D", start=2)
    writer.set_page_label(3, 6, prefix="UPDATES")
    writer.set_page_label(7, 10, "/D", prefix="THYR-")
    writer.set_page_label(11, 21, "/D", prefix="PAP-")
    writer.set_page_label(22, 30, "/D", prefix="FOLL-")
    writer.set_page_label(31, 39, "/D", prefix="HURT-")
    writer.write(pdf_file_path)


@pytest.mark.enable_socket()
def test_iss1601():
    url = "https://github.com/py-pdf/pypdf/files/10579503/badges-38.pdf"
    name = "badge-38.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    original_cs_operations = ContentStream(
        reader.pages[0].get_contents(), reader
    ).operations
    writer = PdfWriter()
    page_1 = writer.add_blank_page(
        reader.pages[0].mediabox[2], reader.pages[0].mediabox[3]
    )
    page_1.merge_transformed_page(reader.pages[0], Transformation())
    page_1_cs_operations = page_1.get_contents().operations
    assert is_sublist(original_cs_operations, page_1_cs_operations)
    page_1 = writer.add_blank_page(
        reader.pages[0].mediabox[2], reader.pages[0].mediabox[3]
    )
    page_1.merge_page(reader.pages[0])
    page_1_cs_operations = page_1.get_contents().operations
    assert is_sublist(original_cs_operations, page_1_cs_operations)


def test_attachments():
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    b = BytesIO()
    writer.write(b)
    b.seek(0)
    reader = PdfReader(b)
    b = None
    assert reader.attachments == {}
    # assert reader._list_attachments() == []
    # assert reader._get_attachments() == {}
    to_add = [
        ("foobar.txt", b"foobarcontent"),
        ("foobar2.txt", b"foobarcontent2"),
        ("foobar2.txt", b"2nd_foobarcontent"),
    ]
    for name, content in to_add:
        writer.add_attachment(name, content)

    b = BytesIO()
    writer.write(b)
    b.seek(0)
    reader = PdfReader(b)
    b = None
    assert sorted(reader.attachments.keys()) == sorted({name for name, _ in to_add})
    assert dict(reader.attachments.items()) == {
        "foobar.txt": b"foobarcontent",
        "foobar2.txt": b"2nd_foobarcontent",
    }
    writer.add_attachment("foobar2.txt", b"overwrite_ignored", overwrite=False)
    assert dict(reader.attachments.items()) == {
        "foobar.txt": b"foobarcontent",
        "foobar2.txt": b"2nd_foobarcontent",
    }
    assert dict(writer.attachments.items()) == {
        "foobar.txt": b"foobarcontent",
        "foobar2.txt": b"2nd_foobarcontent",
    }
    # _l = list({name for name, _ in to_add})
    # _l.sort()
    # assert reader._list_attachments() == _l
    # assert writer._list_attachments() == _l

    # We've added the same key twice - hence only 2 and not 3:
    # att = reader._get_attachments()
    # assert len(att) == 2

    # The content for foobar.txt is clear and just a single value:
    # assert att["foobar.txt"] == b"foobarcontent"

    # Not applicable for writer
    # att = writer._get_attachments()
    # assert len(att) == 2  # we have 2 keys only
    # assert att["foobar.txt"] == b"foobarcontent"

    # The content for foobar2.txt is a list!
    # att = reader._get_attachments("foobar2.txt")
    # assert len(att) == 1
    # assert att["foobar2.txt"] == [b"2nd_foobarcontent"]

    # The content for foobar2.txt is a list!
    # att = writer._get_attachments("foobar2.txt")
    # assert len(att) == 1
    # assert att["foobar2.txt"] == [b"2nd_foobarcontent"]

    # Let's do both cases with the public interface:
    assert reader.attachments["foobar.txt"] == b"foobarcontent"
    assert reader.attachments["foobar2.txt"] == b"2nd_foobarcontent"

    assert writer.attachments["foobar.txt"] == b"foobarcontent"
    assert writer.attachments["foobar2.txt"] == b"2nd_foobarcontent"


@pytest.mark.enable_socket()
def test_iss1614():
    # test of an annotation(link) directly stored in the /Annots in the page
    url = "https://github.com/py-pdf/pypdf/files/10669995/broke.pdf"
    name = "iss1614.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader)
    # test for 2nd error case reported in #1614
    url = "https://github.com/py-pdf/pypdf/files/10696390/broken.pdf"
    name = "iss1614.2.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer.append(reader)


@pytest.mark.enable_socket()
def test_new_removes():
    # test of an annotation(link) directly stored in the /Annots in the page
    url = "https://github.com/py-pdf/pypdf/files/10807951/tt.pdf"
    name = "iss1650.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.remove_images()
    b = BytesIO()
    writer.write(b)
    bb = bytes(b.getbuffer())
    assert b"/Im0 Do" not in bb
    assert b"/Fm0 Do" in bb
    assert b" TJ" in bb

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.remove_text()
    b = BytesIO()
    writer.write(b)
    bb = bytes(b.getbuffer())
    assert b"/Im0" in bb
    assert b"Chap" not in bb
    assert b" TJ" not in bb

    url = "https://github.com/py-pdf/pypdf/files/10832029/tt2.pdf"
    name = "GeoBaseWithComments.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer.append(reader)
    writer.remove_objects_from_page(writer.pages[0], [ObjectDeletionFlag.LINKS])
    assert "/Links" not in [
        a.get_object()["/Subtype"] for a in writer.pages[0]["/Annots"]
    ]
    writer.remove_objects_from_page(writer.pages[0], ObjectDeletionFlag.ATTACHMENTS)
    assert "/FileAttachment" not in [
        a.get_object()["/Subtype"] for a in writer.pages[0]["/Annots"]
    ]

    writer.pages[0]["/Annots"].append(
        DictionaryObject({NameObject("/Subtype"): TextStringObject("/3D")})
    )
    assert "/3D" in [a.get_object()["/Subtype"] for a in writer.pages[0]["/Annots"]]
    writer.remove_objects_from_page(writer.pages[0], ObjectDeletionFlag.OBJECTS_3D)
    assert "/3D" not in [a.get_object()["/Subtype"] for a in writer.pages[0]["/Annots"]]

    writer.remove_links()
    assert len(writer.pages[0]["/Annots"]) == 0
    assert len(writer.pages[3]["/Annots"]) == 0

    writer.remove_annotations("/Text")


@pytest.mark.enable_socket()
def test_late_iss1654():
    url = "https://github.com/py-pdf/pypdf/files/10935632/bid1.pdf"
    name = "bid1.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for p in writer.pages:
        p.compress_content_streams()
    b = BytesIO()
    writer.write(b)


@pytest.mark.enable_socket()
def test_iss1723():
    # test of an annotation(link) directly stored in the /Annots in the page
    url = "https://github.com/py-pdf/pypdf/files/11015242/inputFile.pdf"
    name = "iss1723.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader, (3, 5))


@pytest.mark.enable_socket()
def test_iss1767():
    # test with a pdf which is buggy because the object 389,0 exists 3 times:
    # twice to define catalog and one as an XObject inducing a loop when
    # cloning
    url = "https://github.com/py-pdf/pypdf/files/11138472/test.pdf"
    name = "iss1723.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    PdfWriter(clone_from=reader)


@pytest.mark.enable_socket()
def test_named_dest_page_number():
    """
    Closes iss471
    tests appending with named destinations as integers
    """
    url = "https://github.com/py-pdf/pypdf/files/10704333/central.pdf"
    name = "central.pdf"
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.append(BytesIO(get_data_from_url(url, name=name)), pages=[0, 1, 2])
    assert len(writer._root_object["/Names"]["/Dests"]["/Names"]) == 2
    assert writer._root_object["/Names"]["/Dests"]["/Names"][-1][0] == (1 + 1)
    writer.append(BytesIO(get_data_from_url(url, name=name)))
    assert len(writer._root_object["/Names"]["/Dests"]["/Names"]) == 6
    writer2 = PdfWriter()
    writer2.add_blank_page(100, 100)
    dest = writer2.add_named_destination("toto", 0)
    dest.get_object()[NameObject("/D")][0] = NullObject()
    b = BytesIO()
    writer2.write(b)
    b.seek(0)
    writer.append(b)
    assert len(writer._root_object["/Names"]["/Dests"]["/Names"]) == 6


@pytest.mark.parametrize(
    ("write_data_here", "needs_cleanup"),
    [
        (
            "dont_commit_writer.pdf",
            True,
        )
    ],
)
def test_update_form_fields(write_data_here, needs_cleanup):
    writer = PdfWriter(clone_from=RESOURCE_ROOT / "FormTestFromOo.pdf")
    writer.update_page_form_field_values(
        writer.pages[0],
        {
            "CheckBox1": "/Yes",
            "Text1": "mon Text1",
            "Text2": "ligne1\nligne2",
            "RadioGroup1": "/2",
            "RdoS1": "/",
            "Combo1": "!!monCombo!!",
            "Liste1": "Liste2",
            "Liste2": ["Lst1", "Lst3"],
            "DropList1": "DropListe3",
        },
        auto_regenerate=False,
    )
    del writer.pages[0]["/Annots"][1].get_object()["/AP"]["/N"]
    writer.update_page_form_field_values(
        writer.pages[0],
        {"Text1": "my Text1", "Text2": "ligne1\nligne2\nligne3"},
        auto_regenerate=False,
    )

    writer.write("dont_commit_writer.pdf")
    reader = PdfReader("dont_commit_writer.pdf")
    flds = reader.get_fields()
    assert flds["CheckBox1"]["/V"] == "/Yes"
    assert flds["CheckBox1"].indirect_reference.get_object()["/AS"] == "/Yes"
    assert (
        b"(my Text1)"
        in flds["Text1"].indirect_reference.get_object()["/AP"]["/N"].get_data()
    )
    assert flds["Text2"]["/V"] == "ligne1\nligne2\nligne3"
    assert (
        b"(ligne3)"
        in flds["Text2"].indirect_reference.get_object()["/AP"]["/N"].get_data()
    )
    assert flds["RadioGroup1"]["/V"] == "/2"
    assert flds["RadioGroup1"]["/Kids"][0].get_object()["/AS"] == "/Off"
    assert flds["RadioGroup1"]["/Kids"][1].get_object()["/AS"] == "/2"
    assert all(x in flds["Liste2"]["/V"] for x in ["Lst1", "Lst3"])

    assert all(x in flds["CheckBox1"]["/_States_"] for x in ["/Off", "/Yes"])
    assert all(x in flds["RadioGroup1"]["/_States_"] for x in ["/1", "/2", "/3"])
    assert all(x in flds["Liste1"]["/_States_"] for x in ["Liste1", "Liste2", "Liste3"])

    if needs_cleanup:
        Path(write_data_here).unlink()


@pytest.mark.enable_socket()
def test_iss1862():
    # The file here has "/B" entry to define the font in a object below the page
    # The excluded field shall be considered only at first level (page) and not
    # below
    url = "https://github.com/py-pdf/pypdf/files/11708801/intro.pdf"
    name = "iss1862.pdf"
    writer = PdfWriter()
    writer.append(BytesIO(get_data_from_url(url, name=name)))
    # check that "/B" is in the font
    writer.pages[0]["/Resources"]["/Font"]["/F1"]["/CharProcs"]["/B"].get_data()


def test_empty_objects_before_cloning():
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    writer = PdfWriter(clone_from=reader)
    nb_obj_reader = len(reader.xref_objStm) + sum(
        len(reader.xref[i]) for i in reader.xref
    )
    nb_obj_reader -= 1  # for trailer
    nb_obj_reader -= len(
        {x: 1 for x, y in reader.xref_objStm.values()}
    )  # to remove object streams
    assert len(writer._objects) == nb_obj_reader


@pytest.mark.enable_socket()
def test_watermark():
    url = "https://github.com/py-pdf/pypdf/files/11985889/bg.pdf"
    name = "bgwatermark.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    url = "https://github.com/py-pdf/pypdf/files/11985888/source.pdf"
    name = "srcwatermark.pdf"
    writer = PdfWriter(clone_from=BytesIO(get_data_from_url(url, name=name)))
    for p in writer.pages:
        p.merge_page(reader.pages[0], over=False)

    assert isinstance(p["/Contents"], ArrayObject)
    assert isinstance(p["/Contents"][0], IndirectObject)

    b = BytesIO()
    writer.write(b)
    assert len(b.getvalue()) < 2.1 * 1024 * 1024


@pytest.mark.enable_socket()
@pytest.mark.timeout(4)
def test_watermarking_speed():
    url = "https://github.com/py-pdf/pypdf/files/11985889/bg.pdf"
    name = "bgwatermark.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    url = "https://arxiv.org/pdf/2201.00214.pdf"
    name = "2201.00214.pdf"
    writer = PdfWriter(clone_from=BytesIO(get_data_from_url(url, name=name)))
    for p in writer.pages:
        p.merge_page(reader.pages[0], over=False)
    out_pdf_bytesio = BytesIO()
    writer.write(out_pdf_bytesio)
    pdf_size_in_mib = len(out_pdf_bytesio.getvalue()) / 1024 / 1024
    assert pdf_size_in_mib < 20


@pytest.mark.enable_socket()
@pytest.mark.skipif(GHOSTSCRIPT_BINARY is None, reason="Requires Ghostscript")
def test_watermark_rendering(tmp_path):
    """Ensure the visual appearance of watermarking stays correct."""
    url = "https://github.com/py-pdf/pypdf/files/11985889/bg.pdf"
    name = "bgwatermark.pdf"
    watermark = PdfReader(BytesIO(get_data_from_url(url, name=name))).pages[0]
    url = "https://github.com/py-pdf/pypdf/files/11985888/source.pdf"
    name = "srcwatermark.pdf"
    page = PdfReader(BytesIO(get_data_from_url(url, name=name))).pages[0]
    writer = PdfWriter()
    page.merge_page(watermark, over=False)
    writer.add_page(page)

    target_png_path = tmp_path / "target.png"
    url = "https://github.com/py-pdf/pypdf/assets/96178532/d5c72d0e-7047-4504-bbf6-bc591c80d7c0"
    name = "dstwatermark.png"
    target_png_path.write_bytes(get_data_from_url(url, name=name))

    pdf_path = tmp_path / "out.pdf"
    png_path = tmp_path / "out.png"
    writer.write(pdf_path)

    # False positive: https://github.com/PyCQA/bandit/issues/333
    subprocess.run(
        [  # noqa: S603
            GHOSTSCRIPT_BINARY,
            "-sDEVICE=pngalpha",
            "-o",
            png_path,
            pdf_path,
        ]
    )
    assert png_path.is_file()
    assert image_similarity(png_path, target_png_path) >= 0.95


@pytest.mark.skipif(GHOSTSCRIPT_BINARY is None, reason="Requires Ghostscript")
def test_watermarking_reportlab_rendering(tmp_path):
    """
    This test is showing a rotated+mirrored watermark in pypdf==3.15.4.

    Replacing the generate_base with e.g. the crazyones did not show the issue.
    """
    base_path = SAMPLE_ROOT / "022-pdfkit/pdfkit.pdf"
    watermark_path = SAMPLE_ROOT / "013-reportlab-overlay/reportlab-overlay.pdf"

    reader = PdfReader(base_path)
    base_page = reader.pages[0]
    watermark = PdfReader(watermark_path).pages[0]

    writer = PdfWriter()
    base_page.merge_page(watermark)
    writer.add_page(base_page)

    target_png_path = RESOURCE_ROOT / "test_watermarking_reportlab_rendering.png"
    pdf_path = tmp_path / "out.pdf"
    png_path = tmp_path / "test_watermarking_reportlab_rendering.png"

    writer.write(pdf_path)
    # False positive: https://github.com/PyCQA/bandit/issues/333
    subprocess.run(
        [  # noqa: S603
            GHOSTSCRIPT_BINARY,
            "-r120",
            "-sDEVICE=pngalpha",
            "-o",
            png_path,
            pdf_path,
        ]
    )
    assert png_path.is_file()
    assert image_similarity(png_path, target_png_path) >= 0.999


@pytest.mark.enable_socket()
def test_da_missing_in_annot():
    url = "https://github.com/py-pdf/pypdf/files/12136285/Building.Division.Permit.Application.pdf"
    name = "BuildingDivisionPermitApplication.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter(clone_from=reader)
    writer.update_page_form_field_values(
        writer.pages[0], {"PCN-1": "0"}, auto_regenerate=False
    )
    b = BytesIO()
    writer.write(b)
    reader = PdfReader(BytesIO(b.getvalue()))
    ff = reader.get_fields()
    # check for autosize processing
    assert (
        b"0 Tf"
        not in ff["PCN-1"].indirect_reference.get_object()["/AP"]["/N"].get_data()
    )
    f2 = writer.get_object(ff["PCN-2"].indirect_reference.idnum)
    f2[NameObject("/Parent")] = writer.get_object(
        ff["PCN-1"].indirect_reference.idnum
    ).indirect_reference
    writer.update_page_form_field_values(
        writer.pages[0], {"PCN-2": "1"}, auto_regenerate=False
    )


def test_missing_fields(pdf_file_path):
    reader = PdfReader(RESOURCE_ROOT / "form.pdf")

    writer = PdfWriter()
    writer.add_page(reader.pages[0])

    with pytest.raises(PyPdfError) as exc:
        writer.update_page_form_field_values(
            writer.pages[0], {"foo": "some filled in text"}, flags=1
        )
    assert exc.value.args[0] == "No /AcroForm dictionary in PdfWriter Object"

    writer = PdfWriter()
    writer.append(reader, [0])
    del writer._root_object["/AcroForm"]["/Fields"]
    with pytest.raises(PyPdfError) as exc:
        writer.update_page_form_field_values(
            writer.pages[0], {"foo": "some filled in text"}, flags=1
        )
    assert exc.value.args[0] == "No /Fields dictionary in Pdf in PdfWriter Object"


def test_missing_info():
    reader = PdfReader(RESOURCE_ROOT / "missing_info.pdf")

    writer = PdfWriter(clone_from=reader)
    assert len(writer.pages) == len(reader.pages)


@pytest.mark.enable_socket()
def test_germanfields():
    """Cf #2035"""
    url = "https://github.com/py-pdf/pypdf/files/12194195/test.pdf"
    name = "germanfields.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter(clone_from=reader)
    form_fields = {"Text Box 1": "test æ ø å"}
    writer.update_page_form_field_values(
        writer.pages[0], form_fields, auto_regenerate=False
    )
    bytes_stream = BytesIO()
    writer.write(bytes_stream)
    bytes_stream.seek(0)
    reader2 = PdfReader(bytes_stream)
    assert (
        b"test \xe6 \xf8 \xe5"
        in reader2.get_fields()["Text Box 1"]
        .indirect_reference.get_object()["/AP"]["/N"]
        .get_data()
    )


@pytest.mark.enable_socket()
def test_no_t_in_articles():
    """Cf #2078"""
    url = "https://github.com/py-pdf/pypdf/files/12311735/bad.pdf"
    name = "iss2078.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader)


@pytest.mark.enable_socket()
def test_no_i_in_articles():
    """Cf #2089"""
    url = "https://github.com/py-pdf/pypdf/files/12352793/kim2002.pdf"
    name = "iss2089.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader)


@pytest.mark.enable_socket()
def test_damaged_pdf_length_returning_none():
    """
    Cf #140
    https://github.com/py-pdf/pypdf/issues/140#issuecomment-1685380549
    """
    url = "https://github.com/py-pdf/pypdf/files/12168578/bad_pdf_example.pdf"
    name = "iss140_bad_pdf.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader)


@pytest.mark.enable_socket()
def test_viewerpreferences():
    """Add Tests for ViewerPreferences"""
    url = "https://github.com/py-pdf/pypdf/files/9175966/2015._pb_decode_pg0.pdf"
    name = "2015._pb_decode_pg0.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    v = reader.viewer_preferences
    assert v.center_window == True  # noqa: E712
    writer = PdfWriter(clone_from=reader)
    v = writer.viewer_preferences
    assert v.center_window == True  # noqa: E712
    v.center_window = False
    assert (
        writer._root_object["/ViewerPreferences"]["/CenterWindow"]
        == False  # noqa: E712
    )
    assert v.print_area == "/CropBox"
    with pytest.raises(ValueError):
        v.non_fullscreen_pagemode = "toto"
    with pytest.raises(ValueError):
        v.non_fullscreen_pagemode = "/toto"
    v.non_fullscreen_pagemode = "/UseOutlines"
    assert (
        writer._root_object["/ViewerPreferences"]["/NonFullScreenPageMode"]
        == "/UseOutlines"
    )
    writer = PdfWriter(clone_from=reader)
    v = writer.viewer_preferences
    assert v.center_window == True  # noqa: E712
    v.center_window = False
    assert (
        writer._root_object["/ViewerPreferences"]["/CenterWindow"]
        == False  # noqa: E712
    )

    writer = PdfWriter(clone_from=reader)
    writer._root_object[NameObject("/ViewerPreferences")] = writer._add_object(
        writer._root_object["/ViewerPreferences"]
    )
    v = writer.viewer_preferences
    v.center_window = False
    assert (
        writer._root_object["/ViewerPreferences"]["/CenterWindow"]
        == False  # noqa: E712
    )
    v.num_copies = 1
    assert v.num_copies == 1
    assert v.print_pagerange is None
    with pytest.raises(ValueError):
        v.print_pagerange = "toto"
    v.print_pagerange = ArrayObject()
    assert len(v.print_pagerange) == 0

    writer.create_viewer_preferences()
    assert len(writer._root_object["/ViewerPreferences"]) == 0
    writer.viewer_preferences.direction = "/R2L"
    assert len(writer._root_object["/ViewerPreferences"]) == 1

    del reader.trailer["/Root"]["/ViewerPreferences"]
    assert reader.viewer_preferences is None
    writer = PdfWriter(clone_from=reader)
    assert writer.viewer_preferences is None


def test_extra_spaces_in_da_text(caplog):
    writer = PdfWriter(clone_from=RESOURCE_ROOT / "form.pdf")
    t = writer.pages[0]["/Annots"][0].get_object()["/DA"]
    t = t.replace("/Helv", "/Helv   ")
    writer.pages[0]["/Annots"][0].get_object()[NameObject("/DA")] = TextStringObject(t)
    writer.update_page_form_field_values(
        writer.pages[0], {"foo": "abcd"}, auto_regenerate=False
    )
    t = writer.pages[0]["/Annots"][0].get_object()["/AP"]["/N"].get_data()
    assert "Font dictionary for  not found." not in caplog.text
    assert b"/Helv" in t
    assert b"(abcd)" in t


@pytest.mark.enable_socket()
def test_object_contains_indirect_reference_to_self():
    url = "https://github.com/py-pdf/pypdf/files/12389243/testbook.pdf"
    name = "iss2102.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    width, height = 595, 841
    outpage = writer.add_blank_page(width, height)
    outpage.merge_page(reader.pages[6])
    writer.append(reader)


def test_remove_image_per_type():
    writer = PdfWriter(clone_from=RESOURCE_ROOT / "reportlab-inline-image.pdf")
    writer.remove_images(ImageType.INLINE_IMAGES)

    assert all(
        x not in writer.pages[0].get_contents().get_data()
        for x in (b"BI", b"ID", b"EI")
    )

    with pytest.raises(DeprecationWarning):
        writer.remove_images(True)

    writer = PdfWriter(clone_from=RESOURCE_ROOT / "GeoBase_NHNC1_Data_Model_UML_EN.pdf")
    writer.remove_images(ImageType.DRAWING_IMAGES)
    assert all(
        x not in writer.pages[1].get_contents().get_data()
        for x in (b" re\n", b"W*", b"f*")
    )
    assert all(
        x in writer.pages[1].get_contents().get_data() for x in (b" TJ\n", b"rg", b"Tm")
    )
    assert all(
        x not in writer.pages[9]["/Resources"]["/XObject"]["/Meta84"].get_data()
        for x in (b" re\n", b"W*", b"f*")
    )
    writer.remove_images(ImageType.XOBJECT_IMAGES)
    assert b"Do\n" not in writer.pages[0].get_contents().get_data()
    assert len(writer.pages[0]["/Resources"]["/XObject"]) == 0


@pytest.mark.enable_socket()
def test_add_outlines_on_empty_dict():
    """Cf #2233"""

    def _get_parent_bookmark(current_indent, history_indent, bookmarks) -> Any:
        """The parent of A is the nearest bookmark whose indent is smaller than A's"""
        assert len(history_indent) == len(bookmarks)
        if current_indent == 0:
            return None
        for i in range(len(history_indent) - 1, -1, -1):
            # len(history_indent) - 1   ===>   0
            if history_indent[i] < current_indent:
                return bookmarks[i]
        return None

    bookmark_lines = """1 FUNDAMENTALS OF RADIATIVE TRANSFER 1
1.1 The Electromagnetic Spectrum; Elementary Properties of Radiation 1
1.2 Radiative Flux 2
    Macroscopic Description of the Propagation of Radiation 2
    Flux from an Isotropic Source-The Inverse Square Law 2
1.3 The Specific Intensity and Its Moments 3
    Definition of Specific Intensity or Brightness 3
    Net Flux and Momentum Flux 4
    Radiative Energy Density 5
    Radiation Pressure in an Enclosure Containing an Isotropic Radiation Field 6
    Constancy of Specific Zntensiw Along Rays in Free Space 7
    Proof of the Inverse Square Law for a Uniformly Bright Sphere 7
1.4 Radiative Transfer 8
    Emission 9
    Absorption 9
    The Radiative Transfer Equation 11
    Optical Depth and Source Function 12
    Mean Free Path 14
    Radiation Force 15
1.5 Thermal Radiation 15
    Blackbody Radiation 15
    Kirchhof's Law for Thermal Emission 16
    Thermodynamics of Blackbody Radiation 17
    The Planck Spectrum 20
    Properties of the Planck Law 23
    Characteristic Temperatures Related to Planck Spectrum 25
1.6 The Einstein Coefficients 27
    Definition of Coefficients 27
    Relations between Einstein Coefficients 29
    Absorption and Emission Coefficients in Terms of Einstein Coefficients 30
1.7 Scattering Effects; Random Walks 33
    Pure Scattering 33
    Combined Scattering and Absorption 36
1.8 Radiative Diffusion 39
    The Rosseland Approximation 39
    The Eddington Approximation; Two-Stream Approximation 42
PROBLEMS 45
REFERENCES 50
2 BASIC THEORY OF RADIATION FIELDS 51
2.1 Review of Maxwell’s Equations 51
2.2 Plane Electromagnetic Waves 55
2.3 The Radiation Spectrum 58
2.4 Polarization and Stokes Parameters 62
    Monochromatic Waves 62
    Quasi-monochromatic Waves 65
2.5 Electromagnetic Potentials 69
2.6 Applicability of Transfer Theory and the Geometrical Optics Limit 72
PROBLEMS 74
REFERENCES 76"""
    url = "https://github.com/py-pdf/pypdf/files/12797067/test-12.pdf"
    name = "iss2233.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter(clone_from=reader)

    bookmarks, history_indent = [], []
    for line in bookmark_lines.split("\n"):
        line2 = re.split(r"\s+", line.strip())
        indent_size = len(line) - len(line.lstrip())
        parent = _get_parent_bookmark(indent_size, history_indent, bookmarks)
        history_indent.append(indent_size)
        title, page = " ".join(line2[:-1]), int(line2[-1]) - 1
        new_bookmark = writer.add_outline_item(title, page, parent=parent)
        bookmarks.append(new_bookmark)


def test_merging_many_temporary_files():
    def create_number_pdf(n) -> BytesIO:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(40, 10, str(n))
        byte_string = pdf.output()
        return BytesIO(byte_string)

    writer = PdfWriter()
    for n in range(100):
        reader = PdfReader(create_number_pdf(n))
        for page in reader.pages:
            # Should only be one page.
            writer.add_page(page)

    out = BytesIO()
    writer.write(out)

    out.seek(0)
    reader = PdfReader(out)
    for n, page in enumerate(reader.pages):
        text = page.extract_text()
        assert text == str(n)
