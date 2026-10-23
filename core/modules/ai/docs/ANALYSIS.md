# File analysis and PDF reports

`POST /api/v1/ai/analyze/` accepts authenticated multipart uploads and returns an
attachment named `analysis-report.pdf` (`application/pdf`). Repeat the `files`
field for multiple inputs. Cookie authentication uses the project's existing
CSRF rules. The existing `/api/v1/ai/ask/` chatbot is unchanged.

```bash
curl --request POST http://localhost:8000/api/v1/ai/analyze/ \
  --cookie cookies.txt \
  --header "X-CSRFToken: <csrftoken from your cookie jar>" \
  --form "files=@meeting.png" \
  --form "files=@document.pdf" \
  --output analysis-report.pdf
```

Check the HTTP status before saving a response as PDF: unsuccessful requests
return JSON errors. Browser clients should send `credentials: "include"`, a
`FormData` with repeated `files` fields, and the CSRF header. Let the browser set
the multipart `Content-Type` and boundary.

## Browser tester

With Django running, open `http://localhost:8000/api/v1/ai/test/`, enter your
account email and password, and click **Log in**. Then select files and click
**Send files**. The page displays the HTTP status and response body,
or a download link if the response is a PDF. No separate server is needed.
Login uses `/api/v1/login/` and browser session cookies, without redirects.
The password field is cleared after each login attempt. Without a valid session, the API
returns its normal authentication error. Each submission calls the real backend.

## Processing

The multipart uploader accepts JPEG, PNG, static WebP and PDF. Content is checked
with Pillow or pypdf, independently of the supplied extension and MIME type.
Encrypted, empty, malformed and over-limit documents are rejected. PDFs are sent
intact to Gemini so scanned pages and visual elements can be analyzed without
assuming extractable text. Image pixels and animation are checked before decode.

All inputs are validated before the first provider call. Each file is analyzed
once with a separate structured prompt, using the existing Gemini SDK client and
credentials. Results are validated for required fields, types and lengths before
PDF generation. No document instructions are executed, and model text is escaped
before rendering. Input files and analysis results are held only for the request;
this endpoint does not publish files to Cloudinary or create database records.
Django may spool uploads to temporary disk according to its existing handlers.
The existing idempotency middleware may cache the PDF response when an
`Idempotency-Key` header is supplied.

If any file fails, processing stops and **no partial PDF is returned**. Analysis
errors include the file name, its one-based index, a reason, and a clear detail.
Validation errors appear under `files`. Provider quota errors retain status 429;
provider failures use 500; invalid inputs or model output use 400. Already
completed provider calls may still consume quota when a later file fails.

The report records generation time, file count, each file name, document type,
summary, observed facts, inferences and limitations. Bundled TrueType fonts
support Portuguese accents. Each file starts a separate section/page, with
automatic page breaks for long content. Schema validation checks structure, not
factual accuracy: review generated information against the original files.

## Configuration

Set these optional environment variables before starting the application. They
are read inside the AI module; global settings and `.env.example` are unchanged.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | Existing configuration | Shared Gemini credentials |
| `AI_ANALYSIS_MODEL` | Existing chatbot model constant | Model for file analysis only; must support multimodal inputs and structured JSON |
| `AI_ANALYSIS_MAX_FILES` | `5` | Files per request |
| `AI_ANALYSIS_MAX_FILE_BYTES` | `5242880` | Bytes per file (5 MiB) |
| `AI_ANALYSIS_MAX_TOTAL_BYTES` | `15728640` | Combined bytes (15 MiB) |
| `AI_ANALYSIS_MAX_PDF_PAGES` | `30` | Pages per PDF |
| `AI_ANALYSIS_MAX_IMAGE_PIXELS` | `20000000` | Decoded pixels per image |
| `AI_ANALYSIS_TIMEOUT_MS` | `60000` | Provider timeout per file |

Use positive integer limits. Keep upload and proxy request limits consistent
with these values. This synchronous endpoint uses inline bytes and one provider
attempt per file, without automatic retries. The timeout applies per call;
configure the deployment request timeout for the intended batch size.

Dependencies are declared in `pyproject.toml` and `pdm.lock`; run `pdm sync` to
install them. Run module tests with:

```bash
pdm run manage.py test core.modules.ai
```

Tests mock Gemini calls and do not send files or use API quota.

References: [Gemini document processing](https://ai.google.dev/gemini-api/docs/document-processing),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output),
[pypdf PdfReader](https://pypdf.readthedocs.io/en/latest/modules/PdfReader.html),
[ReportLab fonts](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/).
