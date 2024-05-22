"""Test the pypdf.generic module."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from pypdf import PdfMerger, PdfReader, PdfWriter
from pypdf.constants import CheckboxRadioButtonAttributes
from pypdf.errors import PdfReadError, PdfStreamError
from pypdf.generic import (
    AnnotationBuilder,
    ArrayObject,
    BooleanObject,
    ByteStringObject,
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
    read_hex_string_from_stream,
    read_object,
    read_string_from_stream,
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


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_deprecated_name_object():
    b = BytesIO()
    NameObject("wrong").write_to_stream(b)
    assert b.getvalue() == b"wrong"


def test_name_object():
    stream = BytesIO(b"x")
    with pytest.raises(PdfReadError) as exc:
        NameObject.read_from_stream(stream, None)
    assert exc.value.args[0] == "name read error"

    b = BytesIO()
    with pytest.raises(DeprecationWarning):
        NameObject("hello").write_to_stream(b)

    for binary, value, binary_pypdf in (
        # ISO/DIS 32000-2 Table 4: Examples of literal names
        (b"/Name1", "Name1", None),
        (b"/ASomewhatLongerName", "ASomewhatLongerName", None),
        (
            b"/A;Name_With-Various***Characters?",
            "A;Name_With-Various***Characters?",
            None,
        ),
        (b"/1.2", "1.2", None),
        (b"/$$", "$$", None),
        (b"/@pattern", "@pattern", None),
        (b"/.notdef", ".notdef", None),
        (b"/Lime#20Green", "Lime Green", None),
        (b"/paired#28#29parentheses", "paired()parentheses", None),
        (b"/The_Key_of_F#23_Minor", "The_Key_of_F#_Minor", None),
        (b"/A#42", "AB", b"/AB"),
        # misc tests
        (
            b"/#f1j#d4#aa#0c#ce#87#b4#b3#b0#23J#86#fe#2a#b2jYJ#94",
            "ñjÔª\x0cÎ\x87´³°#J\x86þ*²jYJ\x94",
            b"/#F1j#D4#AA#0C#CE#87#B4#B3#B0#23J#86#FE*#B2jYJ#94",
        ),
        (b"/#JA#231f", "#JA#1f", b"/#23JA#231f"),
        (b"/DocuSign\xae", "DocuSign®", b"/DocuSign#AE"),
        (b"/DocuSign\xc2\xae", "DocuSign®", b"/DocuSign#C2#AE"),
        (b"/DIJMAC+Arial#20Black#231", "DIJMAC+Arial Black#1", None),
        (
            b"/#e4#bd#a0#e5#a5#bd#e4#b8#96#e7#95#8c",
            "你好世界",
            b"/#E4#BD#A0#E5#A5#BD#E4#B8#96#E7#95#8C",
        ),
        (b"/#E4#BD#A0#E5#A5#BD#E4#B8#96#E7#95#8C#20#28#25#29", "你好世界 (%)", None),
        (  # try all allowed values
            b'/#01#02#03#04#05#06#07#08#09#0A#0B#0C#0D#0E#0F#10#11#12#13#14#15#16#17#18#19#1A#1B#1C#1D#1E#1F#20!"#23$#2'
            rb"5&'#28#29*+,-.#2F0123456789:;#3C=#3E?@ABCDEFGHIJKLMNOPQRSTUVWXYZ#5B\#5D^_`abcdefghijklmnopqrstuvwxyz#7B|"
            b"#7D~#7F#80#81#82#83#84#85#86#87#88#89#8A#8B#8C#8D#8E#8F#90#91#92#93#94#95#96#97#98#99#9A#9B#9C#9D#9E#9F#A"
            b"0#A1#A2#A3#A4#A5#A6#A7#A8#A9#AA#AB#AC#AD#AE#AF#B0#B1#B2#B3#B4#B5#B6#B7#B8#B9#BA#BB#BC#BD#BE#BF#C0#C1#C2#C"
            b"3#C4#C5#C6#C7#C8#C9#CA#CB#CC#CD#CE#CF#D0#D1#D2#D3#D4#D5#D6#D7#D8#D9#DA#DB#DC#DD#DE#DF#E0#E1#E2#E3#E4#E5#E"
            b"6#E7#E8#E9#EA#EB#EC#ED#EE#EF#F0#F1#F2#F3#F4#F5#F6#F7#F8#F9#FA#FB#FC#FD#FE#FF",
            bytes(range(1, 0x100)).decode("latin1"),
            None,
        ),
        (b"/\x80\x02\x03", "\x80\x02\x03", b"/#80#02#03"),
    ):
        name = NameObject.read_from_stream(BytesIO(binary), None)
        assert name == f"/{value}"
        bio = BytesIO()
        name.write_to_stream(bio)
        if binary_pypdf:
            assert bio.getvalue() == binary_pypdf
        else:
            assert bio.getvalue() == binary

    with pytest.raises(KeyError):
        NameObject("/\0").write_to_stream(BytesIO())


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
    assert exc.value.args[0] == "key must be PdfObject"


def test_dictionaryobject_xmp_meta():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    assert do.xmp_metadata is None


def test_dictionaryobject_value_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do[NameObject("/S")] = "/GoTo"
    assert exc.value.args[0] == "value must be PdfObject"


def test_dictionaryobject_setdefault_key_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do.setdefault("foo", NameObject("/GoTo"))
    assert exc.value.args[0] == "key must be PdfObject"


def test_dictionaryobject_setdefault_value_is_no_pdfobject():
    do = DictionaryObject({NameObject("/S"): NameObject("/GoTo")})
    with pytest.raises(ValueError) as exc:
        do.setdefault(NameObject("/S"), "/GoTo")
    assert exc.value.args[0] == "value must be PdfObject"


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
    with pytest.raises(Exception) as exc:
        tso.get_original_bytes()
    assert exc.value.args[0] == "no information about original bytes"


def test_textstringobject_autodetect_utf16():
    tso = TextStringObject("foo")
    tso.autodetect_utf16 = True
    assert tso.get_original_bytes() == b"\xfe\xff\x00f\x00o\x00o"


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


@pytest.mark.enable_socket()
@pytest.mark.parametrize(
    ("url", "name", "caplog_content"),
    [
        (  # parse_content_stream_peek_percentage
            "https://corpora.tika.apache.org/base/docs/govdocs1/985/985770.pdf",
            "tika-985770.pdf",
            "",
        ),
        (  # read_inline_image_no_has_q
            "https://corpora.tika.apache.org/base/docs/govdocs1/998/998719.pdf",
            "tika-998719.pdf",
            "",
        ),
        (  # read_inline_image_loc_neg_1
            "https://corpora.tika.apache.org/base/docs/govdocs1/935/935066.pdf",
            "tika-935066.pdf",
            "",
        ),
        (  # object_read_from_stream_unicode_error
            "https://corpora.tika.apache.org/base/docs/govdocs1/974/974966.pdf",
            "tika-974966.pdf",
            "",
        ),
        (  # dict_read_from_stream
            "https://corpora.tika.apache.org/base/docs/govdocs1/984/984877.pdf",
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


@pytest.mark.slow()
@pytest.mark.enable_socket()
def test_text_string_write_to_stream():
    url = "https://corpora.tika.apache.org/base/docs/govdocs1/924/924562.pdf"
    name = "tika-924562.pdf"

    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page in writer.pages:
        page.compress_content_streams()


@pytest.mark.enable_socket()
def test_bool_repr(tmp_path):
    url = "https://corpora.tika.apache.org/base/docs/govdocs1/932/932449.pdf"
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


@pytest.mark.enable_socket()
@patch("pypdf._reader.logger_warning")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_issue_997(mock_logger_warning, pdf_file_path):
    url = (
        "https://github.com/py-pdf/pypdf/files/8908874/"
        "Exhibit_A-2_930_Enterprise_Zone_Tax_Credits_final.pdf"
    )
    name = "gh-issue-997.pdf"

    merger = PdfMerger()
    merger.append(BytesIO(get_data_from_url(url, name=name)))  # here the error raises
    with open(pdf_file_path, "wb") as f:
        merger.write(f)
    merger.close()

    mock_logger_warning.assert_called_with("Overwriting cache for 0 4", "pypdf._reader")

    # Strict
    merger = PdfMerger(strict=True)
    with pytest.raises(PdfReadError) as exc:
        merger.append(
            BytesIO(get_data_from_url(url, name=name))
        )  # here the error raises
    assert exc.value.args[0] == "Could not find object."
    with open(pdf_file_path, "wb") as f:
        merger.write(f)
    merger.close()


def test_annotation_builder_free_text(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        free_text_annotation = AnnotationBuilder.free_text(
            "Hello World - bold and italic\nThis is the second line!",
            rect=(50, 550, 200, 650),
            font="Arial",
            bold=True,
            italic=True,
            font_size="20pt",
            font_color="00ff00",
            border_color=None,
            background_color=None,
        )
    writer.add_annotation(0, free_text_annotation)

    with pytest.warns(DeprecationWarning):
        free_text_annotation = AnnotationBuilder.free_text(
            "Another free text annotation (not bold, not italic)",
            rect=(500, 550, 200, 650),
            font="Arial",
            bold=False,
            italic=False,
            font_size="20pt",
            font_color="00ff00",
            border_color="0000ff",
            background_color="cdcdcd",
        )
    writer.add_annotation(0, free_text_annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_polygon(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError) as exc:
        AnnotationBuilder.polygon(
            vertices=[],
        )
    assert exc.value.args[0] == "A polygon needs at least 1 vertex with two coordinates"

    with pytest.warns(DeprecationWarning):
        annotation = AnnotationBuilder.polygon(
            vertices=[(50, 550), (200, 650), (70, 750), (50, 700)],
        )
    writer.add_annotation(0, annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_polyline(pdf_file_path, pdf_reader_page):
    # Arrange
    writer = PdfWriter()
    writer.add_page(pdf_reader_page)

    # Act
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError) as exc:
        AnnotationBuilder.polyline(
            vertices=[],
        )
    assert exc.value.args[0] == "A polygon needs at least 1 vertex with two coordinates"

    with pytest.warns(DeprecationWarning):
        annotation = AnnotationBuilder.polyline(
            vertices=[(50, 550), (200, 650), (70, 750), (50, 700)],
        )
    writer.add_annotation(0, annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_line(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        line_annotation = AnnotationBuilder.line(
            text="Hello World\nLine2",
            rect=(50, 550, 200, 650),
            p1=(50, 550),
            p2=(200, 650),
        )
    writer.add_annotation(0, line_annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_square(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        square_annotation = AnnotationBuilder.rectangle(
            rect=(50, 550, 200, 650), interiour_color="ff0000"
        )
    writer.add_annotation(0, square_annotation)

    with pytest.warns(DeprecationWarning):
        square_annotation = AnnotationBuilder.rectangle(
            rect=(40, 400, 150, 450),
        )
    writer.add_annotation(0, square_annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_highlight(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        highlight_annotation = AnnotationBuilder.highlight(
            rect=(95.79332, 704.31777, 138.55779, 724.6855),
            highlight_color="ff0000",
            quad_points=ArrayObject(
                [
                    FloatObject(100.060779),
                    FloatObject(723.55398),
                    FloatObject(134.29033),
                    FloatObject(723.55398),
                    FloatObject(100.060779),
                    FloatObject(705.4493),
                    FloatObject(134.29033),
                    FloatObject(705.4493),
                ]
            ),
            printing=False
        )
    writer.add_annotation(0, highlight_annotation)
    for annot in writer.pages[0]["/Annots"]:
        obj = annot.get_object()
        subtype = obj["/Subtype"]
        if subtype == "/Highlight":
            assert "/F" not in obj or obj["/F"] == NumberObject(0)

    writer.add_page(page)
    # Act
    with pytest.warns(DeprecationWarning):
        highlight_annotation = AnnotationBuilder.highlight(
            rect=(95.79332, 704.31777, 138.55779, 724.6855),
            highlight_color="ff0000",
            quad_points=ArrayObject(
                [
                    FloatObject(100.060779),
                    FloatObject(723.55398),
                    FloatObject(134.29033),
                    FloatObject(723.55398),
                    FloatObject(100.060779),
                    FloatObject(705.4493),
                    FloatObject(134.29033),
                    FloatObject(705.4493),
                ]
            ),
            printing=True
        )
    writer.add_annotation(1, highlight_annotation)
    for annot in writer.pages[1]["/Annots"]:
        obj = annot.get_object()
        subtype = obj["/Subtype"]
        if subtype == "/Highlight":
            assert obj["/F"] == NumberObject(4)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_circle(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        circle_annotation = AnnotationBuilder.ellipse(
            rect=(50, 550, 200, 650), interiour_color="ff0000"
        )
    writer.add_annotation(0, circle_annotation)

    diameter = 100
    with pytest.warns(DeprecationWarning):
        circle_annotation = AnnotationBuilder.ellipse(
            rect=(110, 500, 110 + diameter, 500 + diameter),
        )
    writer.add_annotation(0, circle_annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_link(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "outline-without-title.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    # Part 1: Too many args
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError) as exc:
        AnnotationBuilder.link(
            rect=(50, 550, 200, 650),
            url="https://martin-thoma.com/",
            target_page_index=3,
        )
    assert exc.value.args[0] == (
        "Either 'url' or 'target_page_index' have to be provided. "
        "url=https://martin-thoma.com/, target_page_index=3"
    )

    # Part 2: Too few args
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError) as exc:
        AnnotationBuilder.link(
            rect=(50, 550, 200, 650),
        )
    assert (
        exc.value.args[0]
        == "Either 'url' or 'target_page_index' have to be provided. Both were None."
    )

    # Part 3: External Link
    with pytest.warns(DeprecationWarning):
        link_annotation = AnnotationBuilder.link(
            rect=(50, 50, 100, 100),
            url="https://martin-thoma.com/",
            border=[1, 0, 6, [3, 2]],
        )
    writer.add_annotation(0, link_annotation)

    # Part 4: Internal Link
    with pytest.warns(DeprecationWarning):
        link_annotation = AnnotationBuilder.link(
            rect=(100, 100, 300, 200),
            target_page_index=1,
            border=[50, 10, 4],
        )
    writer.add_annotation(0, link_annotation)

    for page in reader.pages[1:]:
        writer.add_page(page)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_text(pdf_file_path):
    # Arrange
    pdf_path = RESOURCE_ROOT / "outline-without-title.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        text_annotation = AnnotationBuilder.text(
            text="Hello World\nThis is the second line!",
            rect=(50, 550, 500, 650),
            open=True,
        )
    writer.add_annotation(0, text_annotation)

    # Assert: You need to inspect the file manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


def test_annotation_builder_popup(caplog):
    # Arrange
    pdf_path = RESOURCE_ROOT / "outline-without-title.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)

    # Act
    with pytest.warns(DeprecationWarning):
        text_annotation = AnnotationBuilder.text(
            text="Hello World\nThis is the second line!",
            rect=(50, 550, 200, 650),
            open=True,
        )
    ta = writer.add_annotation(0, text_annotation)

    with pytest.warns(DeprecationWarning):
        popup_annotation = AnnotationBuilder.popup(
            rect=(50, 550, 200, 650),
            open=True,
            parent=ta,  # prefer to use for evolutivity
        )

    assert caplog.text == ""
    with pytest.warns(DeprecationWarning):
        AnnotationBuilder.popup(
            rect=(50, 550, 200, 650),
            open=True,
            parent=True,  # broken parameter  # type: ignore
        )
    assert "Unregistered Parent object : No Parent field set" in caplog.text

    writer.add_annotation(writer.pages[0], popup_annotation)

    target = "annotated-pdf-popup.pdf"
    writer.write(target)
    Path(target).unlink()  # comment this out for manual inspection


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


def test_create_string_object_utf16be_bom():
    result = create_string_object(
        b"\xfe\xff\x00P\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00"
    )
    assert result == "PaperPort 14\x00"
    assert result.autodetect_utf16 is True


def test_create_string_object_utf16le_bom():
    result = create_string_object(
        b"\xff\xfeP\x00a\x00p\x00e\x00r\x00P\x00o\x00r\x00t\x00 \x001\x004\x00\x00\x00"
    )
    assert result == "PaperPort 14\x00"
    assert result.autodetect_utf16 is True


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


@pytest.mark.enable_socket()
def test_append_with_indirectobject_not_pointing(caplog):
    """
    reported in #1631
    the object 43 0 is not invalid
    """
    url = "https://github.com/py-pdf/pypdf/files/10729142/document.pdf"
    name = "tst_iss1631.pdf"
    data = BytesIO(get_data_from_url(url, name=name))
    reader = PdfReader(data, strict=False)
    writer = PdfWriter()
    writer.append(reader)
    assert "Object 43 0 not defined." in caplog.text


@pytest.mark.enable_socket()
def test_iss1615_1673():
    """
    test cases where /N is not indicating chains of objects
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


@pytest.mark.enable_socket()
def test_destination_withoutzoom():
    """Cf issue #1832"""
    url = (
        "https://raw.githubusercontent.com/xrkk/tmpppppp/main/"
        "2021%20----%20book%20-%20Security%20of%20biquitous%20Computing%20Systems.pdf"
    )
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


@pytest.mark.enable_socket()
def test_calling_indirect_objects():
    """Cope with cases where attributes/items are called from indirectObject"""
    url = (
        "https://raw.githubusercontent.com/xrkk/tmpppppp/main/"
        "2021%20----%20book%20-%20Security%20of%20biquitous%20Computing%20Systems.pdf"
    )
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


@pytest.mark.enable_socket()
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
