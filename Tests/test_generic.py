# -*- coding: utf-8 -*-
from io import BytesIO

import pytest

from PyPDF2.constants import TypFitArguments as TF
from PyPDF2.errors import PdfReadError, PdfStreamError
from PyPDF2.generic import (
    ArrayObject,
    Bookmark,
    BooleanObject,
    Destination,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    PdfObject,
    createStringObject,
    encode_pdfdocencoding,
    readHexStringFromStream,
    readStringFromStream,
)


def test_float_object_exception():
    assert FloatObject("abc") == 0


def test_number_object_exception():
    with pytest.raises(OverflowError):
        NumberObject(1.5 * 2**10000)


def test_createStringObject_exception():
    with pytest.raises(TypeError) as exc:
        createStringObject(123)
    assert exc.value.args[0] == "createStringObject should have str or unicode arg"


@pytest.mark.parametrize("value, expected", [(b"true", b"true"), (b"false", b"false")])
def test_boolean_object(value, expected):
    stream = BytesIO(value)
    BooleanObject.readFromStream(stream)
    stream.seek(0, 0)
    assert stream.read() == expected


def test_boolean_object_write():
    stream = BytesIO()
    boolobj = BooleanObject(None)
    boolobj.writeToStream(stream, encryption_key=None)
    stream.seek(0, 0)
    assert stream.read() == b"false"


def test_boolean_object_exception():
    stream = BytesIO(b"False")
    with pytest.raises(PdfReadError) as exc:
        ArrayObject.readFromStream(stream, None)
    assert exc.value.args[0] == "Could not read array"


def test_array_object_exception():
    stream = BytesIO(b"False")
    with pytest.raises(PdfReadError) as exc:
        BooleanObject.readFromStream(stream)
    assert exc.value.args[0] == "Could not read Boolean object"


def test_null_object_exception():
    stream = BytesIO(b"notnull")
    with pytest.raises(PdfReadError) as exc:
        NullObject.readFromStream(stream)
    assert exc.value.args[0] == "Could not read Null object"


@pytest.mark.parametrize("value", [b"", b"False", b"foo ", b"foo  ", b"foo bar"])
def test_indirect_object_premature(value):
    stream = BytesIO(value)
    with pytest.raises(PdfStreamError) as exc:
        IndirectObject.readFromStream(stream, None)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_readHexStringFromStream():
    stream = BytesIO(b"a1>")
    assert readHexStringFromStream(stream) == "\x10"


def test_readHexStringFromStream_exception():
    stream = BytesIO(b"")
    with pytest.raises(PdfStreamError) as exc:
        readHexStringFromStream(stream)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_readStringFromStream_exception():
    stream = BytesIO(b"x")
    with pytest.raises(PdfStreamError) as exc:
        readStringFromStream(stream)
    assert exc.value.args[0] == "Stream has ended unexpectedly"


def test_NameObject():
    stream = BytesIO(b"x")
    with pytest.raises(PdfReadError) as exc:
        NameObject.readFromStream(stream, None)
    assert exc.value.args[0] == "name read error"


def test_destination_fit_r():
    Destination(
        NameObject("title"),
        PdfObject(),
        NameObject(TF.FIT_R),
        FloatObject(0),
        FloatObject(0),
        FloatObject(0),
        FloatObject(0),
    )


def test_destination_fit_v():
    Destination(NameObject("title"), PdfObject(), NameObject(TF.FIT_V), FloatObject(0))


def test_destination_exception():
    with pytest.raises(PdfReadError):
        Destination(NameObject("title"), PdfObject(), NameObject("foo"), FloatObject(0))


def test_bookmark_write_to_stream():
    stream = BytesIO()
    bm = Bookmark(
        NameObject("title"), NameObject(), NameObject(TF.FIT_V), FloatObject(0)
    )
    bm.writeToStream(stream, None)
    stream.seek(0, 0)
    assert stream.read() == b"<<\n/Title title\n/Dest [  /FitV 0 ]\n>>"


@pytest.mark.no_py27
def test_encode_pdfdocencoding_keyerror():
    with pytest.raises(UnicodeEncodeError) as exc:
        encode_pdfdocencoding("😀")
    assert exc.value.args[0] == "pdfdocencoding"
