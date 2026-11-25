# OpenForge document workspace

Local single-user application for real PDF uploads, page citations, searchable
passages, saved conversations and notes. Data stays in a private local SQLite
store outside the source checkout. A configured local Ollama model can produce
cited answers; without it the app explicitly returns retrieved source excerpts.
No paid API, fake answer, public upload endpoint or hosted backend is implied.

```sh
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r apps/document_workspace/requirements.txt
.venv-docs/bin/python -m apps.document_workspace --data-dir /PRIVATE/DATA/PATH
```

Open http://127.0.0.1:8766. This is loopback-only, not a multi-user or public service.
The server rejects other Host/Origin values and requires its custom header for
writes. There is no cloud account, paid service, remote model, or billing fallback.
Public hosting requires a separate authentication/storage/security design.

## What works now

Create projects, upload text-based PDFs, read their extracted pages or original
file, search sources, ask questions, open page citations/highlights, save notes and
reopen persistent conversations. The application starts empty; the source contains
no invented user projects, documents or answers. Original testing PDFs are separate
QA artifacts, not embedded application data.

Search uses local SQLite FTS5 with English stemming. This is lexical retrieval,
not semantic embeddings. A passage can be relevant without supporting every claim;
inspect original pages. Summaries retrieve initial passages and may omit later
material. Extraction may lose layout and does not perform OCR. Encrypted/image-only
PDFs return actionable errors rather than fake parsed content.

A local Ollama service with qwen2.5:0.5b can provide drafting through
127.0.0.1:11434. Provider requests bypass HTTP proxies and contain only the selected
retrieved passages/question. No tools or external endpoints are exposed to the
model. A generated answer must include valid source references; failures return
explicitly labeled source excerpts. Source cards identify retrieved text, not a
semantic proof that every generated claim is correct. No paid fallback is used.
The runtime/model are not automatically installed or downloaded by the app.
This environment's official runtime/model downloads timed out; no successful local
model inference is claimed for this delivery.

## Resource and access scope

Uploads:15MiB each,1–200 pages,2million extracted characters per PDF. Parsing runs
in a separate child with30s timeout,20s CPU limit and memory/output limits where
supported. These are resource controls, not a full malicious-PDF sandbox. PDFs and
ancestors/host are trusted. Workspace quotas cover200documents,200MiB uploaded-PDF
bytes and20million indexed page characters; they are not a physical SQLite disk cap.
Uploads/model requests are serialized separately. Project/document relationships
and saved citations are checked in SQLite transactions.

Private storage remains outside the Git checkout. No authentication, remote team
access, billing, cloud storage, public file endpoint or public backend is included.
Do not bind this single-user server to a public interface. GitHub Pages cannot run
this Python/SQLite backend; the old static research demo is separate.
