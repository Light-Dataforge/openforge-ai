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

A local Ollama service with qwen2.5:1.5b can provide drafting through
127.0.0.1:11434. Provider requests bypass HTTP proxies and contain only the selected
retrieved passages/question. No tools or external endpoints are exposed to the
model. A generated answer must include valid source references; failures return
explicitly labeled source excerpts. Source cards identify retrieved text, not a
semantic proof that every generated claim is correct. No paid fallback is used.
The runtime/model are not automatically installed or downloaded by the app.
The local runtime has been exercised with the original diagnostics below.

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

Saved notes can be downloaded as a Markdown research brief with source filenames and page numbers. Explicit programming-language questions use conservative extraction of known language names from retrieved passages; this can miss unlisted languages and does not establish proficiency.

### Experimental local semantic retrieval

Keyword search remains the default. To test hybrid retrieval, install
`all-minilm:22m` in the same local Ollama runtime and start this app with
`--semantic-search`. Documents and questions are embedded through loopback only.
No cloud embedding API is used.

The ranker merges lexical and embedding ranks using reciprocal rank fusion
(k=60). New semantic candidates require cosine similarity at least 0.40.
This threshold was calibrated on the small original diagnostic below; it is not
a probability of correctness or validated across arbitrary documents.
It examines at most 200 chunks and embeds the first 1000 characters of each;
large projects, busy embedding work, missing runtime, invalid responses or a
20-second embedding budget trigger keyword fallback. Responses include
`retrieval_mode` so callers can distinguish hybrid results from fallback.
The 512-entry embedding cache is in memory and disappears on restart.
A retrieved passage does not establish that an answer is supported.

Run the small original English diagnostic with the document environment:

```sh
python -m apps.document_workspace.evaluate_retrieval \
  examples/document-retrieval-eval.json --output retrieval-evaluation.json
```

This diagnostic reports top-page agreement on five answerable paraphrases and
two unrelated questions. It is not a representative benchmark or an evaluation
of generated answers, citation entailment, OCR, tables, or multilingual quality.

Use `examples/document-retrieval-holdout.json` with the same command for the held-out phrasing check. It shares the original corpus and does not establish performance on independent documents. Keep calibration and hold-out results separate.


## Generated-answer diagnostics

Generation now requests exact supporting quotes and source numbers. Quotes must
occur in the retrieved excerpts, and every cited source must have a quote. A
second local model call checks whether the answer addresses the requested fact.
Explicitly unsupported answers display **Insufficient evidence** and are preserved
with that label in conversation exports. Invalid output or unavailable generation
returns labeled source excerpts. These checks do not prove factual entailment.

An obvious instruction-like passage triggers a conservative refusal before model
inference. This heuristic can reject legitimate discussions of prompt injection;
it is not comprehensive prompt-injection protection.

Run the original excerpt-only diagnostic with a running local model:

```sh
python -m apps.document_workspace.evaluate_answers examples/document-answer-eval.json --output answer-evaluation.json
python -m apps.document_workspace.evaluate_answers examples/document-answer-holdout.json --output answer-holdout.json
```

The expanded 17-case calibration run passed 16 checks, including six
unsupported-fact questions (one after a changed-fact follow-up) and one
malicious-document case. A separate six-case held-out document run passed all six
checks before the follow-up correction; its final rerun is recorded separately. One answerable return-exclusion
question was refused. The unchanged earlier outputs pass 14 checks under the same
grading criteria: they invented a check-in time and followed a malicious document
instruction. These tiny original English fixtures isolate answer generation from
retrieval and PDF extraction; they are not a general accuracy benchmark. String
checks and valid citation numbers do not establish that every claim is supported.
The verifier adds latency and may wrongly reject supported answers. All inference
runs locally; no paid fallback is configured.

## Evidence tables

Open **Evidence tables** in a project's sidebar to investigate multiple documents
across a set of research questions. Choose 1–10 documents, enter 1–6 questions
(one per line), or start with the research-paper or policy presets. Each cell
retains up to two document-scoped keyword search passages and page citations.
This workflow does not require a running model. Retrieval matches are candidate
evidence, not answers; a missing match does not establish absence.

Open cited pages, add your own findings, and label cells Not reviewed, Supported
(your review), or Needs follow-up. A cell without a retrieved passage cannot be
marked Supported. Findings and review labels persist locally, and revision checks
prevent another browser tab from silently overwriting an edit. Reopen a changed
table before retrying a conflicting save.

Tables are saved snapshots, not live queries; later uploads do not change their
contents. Create another table for a different question set or document selection.
The workspace allows 100 saved tables. CSV export includes one row per document
and question, findings, review labels, source pages, and excerpts; formula-like
text is neutralized for spreadsheet import. No paid model or cloud service is used.
