"""Test the pypdf.generic module."""

import codecs
from base64 import a85encode
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest

from pypdf import PdfReader, PdfWriter
from pypdf.constants import CheckboxRadioButtonAttributes
from pypdf.errors import PdfReadError, PdfStreamError
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    ByteStringObject,
    ContentStream,
    DecodedStreamObject,
    Destination,
    DictionaryObject,
    Fit,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    OutlineItem,
    PdfObject,
    RectangleObject,
    StreamObject,
    TextStringObject,
    TreeObject,
    create_string_object,
    encode_pdfdocencoding,
    is_null_or_none,
    read_hex_string_from_stream,
    read_object,
    read_string_from_stream,
)
from pypdf.generic._image_inline import (
    extract_inline_A85,
    extract_inline_AHx,
    extract_inline_DCT,
    extract_inline_RL,
)

from . import ReaderDummy, get_data_from_url

TESTS_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
RESOURCE_ROOT = PROJECT_ROOT / "resources"


class ChildDummy(DictionaryObject):
    @property
    def indirect_reference(self):
        return self


def test_float_object_exception(caplog):
    assert FloatObject("abc") == 0
    assert caplog.text != ""


def test_number_object_exception(caplog):
    assert NumberObject("0,0") == 0
    assert caplog.text != ""


def test_number_object_no_exception():
    NumberObject(2**100_000_000)


def test_create_string_object_exception():
    with pytest.raises(TypeError) as exc:
        create_string_object(123)
    assert (  # typeguard is not running
        exc.value.args[0] == "create_string_object should have str or unicode arg"
    ) or (  # typeguard is enabled
        'type of argument "string" must be one of (str, bytes); got int instead'
        in exc.value.args[0]
    )


@pytest.mark.parametrize(
    ("value", "expected", "tell"), [(b"true", b"true", 4), (b"false", b"false", 5)]
)
def test_boolean_object(value, expected, tell):
    stream = BytesIO(value)
    assert BooleanObject.read_from_stream(stream).value == (expected == b"true")
    stream.seek(0, 0)
    assert stream.read() == expected
    assert stream.tell() == tell


def test_boolean_object_write():
    stream = BytesIO()
    boolobj = BooleanObject(None)
    boolobj.write_to_stream(stream)
    stream.seek(0, 0)
    assert stream.read() == b"false"


def test_boolean_eq():
    boolobj = BooleanObject(True)
    assert (boolobj == True) is True  # noqa: E712
    assert (boolobj == False) is False  # noqa: E712
    assert (boolobj == "True") is False

    boolobj = BooleanObject(False)
    assert (boolobj == True) is False  # noqa: E712
    assert (boolobj == False) is True  # noqa: E712
    assert (boolobj == "True") is False


def test_boolean_object_exception():
    stream = BytesIO(b"False")
    with pytest.raises(PdfReadError) as exc:
        BooleanObject.read_from_stream(stream)
    assert exc.value.args[0] == "Could not read Boolean object"


def test_array_object_exception():
    stream = BytesIO(b"False")
    with pytest.raises(PdfReadError) as exc:
        ArrayObject.read_from_stream(stream, None)
    assert exc.value.args[0] == "Could not read array"


def test_null_object_exception():
    stream = BytesIO(b"notnull")
    with pytest.raises(PdfReadError) as exc:
        NullObject.read_from_stream(stream)
    assert exc.value.args[0] == "Could not read Null object"


@pytest.mark.parametrize("value", [b"", b"False", b"foo ", b"foo  ", b"foo bar"])
def test_indirect_object_premature(value):
    stream = BytesIO(value)
    with pytest.raises(PdfStreamError) as exc:
        IndirectObject.read_from_stream(stream, None)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_read_hex_string_from_stream():
    stream = BytesIO(b"a1>")
    assert read_hex_string_from_stream(stream) == "\x10"


def test_read_hex_string_from_stream_exception():
    stream = BytesIO(b"")
    with pytest.raises(PdfStreamError) as exc:
        read_hex_string_from_stream(stream)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_read_string_from_stream_exception():
    stream = BytesIO(b"x")
    with pytest.raises(PdfStreamError) as exc:
        read_string_from_stream(stream)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_read_string_from_stream_not_in_escapedict_no_digit():
    stream = BytesIO(b"x\\y")
    with pytest.raises(PdfReadError) as exc:
        read_string_from_stream(stream)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_read_string_from_stream_multichar_eol():
    stream = BytesIO(b"x\\\n )")
    assert read_string_from_stream(stream) == " "


def test_read_string_from_stream_multichar_eol2():
    stream = BytesIO(b"x\\\n\n)")
    assert read_string_from_stream(stream) == ""


def test_read_string_from_stream_excape_digit():
    stream = BytesIO(b"x\\1a )")
    assert read_string_from_stream(stream) == "\x01a "


def test_read_string_from_stream_excape_digit2():
    stream = BytesIO(b"(hello \\1\\2\\3\\4)")
    assert read_string_from_stream(stream) == "hello \x01\x02\x03\x04"


def test_name_object(caplog):
    stream = BytesIO(b"x")
    with pytest.raises(PdfReadError) as exc:
        NameObject.read_from_stream(stream, None)
    assert exc.value.args[0] == "Name read error"
    assert (
        NameObject.read_from_stream(
            BytesIO(b"/A;Name_With-Various***Characters?"), None
        )
        == "/A;Name_With-Various***Characters?"
    )
    assert (
        NameObject.read_from_stream(BytesIO(b"/paired#28#29parentheses"), None)
        == "/paired()parentheses"
    )
    assert NameObject.read_from_stream(BytesIO(b"/A#42"), None) == "/AB"

    assert (
        NameObject.read_from_stream(
            BytesIO(b"/#f1j#d4#aa#0c#ce#87#b4#b3#b0#23J#86#fe#2a#b2jYJ#94"),
            ReaderDummy(),
        )
        == "/ñjÔª\x0cÎ\x87´³°#J\x86þ*²jYJ\x94"
    )

    assert (NameObject.read_from_stream(BytesIO(b"/#JA#231f"), None)) == "/#JA#1f"

    assert (
        NameObject.read_from_stream(
            BytesIO(b"/#e4#bd#a0#e5#a5#bd#e4#b8#96#e7#95#8c"), None
        )
    ) == "/你好世界"

    # to test PDFDocEncoding (latin-1)
    assert (
        NameObject.read_from_stream(BytesIO(b"/DocuSign\xae"), None)
    ) == "/DocuSign®"

    # test write
    b = BytesIO()
    NameObject("/hello").write_to_stream(b)
    assert bytes(b.getbuffer()) == b"/hello"

    caplog.clear()
    b = BytesIO()
    with pytest.raises(DeprecationWarning):
        NameObject("hello").write_to_stream(b)

    caplog.clear()
    b = BytesIO()
    NameObject("/DIJMAC+Arial Black#1").write_to_stream(b)
    assert bytes(b.getbuffer()) == b"/DIJMAC+Arial#20Black#231"
    assert caplog.text == ""

    b = BytesIO()
    NameObject("/你好世界 (%)").write_to_stream(b)
    assert bytes(b.getbuffer()) == b"/#E4#BD#A0#E5#A5#BD#E4#B8#96#E7#95#8C#20#28#25#29"
    assert caplog.text == ""


def test_destination_fit_r():
    d = Destination(
        TextStringObject("title"), NullObject(), Fit.fit_rectangle(0, 0, 0, 0)
    )
    assert d.title == NameObject("title")
    assert d.typ == "/FitR"
    assert d.zoom is None
    assert d.left == FloatObject(0)
    assert d.right == FloatObject(0)
    assert d.top == FloatObject(0)
    assert d.bottom == FloatObject(0)
    assert list(d) == []
    d.empty_tree()


def test_destination_fit_v():
    d = Destination(NameObject("title"), NullObject(), Fit.fit_vertically(left=0))

    writer = PdfWriter()
    writer.add_named_destination_object(d)

    # Trigger Exception
    Destination(NameObject("title"), NullObject(), Fit.fit_vertically(left=None))


def test_outline_item_write_to_stream():
    stream = BytesIO()
    oi = OutlineItem(NameObject("title"), NullObject(), Fit.fit_vertically(left=0))
    oi.write_to_stream(stream)
    stream.seek(0, 0)
    assert stream.read() == b"<<\n/Title (title)\n/Dest [ null /FitV 0.0 ]\n>>"


def test_encode_pdfdocencoding_keyerror():
    with pytest.raises(UnicodeEncodeError) as exc:
        encode_pdfdocencoding("😀")
    assert exc.value.args[0] == "pdfdocencoding"


@pytest.mark.parametrize("test_input", ["", "data"])
def test_encode_pdfdocencoding_returns_bytes(test_input):
    """
    Test that encode_pdfdocencoding() always returns bytes because bytearray
    is duck type compatible with bytes in mypy
    """
    out = encode_pdfdocencoding(test_input)
    assert isinstance(out, bytes)


def test_read_object_comment_exception():
    stream = BytesIO(b"% foobar")
    pdf = None
    with pytest.raises(PdfStreamError) as exc:
        read_object(stream, pdf)
    assert exc.value.args[0] == "File ended unexpectedly."


def test_read_object_empty():
    stream = BytesIO(b"endobj")
    pdf = None
    assert isinstance(read_object(stream, pdf), NullObject)


def test_read_object_empty_in_array():
    stream = BytesIO(b"[endobj")
    pdf = None
    result = read_object(stream, pdf)
    assert isinstance(result, ArrayObject)
    assert len(result) == 1
    assert isinstance(result[0], NullObject)


def test_read_object_invalid():
    stream = BytesIO(b"hello")
    pdf = None
    with pytest.raises(PdfReadError) as exc:
        read_object(stream, pdf)
    assert "hello" in exc.value.args[0]


def test_read_object_comment():
    stream = BytesIO(b"% foobar\n1 ")
    pdf = None
    out = read_object(stream, pdf)
    assert out == 1


def test_bytestringobject():
    bo = ByteStringObject("stream", encoding="utf-8")
    stream = BytesIO(b"")
    bo.write_to_stream(stream)
    stream.seek(0, 0)
    assert stream.read() == b"<73747265616d>"  # TODO: how can we verify this?


def test_dictionaryobject_key_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do["foo"] = NameObject("/GoTo")
    assert exc.value.args[0] == "Key must be a PdfObject"


def test_dictionaryobject_xmp_meta():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    assert do.xmp_metadata is None


def test_dictionaryobject_value_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do[NameObject("/S")] = "/GoTo"
    assert exc.value.args[0] == "Value must be a PdfObject"


def test_dictionaryobject_setdefault_key_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do.setdefault("foo", NameObject("/GoTo"))
    assert exc.value.args[0] == "Key must be a PdfObject"


def test_dictionaryobject_setdefault_value_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do.setdefault(NameObject("/S"), "/GoTo")
    assert exc.value.args[0] == "Value must be a PdfObject"


def test_dictionaryobject_setdefault_value():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    do.setdefault(NameObject("/S"), NameObject("/GoTo"))


def test_dictionaryobject_read_from_stream():
    stream = BytesIO(b"<< /S /GoTo >>")
    pdf = None
    out = DictionaryObject.read_from_stream(stream, pdf)
    assert out.get_object() == {NameObject("/S"): NameObject("/GoTo")}


def test_dictionaryobject_read_from_stream_broken():
    stream = BytesIO(b"< /S /GoTo >>")
    pdf = None
    with pytest.raises(PdfReadError) as exc:
        DictionaryObject.read_from_stream(stream, pdf)
    assert (
        exc.value.args[0]
        == "Dictionary read error at byte 0x2: stream must begin with '<<'"
    )


def test_dictionaryobject_read_from_stream_unexpected_end():
    stream = BytesIO(b"<< \x00/S /GoTo")
    pdf = None
    with pytest.raises(PdfStreamError) as exc:
        DictionaryObject.read_from_stream(stream, pdf)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_dictionaryobject_read_from_stream_stream_no_newline():
    stream = BytesIO(b"<< /S /GoTo >>stream")
    pdf = None
    with pytest.raises(PdfReadError) as exc:
        DictionaryObject.read_from_stream(stream, pdf)
    assert exc.value.args[0] == "Stream data must be followed by a newline"


@pytest.mark.parametrize(("strict"), [(True), (False)])
def test_dictionaryobject_read_from_stream_stream_no_stream_length(strict, caplog):
    stream = BytesIO(b"<< /S /GoTo >>stream\n123456789endstream abcd")

    class Tst:  # to replace pdf
        strict = False

    pdf = Tst()
    pdf.strict = strict
    if strict:
        with pytest.raises(PdfReadError) as exc:
            DictionaryObject.read_from_stream(stream, pdf)
        assert exc.value.args[0] == "Stream length not defined"
    else:
        o = DictionaryObject.read_from_stream(stream, pdf)
        assert "Stream length not defined" in caplog.text
        assert o.get_data() == b"123456789"


@pytest.mark.parametrize(
    ("strict", "length", "should_fail"),
    [
        (True, 6, False),
        (True, 10, False),
        (True, 4, True),
        (False, 6, False),
        (False, 10, False),
    ],
)
def test_dictionaryobject_read_from_stream_stream_stream_valid(
    strict, length, should_fail
):
    stream = BytesIO(b"<< /S /GoTo /Length %d >>stream\nBT /F1\nendstream\n" % length)

    class Tst:  # to replace pdf
        strict = True

    pdf = Tst()
    pdf.strict = strict
    with pytest.raises(PdfReadError) as exc:
        do = DictionaryObject.read_from_stream(stream, pdf)
        # TODO: What should happen with the stream?
        assert do == {"/S": "/GoTo"}
        if length in (6, 10):
            assert b"BT /F1" in do.get_data()
        raise PdfReadError("__ALLGOOD__")
    assert should_fail ^ (exc.value.args[0] == "__ALLGOOD__")


def test_rectangleobject():
    ro = RectangleObject((1, 2, 3, 4))
    assert ro.lower_left == (1, 2)
    assert ro.lower_right == (3, 2)
    assert ro.upper_left == (1, 4)
    assert ro.upper_right == (3, 4)

    ro.lower_left = (5, 6)
    assert ro.lower_left == (5, 6)

    ro.bottom -= 2
    ro.left -= 2
    assert ro.lower_left == (3, 4)

    ro.lower_right = (7, 8)
    assert ro.lower_right == (7, 8)

    ro.upper_left = (9, 11)
    assert ro.upper_left == (9, 11)

    ro.upper_right = (13, 17)
    assert ro.upper_right == (13, 17)
    ro.top += 1
    ro.right += 1
    assert ro.upper_right == (14, 18)


def test_textstringobject_exc():
    tso = TextStringObject("foo")
    assert tso.get_original_bytes() == b"foo"


def test_textstringobject_autodetect_utf16():
    tso = TextStringObject("foo")
    tso.autodetect_utf16 = True
    tso.utf16_bom = codecs.BOM_UTF16_BE
    assert tso.get_original_bytes() == b"\xfe\xff\x00f\x00o\x00o"
    tso.utf16_bom = codecs.BOM_UTF16_LE
    assert tso.get_original_bytes() == b"\xff\xfef\x00o\x00o\x00"
    assert tso.get_encoded_bytes() == b"\xff\xfef\x00o\x00o\x00"


def test_textstringobject__numbers_as_input():
    _ = TextStringObject(42)
    _ = TextStringObject(13.37)


def test_remove_child_not_in_tree():
    tree = TreeObject()
    with pytest.raises(ValueError) as exc:
        tree.remove_child(ChildDummy())
    assert exc.value.args[0] == "Removed child does not appear to be a tree item"


def test_remove_child_not_in_that_tree():
    tree = TreeObject()
    tree.indirect_reference = NullObject()
    child = TreeObject()
    child.indirect_reference = NullObject()
    with pytest.raises(ValueError) as exc:
        child.remove_from_tree()
    assert exc.value.args[0] == "Removed child does not appear to be a tree item"
    tree.add_child(child, ReaderDummy())
    with pytest.raises(ValueError) as exc:
        tree.remove_child(child)
    assert exc.value.args[0] == "Removed child is not a member of this tree"


def test_remove_child_not_found_in_tree():
    class ChildDummy(DictionaryObject):
        @property
        def indirect_reference(self) -> "ChildDummy":
            return self

    tree = TreeObject()
    tree.indirect_reference = NullObject()
    child = ChildDummy(TreeObject())
    tree.add_child(child, ReaderDummy())
    child2 = ChildDummy(TreeObject())
    child2[NameObject("/Parent")] = tree
    with pytest.raises(ValueError) as exc:
        tree.remove_child(child2)
    assert exc.value.args[0] == "Removal couldn't find item in tree"


def test_remove_child_found_in_tree():
    writer = PdfWriter()

    # Add Tree
    tree = TreeObject()
    writer._add_object(tree)

    # Add first child
    # It's important to set a value, otherwise the writer.get_reference will
    # return the same object when a second child is added.
    child1 = TreeObject()
    child1[NameObject("/Foo")] = TextStringObject("bar")
    child1_ref = writer._add_object(child1)
    tree.add_child(child1_ref, writer)
    assert tree[NameObject("/Count")] == 1
    assert len(list(tree.children())) == 1

    # Add second child
    child2 = TreeObject()
    child2[NameObject("/Foo")] = TextStringObject("baz")
    child2_ref = writer._add_object(child2)
    tree.add_child(child2_ref, writer)
    assert tree[NameObject("/Count")] == 2
    assert len(list(tree.children())) == 2

    # Remove last child
    tree.remove_child(child2_ref)
    assert tree[NameObject("/Count")] == 1
    assert len(list(tree.children())) == 1

    # Add new child
    child3 = TreeObject()
    child3[NameObject("/Foo")] = TextStringObject("3")
    child3_ref = writer._add_object(child3)
    tree.add_child(child3_ref, writer)
    assert tree[NameObject("/Count")] == 2
    assert len(list(tree.children())) == 2

    # Remove first child
    child1 = tree[NameObject("/First")]
    tree.remove_child(child1)
    assert tree[NameObject("/Count")] == 1
    assert len(list(tree.children())) == 1

    child4 = TreeObject()
    child4[NameObject("/Foo")] = TextStringObject("4")
    child4_ref = writer._add_object(child4)
    tree.add_child(child4_ref, writer)
    assert tree[NameObject("/Count")] == 2
    assert len(list(tree.children())) == 2

    child5 = TreeObject()
    child5[NameObject("/Foo")] = TextStringObject("5")
    child5_ref = writer._add_object(child5)
    tree.add_child(child5_ref, writer)
    assert tree[NameObject("/Count")] == 3
    assert len(list(tree.children())) == 3

    # Remove middle child
    child4.remove_from_tree()
    assert tree[NameObject("/Count")] == 2
    assert len(list(tree.children())) == 2

    tree.empty_tree()


def test_remove_child_in_tree():
    pdf = RESOURCE_ROOT / "form.pdf"

    tree = TreeObject()
    reader = PdfReader(pdf)
    writer = PdfWriter()
    writer._add_object(tree)
    writer.add_page(reader.pages[0])
    writer.add_outline_item("foo", page_number=0)
    obj = writer._objects[-1]
    tree.add_child(obj, writer)
    tree.remove_child(obj)
    tree.add_child(obj, writer)
    tree.empty_tree()


@pytest.mark.enable_socket
@pytest.mark.parametrize(
    ("url", "name", "caplog_content"),
    [
        (  # parse_content_stream_peek_percentage
            "https://github.com/user-attachments/files/18381763/tika-985770.pdf",
            "tika-985770.pdf",
            "",
        ),
        (  # read_inline_image_no_has_q
            "https://github.com/user-attachments/files/18381775/tika-998719.pdf",
            "tika-998719.pdf",
            "",
        ),
        (  # read_inline_image_loc_neg_1
            "https://github.com/user-attachments/files/18381706/tika-935066.pdf",
            "tika-935066.pdf",
            "",
        ),
        (  # object_read_from_stream_unicode_error
            "https://github.com/user-attachments/files/18381750/tika-974966.pdf",
            "tika-974966.pdf",
            "",
        ),
        (  # dict_read_from_stream
            "https://github.com/user-attachments/files/18381762/tika-984877.pdf",
            "tika-984877.pdf",
            "Multiple definitions in dictionary at byte 0x1084 for key /Length",
        ),
    ],
    ids=[
        "parse_content_stream_peek_percentage",
        "read_inline_image_no_has_q",
        "read_inline_image_loc_neg_1",
        "object_read_from_stream_unicode_error",
        "dict_read_from_stream",
    ],
)
def test_extract_text(caplog, url: str, name: str, caplog_content: str):
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    for page in reader.pages:
        page.extract_text()
    if caplog_content == "":
        assert caplog_content == caplog.text
    else:
        assert caplog_content in caplog.text


@pytest.mark.slow
@pytest.mark.enable_socket
def test_text_string_write_to_stream():
    url = "https://github.com/user-attachments/files/18381698/tika-924562.pdf"
    name = "tika-924562.pdf"

    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page in writer.pages:
        page.compress_content_streams()


@pytest.mark.enable_socket
def test_bool_repr(tmp_path):
    url = "https://github.com/user-attachments/files/18381703/tika-932449.pdf"
    name = "tika-932449.pdf"

    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    write_path = tmp_path / "tmp-fields-report.txt"
    with open(write_path, "w") as fp:
        fields = reader.get_fields(fileobj=fp)
    assert fields
    assert list(fields.keys()) == ["USGPOSignature"]
    with open(write_path) as fp:
        data = fp.read()
    assert data.startswith(
        "Field Name: USGPOSignature\nField Type: Signature\nField Flags: 1\n"
        "Value: {'/Type': '/Sig', '/Filter': '/Adobe.PPKLite', "
        "'/SubFilter':"
    )


@pytest.mark.enable_socket
def test_issue_997(pdf_file_path):
    url = (
        "https://github.com/py-pdf/pypdf/files/8908874/"
        "Exhibit_A-2_930_Enterprise_Zone_Tax_Credits_final.pdf"
    )
    name = "gh-issue-997.pdf"

    merger = PdfWriter()
    merger.append(BytesIO(get_data_from_url(url, name=name)))  # here the error raises
    with open(pdf_file_path, "wb") as f:
        merger.write(f)
    merger.close()

    # Strict
    merger = PdfWriter()
    merger.append(BytesIO(get_data_from_url(url, name=name)))  # here the error raises
    with open(pdf_file_path, "wb") as f:
        merger.write(f)
    merger.close()


def test_checkboxradiobuttonattributes_opt():
    assert "/Opt" in CheckboxRadioButtonAttributes.attributes_dict()


def test_name_object_invalid_decode():
    charsets = deepcopy(NameObject.CHARSETS)
    try:
        NameObject.CHARSETS = ("utf-8",)
        stream = BytesIO(b"/\x80\x02\x03")
        # strict:
        with pytest.raises(PdfReadError) as exc:
            NameObject.read_from_stream(stream, ReaderDummy(strict=True))
        assert "Illegal character in NameObject " in exc.value.args[0]

        # non-strict:
        stream.seek(0)
        NameObject.read_from_stream(stream, ReaderDummy(strict=False))
    finally:
        NameObject.CHARSETS = charsets


def test_indirect_object_invalid_read():
    stream = BytesIO(b"0 1 s")
    with pytest.raises(PdfReadError) as exc:
        IndirectObject.read_from_stream(stream, ReaderDummy())
    assert exc.value.args[0] == "Error reading indirect object reference at byte 0x5"


def test_create_string_object_utf16_bom():
    # utf16-be
    result = create_string_object(
        b"\xfe\xff\x00P\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00"
    )
    assert result == "PaperPort 14\x00"
    assert result.autodetect_utf16 is True
    assert result.utf16_bom == b"\xfe\xff"
    assert (
        result.get_encoded_bytes()
        == b"\xfe\xff\x00P\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00"
    )

    # utf16-le
    result = create_string_object(
        b"\xff\xfeP\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00\x00"
    )
    assert result == "PaperPort 14\x00"
    assert result.autodetect_utf16 is True
    assert result.utf16_bom == b"\xff\xfe"
    assert (
        result.get_encoded_bytes()
        == b"\xff\xfeP\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00\x00"
    )
    result = TextStringObject(
        b"\xff\xfeP\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00\x00"
    )
    assert result == "PaperPort 14\x00"
    assert result.autodetect_utf16 is True
    assert result.utf16_bom == b"\xff\xfe"
    assert (
        result.get_encoded_bytes()
        == b"\xff\xfeP\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00\x00"
    )

    # utf16-be without bom
    result = TextStringObject("ÿ")
    result.autodetect_utf16 = True
    result.utf16_bom = b""
    assert result.get_encoded_bytes() == b"\x00\xFF"
    assert result.original_bytes == b"\x00\xFF"


def test_create_string_object_force():
    assert create_string_object(b"Hello World", []) == "Hello World"
    assert create_string_object(b"Hello World", {72: "A"}) == "Aello World"
    assert create_string_object(b"Hello World", "utf8") == "Hello World"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.000000", "0.0"),
        ("0.0", "0.0"),
        ("1.0", "1"),
        ("0.123000", "0.123"),
        ("0.000123000", "0.000123"),
        ("0.0", "0.0"),
        ("0", "0.0"),
        ("1", "1"),
        ("1.0", "1"),
        ("1.01", "1.01"),
        ("1.010", "1.01"),
        ("0000.0000", "0.0"),
        ("0.10101010", "0.1010101"),
        ("50000000000", "50000000000"),
        ("99900000000000000123", "99900000000000000000"),
        ("99900000000000000123.456000", "99900000000000000000"),
        ("0.00000000000000000000123", "0.00000000000000000000123"),
        ("0.00000123", "0.00000123"),
        ("0.00000000000000000000123000", "0.00000000000000000000123"),
        ("-4.6", "-4.6"),  # from #1910
        # (
        #    "50032481330523882508234.00000000000000000000123000",
        #    "50032481330523882508234.00000000000000000000123",
        # ),
        # (
        #    "928457298572093487502198745102973402987412908743.75249875981374981237498213740000",
        #    "928457298572093487502198745102973402987412908743.7524987598137498123749821374",
        # ),
    ],
)
def test_float_object_decimal_to_string(value, expected):
    assert repr(FloatObject(value)) == expected


def test_cloning(caplog):
    writer = PdfWriter()
    with pytest.raises(Exception) as exc:
        PdfObject().clone(writer)
    assert "PdfObject does not implement .clone so far" in exc.value.args[0]

    obj1 = DictionaryObject()
    obj1.indirect_reference = None
    n = len(writer._objects)
    obj2 = obj1.clone(writer)
    assert len(writer._objects) == n + 1
    obj3 = obj2.clone(writer)
    assert len(writer._objects) == n + 1
    assert obj2.indirect_reference == obj3.indirect_reference
    obj3 = obj2.indirect_reference.clone(writer)
    assert len(writer._objects) == n + 1
    assert obj2.indirect_reference == obj3.indirect_reference
    assert (
        obj2.indirect_reference
        == obj2._reference_clone(obj2, writer).indirect_reference
    )
    assert len(writer._objects) == n + 1
    assert obj2.indirect_reference == obj3.indirect_reference

    obj3 = obj2.indirect_reference.clone(writer, True)
    assert len(writer._objects) == n + 2
    assert obj2.indirect_reference != obj3.indirect_reference

    arr1 = ArrayObject([obj2])
    arr2 = arr1.clone(writer)
    arr3 = arr2.clone(writer)
    assert arr2 == arr3
    obj10 = StreamObject()
    arr1 = ArrayObject([obj10])
    obj11 = obj10.clone(writer)
    assert arr1[0] == obj11

    obj20 = DictionaryObject(
        {NameObject("/Test"): NumberObject(1), NameObject("/Test2"): StreamObject()}
    )
    obj21 = obj20.clone(writer, ignore_fields=None)
    assert "/Test" in obj21
    assert isinstance(obj21.get("/Test2"), IndirectObject)


@pytest.mark.enable_socket
def test_append_with_indirectobject_not_pointing(caplog):
    """
    Reported in #1631
    the object 43 0 is not invalid
    """
    url = "https://github.com/py-pdf/pypdf/files/10729142/document.pdf"
    name = "tst_iss1631.pdf"
    data = BytesIO(get_data_from_url(url, name=name))
    reader = PdfReader(data, strict=False)
    writer = PdfWriter()
    writer.append(reader)
    assert "Object 43 0 not defined." in caplog.text


@pytest.mark.enable_socket
def test_iss1615_1673():
    """
    Test cases where /N is not indicating chains of objects
    test also where /N,... are not part of chains
    """
    # #1615
    url = "https://github.com/py-pdf/pypdf/files/10671366/graph_letter.pdf"
    name = "graph_letter.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.append(reader)
    assert (
        "/N"
        in writer.pages[0]["/Annots"][0]
        .get_object()["/AP"]["/N"]["/Resources"]["/ColorSpace"]["/Cs1"][1]
        .get_object()
    )
    # #1673
    url = "https://github.com/py-pdf/pypdf/files/10848750/budgeting-loan-form-sf500.pdf"
    name = "budgeting-loan-form-sf500.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)


@pytest.mark.enable_socket
def test_destination_withoutzoom():
    """Cf issue #1832"""
    url = "https://github.com/user-attachments/files/15605648/2021_book_security.pdf"
    name = "2021_book_security.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.outline

    out = BytesIO()
    writer = PdfWriter(clone_from=reader)
    writer.write(out)


def test_encodedstream_set_data():
    """
    EncodedStreamObject.set_data to extend data stream works.

    Checks also the flate_encode.
    """
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    co = reader.pages[0]["/Contents"][0].get_object()
    co.set_data(b"%hello\n" + co.get_data())
    assert b"hello" in co.get_data()
    b = BytesIO()
    co.write_to_stream(b)
    b.seek(0)
    aa = read_object(b, None)
    assert b"hello" in aa.get_data()
    assert aa["/Filter"] == "/FlateDecode"
    assert "/DecodeParms" not in aa
    bb = aa.flate_encode()
    assert b"hello" in bb.get_data()
    assert bb["/Filter"] == ["/FlateDecode", "/FlateDecode"]
    assert str(bb["/DecodeParms"]) == "[NullObject, NullObject]"
    bb[NameObject("/Test")] = NameObject("/MyTest")
    cc = bb.flate_encode()
    assert bb["/Filter"] == ["/FlateDecode", "/FlateDecode"]
    assert b"hello" in cc.get_data()
    assert cc["/Filter"] == ["/FlateDecode", "/FlateDecode", "/FlateDecode"]
    assert str(cc["/DecodeParms"]) == "[NullObject, NullObject, NullObject]"
    assert cc[NameObject("/Test")] == "/MyTest"

    with pytest.raises(TypeError):
        aa.set_data("toto")

    aa[NameObject("/Filter")] = NameObject("/JPXEncode")
    with pytest.raises(PdfReadError):
        aa.set_data(b"toto")


@pytest.mark.enable_socket
def test_set_data_2():
    """
    Modify a stream not yet loaded and
    where the filter is ["/FlateDecode"]
    """
    url = "https://github.com/user-attachments/files/16796095/f5471sm-2.pdf"
    name = "iss2780.pdf"
    writer = PdfWriter(BytesIO(get_data_from_url(url, name=name)))
    writer.root_object["/AcroForm"]["/XFA"][7].set_data(b"test")
    assert writer.root_object["/AcroForm"]["/XFA"][7].get_object()["/Filter"] == [
        "/FlateDecode"
    ]
    assert writer.root_object["/AcroForm"]["/XFA"][7].get_object().get_data() == b"test"


@pytest.mark.enable_socket
def test_calling_indirect_objects():
    """Cope with cases where attributes/items are called from indirectObject"""
    url = "https://github.com/user-attachments/files/15605648/2021_book_security.pdf"
    name = "2021_book_security.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.trailer.get("/Info")["/Creator"]
    reader.pages[0]["/Contents"][0].get_data()
    writer = PdfWriter(clone_from=reader)
    ind = writer._add_object(writer)
    assert ind.fileobj == writer.fileobj
    with pytest.raises(AttributeError):
        ind.not_existing_attribute
    # create an IndirectObject referencing an IndirectObject.
    writer._objects.append(writer.pages[0].indirect_reference)
    ind = IndirectObject(len(writer._objects), 0, writer)
    with pytest.raises(PdfStreamError):
        ind["/Type"]


@pytest.mark.enable_socket
def test_indirect_object_page_dimensions():
    url = "https://github.com/py-pdf/pypdf/files/13302338/Zymeworks_Corporate.Presentation_FINAL1101.pdf.pdf"
    name = "issue2287.pdf"
    data = BytesIO(get_data_from_url(url, name=name))
    reader = PdfReader(data, strict=False)
    mediabox = reader.pages[0].mediabox
    assert mediabox == RectangleObject((0, 0, 792, 612))


def test_array_operators():
    a = ArrayObject(
        [
            NumberObject(1),
            NumberObject(2),
            NumberObject(3),
            NumberObject(4),
        ]
    )
    b = a + 5
    assert isinstance(b, ArrayObject)
    assert b == [1, 2, 3, 4, 5]
    assert a == [1, 2, 3, 4]
    a -= 2
    a += "abc"
    a -= (3, 4)
    a += ["d", "e"]
    a += BooleanObject(True)
    assert a == [1, "abc", "d", "e", True]
    a += "/toto"
    assert isinstance(a[-1], NameObject)
    assert isinstance(a[1], TextStringObject)
    a += b"1234"
    assert a[-1] == ByteStringObject(b"1234")
    la = len(a)
    a -= 300
    assert len(a) == la


def test_unitary_extract_inline_buffer_invalid():
    with pytest.raises(PdfReadError):
        extract_inline_AHx(BytesIO())
    with pytest.raises(PdfReadError):
        extract_inline_AHx(BytesIO(4095 * b"00" + b"   "))
    with pytest.raises(PdfReadError):
        extract_inline_AHx(BytesIO(b"00"))
    with pytest.raises(PdfReadError):
        extract_inline_A85(BytesIO())
    with pytest.raises(PdfReadError):
        extract_inline_A85(BytesIO(a85encode(b"1")))
    with pytest.raises(PdfReadError):
        extract_inline_A85(BytesIO(a85encode(b"1") + b"~> Q"))
    with pytest.raises(PdfReadError):
        extract_inline_A85(BytesIO(a85encode(b"1234578" * 990)))
    with pytest.raises(PdfReadError):
        extract_inline_RL(BytesIO())
    with pytest.raises(PdfReadError):
        extract_inline_RL(BytesIO(b"\x01\x01\x80"))
    with pytest.raises(PdfReadError):
        extract_inline_DCT(BytesIO(b"\xFF\xD9"))


def test_unitary_extract_inline():
    # AHx
    b = 16000 * b"00"
    assert len(extract_inline_AHx(BytesIO(b + b" EI"))) == len(b)
    with pytest.raises(PdfReadError):
        extract_inline_AHx(BytesIO(b + b"> "))
    # RL
    b = 8200 * b"\x00\xAB" + b"\x80"
    assert len(extract_inline_RL(BytesIO(b + b" EI"))) == len(b)

    # default
    # EIDD instead of EI; using A85
    b = b"""1 0 0 1 0 0 cm  BT /F1 12 Tf 14.4 TL ET\nq 100 0 0 100 100 100 cm
BI\n/W 16 /H 16 /BPC 8 /CS /RGB /F [/A85 /Fl]\nID
Gar8O(o6*is8QV#;;JAuTq2lQ8J;%6#\'d5b"Q[+ZD?\'\\+CGj9~>
EIDD
Q\nBT 1 0 0 1 200 100 Tm (Test) Tj T* ET\n \n"""
    ec = DecodedStreamObject()
    ec.set_data(b)
    co = ContentStream(ec, None)
    with pytest.raises(PdfReadError) as exc:
        co.operations
    assert "EI stream not found" in exc.value.args[0]
    # EIDD instead of EI; using /Fl (default extraction)
    b = b"""1 0 0 1 0 0 cm  BT /F1 12 Tf 14.4 TL ET\nq 100 0 0 100 100 100 cm
BI\n/W 16 /H 16 /BPC 8 /CS /RGB /F /Fl \nID
Gar8O(o6*is8QV#;;JAuTq2lQ8J;%6#\'d5b"Q[+ZD?\'\\+CGj9~>
EIDD
Q\nBT 1 0 0 1 200 100 Tm (Test) Tj T* ET\n \n"""
    ec = DecodedStreamObject()
    ec.set_data(b)
    co = ContentStream(ec, None)
    with pytest.raises(PdfReadError) as exc:
        co.operations
    assert "Unexpected end of stream" in exc.value.args[0]

    b = b"""1 0 0 1 0 0 cm  BT /F1 12 Tf 14.4 TL ET\nq 100 0 0 100 100 100 cm
BI\n/W 16 /H 16 /BPC 8 /CS /RGB /F /Fl \nID
Gar8O(o6*is8QV#;;JAuTq2lQ8J;%6#\'d5b"Q[+ZD?\'\\+CGj9~>EI
BT\nQ\nBT 1 0 0 1 200 100 Tm (Test) Tj T* ET\n \n"""
    ec = DecodedStreamObject()
    ec.set_data(b)
    co = ContentStream(ec, None)
    with pytest.raises(PdfReadError) as exc:
        co.operations
    assert "Unexpected end of stream" in exc.value.args[0]

    b = b"""1 0 0 1 0 0 cm  BT /F1 12 Tf 14.4 TL ET\nq 100 0 0 100 100 100 cm
BI\n/W 4 /H 4 /CS /G \nID
abcdefghijklmnopEI
Q\nQ\nBT 1 0 0 1 200 100 Tm (Test) Tj T* ET\n \n"""
    ec = DecodedStreamObject()
    ec.set_data(b)
    co = ContentStream(ec, None)
    assert co.operations[7][0]["data"] == b"abcdefghijklmnop"

    b = b"""1 0 0 1 0 0 cm  BT /F1 12 Tf 14.4 TL ET\nq 100 0 0 100 100 100 cm
BI\n/W 4 /H 4 \nID
abcdefghijklmnopEI
Q\nQ\nBT 1 0 0 1 200 100 Tm (Test) Tj T* ET\n \n"""
    ec = DecodedStreamObject()
    ec.set_data(b)
    co = ContentStream(ec, None)
    assert co.operations[7][0]["data"] == b"abcdefghijklmnop"


def test_missing_hashbin():
    assert NullObject().hash_bin() == hash((NullObject,))
    t = ByteStringObject(b"123")
    assert t.hash_bin() == hash((ByteStringObject, b"123"))


def test_is_null_or_none():
    assert is_null_or_none(NullObject())
    assert not is_null_or_none(PdfObject())

    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    # used with get
    assert is_null_or_none(reader.root_object.get("/do_no_exist"))
    # object unknown...
    assert is_null_or_none(IndirectObject(99999, 0, reader).get_object())
    # ... or which has been replaced with NullObject
    writer = PdfWriter(reader)
    writer.pages[0]["/Contents"].append(writer._add_object(NullObject()))
    assert is_null_or_none(writer.pages[0]["/Contents"][-1])


def test_coverage_arrayobject():
    writer = PdfWriter()
    a = ArrayObject([1])
    assert isinstance(a.replicate(writer)[0], int)
    assert isinstance(a.clone(writer)[0], int)
    a.indirect_reference = IndirectObject(1, 0, writer)
    assert isinstance(a.clone(writer)[0], int)
    r = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    a = ArrayObject([r.pages[0]["/Contents"][0].get_object()])
    aa = a.clone(writer)
    assert isinstance(aa[0], IndirectObject)
    for k, v in aa.items():
        assert isinstance(k, int)
        assert isinstance(v, PdfObject)


def test_coverage_streamobject():
    writer = PdfWriter()
    s = StreamObject()
    del s.decoded_self
    s.replicate(writer)
    s.clone(writer)

    co = ContentStream(None, None)
    co.replicate(writer)
    co.clone(writer, False, None)
    co.indirect_reference = IndirectObject(1, 0, writer)
    assert co == co.clone(writer)

    r = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    co = r.pages[0].get_contents()
    co[NameObject("/testkey")] = NameObject("/test")
    co.decoded_self = None
    assert "/testkey" in co.replicate(writer)
    co = r.pages[0].get_contents()
    co[NameObject("/testkey")] = NameObject("/test")
    co.decoded_self = DecodedStreamObject()
    assert "/testkey" in co.replicate(writer)


def test_contentstream_arrayobject_containing_nullobject(caplog):
    stream_object = DecodedStreamObject()
    stream_object.set_data(b"Hello World!")

    input_stream = ArrayObject([NullObject(), stream_object])
    content_stream = ContentStream(stream=input_stream, pdf=None)
    assert content_stream.get_data() == b"Hello World!\n"
    assert caplog.text == ""
