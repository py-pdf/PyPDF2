"""
All errors/exceptions PyPDF2 raises and all of the warnings it uses.

Please note that broken PDF files might cause other Exceptions.
"""


class DependencyError(Exception):
    pass


class PyPdfError(Exception):
    pass


class PdfReadError(PyPdfError):
    pass


class PageSizeNotDefinedError(PyPdfError):
    pass


class PdfReadWarning(UserWarning):
    pass


class PdfStreamError(PdfReadError):
    pass


class ParseError(Exception):
    pass


STREAM_TRUNCATED_PREMATURELY = "Stream has ended unexpectedly"
