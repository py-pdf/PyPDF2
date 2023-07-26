"""
pypdf is a free and open-source pure-python PDF library capable of splitting,
merging, cropping, and transforming the pages of PDF files. It can also add
custom data, viewing options, and passwords to PDF files. pypdf can retrieve
text and metadata from PDFs as well.

You can read the full docs at https://pypdf.readthedocs.io/.
"""

from ._encryption import PasswordType
from ._merger import PdfFileMerger, PdfMerger
from ._page import PageObject, Transformation
from ._reader import DocumentInformation, PdfFileReader, PdfReader
from ._utils import overload_logger_warning
from ._version import __version__
from ._writer import ObjectDeletionFlag, PdfFileWriter, PdfWriter
from .pagerange import PageRange, parse_filename_page_ranges
from .papersizes import PaperSize

__all__ = [
    "__version__",
    "overload_logger_warning",
    "PageRange",
    "PaperSize",
    "DocumentInformation",
    "ObjectDeletionFlag",
    "parse_filename_page_ranges",
    "PdfFileMerger",  # will be removed in pypdf==4.0.0; use PdfMerger instead
    "PdfFileReader",  # will be removed in pypdf==4.0.0; use PdfReader instead
    "PdfFileWriter",  # will be removed in pypdf==4.0.0; use PdfWriter instead
    "PdfMerger",
    "PdfReader",
    "PdfWriter",
    "Transformation",
    "PageObject",
    "PasswordType",
]
