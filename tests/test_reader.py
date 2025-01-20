"""Test the pypdf._reader module."""
import io
import time
from io import BytesIO
from pathlib import Path
from typing import List, Union

import pytest

from pypdf import PdfReader, PdfWriter
from pypdf._crypt_providers import crypt_provider
from pypdf._reader import convert_to_int
from pypdf.constants import ImageAttributes as IA
from pypdf.constants import PageAttributes as PG
from pypdf.constants import UserAccessPermissions as UAP
from pypdf.errors import (
    EmptyFileError,
    FileNotDecryptedError,
    PdfReadError,
    PdfStreamError,
    WrongPasswordError,
)
from pypdf.generic import (
    ArrayObject,
    Destination,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from . import get_data_from_url, normalize_warnings

HAS_AES = crypt_provider[0] in ["pycryptodome", "cryptography"]
TESTS_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
RESOURCE_ROOT = PROJECT_ROOT / "resources"
SAMPLE_ROOT = PROJECT_ROOT / "sample-files"


NestedList = Union[int, None, List["NestedList"]]


@pytest.mark.parametrize(
    ("src", "num_pages"),
    [("selenium-pypdf-issue-177.pdf", 1), ("pdflatex-outline.pdf", 4)],
)
def test_get_num_pages(src, num_pages):
    src = RESOURCE_ROOT / src
    with PdfReader(src) as reader:
        assert len(reader.pages) == num_pages
        # from #1911
        assert "/Size" in reader.trailer


@pytest.mark.parametrize(
    ("pdf_path", "expected"),
    [
        (
            RESOURCE_ROOT / "crazyones.pdf",
            {
                "/CreationDate": "D:20150604133406-06'00'",
                "/Creator": " XeTeX output 2015.06.04:1334",
                "/Producer": "xdvipdfmx (20140317)",
            },
        ),
        (
            RESOURCE_ROOT / "metadata.pdf",
            {
                "/CreationDate": "D:20220415093243+02'00'",
                "/ModDate": "D:20220415093243+02'00'",
                "/Creator": "pdflatex, or other tool",
                "/Producer": "Latex with hyperref, or other system",
                "/Author": "Martin Thoma",
                "/Keywords": "Some Keywords, other keywords; more keywords",
                "/Subject": "The Subject",
                "/Title": "The Title",
                "/Trapped": "/False",
                "/PTEX.Fullbanner": (
                    "This is pdfTeX, Version "
                    "3.141592653-2.6-1.40.23 (TeX Live 2021) "
                    "kpathsea version 6.3.3"
                ),
            },
        ),
    ],
    ids=["crazyones", "metadata"],
)
def test_read_metadata(pdf_path, expected):
    with open(pdf_path, "rb") as inputfile:
        reader = PdfReader(inputfile)
        docinfo = reader.metadata
        assert docinfo is not None
        metadict = dict(docinfo)
        assert metadict == expected
        docinfo.title
        docinfo.title_raw
        docinfo.author
        docinfo.author_raw
        docinfo.creator
        docinfo.creator_raw
        docinfo.producer
        docinfo.producer_raw
        docinfo.subject
        docinfo.subject_raw
        docinfo.creation_date
        docinfo.creation_date_raw
        docinfo.modification_date
        docinfo.modification_date_raw
        docinfo.keywords
        docinfo.keywords_raw
        if "/Title" in metadict:
            assert isinstance(docinfo.title, str)
            assert metadict["/Title"] == docinfo.title


def test_read_metadata_title_is_utf8():
    with open(RESOURCE_ROOT / "bytes.pdf", "rb") as inputfile:
        reader = PdfReader(inputfile)
        title = reader.metadata.title
        # Should be a str.
        assert title == "Microsoft Word - トランスバース社買収電話会議英語Final.docx"


def test_iss1943():
    with PdfReader(RESOURCE_ROOT / "crazyones.pdf") as reader:
        docinfo = reader.metadata
        docinfo.update(
            {
                NameObject("/CreationDate"): TextStringObject(
                    "D:20230705005151Z00'00'"
                ),
                NameObject("/ModDate"): TextStringObject("D:20230705005151Z00'00'"),
            }
        )
        docinfo.creation_date
        docinfo.creation_date_raw
        docinfo.modification_date
        docinfo.modification_date_raw
        docinfo.update({NameObject("/CreationDate"): NumberObject(1)})
        assert docinfo.creation_date is None


@pytest.mark.samples
@pytest.mark.parametrize(
    "pdf_path", [SAMPLE_ROOT / "017-unreadable-meta-data/unreadablemetadata.pdf"]
)
def test_broken_meta_data(pdf_path):
    with open(pdf_path, "rb") as f:
        reader = PdfReader(f)
        assert reader.metadata is None

    with open(RESOURCE_ROOT / "crazyones.pdf", "rb") as f:
        b = f.read(-1)
    reader = PdfReader(BytesIO(b.replace(b"/Info 2 0 R", b"/Info 2    ")))
    with pytest.raises(PdfReadError) as exc:
        reader.metadata
    assert "does not point to document information directory" in repr(exc)


@pytest.mark.parametrize(
    "src",
    [
        RESOURCE_ROOT / "crazyones.pdf",
        RESOURCE_ROOT / "commented.pdf",
    ],
)
def test_get_annotations(src):
    with PdfReader(src) as reader:
        for page in reader.pages:
            if PG.ANNOTS in page:
                for annot in page[PG.ANNOTS]:
                    subtype = annot.get_object()[IA.SUBTYPE]
                    if subtype == "/Text":
                        annot.get_object()[PG.CONTENTS]


@pytest.mark.parametrize(
    ("src", "nb_attachments"),
    [
        (RESOURCE_ROOT / "attachment.pdf", 1),
        (RESOURCE_ROOT / "crazyones.pdf", 0),
    ],
)
def test_get_attachments(src, nb_attachments):
    reader = PdfReader(src)

    attachments = {}
    for page in reader.pages:
        if PG.ANNOTS in page:
            for annotation in page[PG.ANNOTS]:
                annotobj = annotation.get_object()
                if annotobj[IA.SUBTYPE] == "/FileAttachment":
                    fileobj = annotobj["/FS"]
                    attachments[fileobj["/F"]] = fileobj["/EF"]["/F"].get_data()
    assert len(attachments) == nb_attachments


@pytest.mark.parametrize(
    ("src", "outline_elements"),
    [
        (RESOURCE_ROOT / "pdflatex-outline.pdf", 9),
        (RESOURCE_ROOT / "crazyones.pdf", 0),
    ],
)
def test_get_outline(src, outline_elements):
    reader = PdfReader(src)
    outline = reader.outline
    assert len(outline) == outline_elements


@pytest.mark.samples
@pytest.mark.parametrize(
    ("src", "expected_images"),
    [
        ("pdflatex-outline.pdf", []),
        ("crazyones.pdf", []),
        ("git.pdf", ["Image9.png"]),
        pytest.param(
            "imagemagick-lzw.pdf",
            ["Im0.png"],
            marks=pytest.mark.xfail(reason="broken image extraction"),
        ),
        pytest.param(
            "imagemagick-ASCII85Decode.pdf",
            ["Im0.png"],
            # marks=pytest.mark.xfail(reason="broken image extraction"),
        ),
        ("imagemagick-CCITTFaxDecode.pdf", ["Im0.tiff"]),
        (SAMPLE_ROOT / "019-grayscale-image/grayscale-image.pdf", ["X0.png"]),
    ],
)
def test_get_images(src, expected_images):
    from PIL import Image

    src_abs = RESOURCE_ROOT / src
    reader = PdfReader(src_abs)
    page = reader.pages[0]
    images_extracted = page.images

    assert len(images_extracted) == len(expected_images)
    for image, expected_image in zip(images_extracted, expected_images):
        assert image.name == expected_image
        assert (
            image.name.split(".")[-1].upper()
            == Image.open(io.BytesIO(image.data)).format
        )


@pytest.mark.parametrize(
    ("strict", "with_prev_0", "startx_correction", "should_fail", "warning_msgs"),
    [
        (
            True,
            False,
            -1,
            False,
            [
                "startxref on same line as offset",
                "Xref table not zero-indexed. "
                "ID numbers for objects will be corrected.",
            ],
        ),  # all nominal => no fail
        (True, True, -1, True, ""),  # Prev=0 => fail expected
        (
            False,
            False,
            -1,
            False,
            [
                "startxref on same line as offset",
            ],
        ),
        (
            False,
            True,
            -1,
            False,
            [
                "startxref on same line as offset",
                "/Prev=0 in the trailer - assuming there is no previous xref table",
            ],
        ),  # Prev =0 => no strict so tolerant
        (True, False, 0, True, ""),  # error on startxref, in strict => fail expected
        (True, True, 0, True, ""),
        (
            False,
            False,
            0,
            False,
            [
                "startxref on same line as offset",
                "incorrect startxref pointer(1)",
                "parsing for Object Streams",
            ],
        ),  # error on startxref, but no strict => xref rebuilt,no fail
        (
            False,
            True,
            0,
            False,
            [
                "startxref on same line as offset",
                "incorrect startxref pointer(1)",
                "parsing for Object Streams",
            ],
        ),
    ],
)
def test_get_images_raw(
    caplog, strict, with_prev_0, startx_correction, should_fail, warning_msgs
):
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << %s/Root 5 0 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        # - 1 below in the find because of the double %
        pdf_data.find(b"1 0 obj") - 1,
        pdf_data.find(b"2 0 obj") - 1,
        pdf_data.find(b"3 0 obj") - 1,
        pdf_data.find(b"4 0 obj") - 1,
        pdf_data.find(b"5 0 obj") - 1,
        b"/Prev 0 " if with_prev_0 else b"",
        # startx_correction should be -1 due to double % at the beginning
        # inducing an error on startxref computation
        pdf_data.find(b"xref") + startx_correction,
    )
    pdf_stream = io.BytesIO(pdf_data)
    if should_fail:
        with pytest.raises(PdfReadError) as exc:
            PdfReader(pdf_stream, strict=strict)
        assert exc.type == PdfReadError
        if startx_correction == -1:
            assert (
                exc.value.args[0]
                == "/Prev=0 in the trailer (try opening with strict=False)"
            )
    else:
        PdfReader(pdf_stream, strict=strict)
        assert normalize_warnings(caplog.text) == warning_msgs


def test_issue297(caplog):
    path = RESOURCE_ROOT / "issue-297.pdf"
    with pytest.raises(PdfReadError) as exc:
        reader = PdfReader(path, strict=True)
    assert caplog.text == ""
    assert "Broken xref table" in exc.value.args[0]
    reader = PdfReader(path, strict=False)
    assert normalize_warnings(caplog.text) == [
        "incorrect startxref pointer(1)",
        "parsing for Object Streams",
    ]
    reader.pages[0]


@pytest.mark.parametrize(
    ("pdffile", "password", "should_fail"),
    [
        ("encrypted-file.pdf", "test", False),
        ("encrypted-file.pdf", b"test", False),
        ("encrypted-file.pdf", "qwerty", True),
        ("encrypted-file.pdf", b"qwerty", True),
    ],
)
def test_get_page_of_encrypted_file(pdffile, password, should_fail):
    """
    Check if we can read a page of an encrypted file.

    This is a regression test for issue 327:
    IndexError for get_page() of decrypted file
    """
    path = RESOURCE_ROOT / pdffile
    if should_fail:
        with pytest.raises(PdfReadError):
            PdfReader(path, password=password)
    else:
        PdfReader(path, password=password).pages[0]


@pytest.mark.parametrize(
    ("src", "expected", "expected_get_fields"),
    [
        (
            "form.pdf",
            {"foo": ""},
            {"foo": {"/DV": "", "/FT": "/Tx", "/T": "foo", "/V": ""}},
        ),
        (
            "form_acrobatReader.pdf",
            {"foo": "Bar"},
            {"foo": {"/DV": "", "/FT": "/Tx", "/T": "foo", "/V": "Bar"}},
        ),
        (
            "form_evince.pdf",
            {"foo": "bar"},
            {"foo": {"/DV": "", "/FT": "/Tx", "/T": "foo", "/V": "bar"}},
        ),
        (
            "crazyones.pdf",
            {},
            None,
        ),
    ],
)
def test_get_form(src, expected, expected_get_fields, txt_file_path):
    """Check if we can read out form data."""
    src = RESOURCE_ROOT / src
    reader = PdfReader(src)
    fields = reader.get_form_text_fields()
    assert fields == expected

    with open(txt_file_path, "w") as f:
        fields = reader.get_fields(fileobj=f)
    assert fields == expected_get_fields
    if fields:
        for field in fields.values():
            # Just access the attributes
            [
                field.field_type,
                field.parent,
                field.kids,
                field.name,
                field.alternate_name,
                field.mapping_name,
                field.flags,
                field.value,
                field.default_value,
                field.additional_actions,
            ]


@pytest.mark.parametrize(
    ("src", "page_number"),
    [
        ("form.pdf", 0),
        ("pdflatex-outline.pdf", 2),
    ],
)
def test_get_page_number(src, page_number):
    src = RESOURCE_ROOT / src
    reader = PdfReader(src)
    reader.get_page(0)
    page = reader.pages[page_number]
    assert reader.get_page_number(page) == page_number


@pytest.mark.parametrize(
    ("src", "expected"),
    [("form.pdf", None), ("AutoCad_Simple.pdf", "/SinglePage")],
)
def test_get_page_layout(src, expected):
    src = RESOURCE_ROOT / src
    reader = PdfReader(src)
    assert reader.page_layout == expected


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("form.pdf", "/UseNone"),
        ("crazyones.pdf", None),
    ],
)
def test_get_page_mode(src, expected):
    src = RESOURCE_ROOT / src
    reader = PdfReader(src)
    assert reader.page_mode == expected


def test_read_empty():
    with pytest.raises(EmptyFileError) as exc:
        PdfReader(io.BytesIO())
    assert exc.value.args[0] == "Cannot read an empty file"


def test_read_malformed_header(caplog):
    with pytest.raises(PdfReadError) as exc:
        PdfReader(io.BytesIO(b"foo"), strict=True)
    assert exc.value.args[0] == "PDF starts with 'foo', but '%PDF-' expected"
    caplog.clear()
    try:
        PdfReader(io.BytesIO(b"foo"), strict=False)
    except Exception:
        pass
    assert caplog.messages[0].startswith("invalid pdf header")


def test_read_malformed_body():
    with pytest.raises(PdfReadError) as exc:
        PdfReader(io.BytesIO(b"%PDF-"), strict=True)
    assert (
        exc.value.args[0] == "EOF marker not found"
    )  # used to be:STREAM_TRUNCATED_PREMATURELY


def test_read_prev_0_trailer():
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << %s/Root 5 0 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    with_prev_0 = True
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        b"/Prev 0 " if with_prev_0 else b"",
        pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    with pytest.raises(PdfReadError) as exc:
        PdfReader(pdf_stream, strict=True)
    assert exc.value.args[0] == "/Prev=0 in the trailer (try opening with strict=False)"


def test_read_missing_startxref():
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << /Root 5 0 R /Size 6 >>\n"
        # Removed for this test: b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        # Removed for this test: pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    with pytest.raises(PdfReadError) as exc:
        PdfReader(pdf_stream, strict=True)
    assert exc.value.args[0] == "startxref not found"


def test_read_unknown_zero_pages(caplog):
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        # Pages 0 0 is the key point:
        b"5 0 obj << /Pages 0 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << /Root 5 1 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj") - 1,
        pdf_data.find(b"2 0 obj") - 1,
        pdf_data.find(b"3 0 obj") - 1,
        pdf_data.find(b"4 0 obj") - 1,
        pdf_data.find(b"5 0 obj") - 1,
        pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    reader = PdfReader(pdf_stream, strict=True)
    warnings = [
        "startxref on same line as offset",
        "Xref table not zero-indexed. ID numbers for objects will be corrected.",
    ]
    assert normalize_warnings(caplog.text) == warnings
    with pytest.raises(PdfReadError) as exc:
        len(reader.pages)

    assert exc.value.args[0] == "Could not find object."
    reader = PdfReader(pdf_stream, strict=False)
    warnings += [
        "Object 5 1 not defined.",
        "startxref on same line as offset",
    ]
    assert normalize_warnings(caplog.text) == warnings
    with pytest.raises(PdfReadError) as exc:
        len(reader.pages)
    assert exc.value.args[0] == "Invalid object in /Pages"


def test_read_encrypted_without_decryption():
    src = RESOURCE_ROOT / "libreoffice-writer-password.pdf"
    reader = PdfReader(src)
    with pytest.raises(FileNotDecryptedError) as exc:
        len(reader.pages)
    assert exc.value.args[0] == "File has not been decrypted"


def test_get_destination_page_number():
    src = RESOURCE_ROOT / "pdflatex-outline.pdf"
    reader = PdfReader(src)
    outline = reader.outline
    for outline_item in outline:
        if not isinstance(outline_item, list):
            reader.get_destination_page_number(outline_item)


def test_do_not_get_stuck_on_large_files_without_start_xref():
    """
    Tests for the absence of a DoS bug, where a large file without an
    startxref mark would cause the library to hang for minutes to hours.
    """
    start_time = time.time()
    broken_stream = BytesIO(b"\0" * 5 * 1000 * 1000)
    with pytest.raises(PdfReadError):
        PdfReader(broken_stream)
    parse_duration = time.time() - start_time
    # parsing is expected take less than a second on a modern cpu, but include
    # a large tolerance to account for busy or slow systems
    assert parse_duration < 60


@pytest.mark.enable_socket
def test_decrypt_when_no_id():
    """
    Decrypt an encrypted file that's missing the 'ID' value in its trailer.

    https://github.com/py-pdf/pypdf/issues/608
    """
    with open(RESOURCE_ROOT / "encrypted_doc_no_id.pdf", "rb") as inputfile:
        ipdf = PdfReader(inputfile)
        ipdf.decrypt("")
        assert ipdf.metadata == {"/Producer": "European Patent Office"}


def test_reader_properties():
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    assert reader.outline == []
    assert len(reader.pages) == 1
    assert reader.page_layout is None
    assert reader.page_mode is None
    assert reader.is_encrypted is False


@pytest.mark.parametrize(
    "strict",
    [True, False],
)
def test_issue604(caplog, strict):
    """Test with invalid destinations."""  # TODO
    with open(RESOURCE_ROOT / "issue-604.pdf", "rb") as f:
        pdf = None
        outline = None
        if strict:
            pdf = PdfReader(f, strict=strict)
            with pytest.raises(PdfReadError) as exc:
                outline = pdf.outline
            if "Unknown Destination" not in exc.value.args[0]:
                raise Exception("Expected exception not raised")
            return  # outline is not correct
        else:
            pdf = PdfReader(f, strict=strict)
            outline = pdf.outline
            msg = [
                "Unknown destination: ms_Thyroid_2_2020_071520_watermarked.pdf [0, 1]"
            ]
            assert normalize_warnings(caplog.text) == msg

        def get_dest_pages(x) -> NestedList:
            if isinstance(x, list):
                return [get_dest_pages(y) for y in x]
            else:
                destination_page_number = pdf.get_destination_page_number(x)
                if destination_page_number is None:
                    return destination_page_number
                return destination_page_number + 1

        out = []

        # oi can be destination or a list:preferred to just print them
        for oi in outline:
            out.append(get_dest_pages(oi))  # noqa: PERF401


def test_decode_permissions():
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    base = {
        "accessability": False,  # Do not fix typo, as part of official, but deprecated API.
        "annotations": False,
        "assemble": False,
        "copy": False,
        "forms": False,
        "modify": False,
        "print_high_quality": False,
        "print": False,
    }

    print_ = base.copy()
    print_["print"] = True
    with pytest.raises(
        DeprecationWarning,
        match="decode_permissions is deprecated and will be removed in pypdf 5.0.0. Use user_access_permissions instead",  # noqa: E501
    ):
        assert reader.decode_permissions(4) == print_

    modify = base.copy()
    modify["modify"] = True
    with pytest.raises(
        DeprecationWarning,
        match="decode_permissions is deprecated and will be removed in pypdf 5.0.0. Use user_access_permissions instead",  # noqa: E501
    ):
        assert reader.decode_permissions(8) == modify


@pytest.mark.skipif(not HAS_AES, reason="No AES implementation")
def test_user_access_permissions():
    # Not encrypted.
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    assert reader.user_access_permissions is None

    # Encrypted.
    reader = PdfReader(RESOURCE_ROOT / "encryption" / "r6-owner-password.pdf")
    assert reader.user_access_permissions == UAP.all()

    # Custom writer permissions.
    writer = PdfWriter(clone_from=RESOURCE_ROOT / "crazyones.pdf")
    writer.encrypt(
        user_password="",
        owner_password="abc",
        permissions_flag=UAP.minimal() | UAP.PRINT | UAP.FILL_FORM_FIELDS,
    )
    output = BytesIO()
    writer.write(output)
    reader = PdfReader(output)
    assert reader.user_access_permissions == (UAP.minimal() | UAP.PRINT | UAP.FILL_FORM_FIELDS)

    # All writer permissions.
    writer = PdfWriter(clone_from=RESOURCE_ROOT / "crazyones.pdf")
    writer.encrypt(
        user_password="",
        owner_password="abc",
        permissions_flag=UAP.all(),
    )
    output = BytesIO()
    writer.write(output)
    reader = PdfReader(output)
    assert reader.user_access_permissions == UAP.all()


def test_pages_attribute():
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)

    # Test if getting as slice throws an error
    assert len(reader.pages[:]) == 1

    with pytest.raises(IndexError) as exc:
        reader.pages[-1000]

    assert exc.value.args[0] == "Sequence index out of range"

    with pytest.raises(IndexError):
        reader.pages[1000]

    assert exc.value.args[0] == "Sequence index out of range"


def test_convert_to_int():
    assert convert_to_int(b"\x01", 8) == 1


def test_convert_to_int_error():
    with pytest.raises(PdfReadError) as exc:
        convert_to_int(b"256", 16)
    assert exc.value.args[0] == "Invalid size in convert_to_int"


@pytest.mark.enable_socket
def test_iss925():
    url = "https://github.com/py-pdf/pypdf/files/8796328/1.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name="iss925.pdf")))

    for page_sliced in reader.pages:
        page_object = page_sliced.get_object()
        # Extracts the PDF's Annots (Annotations and Commenting):
        annots = page_object.get("/Annots")
        if annots is not None:
            for annot in annots:
                annot.get_object()


def test_get_object():
    reader = PdfReader(RESOURCE_ROOT / "hello-world.pdf")
    assert reader.get_object(22)["/Type"] == "/Catalog"
    assert reader._get_indirect_object(22, 0)["/Type"] == "/Catalog"


def test_extract_text_hello_world():
    reader = PdfReader(RESOURCE_ROOT / "hello-world.pdf")
    text = reader.pages[0].extract_text().split("\n")
    assert text == [
        "English:",
        "Hello World",
        "Arabic:",
        "مرحبا بالعالم",
        "Russian:",
        "Привет, мир",
        "Chinese (traditional):",
        "你好世界",
        "Thai:",
        "สวัสดีชาวโลก",
        "Japanese:",
        "こんにちは世界",
    ]


def test_read_path():
    path = Path(RESOURCE_ROOT, "crazyones.pdf")
    reader = PdfReader(path)
    assert len(reader.pages) == 1


def test_read_not_binary_mode(caplog):
    with open(RESOURCE_ROOT / "crazyones.pdf") as f:
        msg = (
            "PdfReader stream/file object is not in binary mode. "
            "It may not be read correctly."
        )
        with pytest.raises(io.UnsupportedOperation):
            PdfReader(f)
    assert normalize_warnings(caplog.text) == [msg]


@pytest.mark.enable_socket
@pytest.mark.skipif(not HAS_AES, reason="No AES algorithm available")
def test_read_form_416():
    url = (
        "https://www.fda.gov/downloads/AboutFDA/ReportsManualsForms/Forms/UCM074728.pdf"
    )
    reader = PdfReader(BytesIO(get_data_from_url(url, name="issue_416.pdf")))
    fields = reader.get_form_text_fields()
    assert len(fields) > 0


def test_form_topname_with_and_without_acroform(caplog):
    r = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    r.add_form_topname("no")
    r.rename_form_topname("renamed")
    assert "/AcroForm" not in r.trailer["/Root"]
    r.trailer["/Root"][NameObject("/AcroForm")] = DictionaryObject()
    r.add_form_topname("toto")
    r.rename_form_topname("renamed")
    assert len(r.get_fields()) == 0

    r = PdfReader(RESOURCE_ROOT / "form.pdf")
    r.add_form_topname("top")
    flds = r.get_fields()
    assert "top" in flds
    assert "top.foo" in flds
    r.rename_form_topname("renamed")
    flds = r.get_fields()
    assert "renamed" in flds
    assert "renamed.foo" in flds

    r = PdfReader(RESOURCE_ROOT / "form.pdf")
    r.get_fields()["foo"].indirect_reference.get_object()[
        NameObject("/Parent")
    ] = DictionaryObject()
    r.add_form_topname("top")
    assert "have a non-expected parent" in caplog.text


@pytest.mark.enable_socket
def test_extract_text_xref_issue_2(caplog):
    # pdf/0264cf510015b2a4b395a15cb23c001e.pdf
    url = "https://github.com/user-attachments/files/18381758/tika-981961.pdf"
    msg = [
        "incorrect startxref pointer(2)",
        "parsing for Object Streams",
    ]
    reader = PdfReader(BytesIO(get_data_from_url(url, name="tika-981961.pdf")))
    for page in reader.pages:
        page.extract_text()
    assert normalize_warnings(caplog.text) == msg


@pytest.mark.enable_socket
@pytest.mark.slow
def test_extract_text_xref_issue_3(caplog):
    # pdf/0264cf510015b2a4b395a15cb23c001e.pdf
    url = "https://github.com/user-attachments/files/18381755/tika-977774.pdf"
    msg = [
        "incorrect startxref pointer(3)",
    ]
    reader = PdfReader(BytesIO(get_data_from_url(url, name="tika-977774.pdf")))
    for page in reader.pages:
        page.extract_text()
    assert normalize_warnings(caplog.text) == msg


@pytest.mark.enable_socket
def test_extract_text_pdf15():
    # pdf/0264cf510015b2a4b395a15cb23c001e.pdf
    url = "https://github.com/user-attachments/files/18381751/tika-976030.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name="tika-976030.pdf")))
    for page in reader.pages:
        page.extract_text()


@pytest.mark.enable_socket
def test_extract_text_xref_table_21_bytes_clrf():
    # pdf/0264cf510015b2a4b395a15cb23c001e.pdf
    url = "https://github.com/user-attachments/files/18381723/tika-956939.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name="tika-956939.pdf")))
    for page in reader.pages:
        page.extract_text()


@pytest.mark.enable_socket
def test_get_fields():
    url = "https://github.com/user-attachments/files/18381747/tika-972486.pdf"
    name = "tika-972486.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    fields = reader.get_fields()
    assert fields is not None
    assert "c1-1" in fields
    assert dict(fields["c1-1"]) == (
        {"/FT": "/Btn", "/T": "c1-1", "/_States_": ["/On", "/Off"]}
    )


@pytest.mark.enable_socket
def test_get_full_qualified_fields():
    url = "https://github.com/py-pdf/pypdf/files/10142389/fields_with_dots.pdf"
    name = "fields_with_dots.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    fields = reader.get_form_text_fields(True)
    assert fields is not None
    assert "customer.name" in fields

    fields = reader.get_form_text_fields(False)
    assert fields is not None
    assert "customer.name" not in fields
    assert "name" in fields

    fields = reader.get_fields(True)
    assert fields is not None
    assert "customer.name" in fields
    assert fields["customer.name"]["/T"] == "name"


@pytest.mark.enable_socket
@pytest.mark.filterwarnings("ignore::pypdf.errors.PdfReadWarning")
def test_get_fields_read_else_block():
    # covers also issue 1089
    url = "https://github.com/user-attachments/files/18381705/tika-934771.pdf"
    name = "tika-934771.pdf"
    PdfReader(BytesIO(get_data_from_url(url, name=name)))


@pytest.mark.enable_socket
def test_get_fields_read_else_block2():
    url = "https://github.com/user-attachments/files/18381689/tika-914902.pdf"
    name = "tika-914902.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    fields = reader.get_fields()
    assert fields is None


@pytest.mark.enable_socket
@pytest.mark.filterwarnings("ignore::pypdf.errors.PdfReadWarning")
def test_get_fields_read_else_block3():
    url = "https://github.com/user-attachments/files/18381726/tika-957721.pdf"
    name = "tika-957721.pdf"
    PdfReader(BytesIO(get_data_from_url(url, name=name)))


@pytest.mark.enable_socket
def test_metadata_is_none():
    url = "https://github.com/user-attachments/files/18381735/tika-963692.pdf"
    name = "tika-963692.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert reader.metadata is None


@pytest.mark.enable_socket
def test_get_fields_read_write_report(txt_file_path):
    url = "https://github.com/user-attachments/files/18381683/tika-909655.pdf"
    name = "tika-909655.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    with open(txt_file_path, "w") as fp:
        fields = reader.get_fields(fileobj=fp)
    assert fields


@pytest.mark.parametrize(
    "src",
    [
        RESOURCE_ROOT / "crazyones.pdf",
        RESOURCE_ROOT / "commented.pdf",
    ],
)
def test_xfa(src):
    reader = PdfReader(src)
    assert reader.xfa is None


@pytest.mark.enable_socket
def test_xfa_non_empty():
    url = "https://github.com/user-attachments/files/18381713/tika-942050.pdf"
    name = "tika-942050.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert list(reader.xfa.keys()) == [
        "preamble",
        "config",
        "template",
        "PDFSecurity",
        "datasets",
        "postamble",
    ]


@pytest.mark.parametrize(
    ("src", "pdf_header"),
    [
        (RESOURCE_ROOT / "attachment.pdf", "%PDF-1.5"),
        (RESOURCE_ROOT / "crazyones.pdf", "%PDF-1.5"),
    ],
)
def test_header(src, pdf_header):
    reader = PdfReader(src)

    assert reader.pdf_header == pdf_header


@pytest.mark.enable_socket
def test_outline_color():
    reader = PdfReader(BytesIO(get_data_from_url(name="tika-924546.pdf")))
    assert reader.outline[0].color == [0, 0, 1]


@pytest.mark.enable_socket
def test_outline_font_format():
    reader = PdfReader(BytesIO(get_data_from_url(name="tika-924546.pdf")))
    assert reader.outline[0].font_format == 2


def get_outline_property(outline, attribute_name: str):
    results = []
    if isinstance(outline, list):
        for outline_item in outline:
            if isinstance(outline_item, Destination):
                results.append(getattr(outline_item, attribute_name))
            else:
                results.append(get_outline_property(outline_item, attribute_name))
    else:
        raise ValueError(f"got {type(outline)}")
    return results


@pytest.mark.samples
def test_outline_title_issue_1121():
    reader = PdfReader(SAMPLE_ROOT / "014-outlines/mistitled_outlines_example.pdf")

    assert get_outline_property(reader.outline, "title") == [
        "First",
        [
            "Second",
            "Third",
            "Fourth",
            [
                "Fifth",
                "Sixth",
            ],
            "Seventh",
            [
                "Eighth",
                "Ninth",
            ],
        ],
        "Tenth",
        [
            "Eleventh",
            "Twelfth",
            "Thirteenth",
            "Fourteenth",
        ],
        "Fifteenth",
        [
            "Sixteenth",
            "Seventeenth",
        ],
        "Eighteenth",
        "Nineteenth",
        [
            "Twentieth",
            "Twenty-first",
            "Twenty-second",
            "Twenty-third",
            "Twenty-fourth",
            "Twenty-fifth",
            "Twenty-sixth",
            "Twenty-seventh",
        ],
    ]


@pytest.mark.samples
def test_outline_count():
    reader = PdfReader(SAMPLE_ROOT / "014-outlines/mistitled_outlines_example.pdf")

    assert get_outline_property(reader.outline, "outline_count") == [
        5,
        [
            None,
            None,
            2,
            [
                None,
                None,
            ],
            -2,
            [
                None,
                None,
            ],
        ],
        4,
        [
            None,
            None,
            None,
            None,
        ],
        -2,
        [
            None,
            None,
        ],
        None,
        8,
        [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ],
    ]


def test_outline_missing_title(caplog):
    # Strict
    reader = PdfReader(RESOURCE_ROOT / "outline-without-title.pdf", strict=True)
    with pytest.raises(PdfReadError) as exc:
        reader.outline
    assert exc.value.args[0].startswith("Outline Entry Missing /Title attribute:")

    # Non-strict : no errors
    reader = PdfReader(RESOURCE_ROOT / "outline-without-title.pdf", strict=False)
    assert reader.outline[0]["/Title"] == ""


@pytest.mark.enable_socket
@pytest.mark.parametrize(
    ("url", "name"),
    [
        # 1st case : the named_dest are stored directly as a dictionary, PDF 1.1 style
        (
            "https://github.com/py-pdf/pypdf/files/9197028/lorem_ipsum.pdf",
            "lorem_ipsum.pdf",
        ),
        # 2nd case : Dest below names and with Kids...
        (
            "https://github.com/py-pdf/pypdf/files/11714214/PDF32000_2008.pdf",
            "PDF32000_2008.pdf",
        )
        # 3rd case : Dests with Name tree (TODO: Add this case)
    ],
    ids=["stored_directly", "dest_below_names_with_kids"],
)
def test_named_destination(url, name):
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert len(reader.named_destinations) > 0


@pytest.mark.enable_socket
def test_outline_with_missing_named_destination():
    url = "https://github.com/user-attachments/files/18381686/tika-913678.pdf"
    name = "tika-913678.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    # outline items in document reference a named destination that is not defined
    assert reader.outline[1][0].title.startswith("Report for 2002AZ3B: Microbial")


@pytest.mark.enable_socket
def test_outline_with_empty_action():
    url = "https://github.com/user-attachments/files/18381697/tika-924546.pdf"
    name = "tika-924546.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    # outline items (entitled Tables and Figures) utilize an empty action (/A)
    # that has no type or destination
    assert reader.outline[-4].title == "Tables"


def test_outline_with_invalid_destinations():
    reader = PdfReader(RESOURCE_ROOT / "outlines-with-invalid-destinations.pdf")
    # contains 9 outline items, 6 with invalid destinations
    # caused by different malformations
    assert len(reader.outline) == 9


@pytest.mark.enable_socket
def test_pdfreader_multiple_definitions(caplog):
    """iss325"""
    url = "https://github.com/py-pdf/pypdf/files/9176644/multipledefs.pdf"
    name = "multipledefs.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.pages[0].extract_text()
    assert normalize_warnings(caplog.text) == [
        "Multiple definitions in dictionary at byte 0xb5 for key /Group"
    ]


def test_wrong_password_error():
    encrypted_pdf_path = RESOURCE_ROOT / "encrypted-file.pdf"
    with pytest.raises(WrongPasswordError):
        PdfReader(
            encrypted_pdf_path,
            password="definitely_the_wrong_password!",
        )


def test_get_page_number_by_indirect():
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    reader._get_page_number_by_indirect(1)


@pytest.mark.enable_socket
def test_corrupted_xref_table():
    # issue #1292
    url = "https://github.com/py-pdf/pypdf/files/9444747/BreezeManual.orig.pdf"
    name = "BreezeMan1.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.pages[0].extract_text()
    url = "https://github.com/py-pdf/pypdf/files/9444748/BreezeManual.failed.pdf"
    name = "BreezeMan2.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.pages[0].extract_text()


@pytest.mark.enable_socket
def test_reader(caplog):
    # iss #1273
    url = "https://github.com/py-pdf/pypdf/files/9464742/shiv_resume.pdf"
    name = "shiv_resume.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert "Previous trailer cannot be read" in caplog.text
    caplog.clear()
    # first call requires some reparations...
    reader.pages[0].extract_text()
    caplog.clear()
    # ...and now no more required
    reader.pages[0].extract_text()
    assert caplog.text == ""


@pytest.mark.enable_socket
def test_zeroing_xref():
    # iss #328
    url = (
        "https://github.com/py-pdf/pypdf/files/9066120/"
        "UTA_OSHA_3115_Fall_Protection_Training_09162021_.pdf"
    )
    name = "UTA_OSHA.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    len(reader.pages)


@pytest.mark.enable_socket
def test_thread():
    url = (
        "https://github.com/py-pdf/pypdf/files/9066120/"
        "UTA_OSHA_3115_Fall_Protection_Training_09162021_.pdf"
    )
    name = "UTA_OSHA.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert reader.threads is None
    url = "https://github.com/user-attachments/files/18381699/tika-924666.pdf"
    name = "tika-924666.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert isinstance(reader.threads, ArrayObject)
    assert len(reader.threads) >= 1


@pytest.mark.enable_socket
def test_build_outline_item(caplog):
    url = "https://github.com/py-pdf/pypdf/files/9464742/shiv_resume.pdf"
    name = "shiv_resume.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    outline = reader._build_outline_item(
        DictionaryObject(
            {
                NameObject("/Title"): TextStringObject("Toto"),
                NameObject("/Dest"): NumberObject(2),
            }
        )
    )
    assert "Removed unexpected destination 2 from destination" in caplog.text
    assert outline["/Title"] == "Toto"
    reader.strict = True
    with pytest.raises(PdfReadError) as exc:
        reader._build_outline_item(
            DictionaryObject(
                {
                    NameObject("/Title"): TextStringObject("Toto"),
                    NameObject("/Dest"): NumberObject(2),
                }
            )
        )
    assert "Unexpected destination 2" in exc.value.args[0]


@pytest.mark.samples
@pytest.mark.parametrize(
    ("src", "page_labels"),
    [
        (RESOURCE_ROOT / "selenium-pypdf-issue-177.pdf", ["1"]),
        (RESOURCE_ROOT / "encrypted_doc_no_id.pdf", ["1", "2", "3"]),
        (RESOURCE_ROOT / "pdflatex-outline.pdf", ["1", "2", "3", "4"]),
        (
            SAMPLE_ROOT / "009-pdflatex-geotopo/GeoTopo.pdf",
            ["i", "ii", "iii", "1", "2", "3"],
        ),
    ],
    ids=[
        "selenium-pypdf-issue-177.pdf",
        "encrypted_doc_no_id.pdf",
        "pdflatex-outline.pdf",
        "GeoTopo.pdf",
    ],
)
def test_page_labels(src, page_labels):
    max_indices = 6
    assert PdfReader(src).page_labels[:max_indices] == page_labels[:max_indices]


@pytest.mark.enable_socket
def test_iss1559():
    url = "https://github.com/py-pdf/pypdf/files/10441992/default.pdf"
    name = "iss1559.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    for p in reader.pages:
        p.extract_text()


@pytest.mark.enable_socket
def test_iss1652():
    # test of an annotation(link) directly stored in the /Annots in the page
    url = "https://github.com/py-pdf/pypdf/files/10818844/tt.pdf"
    name = "invalidNamesDest.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.named_destinations


@pytest.mark.enable_socket
def test_iss1689():
    url = "https://github.com/py-pdf/pypdf/files/10948283/error_file_without_data.pdf"
    name = "iss1689.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.pages[0]


@pytest.mark.enable_socket
def test_iss1710():
    url = "https://github.com/py-pdf/pypdf/files/15234776/irbookonlinereading.pdf"
    name = "irbookonlinereading.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.outline


def test_broken_file_header():
    pdf_data = (
        b"%%PDF-\xa0sd\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << %s/Root 5 0 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    with_prev_0 = True
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        b"/Prev 0 " if with_prev_0 else b"",
        pdf_data.find(b"xref") - 1,
    )
    PdfReader(io.BytesIO(pdf_data))


@pytest.mark.enable_socket
def test_iss1756():
    url = "https://github.com/py-pdf/pypdf/files/11105591/641-Attachment-B-Pediatric-Cardiac-Arrest-8-1-2019.pdf"
    name = "iss1756.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.trailer["/ID"]
    # removed to cope with missing cryptodome during commit check : len(reader.pages)


@pytest.mark.enable_socket
@pytest.mark.timeout(30)
def test_iss1825():
    url = "https://github.com/py-pdf/pypdf/files/11367871/MiFO_LFO_FEIS_NOA_Published.3.pdf"
    name = "iss1825.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    page = reader.pages[0]
    page.extract_text()


@pytest.mark.enable_socket
def test_iss2082():
    url = "https://github.com/py-pdf/pypdf/files/12317939/test.pdf"
    name = "iss2082.pdf"
    b = get_data_from_url(url, name=name)
    reader = PdfReader(BytesIO(b))
    reader.pages[0].extract_text()

    bb = bytearray(b)
    bb[b.find(b"xref") + 2] = ord(b"E")
    with pytest.raises(PdfReadError):
        reader = PdfReader(BytesIO(bb))


@pytest.mark.enable_socket
def test_issue_140():
    url = "https://github.com/py-pdf/pypdf/files/12168578/bad_pdf_example.pdf"
    name = "issue-140.pdf"
    b = get_data_from_url(url, name=name)
    reader = PdfReader(BytesIO(b))
    assert len(reader.pages) == 54


@pytest.mark.enable_socket
def test_xyz_with_missing_param():
    """Cf #2236"""
    url = "https://github.com/py-pdf/pypdf/files/12795356/tt1.pdf"
    name = "issue2236.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert reader.outline[0]["/Left"] == 820
    assert reader.outline[0]["/Top"] == 0
    assert reader.outline[1]["/Left"] == 0
    assert reader.outline[0]["/Top"] == 0


@pytest.mark.enable_socket
def test_corrupted_xref():
    url = "https://github.com/py-pdf/pypdf/files/14628314/iss2516.pdf"
    name = "iss2516.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert reader.root_object["/Type"] == "/Catalog"


@pytest.mark.enable_socket
def test_truncated_xref(caplog):
    url = "https://github.com/py-pdf/pypdf/files/14843553/002-trivial-libre-office-writer-broken.pdf"
    name = "iss2575.pdf"
    PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert "Invalid/Truncated xref table. Rebuilding it." in caplog.text


@pytest.mark.enable_socket
def test_damaged_pdf():
    url = "https://github.com/py-pdf/pypdf/files/15186107/malformed_pdf.pdf"
    name = "malformed_pdf.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)), strict=False)
    len(reader.pages)
    strict_reader = PdfReader(BytesIO(get_data_from_url(url, name=name)), strict=True)
    with pytest.raises(PdfReadError) as exc:
        len(strict_reader.pages)
    assert (
        exc.value.args[0] == "Expected object ID (21 0) does not match actual (-1 -1)."
    )


@pytest.mark.enable_socket
@pytest.mark.timeout(10)
def test_looping_form(caplog):
    """Cf iss 2643"""
    url = "https://github.com/py-pdf/pypdf/files/15306053/inheritance.pdf"
    name = "iss2643.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)), strict=False)
    flds = reader.get_fields()
    assert all(
        x in flds
        for x in (
            "Text10",
            "Text10.0.0.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1",
            "amt1.0",
            "amt1.1",
            "DSS#3pg3#0hgu7",
        )
    )
    writer = PdfWriter(reader)
    writer.root_object["/AcroForm"]["/Fields"][5]["/Kids"].append(
        writer.root_object["/AcroForm"]["/Fields"][5]["/Kids"][0]
    )
    flds2 = writer.get_fields()
    assert "Text68.0 already parsed" in caplog.text
    assert list(flds.keys()) == list(flds2.keys())


def test_context_manager_with_stream():
    pdf_data = (
        b"%%PDF-1.7\n"
        b"1 0 obj << /Count 1 /Kids [4 0 R] /Type /Pages >> endobj\n"
        b"2 0 obj << >> endobj\n"
        b"3 0 obj << >> endobj\n"
        b"4 0 obj << /Contents 3 0 R /CropBox [0.0 0.0 2550.0 3508.0]"
        b" /MediaBox [0.0 0.0 2550.0 3508.0] /Parent 1 0 R"
        b" /Resources << /Font << >> >>"
        b" /Rotate 0 /Type /Page >> endobj\n"
        b"5 0 obj << /Pages 1 0 R /Type /Catalog >> endobj\n"
        b"xref 1 5\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"%010d 00000 n\n"
        b"trailer << /Root 5 0 R /Size 6 >>\n"
        b"startxref %d\n"
        b"%%%%EOF"
    )
    pdf_data = pdf_data % (
        pdf_data.find(b"1 0 obj"),
        pdf_data.find(b"2 0 obj"),
        pdf_data.find(b"3 0 obj"),
        pdf_data.find(b"4 0 obj"),
        pdf_data.find(b"5 0 obj"),
        pdf_data.find(b"xref") - 1,
    )
    pdf_stream = io.BytesIO(pdf_data)
    with PdfReader(pdf_stream) as reader:
        assert not reader.stream.closed
    assert not pdf_stream.closed


@pytest.mark.enable_socket
@pytest.mark.timeout(10)
def test_iss2761():
    url = "https://github.com/user-attachments/files/16312198/crash-b26d05712a29b241ac6f9dc7fff57428ba2d1a04.pdf"
    name = "iss2761.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)), strict=False)
    with pytest.raises(PdfReadError):
        reader.pages[0].extract_text()


@pytest.mark.enable_socket
def test_iss2817():
    """Test for rebuiling Xref_ObjStm"""
    url = "https://github.com/user-attachments/files/16764070/crash-7e1356f1179b4198337f282304cb611aea26a199.pdf"
    name = "iss2817.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert (
        reader.pages[0]["/Annots"][0].get_object()["/Contents"]
        == "A\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0 B"
    )


@pytest.mark.enable_socket
def test_truncated_files(caplog):
    """Cf #2853"""
    url = "https://github.com/user-attachments/files/16796095/f5471sm-2.pdf"
    name = "iss2780.pdf"  # reused
    b = get_data_from_url(url, name=name)
    reader = PdfReader(BytesIO(b))
    assert caplog.text == ""
    # remove \n at end of file : invisible
    reader = PdfReader(BytesIO(b[:-1]))
    assert caplog.text == ""
    # truncate but still detectable
    for i in range(-2, -6, -1):
        caplog.clear()
        reader = PdfReader(BytesIO(b[:i]))
        assert "EOF marker seems truncated" in caplog.text
        assert reader._startxref == 100993
    # remove completely EOF : we will not read last section
    caplog.clear()
    reader = PdfReader(BytesIO(b[:-6]))
    assert "CAUTION: startxref found while searching for %%EOF" in caplog.text
    assert reader._startxref < 100993


@pytest.mark.enable_socket
def test_comments_in_array(caplog):
    """Cf #2843: this deals with comments"""
    url = "https://github.com/user-attachments/files/16992416/crash-2347912aa2a6f0fab5df4ebc8a424735d5d0d128.pdf"
    name = "iss2843.pdf"  # reused
    b = get_data_from_url(url, name=name)
    reader = PdfReader(BytesIO(b))
    reader.pages[0]
    assert caplog.text == ""
    reader = PdfReader(BytesIO(b))
    reader.stream = BytesIO(b[:1149])
    with pytest.raises(PdfStreamError):
        reader.pages[0]


@pytest.mark.enable_socket
def test_space_in_names_to_continue_processing(caplog):
    """
    This deals with space not encoded in names inducing errors.
    Also covers case where NameObject not met for key.
    """
    url = "https://github.com/user-attachments/files/17095516/crash-e108c4f677040b61e12fa9f1cfde025d704c9b0d.pdf"
    name = "iss2866.pdf"  # reused
    b = get_data_from_url(url, name=name)
    reader = PdfReader(BytesIO(b))
    obj = reader.get_object(70)
    assert all(
        x in obj
        for x in (
            "/BaseFont",
            "/DescendantFonts",
            "/Encoding",
            "/Subtype",
            "/ToUnicode",
            "/Type",
        )
    )
    assert obj["/BaseFont"] == "/AASGAA+Arial,Unicode"  # MS is missing to meet spec
    assert 'PdfReadError("Invalid Elementary Object starting with' in caplog.text

    caplog.clear()

    b = b[:264] + b"(Inv) /d " + b[273:]
    reader = PdfReader(BytesIO(b))
    obj = reader.get_object(70)
    assert all(
        x in obj
        for x in ["/DescendantFonts", "/Encoding", "/Subtype", "/ToUnicode", "/Type"]
    )
    assert all(
        x in caplog.text
        for x in (
            "Expecting a NameObject for key but",
            'PdfReadError("Invalid Elementary Object starting with',
        )
    )
    reader = PdfReader(BytesIO(b), strict=True)
    with pytest.raises(PdfReadError):
        obj = reader.get_object(70)


@pytest.mark.enable_socket
def test_unbalanced_brackets_in_dictionary_object(caplog):
    """Cf #2877"""
    url = "https://github.com/user-attachments/files/17162634/7f40cb209fb97d1782bffcefc5e7be40.pdf"
    name = "iss2877.pdf"  # reused
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert len(reader.pages) == 43  # note:  /Count = 46 but 3 kids are None


@pytest.mark.enable_socket
def test_repair_root(caplog):
    """Cf #2877"""
    url = "https://github.com/user-attachments/files/17162216/crash-6620e8b1abfe3da639b654595da859b87f985748.pdf"
    name = "iss2875.pdf"

    b = get_data_from_url(url, name=name)
    reader = PdfReader(BytesIO(b))
    assert len(reader.pages) == 1
    assert all(
        msg in caplog.text
        for msg in (
            "Invalid Root object",
            'Searching object with "/Catalog" key',
            "Root found at IndirectObject(2, 0,",
        )
    )

    # no /Root Entry
    reader = PdfReader(BytesIO(b.replace(b"/Root", b"/Roo ")))
    caplog.clear()
    assert len(reader.pages) == 1
    assert all(
        msg in caplog.text
        for msg in (
            'Cannot find "/Root" key in trailer',
            'Searching object with "/Catalog" key',
            "Root found at IndirectObject(2, 0,",
        )
    )

    # Invalid /Root Entry
    caplog.clear()
    reader = PdfReader(
        BytesIO(
            b.replace(b"/Root 1 0 R", b"/Root 2 0 R").replace(b"/Catalog", b"/Catalo ")
        )
    )
    with pytest.raises(PdfReadError):
        len(reader.pages)
    assert all(
        msg in caplog.text
        for msg in (
            "Invalid Root object in trailer",
            'Searching object with "/Catalog" key',
        )
    )

    # Invalid /Root Entry + error in get_object
    caplog.clear()
    b = b.replace(b"/Root 1 0 R", b"/Root 2 0 R").replace(b"/Catalog", b"/Catalo ")
    b = b[:5124] + b"A" + b[5125:]
    reader = PdfReader(BytesIO(b))
    with pytest.raises(PdfReadError):
        len(reader.pages)
    assert all(
        msg in caplog.text
        for msg in (
            "Invalid Root object in trailer",
            'Searching object with "/Catalog" key',
        )
    )
