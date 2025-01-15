"""Test the pypdf._page module."""
import json
import math
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from random import shuffle
from typing import List, Tuple

import pytest

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf._page import PageObject
from pypdf.constants import PageAttributes as PG
from pypdf.errors import PdfReadError, PdfReadWarning, PyPdfError
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NullObject,
    RectangleObject,
    TextStringObject,
)

from . import get_data_from_url, normalize_warnings

TESTS_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
RESOURCE_ROOT = PROJECT_ROOT / "resources"
SAMPLE_ROOT = PROJECT_ROOT / "sample-files"


def get_all_sample_files():
    meta_file = SAMPLE_ROOT / "files.json"
    if not Path(meta_file).is_file():
        return {"data": []}
    with open(meta_file) as fp:
        data = fp.read()
    meta = json.loads(data)
    return meta


all_files_meta = get_all_sample_files()


@pytest.mark.samples
@pytest.mark.parametrize(
    "meta",
    [m for m in all_files_meta["data"] if not m["encrypted"]],
    ids=[m["path"] for m in all_files_meta["data"] if not m["encrypted"]],
)
@pytest.mark.filterwarnings("ignore::pypdf.errors.PdfReadWarning")
def test_read(meta):
    pdf_path = SAMPLE_ROOT / meta["path"]
    reader = PdfReader(pdf_path)
    try:
        reader.pages[0]
    except Exception:
        return
    assert len(reader.pages) == meta["pages"]


@pytest.mark.samples
@pytest.mark.enable_socket
@pytest.mark.parametrize(
    ("pdf_path", "password"),
    [
        ("crazyones.pdf", None),
        ("attachment.pdf", None),
        (
            "libreoffice-writer-password.pdf",
            "openpassword",
        ),
        ("imagemagick-images.pdf", None),
        ("imagemagick-lzw.pdf", None),
        ("reportlab-inline-image.pdf", None),
        ("https://arxiv.org/pdf/2201.00029.pdf", None),
    ],
)
def test_page_operations(pdf_path, password):
    """
    This test just checks if the operation throws an exception.

    This should be done way more thoroughly: It should be checked if the output
    is as expected.
    """
    if pdf_path.startswith("http"):
        pdf_path = BytesIO(get_data_from_url(pdf_path, pdf_path.split("/")[-1]))
    else:
        pdf_path = RESOURCE_ROOT / pdf_path
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    if password:
        reader.decrypt(password)

    writer.clone_document_from_reader(reader)
    page: PageObject = writer.pages[0]

    t = Transformation().translate(50, 100).rotate(90)
    assert abs(t.ctm[4] + 100) < 0.01
    assert abs(t.ctm[5] - 50) < 0.01

    transformation = (
        Transformation()
        .rotate(90)
        .scale(1)
        .translate(1, 1)
        .transform(Transformation((1, 0, 0, -1, 0, 0)))
    )
    page.add_transformation(transformation, expand=True)
    page.add_transformation((1, 0, 0, 0, 0, 0))
    page.scale(2, 2)
    page.scale_by(0.5)
    page.scale_to(100, 100)
    page.compress_content_streams()
    page.extract_text()
    page.scale_by(0.5)
    page.scale_to(100, 100)
    page.extract_text()


@pytest.mark.parametrize(
    ("angle", "expected_width", "expected_height"),
    [
        (175, 680, 844),
        (45, 994, 994),
        (-80, 888, 742),
    ],
)
def test_mediabox_expansion_after_rotation(
    angle: float, expected_width: int, expected_height: int
):
    """
    Mediabox dimensions after rotation at a non-right angle with expansion are correct.

    The test was validated against pillow (see PR #2282)
    """
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)

    transformation = Transformation().rotate(angle)
    for page_box in reader.pages:
        page_box.add_transformation(transformation, expand=True)

    mediabox = reader.pages[0].mediabox

    # Deviation of up to 2 pixels is acceptable
    assert math.isclose(mediabox.width, expected_width, abs_tol=2)
    assert math.isclose(mediabox.height, expected_height, abs_tol=2)


def test_transformation_equivalence():
    pdf_path = RESOURCE_ROOT / "labeled-edges-center-image.pdf"
    reader_base = PdfReader(pdf_path)
    page_base = reader_base.pages[0]

    pdf_path = RESOURCE_ROOT / "box.pdf"
    reader_add = PdfReader(pdf_path)
    page_box = reader_add.pages[0]

    op = Transformation().scale(2).rotate(45)

    # Option 1: The new way
    page_box1 = deepcopy(page_box)
    page_base1 = deepcopy(page_base)
    page_box1.add_transformation(op, expand=True)
    page_base1.merge_page(page_box1, expand=False)

    # Option 2: The old way
    page_box2 = deepcopy(page_box)
    page_base2 = deepcopy(page_base)
    page_base2.merge_transformed_page(page_box2, op, expand=False)
    page_box2.add_transformation(op)
    page_base2.merge_page(page_box2)

    # Should be the same
    assert page_base1[NameObject(PG.CONTENTS)] == page_base2[NameObject(PG.CONTENTS)]
    assert page_base1.mediabox == page_base2.mediabox
    assert page_base1.trimbox == page_base2.trimbox
    assert page_base1[NameObject(PG.ANNOTS)] == page_base2[NameObject(PG.ANNOTS)]
    compare_dict_objects(
        page_base1[NameObject(PG.RESOURCES)], page_base2[NameObject(PG.RESOURCES)]
    )


def test_transformation_equivalence2():
    pdf_path = RESOURCE_ROOT / "labeled-edges-center-image.pdf"
    reader_base = PdfReader(pdf_path)

    pdf_path = RESOURCE_ROOT / "box.pdf"
    reader_add = PdfReader(pdf_path)

    writer = PdfWriter()
    writer.append(reader_base)
    writer.pages[0].merge_transformed_page(
        reader_add.pages[0], Transformation().scale(2).rotate(-45), False, False
    )
    writer.pages[0].merge_transformed_page(
        reader_add.pages[0], Transformation().scale(2).translate(100, 100), True, False
    )
    # No special assert: the test should be visual in a viewer; 2 box with a arrow rotated  and translated

    writer = PdfWriter()
    writer.append(reader_add)
    writer.pages[0].merge_transformed_page(
        reader_base.pages[0], Transformation(), True, True
    )
    # No special assert: Visual check the page has been  increased and all is visible (box+graph)

    writer = PdfWriter()
    writer.append(reader_add)
    height = reader_add.pages[0].mediabox.height
    writer.pages[0].merge_transformed_page(
        reader_base.pages[0],
        Transformation().transform(Transformation((1, 0, 0, -1, 0, height))),
        False,
        False,
    )
    # No special assert: Visual check the page has been  increased and all is visible (box+graph)

    pdf_path = RESOURCE_ROOT / "commented-xmp.pdf"
    reader_comments = PdfReader(pdf_path)

    writer = PdfWriter()
    writer.append(reader_base)
    writer.pages[0].merge_transformed_page(
        reader_comments.pages[0], Transformation().rotate(-15), True, True
    )
    nb_annots1 = len(writer.pages[0]["/Annots"])
    writer.pages[0].merge_transformed_page(
        reader_comments.pages[0], Transformation().rotate(-30), True, True
    )
    assert len(writer.pages[0]["/Annots"]) == 2 * nb_annots1
    # No special assert: Visual check the overlay has its comments at the good position


def test_get_user_unit_property():
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    assert reader.pages[0].user_unit == 1


def compare_dict_objects(d1, d2):
    assert sorted(d1.keys()) == sorted(d2.keys())
    for key in d1:
        if isinstance(d1[key], DictionaryObject):
            compare_dict_objects(d1[key], d2[key])
        else:
            assert d1[key] == d2[key]


@pytest.mark.slow
def test_page_transformations():
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)

    page: PageObject = reader.pages[0]
    page.merge_rotated_page(page, 90, expand=True)

    op = Transformation().rotate(90).scale(1, 1)
    page.merge_transformed_page(page, op, expand=True)

    op = Transformation().rotate(90).scale(1, 1).translate(1, 1)
    page.merge_transformed_page(page, op, expand=True)

    op = Transformation().translate(-100, -100).rotate(90).translate(100, 100)
    page.merge_transformed_page(page, op, expand=False)

    page.merge_scaled_page(page, 2, expand=False)

    op = Transformation().scale(1, 1).translate(1, 1)
    page.merge_transformed_page(page, op)

    page.merge_translated_page(page, 100, 100, expand=False)
    page.add_transformation((1, 0, 0, 0, 0, 0))


@pytest.mark.parametrize(
    ("pdf_path", "password"),
    [
        (RESOURCE_ROOT / "crazyones.pdf", None),
        (RESOURCE_ROOT / "attachment.pdf", None),
        (RESOURCE_ROOT / "side-by-side-subfig.pdf", None),
        (
            RESOURCE_ROOT / "libreoffice-writer-password.pdf",
            "openpassword",
        ),
    ],
)
def test_compress_content_streams(pdf_path, password):
    reader = PdfReader(pdf_path)

    writer = PdfWriter()
    if password:
        reader.decrypt(password)
    for i, page in enumerate(reader.pages):
        assert i == page.page_number

    assert isinstance(reader.pages[0].get_contents(), ContentStream)
    writer.clone_document_from_reader(reader)
    assert isinstance(writer.pages[0].get_contents(), ContentStream)
    for i, page in enumerate(writer.pages):
        assert i == page.page_number
        page.compress_content_streams()

    # test from reader should fail as adding_object out of
    # PdfWriter not possible
    with pytest.raises(ValueError):
        reader.pages[0].compress_content_streams()


def test_page_properties():
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    page = reader.pages[0]
    assert page.mediabox == RectangleObject((0, 0, 612, 792))
    assert page.cropbox == RectangleObject((0, 0, 612, 792))
    assert page.bleedbox == RectangleObject((0, 0, 612, 792))
    assert page.trimbox == RectangleObject((0, 0, 612, 792))
    assert page.artbox == RectangleObject((0, 0, 612, 792))

    page.bleedbox = RectangleObject((0, 1, 100, 101))
    assert page.bleedbox == RectangleObject((0, 1, 100, 101))


@pytest.mark.parametrize("key", [PG.MEDIABOX, PG.CROPBOX])
@pytest.mark.parametrize("values", [
    [0, 0, 612, 792, 0, 0, 612, 792],
    (0, 0, 612, 792, 0, 0, 612, 792),
    [0, 0, 612, 792, 0, 0, 612, 792, 0, 0],
    (0, 0, 612, 792, 0, 0, 612, 792, 0, 0),
])
def test_page_handles_long_media_and_crop_box_iss_2991(key: str, values: List[float] | Tuple[float, ...]):
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    page = reader.pages[0]
    page[NameObject(key)] = ArrayObject(values)
    assert page.mediabox == RectangleObject((0, 0, 612, 792))


def test_page_rotation():
    reader = PdfReader(RESOURCE_ROOT / "crazyones.pdf")
    page = reader.pages[0]
    with pytest.raises(ValueError) as exc:
        page.rotate(91)
    assert exc.value.args[0] == "Rotation angle must be a multiple of 90"

    # test rotation
    assert page.rotation == 0
    page.rotation = 180
    assert page.rotation == 180
    page.rotation += 190
    assert page.rotation == 0

    # test transfer_rotate_to_content
    page.rotation -= 90
    page.transfer_rotation_to_content()
    assert abs(float(page.mediabox.left) - 0) < 0.1
    assert abs(float(page.mediabox.bottom) - 0) < 0.1
    assert abs(float(page.mediabox.right) - 792) < 0.1
    assert abs(float(page.mediabox.top) - 612) < 0.1


def test_page_indirect_rotation():
    reader = PdfReader(RESOURCE_ROOT / "indirect-rotation.pdf")
    page = reader.pages[0]

    # test rotation
    assert page.rotation == 0


def test_page_scale():
    op = Transformation()
    with pytest.raises(ValueError) as exc:
        op.scale()
    assert exc.value.args[0] == "Either sx or sy must be specified"

    assert op.scale(sx=2).ctm == (2, 0, 0, 2, 0, 0)
    assert op.scale(sy=3).ctm == (3, 0, 0, 3, 0, 0)


def test_add_transformation_on_page_without_contents():
    page = PageObject()
    assert page.get_contents() is None
    page.add_transformation(Transformation())
    page[NameObject("/Contents")] = ContentStream(None, None)
    assert isinstance(page.get_contents(), ContentStream)


@pytest.mark.enable_socket
def test_iss_1142():
    # check fix for problem of context save/restore (q/Q)
    url = "https://github.com/py-pdf/pypdf/files/9150656/ST.2019.PDF"
    name = "st2019.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    txt = reader.pages[3].extract_text()
    # The following text is contained in two different cells:
    assert txt.find("有限公司") > 0
    assert txt.find("郑州分公司") > 0
    # 有限公司 = limited company
    # 郑州分公司 = branch office in Zhengzhou
    # First cell (see page 4/254):
    assert txt.find("郑州药素电子商务有限公司") > 0
    # Next cell (first cell in next line):
    assert txt.find("郑州分公司") > 0


@pytest.mark.enable_socket
@pytest.mark.slow
@pytest.mark.parametrize(
    ("url", "name"),
    [
        # keyerror_potentially_empty_page
        (
            "https://github.com/user-attachments/files/18381736/tika-964029.pdf",
            "tika-964029.pdf",
        ),
        # 1140 / 1141:
        (
            "https://github.com/user-attachments/files/18381702/tika-932446.pdf",
            "tika-932446.pdf",
        ),
        # iss 1134:
        (
            "https://github.com/py-pdf/pypdf/files/9150656/ST.2019.PDF",
            "iss_1134.pdf",
        ),
        # iss 1:
        (
            "https://github.com/py-pdf/pypdf/files/9432350/Work.Flow.From.Check.to.QA.pdf",
            "WFCA.pdf",
        ),
        (
            "https://github.com/user-attachments/files/18381736/tika-964029.pdf",
            "tika-964029.pdf",
        ),  # single_quote_op
        (
            "https://github.com/py-pdf/pypdf/files/9428434/TelemetryTX_EM.pdf",
            "tika-964029.pdf",
        ),  # no_ressources
        (
            # https://www.itu.int/rec/T-REC-X.25-199610-I/en
            "https://github.com/py-pdf/pypdf/files/12423313/T-REC-X.25-199610-I.PDF-E.pdf",
            "T-REC-X.25-199610-I!!PDF-E.pdf",
        ),
    ],
)
def test_extract_text(url, name):
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    for page in reader.pages:
        page.extract_text()


@pytest.mark.enable_socket
@pytest.mark.slow
def test_extract_text_page_pdf_impossible_decode_xform(caplog):
    url = "https://github.com/user-attachments/files/18381748/tika-972962.pdf"
    name = "tika-972962.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    for page in reader.pages:
        page.extract_text()
    warn_msgs = normalize_warnings(caplog.text)
    assert warn_msgs == [""]  # text extraction recognise no text


@pytest.mark.enable_socket
@pytest.mark.slow
def test_extract_text_operator_t_star():  # L1266, L1267
    url = "https://github.com/user-attachments/files/18381740/tika-967943.pdf"
    name = "tika-967943.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    for page in reader.pages:
        page.extract_text()


def test_extract_text_visitor_callbacks():
    """
    Extract text in rectangle-objects or simple tables.

    This test uses GeoBase_NHNC1_Data_Model_UML_EN.pdf.
    It extracts the labels of package-boxes in Figure 2.
    It extracts the texts in table "REVISION HISTORY".
    """
    import logging

    class PositionedText:
        """
        Specify a text with coordinates, font-dictionary and font-size.

        The font-dictionary may be None in case of an unknown font.
        """

        def __init__(self, text, x, y, font_dict, font_size) -> None:
            # TODO \0-replace: Encoding issue in some files?
            self.text = text.replace("\0", "")
            self.x = x
            self.y = y
            self.font_dict = font_dict
            self.font_size = font_size

        def get_base_font(self) -> str:
            """
            Gets the base font of the text.

            Return UNKNOWN in case of an unknown font.
            """
            if (self.font_dict is None) or "/BaseFont" not in self.font_dict:
                return "UNKNOWN"
            return self.font_dict["/BaseFont"]

    class Rectangle:
        """Specify a rectangle."""

        def __init__(self, x, y, w, h) -> None:
            self.x = x.as_numeric()
            self.y = y.as_numeric()
            self.w = w.as_numeric()
            self.h = h.as_numeric()

        def contains(self, x, y) -> bool:
            return (
                self.x <= x <= (self.x + self.w)
                and self.y <= y <= (self.y + self.h)
            )

    def extract_text_and_rectangles(
        page: PageObject, rect_filter=None
    ) -> Tuple[List[PositionedText], List[Rectangle]]:
        """
        Extracts texts and rectangles of a page of type pypdf._page.PageObject.

        This function supports simple coordinate transformations only.
        The optional rect_filter-lambda can be used to filter wanted
        rectangles.
        rect_filter has Rectangle as argument and must return a boolean.

        It returns a tuple containing a list of extracted texts and
        a list of extracted rectangles.
        """
        logger = logging.getLogger("extract_text_and_rectangles")

        rectangles = []
        texts = []

        def print_op_b(op, args, cm_matrix, tm_matrix) -> None:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"before: {op} at {cm_matrix}, {tm_matrix}")
            if op == b"re":
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"  add rectangle: {args}")
                w = args[2]
                h = args[3]
                r = Rectangle(args[0], args[1], w, h)
                if (rect_filter is None) or rect_filter(r):
                    rectangles.append(r)

        def print_visi(text, cm_matrix, tm_matrix, font_dict, font_size) -> None:
            if text.strip() != "":
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"at {cm_matrix}, {tm_matrix}, font size={font_size}")
                texts.append(
                    PositionedText(
                        text, tm_matrix[4], tm_matrix[5], font_dict, font_size
                    )
                )

        visitor_before = print_op_b
        visitor_text = print_visi

        page.extract_text(
            visitor_operand_before=visitor_before, visitor_text=visitor_text
        )

        return (texts, rectangles)

    def extract_table(
        texts: List[PositionedText], rectangles: List[Rectangle]
    ) -> List[List[List[PositionedText]]]:
        """
        Extracts a table containing text.

        It is expected that each cell is marked by a rectangle-object.
        It is expected that the page contains one table only.
        It is expected that the table contains at least 3 columns and 2 rows.

        A list of rows is returned.
        Each row contains a list of cells.
        Each cell contains a list of PositionedText-elements.
        """
        logger = logging.getLogger("extractTable")

        # Step 1: Count number of x- and y-coordinates of rectangles.
        # Remove duplicate rectangles. The new list is rectangles_filtered.
        col2count = {}
        row2count = {}
        key2rectangle = {}
        rectangles_filtered = []
        for r in rectangles:
            # Coordinates may be inaccurate, we have to round.
            # cell: x=72.264, y=386.57, w=93.96, h=46.584
            # cell: x=72.271, y=386.56, w=93.96, h=46.59
            key = f"{round(r.x, 0)} {round(r.y, 0)} {round(r.w, 0)} {round(r.h, 0)}"
            if key in key2rectangle:
                # Ignore duplicate rectangles
                continue
            key2rectangle[key] = r
            if r.x not in col2count:
                col2count[r.x] = 0
            if r.y not in row2count:
                row2count[r.y] = 0
            col2count[r.x] += 1
            row2count[r.y] += 1
            rectangles_filtered.append(r)

        # Step 2: Look for texts in rectangles.
        rectangle2texts = {}
        for text in texts:
            for r in rectangles_filtered:
                if r.contains(text.x, text.y):
                    if r not in rectangle2texts:
                        rectangle2texts[r] = []
                    rectangle2texts[r].append(text)
                    break

        # PDF: y = 0 is expected at the bottom of the page.
        # So the header-row is expected to have the highest y-value.
        rectangles.sort(key=lambda r: (-r.y, r.x))

        # Step 3: Build the list of rows containing list of cell-texts.
        rows = []
        row_nr = 0
        col_nr = 0
        curr_y = None
        curr_row = None
        for r in rectangles_filtered:
            if col2count[r.x] < 3 or row2count[r.y] < 2:
                # We expect at least 3 columns and 2 rows.
                continue
            if curr_y is None or r.y != curr_y:
                # next row
                curr_y = r.y
                col_nr = 0
                row_nr += 1
                curr_row = []
                rows.append(curr_row)
            col_nr += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"cell: x={r.x}, y={r.y}, w={r.w}, h={r.h}")
            if r not in rectangle2texts:
                curr_row.append("")
                continue
            cell_texts = list(rectangle2texts[r])
            curr_row.append(cell_texts)

        return rows

    def extract_cell_text(cell_texts: List[PositionedText]) -> str:
        """Joins the text-objects of a cell."""
        return ("".join(t.text for t in cell_texts)).strip()

    # Test 1: We test the analysis of page 7 "2.1 LRS model".
    reader = PdfReader(RESOURCE_ROOT / "GeoBase_NHNC1_Data_Model_UML_EN.pdf")
    page_lrs_model = reader.pages[6]

    # We ignore the invisible large rectangles.
    def ignore_large_rectangles(r) -> bool:
        return r.w < 400 and r.h < 400

    (texts, rectangles) = extract_text_and_rectangles(
        page_lrs_model, rect_filter=ignore_large_rectangles
    )

    # We see ten rectangles (5 tabs, 5 boxes) but there are 64 rectangles
    # (including some invisible ones).
    assert len(rectangles) == 60
    rectangle2texts = {}
    for t in texts:
        for r in rectangles:
            if r.contains(t.x, t.y):
                texts = rectangle2texts.setdefault(r, [])
                texts.append(t.text.strip())
                break
    # Five boxes and the figure-description below.
    assert len(rectangle2texts) == 6
    box_texts = [" ".join(texts) for texts in rectangle2texts.values()]
    assert "Hydro Network" in box_texts
    assert "Hydro Events" in box_texts
    assert "Metadata" in box_texts
    assert "Hydrography" in box_texts
    assert "Toponymy (external model)" in box_texts

    # Test 2: Parse table "REVISION HISTORY" on page 3.
    page_revisions = reader.pages[2]
    # We ignore the second table, therefore: r.y > 350

    def filter_first_table(r) -> bool:
        return r.w > 1 and r.h > 1 and r.w < 400 and r.h < 400 and r.y > 350

    (texts, rectangles) = extract_text_and_rectangles(
        page_revisions, rect_filter=filter_first_table
    )
    rows = extract_table(texts, rectangles)

    assert len(rows) == 9
    assert extract_cell_text(rows[0][0]) == "Date"
    assert extract_cell_text(rows[0][1]) == "Version"
    assert extract_cell_text(rows[0][2]) == "Description"
    assert extract_cell_text(rows[1][0]) == "September 2002"
    # The line break between "English review;"
    # and "Remove" is not detected.
    assert (
        extract_cell_text(rows[6][2])
        == "English review;Remove the UML model for the Segmented view."
    )
    assert extract_cell_text(rows[7][2]) == "Update from the March Workshop comments."

    # Check the fonts. We check: /F2 9.96 Tf [...] [(Dat)-2(e)] TJ
    text_dat_of_date = rows[0][0][0]
    assert text_dat_of_date.font_dict is not None
    assert text_dat_of_date.font_dict["/Name"] == "/F2"
    assert text_dat_of_date.get_base_font() == "/Arial,Bold"
    assert text_dat_of_date.font_dict["/Encoding"] == "/WinAnsiEncoding"
    assert text_dat_of_date.font_size == 9.96
    # Check: /F1 9.96 Tf [...] [(S)4(ep)4(t)-10(em)-20(be)4(r)-3( 20)4(02)] TJ
    texts = rows[1][0][0]
    assert texts.font_dict is not None
    assert texts.font_dict["/Name"] == "/F1"
    assert texts.get_base_font() == "/Arial"
    assert texts.font_dict["/Encoding"] == "/WinAnsiEncoding"
    assert text_dat_of_date.font_size == 9.96

    # Test 3: Read a table in a document using a non-translating
    #         but scaling Tm-operand
    reader = PdfReader(RESOURCE_ROOT / "Sample_Td-matrix.pdf")
    page_td_model = reader.pages[0]
    # We store the translations of the Td-executions.
    list_td = []

    def visitor_td(op, args, cm, tm) -> None:
        if op == b"Td":
            list_td.append((tm[4], tm[5]))

    page_td_model.extract_text(visitor_operand_after=visitor_td)
    assert len(list_td) == 4
    # Check the translations of the four Td-executions.
    assert list_td[0] == (210.0, 110.0)
    assert list_td[1] == (410.0, 110.0)
    assert list_td[2] == (210.0, 210.0)
    assert list_td[3] == (410.0, 210.0)


@pytest.mark.parametrize(
    ("pdf_path", "password", "embedded", "unembedded"),
    [
        (
            RESOURCE_ROOT / "crazyones.pdf",
            None,
            {
                "/HHXGQB+SFTI1440",
                "/TITXYI+SFRM0900",
                "/YISQAD+SFTI1200",
            },
            set(),
        ),
        (
            RESOURCE_ROOT / "attachment.pdf",
            None,
            {
                "/HHXGQB+SFTI1440",
                "/TITXYI+SFRM0900",
                "/YISQAD+SFTI1200",
            },
            set(),
        ),
        (
            RESOURCE_ROOT / "libreoffice-writer-password.pdf",
            "openpassword",
            {"/BAAAAA+DejaVuSans"},
            set(),
        ),
        (
            RESOURCE_ROOT / "imagemagick-images.pdf",
            None,
            set(),
            {"/Helvetica"},
        ),
        (RESOURCE_ROOT / "imagemagick-lzw.pdf", None, set(), set()),
        (
            RESOURCE_ROOT / "reportlab-inline-image.pdf",
            None,
            set(),
            {"/Helvetica"},
        ),
        # fonts in annotations
        (
            RESOURCE_ROOT / "FormTestFromOo.pdf",
            None,
            {"/CAAAAA+LiberationSans", "/EAAAAA+SegoeUI", "/BAAAAA+LiberationSerif"},
            {"/LiberationSans", "/ZapfDingbats"},
        ),
    ],
)
def test_get_fonts(pdf_path, password, embedded, unembedded):
    reader = PdfReader(pdf_path, password=password)
    a = set()
    b = set()
    for page in reader.pages:
        a_tmp, b_tmp = page._get_fonts()
        a = a.union(a_tmp)
        b = b.union(b_tmp)
    assert (a, b) == (embedded, unembedded)


@pytest.mark.enable_socket
def test_get_fonts2():
    url = "https://github.com/py-pdf/pypdf/files/12618104/WS_T.483.8-2016.pdf"
    name = "WS_T.483.8-2016.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    assert reader.pages[1]._get_fonts() == (
        {
            "/E-HZ9-PK7483a5-Identity-H",
            "/SSJ-PK748200005d9-Identity-H",
            "/QGNGZS+FzBookMaker1DlFont10536872415",
            "/E-BZ9-PK748344-Identity-H",
            "/E-FZ9-PK74836f-Identity-H",
            "/O9-PK748464-Identity-H",
            "/QGNGZR+FzBookMaker0DlFont00536872414",
            "/SSJ-PK748200005db-Identity-H",
            "/F-BZ9-PK7483cb-Identity-H",
            "/SSJ-PK748200005da-Identity-H",
            "/H-SS9-PK748200005e0-Identity-H",
            "/H-HT9-PK748200005e1-Identity-H",
        },
        set(),
    )
    assert reader.pages[2]._get_fonts() == (
        {
            "/E-HZ9-PK7483a5-Identity-H",
            "/E-FZ9-PK74836f-Identity-H",
            "/E-BZ9-PK748344-Identity-H",
            "/QGNGZT+FzBookMaker0DlFont00536872418",
            "/O9-PK748464-Identity-H",
            "/F-BZ9-PK7483cb-Identity-H",
            "/H-SS9-PK748200005e0-Identity-H",
            "/QGNGZU+FzBookMaker1DlFont10536872420",
            "/H-HT9-PK748200005e1-Identity-H",
        },
        set(),
    )


def test_annotation_getter():
    pdf_path = RESOURCE_ROOT / "commented.pdf"
    reader = PdfReader(pdf_path)
    annotations = reader.pages[0].annotations
    assert annotations is not None
    assert isinstance(annotations[0], IndirectObject)

    annot_dict = dict(annotations[0].get_object())
    assert "/P" in annot_dict
    assert isinstance(annot_dict["/P"], IndirectObject)
    del annot_dict["/P"]

    annot_dict["/Popup"] = annot_dict["/Popup"].get_object()
    del annot_dict["/Popup"]["/P"]
    del annot_dict["/Popup"]["/Parent"]
    assert annot_dict == {
        "/Type": "/Annot",
        "/Subtype": "/Text",
        "/Rect": ArrayObject(
            [
                270.75,
                596.25,
                294.75,
                620.25,
            ]
        ),
        "/Contents": "Note in second paragraph",
        "/C": ArrayObject([1, 1, 0]),
        "/M": "D:20220406191858+02'00",
        "/Popup": DictionaryObject(
            {
                "/M": "D:20220406191847+02'00",
                "/Rect": ArrayObject([294.75, 446.25, 494.75, 596.25]),
                "/Subtype": "/Popup",
                "/Type": "/Annot",
            }
        ),
        "/T": "moose",
    }


def test_annotation_setter(pdf_file_path):
    # Arange
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    writer = PdfWriter()
    writer.add_page(page)
    with pytest.raises(ValueError):
        writer.add_page(DictionaryObject())

    # Act
    page_number = 0
    page_link = writer.get_object(writer._pages)["/Kids"][page_number]
    annot_dict = {
        NameObject("/P"): page_link,
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Text"),
        NameObject("/Rect"): ArrayObject(
            [
                FloatObject(270.75),
                FloatObject(596.25),
                FloatObject(294.75),
                FloatObject(620.25),
            ]
        ),
        NameObject("/Contents"): TextStringObject("Note in second paragraph"),
        NameObject("/C"): ArrayObject([FloatObject(1), FloatObject(1), FloatObject(0)]),
        NameObject("/M"): TextStringObject("D:20220406191858+02'00"),
        NameObject("/Popup"): DictionaryObject(
            {
                NameObject("/M"): TextStringObject("D:20220406191847+02'00"),
                NameObject("/Rect"): ArrayObject(
                    [
                        FloatObject(294.75),
                        FloatObject(446.25),
                        FloatObject(494.75),
                        FloatObject(596.25),
                    ]
                ),
                NameObject("/Subtype"): NameObject("/Popup"),
                NameObject("/Type"): TextStringObject("/Annot"),
            }
        ),
        NameObject("/T"): TextStringObject("moose"),
    }
    arr = ArrayObject()
    page.annotations = arr

    # Delete Annotations
    page.annotations = None

    d = DictionaryObject(annot_dict)
    ind_obj = writer._add_object(d)
    arr.append(ind_obj)

    # Assert manually
    with open(pdf_file_path, "wb") as fp:
        writer.write(fp)


@pytest.mark.enable_socket
@pytest.mark.xfail(reason="#1091")
def test_text_extraction_issue_1091():
    url = "https://github.com/user-attachments/files/18381737/tika-966635.pdf"
    name = "tika-966635.pdf"
    stream = BytesIO(get_data_from_url(url, name=name))
    with pytest.warns(PdfReadWarning):
        reader = PdfReader(stream)
    for page in reader.pages:
        page.extract_text()


@pytest.mark.enable_socket
def test_empyt_password_1088():
    url = "https://github.com/user-attachments/files/18381712/tika-941536.pdf"
    name = "tika-941536.pdf"
    stream = BytesIO(get_data_from_url(url, name=name))
    reader = PdfReader(stream)
    len(reader.pages)


@pytest.mark.enable_socket
def test_old_habibi():
    # this habibi has multiple characters associated with the h
    reader = PdfReader(SAMPLE_ROOT / "015-arabic/habibi.pdf")
    txt = reader.pages[0].extract_text()  # very odd file
    # extract from acrobat reader "حَبيبي habibi􀀃􀏲􀎒􀏴􀎒􀎣􀋴
    assert "habibi" in txt
    assert "حَبيبي" in txt


@pytest.mark.samples
def test_read_link_annotation():
    reader = PdfReader(SAMPLE_ROOT / "016-libre-office-link/libre-office-link.pdf")
    assert len(reader.pages[0].annotations) == 1
    annot = dict(reader.pages[0].annotations[0].get_object())
    expected = {
        "/Type": "/Annot",
        "/Subtype": "/Link",
        "/A": DictionaryObject(
            {
                "/S": "/URI",
                "/Type": "/Action",
                "/URI": "https://martin-thoma.com/",
            }
        ),
        "/Border": ArrayObject([0, 0, 0]),
        "/Rect": [
            92.043,
            771.389,
            217.757,
            785.189,
        ],
    }

    assert set(expected.keys()) == set(annot.keys())
    del expected["/Rect"]
    del annot["/Rect"]
    assert annot == expected


@pytest.mark.enable_socket
def test_no_resources():
    url = "https://github.com/py-pdf/pypdf/files/9572045/108.pdf"
    name = "108.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    page_one = reader.pages[0]
    page_two = reader.pages[0]
    page_one.merge_page(page_two)


def test_merge_page_reproducible_with_proc_set():
    page1 = PageObject.create_blank_page(width=100, height=100)
    page2 = PageObject.create_blank_page(width=100, height=100)

    ordered = sorted(NameObject(f"/{x}") for x in range(20))

    shuffled = list(ordered)
    shuffle(shuffled)

    # each page has some overlap in their /ProcSet, and they're in a weird order
    page1[NameObject("/Resources")][NameObject("/ProcSet")] = ArrayObject(shuffled[:15])
    page2[NameObject("/Resources")][NameObject("/ProcSet")] = ArrayObject(shuffled[5:])
    page1.merge_page(page2)

    assert page1[NameObject("/Resources")][NameObject("/ProcSet")] == ordered


@pytest.mark.parametrize(
    ("apage1", "apage2", "expected_result", "expected_renames"),
    [
        # simple cases:
        pytest.param({}, {}, {}, {}, id="no resources"),
        pytest.param(
            {"/1": "/v1"},
            {"/2": "/v2"},
            {"/1": "/v1", "/2": "/v2"},
            {},
            id="no overlap",
        ),
        pytest.param(
            {"/x": "/v"}, {"/x": "/v"}, {"/x": "/v"}, {}, id="overlap, matching values"
        ),
        pytest.param(
            {"/x": "/v1"},
            {"/x": "/v2"},
            {"/x": "/v1", "/x-0": "/v2"},
            {"/x": "/x-0"},
            id="overlap, different values",
        ),
        # carefully crafted names that match the renaming pattern:
        pytest.param(
            {"/x": "/v1", "/x-0": "/v1", "/x-1": "/v1"},
            {"/x": "/v2"},
            {
                "/x": "/v1",
                "/x-0": "/v1",
                "/x-1": "/v1",
                "/x-2": "/v2",
            },
            {"/x": "/x-2"},
            id="crafted, different values",
        ),
        pytest.param(
            {"/x": "/v1", "/x-0": "/v1", "/x-1": "/v"},
            {"/x": "/v"},
            {"/x": "/v1", "/x-0": "/v1", "/x-1": "/v"},
            {"/x": "/x-1"},
            id="crafted, matching value in chain",
        ),
        pytest.param(
            {"/x": "/v1"},
            {"/x": "/v2.1", "/x-0": "/v2.2"},
            {"/x": "/v1", "/x-0": "/v2.1", "/x-0-0": "/v2.2"},
            {"/x": "/x-0", "/x-0": "/x-0-0"},
            id="crafted, overlaps with previous rename, different value",
        ),
        pytest.param(
            {"/x": "/v1"},
            {"/x": "/v2", "/x-0": "/v2"},
            {"/x": "/v1", "/x-0": "/v2"},
            {"/x": "/x-0"},
            id="crafted, overlaps with previous rename, matching value",
        ),
    ],
)
def test_merge_resources(apage1, apage2, expected_result, expected_renames):
    for new_res in (False, True):
        # Arrange
        page1 = PageObject()
        page1[NameObject(PG.RESOURCES)] = DictionaryObject()
        for k, v in apage1.items():
            page1[PG.RESOURCES][NameObject(k)] = NameObject(v)

        page2 = PageObject()
        page2[NameObject(PG.RESOURCES)] = DictionaryObject()
        for k, v in apage2.items():
            page2[PG.RESOURCES][NameObject(k)] = NameObject(v)

        # Act
        result, renames = page1._merge_resources(page1, page2, PG.RESOURCES, new_res)

        # Assert
        assert result == expected_result
    assert renames == expected_renames


def test_merge_page_resources_smoke_test():
    # Arrange
    page1 = PageObject.create_blank_page(width=100, height=100)
    page2 = PageObject.create_blank_page(width=100, height=100)

    NO = NameObject

    # set up some dummy resources that overlap (or not) between the two pages
    # (note, all the edge cases are tested in test_merge_resources)
    props1 = page1[NO("/Resources")][NO("/Properties")] = DictionaryObject(
        {
            NO("/just1"): NO("/just1-value"),
            NO("/overlap-matching"): NO("/overlap-matching-value"),
            NO("/overlap-different"): NO("/overlap-different-value1"),
        }
    )
    props2 = page2[NO("/Resources")][NO("/Properties")] = DictionaryObject(
        {
            NO("/just2"): NO("/just2-value"),
            NO("/overlap-matching"): NO("/overlap-matching-value"),
            NO("/overlap-different"): NO("/overlap-different-value2"),
        }
    )
    # use these keys for some "operations", to validate renaming
    # (the operand name doesn't matter)
    contents1 = page1[NO("/Contents")] = ContentStream(None, None)
    contents1.operations = [(ArrayObject(props1.keys()), b"page1-contents")]
    contents2 = page2[NO("/Contents")] = ContentStream(None, None)
    contents2.operations = [(ArrayObject(props2.keys()), b"page2-contents")]

    expected_properties = {
        "/just1": "/just1-value",
        "/just2": "/just2-value",
        "/overlap-matching": "/overlap-matching-value",
        "/overlap-different": "/overlap-different-value1",
        "/overlap-different-0": "/overlap-different-value2",
    }
    expected_operations = [
        # no renaming
        (ArrayObject(props1.keys()), b"page1-contents"),
        # some renaming
        (
            ArrayObject(
                [
                    NO("/just2"),
                    NO("/overlap-matching"),
                    NO("/overlap-different-0"),
                ]
            ),
            b"page2-contents",
        ),
    ]

    # Act
    page1.merge_page(page2)

    # Assert
    assert page1[NO("/Resources")][NO("/Properties")] == expected_properties

    relevant_operations = [
        (op, name)
        for op, name in page1.get_contents().operations
        if name in (b"page1-contents", b"page2-contents")
    ]
    assert relevant_operations == expected_operations


@pytest.mark.enable_socket
def test_merge_transformed_page_into_blank():
    url = "https://github.com/py-pdf/pypdf/files/10768334/badges_3vjrh_7LXDZ_1-1.pdf"
    name = "badges_3vjrh_7LXDZ_1.pdf"
    r1 = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    url = "https://github.com/py-pdf/pypdf/files/10768335/badges_3vjrh_7LXDZ_2-1.pdf"
    name = "badges_3vjrh_7LXDZ_2.pdf"
    r2 = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.pages[0].merge_translated_page(r1.pages[0], 0, 0, True, True)
    writer.pages[0].merge_translated_page(r2.pages[0], 1000, 1000, True, True)
    assert (
        writer.pages[0]["/Resources"]["/Font"].raw_get("/F2+0").idnum
        != writer.pages[0]["/Resources"]["/Font"].raw_get("/F2+0-0").idnum
    )
    writer.add_blank_page(100, 100)
    for x in range(4):
        for y in range(7):
            writer.pages[1].merge_translated_page(
                r1.pages[0],
                x * r1.pages[0].trimbox[2],
                y * r1.pages[0].trimbox[3],
                True,
                True,
            )
    blank = PageObject.create_blank_page(width=100, height=100)
    assert blank.page_number is None
    inserted_blank = writer.add_page(blank)
    assert blank.page_number is None  # the inserted page is a clone
    assert inserted_blank.page_number == len(writer.pages) - 1
    writer.remove_page(inserted_blank.indirect_reference)
    assert inserted_blank.page_number is None
    inserted_blank = writer.add_page(blank)
    del writer._pages.get_object()["/Kids"][-1]
    assert inserted_blank.page_number is not None


def test_pages_printing():
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    assert str(reader.pages) == "[PageObject(0)]"
    assert len(reader.pages[0].images) == 0
    with pytest.raises(KeyError):
        reader.pages[0].images["~1~"]


@pytest.mark.enable_socket
def test_del_pages():
    url = "https://github.com/user-attachments/files/18381712/tika-941536.pdf"
    name = "tika-941536.pdf"
    writer = PdfWriter(clone_from=BytesIO(get_data_from_url(url, name=name)))
    ll = len(writer.pages)
    pp = writer.pages[1].indirect_reference
    del writer.pages[1]
    assert len(writer.pages) == ll - 1
    pages = writer._pages.get_object()
    assert pages["/Count"] == ll - 1
    assert len(pages["/Kids"]) == ll - 1
    assert pp not in pages["/Kids"]
    del writer.pages[-2]
    with pytest.raises(TypeError):
        del writer.pages["aa"]
    with pytest.raises(IndexError):
        del writer.pages[9999]
    pp = tuple(p.indirect_reference for p in writer.pages[3:5])
    ll = len(writer.pages)
    del writer.pages[3:5]
    assert len(writer.pages) == ll - 2
    for p in pp:
        assert p not in pages["/Kids"]
    # del whole arborescence
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    # error case
    pp = reader.pages[2]
    i = pp["/Parent"].get_object()["/Kids"].index(pp.indirect_reference)
    del pp["/Parent"].get_object()["/Kids"][i]
    with pytest.raises(PdfReadError):
        del reader.pages[2]

    url = "https://github.com/py-pdf/pypdf/files/13946477/panda.pdf"
    name = "iss2343b.pdf"
    writer = PdfWriter(BytesIO(get_data_from_url(url, name=name)), incremental=True)
    node, idx = writer._get_page_in_node(53)
    assert (node.indirect_reference.idnum, idx) == (11776, 1)
    node, idx = writer._get_page_in_node(10000)
    assert (node.indirect_reference.idnum, idx) == (11769, -1)
    with pytest.raises(PyPdfError):
        writer._get_page_in_node(-1)

    del writer.pages[4]  # to propagate among /Pages
    del writer.pages[:]
    assert len(writer.pages) == 0
    assert len(writer.root_object["/Pages"]["/Kids"]) == 0
    assert len(writer.flattened_pages) == 0


def test_pdf_pages_missing_type():
    pdf_path = RESOURCE_ROOT / "crazyones.pdf"
    reader = PdfReader(pdf_path)
    del reader.trailer["/Root"]["/Pages"]["/Kids"][0].get_object()["/Type"]
    reader.pages[0]
    writer = PdfWriter(clone_from=reader)
    writer.pages[0]


@pytest.mark.enable_socket
def test_merge_with_stream_wrapped_in_save_restore():
    """Test for issue #2587"""
    url = "https://github.com/py-pdf/pypdf/files/14895914/blank_portrait.pdf"
    name = "blank_portrait.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    page_one = reader.pages[0]
    assert page_one.get_contents().get_data() == b"q Q"
    page_two = reader.pages[0]
    page_one.merge_page(page_two)
    assert b"QQ" not in page_one.get_contents().get_data()


@pytest.mark.samples
def test_compression():
    """Test for issue #1897"""

    def create_stamp_pdf() -> BytesIO:
        pytest.importorskip("fpdf")
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(40, 10, "Hello World!")
        byte_string = pdf.output()
        return BytesIO(byte_string)

    template = PdfReader(create_stamp_pdf())
    template_page = template.pages[0]
    writer = PdfWriter()
    writer.append(SAMPLE_ROOT / "009-pdflatex-geotopo/GeoTopo.pdf", [1])
    nb1 = len(writer._objects)

    # 1 page only is modified
    for page in writer.pages:
        page.merge_page(template_page)
    # font is added; +1 streamobjects + 1 ArrayObject
    assert len(writer._objects) == nb1 + 1 + 2
    for page in writer.pages:
        page.compress_content_streams()
    # objects are recycled
    assert len(writer._objects) == nb1 + 1 + 2

    contents = writer.pages[0]["/Contents"]
    writer.pages[0].replace_contents(None)
    writer.pages[0].replace_contents(None)
    assert isinstance(
        writer._objects[contents.indirect_reference.idnum - 1], NullObject
    )


def test_merge_with_no_resources():
    """Test for issue #2147"""
    writer = PdfWriter()
    p0 = writer.add_blank_page(900, 1200)
    del p0["/Resources"]
    p1 = writer.add_blank_page(900, 1200)
    del p1["/Resources"]
    writer.pages[0].merge_page(p1)


def test_get_contents_from_nullobject():
    """Issue #2157"""
    writer = PdfWriter()
    page1 = writer.add_blank_page(100, 100)
    page1[NameObject("/Contents")] = writer._add_object(NullObject())
    assert page1.get_contents() is None
    page2 = writer.add_blank_page(100, 100)
    page1.merge_page(page2, over=True)


@pytest.mark.enable_socket
def test_pos_text_in_textvisitor():
    """See #2200"""
    url = "https://github.com/py-pdf/pypdf/files/12675974/page_178.pdf"
    name = "test_text_pos.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    p = ()

    def visitor_body2(text, cm, tm, fontdict, fontsize) -> None:
        nonlocal p
        if text.startswith("5425."):
            p = (tm[4], tm[5])

    reader.pages[0].extract_text(visitor_text=visitor_body2)
    assert abs(p[0] - 323.5) < 0.1
    assert abs(p[1] - 457.4) < 0.1


@pytest.mark.enable_socket
def test_pos_text_in_textvisitor2():
    """See #2075"""
    url = "https://github.com/py-pdf/pypdf/files/12318042/LegIndex-page6.pdf"
    name = "LegIndex-page6.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    x_lvl = 26
    lst = []

    def visitor_lvl(text, cm, tm, fontdict, fontsize) -> None:
        nonlocal x_lvl, lst
        if abs(tm[4] - x_lvl) < 2 and tm[5] < 740 and tm[5] > 210:
            lst.append(text.strip(" \n"))

    reader.pages[0].extract_text(visitor_text=visitor_lvl)
    assert lst == [
        "ACUPUNCTURE BOARD",
        "ACUPUNCTURISTS AND ACUPUNCTURE",
        "ADMINISTRATIVE LAW AND PROCEDURE",
        "ADMINISTRATIVE LAW, OFFICE OF",
        "ADOPTION",
        "ADULT EDUCATION",
        "ADVERTISING. See also MARKETING; and particular subject matter (e.g.,",
    ]
    x_lvl = 35
    lst = []
    reader.pages[0].extract_text(visitor_text=visitor_lvl)
    assert lst == [
        "members,  AB 1264",
        "assistants, acupuncture,  AB 1264",
        "complaints, investigations, etc.,  AB 1264",
        "day, california acupuncture,  HR 48",
        "massage services, asian,  AB 1264",
        "supervising acupuncturists,  AB 1264",
        "supportive acupuncture services, basic,  AB 1264",
        "rules and regulations—",
        "professional assistants and employees: employment and compensation,  AB 916",
        "adults, adoption of,  AB 1756",
        "agencies, organizations, etc.: requirements, prohibitions, etc.,  SB 807",
        "assistance programs, adoption: nonminor dependents,  SB 9",
        "birth certificates,  AB 1302",
        "contact agreements, postadoption—",
        "facilitators, adoption,  AB 120",
        "failed adoptions: reproductive loss leave,  SB 848",
        "hearings, adoption finalization: remote proceedings, technology, etc.,  SB 21",
        "native american tribes,  AB 120",
        "parental rights, reinstatement of,  AB 20",
        "parents, prospective adoptive: criminal background checks,  SB 824",
        "services, adult educational,  SB 877",
        "week, adult education,  ACR 31",
        "alcoholic beverages: tied-house restrictions,  AB 546",
        "campaign re social equity, civil rights, etc.,  SB 447",
        "cannabis,  AB 794",
        "elections. See ELECTIONS.",
        "false, misleading, etc., advertising—",
        "hotels, short-term rentals, etc., advertised rates: mandatory fee disclosures,  SB 683",
        "housing rental properties advertised rates: disclosures,  SB 611",
    ]


@pytest.mark.enable_socket
def test_missing_basefont_in_type3():
    """Cf #2289"""
    url = "https://github.com/py-pdf/pypdf/files/13307713/missing-base-font.pdf"
    name = "missing-base-font.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url, name=name)))
    reader.pages[0]._get_fonts()


def test_invalid_index():
    src_abs = RESOURCE_ROOT / "git.pdf"
    reader = PdfReader(src_abs)
    with pytest.raises(TypeError):
        _ = reader.pages["0"]


def test_negative_index():
    src_abs = RESOURCE_ROOT / "git.pdf"
    reader = PdfReader(src_abs)
    assert reader.pages[0] == reader.pages[-1]


def test_get_contents_as_bytes():
    writer = PdfWriter(RESOURCE_ROOT / "crazyones.pdf")
    co = writer.pages[0]["/Contents"][0]
    expected = co.get_data()
    assert writer.pages[0]._get_contents_as_bytes() == expected
    writer.pages[0][NameObject("/Contents")] = writer.pages[0]["/Contents"][0]
    assert writer.pages[0]._get_contents_as_bytes() == expected


def test_recursive_get_page_from_node():
    writer = PdfWriter(RESOURCE_ROOT / "crazyones.pdf", incremental=True)
    writer.root_object["/Pages"].get_object()[
        NameObject("/Parent")
    ] = writer.root_object["/Pages"].indirect_reference
    with pytest.raises(PyPdfError):
        writer.add_page(writer.pages[0])
    writer = PdfWriter(RESOURCE_ROOT / "crazyones.pdf", incremental=True)
    writer.insert_page(writer.pages[0], -1)
    with pytest.raises(ValueError):
        writer.insert_page(writer.pages[0], -10)
