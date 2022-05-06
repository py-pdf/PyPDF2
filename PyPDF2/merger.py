# Copyright (c) 2006, Mathieu Fenniak
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from io import BytesIO
from io import FileIO as file
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, cast

try:
    from typing import Literal  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Literal  # type: ignore[misc]

from PyPDF2._page import PageObject
from PyPDF2._reader import PdfFileReader
from PyPDF2._writer import PdfFileWriter
from PyPDF2.constants import PagesAttributes as PA
from PyPDF2.generic import *
from PyPDF2.pagerange import PageRange, PageRangeSpec
from PyPDF2.utils import StrByteType, StreamType, str_

StreamIO = BytesIO

ERR_CLOSED_WRITER = "close() was called and thus the writer cannot be used anymore"


class _MergedPage:
    """
    _MergedPage is used internally by PdfFileMerger to collect necessary
    information on each page that is being merged.
    """

    def __init__(self, pagedata: PageObject, src: PdfFileReader, id: int) -> None:
        self.src = src
        self.pagedata = pagedata
        self.out_pagedata = None
        self.id = id


class PdfFileMerger:
    """
    Initializes a ``PdfFileMerger`` object. ``PdfFileMerger`` merges multiple
    PDFs into a single PDF. It can concatenate, slice, insert, or any
    combination of the above.

    See the functions :meth:`merge()<merge>` (or :meth:`append()<append>`)
    and :meth:`write()<write>` for usage information.

    :param bool strict: Determines whether user should be warned of all
            problems and also causes some correctable problems to be fatal.
            Defaults to ``False``.
    """

    def __init__(self, strict: bool = False) -> None:
        self.inputs: List[Tuple[Any, PdfFileReader, bool]] = []
        self.pages: List[Any] = []
        self.output: Optional[PdfFileWriter] = PdfFileWriter()
        self.bookmarks: List[Union[Bookmark, Destination, List[Destination]]] = []
        self.named_dests: List[Any] = []
        self.id_count = 0
        self.strict = strict

    def merge(
        self,
        position: int,
        fileobj: Union[StrByteType, PdfFileReader],
        bookmark: Optional[str] = None,
        pages: Optional[PageRangeSpec] = None,
        import_bookmarks: bool = True,
    ) -> None:
        """
        Merges the pages from the given file into the output file at the
        specified page number.

        :param int position: The *page number* to insert this file. File will
            be inserted after the given number.

        :param fileobj: A File Object or an object that supports the standard
            read and seek methods similar to a File Object. Could also be a
            string representing a path to a PDF file.

        :param str bookmark: Optionally, you may specify a bookmark to be
            applied at the beginning of the included file by supplying the text
            of the bookmark.

        :param pages: can be a :class:`PageRange<PyPDF2.pagerange.PageRange>`
            or a ``(start, stop[, step])`` tuple
            to merge only the specified range of pages from the source
            document into the output document.

        :param bool import_bookmarks: You may prevent the source document's
            bookmarks from being imported by specifying this as ``False``.
        """

        # This parameter is passed to self.inputs.append and means
        # that the stream used was created in this method.
        my_file = False

        # If the fileobj parameter is a string, assume it is a path
        # and create a file object at that location. If it is a file,
        # copy the file's contents into a BytesIO (or StreamIO) stream object; if
        # it is a PdfFileReader, copy that reader's stream into a
        # BytesIO (or StreamIO) stream.
        # If fileobj is none of the above types, it is not modified
        decryption_key = None
        if isinstance(fileobj, str):
            fileobj = file(fileobj, "rb")
            my_file = True
        elif hasattr(fileobj, "seek") and hasattr(fileobj, "read"):
            fileobj.seek(0)  # type: ignore
            filecontent = fileobj.read()  # type: ignore
            fileobj = StreamIO(filecontent)  # type: ignore[arg-type]
            my_file = True
        elif isinstance(fileobj, PdfFileReader):
            if hasattr(fileobj, "_decryption_key"):
                decryption_key = fileobj._decryption_key
            orig_tell = fileobj.stream.tell()
            fileobj.stream.seek(0)
            filecontent = StreamIO(fileobj.stream.read())  # type: ignore[assignment]

            # reset the stream to its original location
            fileobj.stream.seek(orig_tell)

            fileobj = filecontent  # type: ignore[assignment]
            my_file = True

        # Create a new PdfFileReader instance using the stream
        # (either file or BytesIO or StringIO) created above
        pdfr = PdfFileReader(fileobj, strict=self.strict)  # type: ignore[arg-type]
        if decryption_key is not None:
            pdfr._decryption_key = decryption_key

        # Find the range of pages to merge.
        if pages is None:
            pages = (0, pdfr.getNumPages())
        elif isinstance(pages, PageRange):
            pages = pages.indices(pdfr.getNumPages())
        elif not isinstance(pages, tuple):
            raise TypeError('"pages" must be a tuple of (start, stop[, step])')

        srcpages = []

        outline = []
        if import_bookmarks:
            outline = pdfr.getOutlines()
            outline = self._trim_outline(pdfr, outline, pages)  # type: ignore

        if bookmark:
            bookmark_typ = Bookmark(
                TextStringObject(bookmark),
                NumberObject(self.id_count),
                NameObject("/Fit"),
            )
            self.bookmarks += [bookmark_typ, outline]  # type: ignore
        else:
            self.bookmarks += outline

        dests = pdfr.namedDestinations
        trimmed_dests = self._trim_dests(pdfr, dests, pages)
        self.named_dests += trimmed_dests

        # Gather all the pages that are going to be merged
        for i in range(*pages):  # type: ignore
            pg = pdfr.getPage(i)

            id = self.id_count
            self.id_count += 1

            mp = _MergedPage(pg, pdfr, id)

            srcpages.append(mp)

        self._associate_dests_to_pages(srcpages)
        self._associate_bookmarks_to_pages(srcpages)

        # Slice to insert the pages at the specified position
        self.pages[position:position] = srcpages

        # Keep track of our input files so we can close them later
        self.inputs.append((fileobj, pdfr, my_file))

    def append(
        self,
        fileobj: Union[StrByteType, PdfFileReader],
        bookmark: Optional[str] = None,
        pages: Union[None, PageRange, Tuple[int, int], Tuple[int, int, int]] = None,
        import_bookmarks: bool = True,
    ) -> None:
        """
        Identical to the :meth:`merge()<merge>` method, but assumes you want to
        concatenate all pages onto the end of the file instead of specifying a
        position.

        :param fileobj: A File Object or an object that supports the standard
            read and seek methods similar to a File Object. Could also be a
            string representing a path to a PDF file.

        :param str bookmark: Optionally, you may specify a bookmark to be
            applied at the beginning of the included file by supplying the text
            of the bookmark.

        :param pages: can be a :class:`PageRange<PyPDF2.pagerange.PageRange>`
            or a ``(start, stop[, step])`` tuple
            to merge only the specified range of pages from the source
            document into the output document.

        :param bool import_bookmarks: You may prevent the source document's
            bookmarks from being imported by specifying this as ``False``.
        """
        self.merge(len(self.pages), fileobj, bookmark, pages, import_bookmarks)

    def write(self, fileobj: StrByteType) -> None:
        """
        Writes all data that has been merged to the given output file.

        :param fileobj: Output file. Can be a filename or any kind of
            file-like object.
        """
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        my_file = False
        if isinstance(fileobj, str):
            fileobj = file(fileobj, "wb")
            my_file = True

        # Add pages to the PdfFileWriter
        # The commented out line below was replaced with the two lines below it
        # to allow PdfFileMerger to work with PyPdf 1.13
        for page in self.pages:
            self.output.addPage(page.pagedata)
            pages_obj: Dict[str, Any] = self.output._pages.getObject()  # type: ignore
            page.out_pagedata = self.output.getReference(
                pages_obj[PA.KIDS][-1].getObject()
            )
            # idnum = self.output._objects.index(self.output._pages.getObject()[PA.KIDS][-1].getObject()) + 1
            # page.out_pagedata = IndirectObject(idnum, 0, self.output)

        # Once all pages are added, create bookmarks to point at those pages
        self._write_dests()
        self._write_bookmarks()

        # Write the output to the file
        self.output.write(fileobj)

        if my_file:
            fileobj.close()

    def close(self) -> None:
        """
        Shuts all file descriptors (input and output) and clears all memory
        usage.
        """
        self.pages = []
        for fo, _pdfr, mine in self.inputs:
            if mine:
                fo.close()

        self.inputs = []
        self.output = None

    def addMetadata(self, infos: Dict[str, Any]) -> None:
        """
        Add custom metadata to the output.

        :param dict infos: a Python dictionary where each key is a field
            and each value is your new metadata.
            Example: ``{u'/Title': u'My title'}``
        """
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        self.output.addMetadata(infos)

    def setPageLayout(
        self,
        layout: Literal[
            "/NoLayout",
            "/SinglePage",
            "/OneColumn",
            "/TwoColumnLeft",
            "/TwoColumnRight",
        ],
    ) -> None:
        """
        Set the page layout

        :param str layout: The page layout to be used

        .. list-table:: Valid ``layout`` arguments
           :widths: 50 200

           * - /NoLayout
             - Layout explicitly not specified
           * - /SinglePage
             - Show one page at a time
           * - /OneColumn
             - Show one column at a time
           * - /TwoColumnLeft
             - Show pages in two columns, odd-numbered pages on the left
           * - /TwoColumnRight
             - Show pages in two columns, odd-numbered pages on the right
           * - /TwoPageLeft
             - Show two pages at a time, odd-numbered pages on the left
           * - /TwoPageRight
             - Show two pages at a time, odd-numbered pages on the right
        """
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        self.output.setPageLayout(layout)

    def setPageMode(
        self,
        mode: Literal[
            "/UseNone", "/UseOutlines", "/UseThumbs", "/UseOC", "/UseAttachments"
        ],
    ) -> None:
        """
        Set the page mode.

        :param str mode: The page mode to use.

        .. list-table:: Valid ``mode`` arguments
           :widths: 50 200

           * - /UseNone
             - Do not show outlines or thumbnails panels
           * - /UseOutlines
             - Show outlines (aka bookmarks) panel
           * - /UseThumbs
             - Show page thumbnails panel
           * - /FullScreen
             - Fullscreen view
           * - /UseOC
             - Show Optional Content Group (OCG) panel
           * - /UseAttachments
             - Show attachments panel
        """
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        self.output.setPageMode(mode)

    def _trim_dests(
        self,
        pdf: PdfFileReader,
        dests: Dict[str, Dict[str, Any]],
        pages: Union[Tuple[int, int], Tuple[int, int, int]],
    ) -> List[Dict[str, Any]]:
        """
        Removes any named destinations that are not a part of the specified
        page set.
        """
        new_dests = []
        for key, obj in dests.items():
            for j in range(*pages):
                if pdf.getPage(j).getObject() == obj["/Page"].getObject():
                    obj[NameObject("/Page")] = obj["/Page"].getObject()
                    assert str_(key) == str_(obj["/Title"])
                    new_dests.append(obj)
                    break
        return new_dests

    def _trim_outline(
        self,
        pdf: PdfFileReader,
        outline: List[Destination],
        pages: Union[Tuple[int, int], Tuple[int, int, int]],
    ) -> List[Destination]:
        """
        Removes any outline/bookmark entries that are not a part of the
        specified page set.
        """
        new_outline = []
        prev_header_added = True
        for i, o in enumerate(outline):
            if isinstance(o, list):
                sub = self._trim_outline(pdf, o, pages)
                if sub:
                    if not prev_header_added:
                        new_outline.append(outline[i - 1])
                    new_outline.append(sub)
            else:
                prev_header_added = False
                for j in range(*pages):
                    if pdf.getPage(j).getObject() == o["/Page"].getObject():
                        o[NameObject("/Page")] = o["/Page"].getObject()
                        new_outline.append(o)
                        prev_header_added = True
                        break
        return new_outline

    def _write_dests(self) -> None:
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        for named_dest in self.named_dests:
            pageno = None
            if "/Page" in named_dest:
                for pageno, page in enumerate(self.pages):  # noqa: B007
                    if page.id == named_dest["/Page"]:
                        named_dest[NameObject("/Page")] = page.out_pagedata
                        break

            if pageno is not None:
                self.output.addNamedDestinationObject(named_dest)

    def _write_bookmarks(
        self,
        bookmarks: Optional[Iterable[Bookmark]] = None,
        parent: Optional[IndirectObject] = None,
    ) -> None:
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        if bookmarks is None:
            bookmarks = self.bookmarks  # type: ignore
        assert bookmarks is not None, "hint for mypy"  # TODO: is that true?

        last_added = None
        for bookmark in bookmarks:
            if isinstance(bookmark, list):
                self._write_bookmarks(bookmark, last_added)
                continue

            page_no = None
            if "/Page" in bookmark:
                for page_no, page in enumerate(self.pages):  # noqa: B007
                    if page.id == bookmark["/Page"]:
                        self._write_bookmark_on_page(bookmark, page)
                        break
            if page_no is not None:
                del bookmark["/Page"], bookmark["/Type"]
                last_added = self.output.addBookmarkDict(bookmark, parent)

    def _write_bookmark_on_page(
        self, bookmark: Union[Bookmark, Destination], page: _MergedPage
    ) -> None:
        # b[NameObject('/Page')] = p.out_pagedata
        args = [NumberObject(page.id), NameObject(bookmark["/Type"])]
        # nothing more to add
        # if b['/Type'] == '/Fit' or b['/Type'] == '/FitB'
        if bookmark["/Type"] == "/FitH" or bookmark["/Type"] == "/FitBH":
            if "/Top" in bookmark and not isinstance(bookmark["/Top"], NullObject):
                args.append(FloatObject(bookmark["/Top"]))
            else:
                args.append(FloatObject(0))
            del bookmark["/Top"]
        elif bookmark["/Type"] == "/FitV" or bookmark["/Type"] == "/FitBV":
            if "/Left" in bookmark and not isinstance(bookmark["/Left"], NullObject):
                args.append(FloatObject(bookmark["/Left"]))
            else:
                args.append(FloatObject(0))
            del bookmark["/Left"]
        elif bookmark["/Type"] == "/XYZ":
            if "/Left" in bookmark and not isinstance(bookmark["/Left"], NullObject):
                args.append(FloatObject(bookmark["/Left"]))
            else:
                args.append(FloatObject(0))
            if "/Top" in bookmark and not isinstance(bookmark["/Top"], NullObject):
                args.append(FloatObject(bookmark["/Top"]))
            else:
                args.append(FloatObject(0))
            if "/Zoom" in bookmark and not isinstance(bookmark["/Zoom"], NullObject):
                args.append(FloatObject(bookmark["/Zoom"]))
            else:
                args.append(FloatObject(0))
            del bookmark["/Top"], bookmark["/Zoom"], bookmark["/Left"]
        elif bookmark["/Type"] == "/FitR":
            if "/Left" in bookmark and not isinstance(bookmark["/Left"], NullObject):
                args.append(FloatObject(bookmark["/Left"]))
            else:
                args.append(FloatObject(0))
            if "/Bottom" in bookmark and not isinstance(
                bookmark["/Bottom"], NullObject
            ):
                args.append(FloatObject(bookmark["/Bottom"]))
            else:
                args.append(FloatObject(0))
            if "/Right" in bookmark and not isinstance(bookmark["/Right"], NullObject):
                args.append(FloatObject(bookmark["/Right"]))
            else:
                args.append(FloatObject(0))
            if "/Top" in bookmark and not isinstance(bookmark["/Top"], NullObject):
                args.append(FloatObject(bookmark["/Top"]))
            else:
                args.append(FloatObject(0))
            del (
                bookmark["/Left"],
                bookmark["/Right"],
                bookmark["/Bottom"],
                bookmark["/Top"],
            )

        bookmark[NameObject("/A")] = DictionaryObject(
            {NameObject("/S"): NameObject("/GoTo"), NameObject("/D"): ArrayObject(args)}
        )

    def _associate_dests_to_pages(self, pages: List[_MergedPage]) -> None:
        for nd in self.named_dests:
            pageno = None
            np = nd["/Page"]

            if isinstance(np, NumberObject):
                continue

            for p in pages:
                if np.getObject() == p.pagedata.getObject():
                    pageno = p.id

            if pageno is not None:
                nd[NameObject("/Page")] = NumberObject(pageno)
            else:
                raise ValueError(
                    "Unresolved named destination '{}'".format(nd["/Title"])
                )

    def _associate_bookmarks_to_pages(
        self, pages: List[_MergedPage], bookmarks: Optional[Iterable[Bookmark]] = None
    ) -> None:
        if bookmarks is None:
            bookmarks = self.bookmarks  # type: ignore # TODO: self.bookmarks can be none!
        assert bookmarks is not None, "hint for mypy"
        for b in bookmarks:
            if isinstance(b, list):
                self._associate_bookmarks_to_pages(pages, b)
                continue

            pageno = None
            bp = b["/Page"]

            if isinstance(bp, NumberObject):
                continue

            for p in pages:
                if bp.getObject() == p.pagedata.getObject():
                    pageno = p.id

            if pageno is not None:
                b[NameObject("/Page")] = NumberObject(pageno)
            else:
                raise ValueError("Unresolved bookmark '{}'".format(b["/Title"]))

    def findBookmark(
        self,
        bookmark: Dict[str, Any],
        root: Optional[
            Iterable[Union[Bookmark, Destination, List[Destination]]]
        ] = None,
    ) -> Optional[List[int]]:
        if root is None:
            root = self.bookmarks

        for i, b in enumerate(root):
            if isinstance(b, list):
                res = self.findBookmark(bookmark, b)
                if res:
                    return [i] + res
            elif b == bookmark or b["/Title"] == bookmark:
                return [i]

        return None

    def addBookmark(
        self,
        title: str,
        pagenum: int,
        parent: Union[None, TreeObject, IndirectObject] = None,
        color: Optional[Tuple[float, float, float]] = None,
        bold: bool = False,
        italic: bool = False,
        fit: str = "/Fit",
        *args: Optional[float]
    ) -> IndirectObject:
        """
        Add a bookmark to this PDF file.

        :param str title: Title to use for this bookmark.
        :param int pagenum: Page number this bookmark will point to.
        :param parent: A reference to a parent bookmark to create nested
            bookmarks.
        :param tuple color: Color of the bookmark as a red, green, blue tuple
            from 0.0 to 1.0
        :param bool bold: Bookmark is bold
        :param bool italic: Bookmark is italic
        :param str fit: The fit of the destination page. See
            :meth:`addLink()<addLin>` for details.
        """
        if self.output is None:
            raise RuntimeError(ERR_CLOSED_WRITER)
        out_pages: Dict[str, Any] = self.output.getObject(self.output._pages)  # type: ignore
        if len(out_pages["/Kids"]) > 0:
            page_ref = out_pages["/Kids"][pagenum]
        else:
            page_ref = out_pages

        action = DictionaryObject()
        zoom_args: List[Union[NumberObject, NullObject]] = []
        for a in args:
            if a is not None:
                zoom_args.append(NumberObject(a))
            else:
                zoom_args.append(NullObject())
        dest = Destination(
            NameObject("/" + title + " bookmark"), page_ref, NameObject(fit), *zoom_args
        )
        dest_array = dest.getDestArray()
        action.update(
            {NameObject("/D"): dest_array, NameObject("/S"): NameObject("/GoTo")}
        )
        action_ref = self.output._addObject(action)

        outline_ref = self.output.getOutlineRoot()

        if parent is None:
            parent = outline_ref

        bookmark = TreeObject()

        bookmark.update(
            {
                NameObject("/A"): action_ref,
                NameObject("/Title"): createStringObject(title),
            }
        )

        if color is not None:
            bookmark.update(
                {NameObject("/C"): ArrayObject([FloatObject(c) for c in color])}
            )

        format = 0
        if italic:
            format += 1
        if bold:
            format += 2
        if format:
            bookmark.update({NameObject("/F"): NumberObject(format)})

        bookmark_ref = self.output._addObject(bookmark)
        parent = cast(Bookmark, parent.getObject())
        assert parent is not None, "hint for mypy"
        parent.addChild(bookmark_ref, self.output)

        return bookmark_ref

    def addNamedDestination(self, title: str, pagenum: int) -> None:
        """
        Add a destination to the output.

        :param str title: Title to use
        :param int pagenum: Page number this destination points at.
        """

        dest = Destination(
            TextStringObject(title),
            NumberObject(pagenum),
            NameObject("/FitH"),
            NumberObject(826),
        )
        self.named_dests.append(dest)
