# Streaming Data with pypdf

In some cases you might want to avoid saving things explicitly as a file
to disk, e.g. when you want to store the PDF in a database or AWS S3.

pypdf supports streaming data to a file-like object:

```python
from io import BytesIO

# Prepare example
with open("example.pdf", "rb") as fh:
    bytes_stream = BytesIO(fh.read())

# Read from bytes_stream
reader = PdfReader(bytes_stream)

# Write to bytes_stream
writer = PdfWriter()
with BytesIO() as bytes_stream:
    writer.write(bytes_stream)
```

## Writing a PDF directly to AWS S3

Suppose you want to manipulate a PDF and write it directly to AWS S3 without having
to write the document to a file first. We have the original PDF in `raw_bytes_data` as `bytes`
and want to set `my-secret-password`:

```python
from io import BytesIO

import boto3
from pypdf import PdfReader, PdfWriter


reader = PdfReader(BytesIO(raw_bytes_data))
writer = PdfWriter()

# Add all pages to the writer
for page in reader.pages:
    writer.add_page(page)

# Add a password to the new PDF
writer.encrypt("my-secret-password")

# Save the new PDF to a file
with BytesIO() as bytes_stream:
    writer.write(bytes_stream)
    bytes_stream.seek(0)
    s3 = boto3.client("s3")
    s3.write_get_object_response(
        Body=bytes_stream, RequestRoute=request_route, RequestToken=request_token
    )
```

## Reading PDFs directly from cloud services

One option is to first download the file and then pass the local file path to `PdfReader`.
Another option is to get a byte stream.

For AWS S3 it works like this:

```python
from io import BytesIO

import boto3
from pypdf import PdfReader


s3 = boto3.client("s3")
obj = s3.get_object(Body=csv_buffer.getvalue(), Bucket="my-bucket", Key="my/doc.pdf")
reader = PdfReader(BytesIO(obj["Body"].read()))
```

To use with Google Cloud storage:

```python
from io import BytesIO

from google.cloud import storage

# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] must be set
storage_client = storage.Client()
blob = storage_client.bucket("my-bucket").blob("mydoc.pdf")
file_stream = BytesIO()
blob.download_to_file(file_stream)
reader = PdfReader(file_stream)
```
