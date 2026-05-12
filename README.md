# PDF Tech → HTML

Convert technical PDFs to faithful HTML — preserving text, tables, and diagrams as structured semantic web content.

## Architecture (V2)

```
PDF Upload → Pre-Validation Gate → Docling Parse → Diagram Type Classifier
  → Format-Specific Pipeline → Jinja2 Assembly → HTML Output
```

Supported outputs: Mermaid, PlantUML, BPMN XML, SMILES, MathJax, SVG, plain HTML tables.

## Project Structure

```
pdf-to-html/
├── backend/
│   ├── api/               # FastAPI endpoints
│   │   ├── main.py        # App setup + CORS
│   │   ├── routes.py      # /api/convert, /status, /download
│   │   └── schemas.py     # Pydantic models
│   ├── pipeline/
│   │   ├── pre_validation.py  # PDF gate (encrypted, size, scanned)
│   │   ├── parser.py          # Docling wrapper
│   │   ├── classifier.py      # CLIP diagram type detection
│   │   ├── mermaid/           # GPT-4o → Mermaid conversion
│   │   ├── equations/         # LaTeX-OCR
│   │   ├── tables/            # Multi-page table merge
│   │   └── html/              # Jinja2 assembly
│   ├── output/            # Generated HTML
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/              # Next.js (future)
├── docs/
│   ├── architecture.md    # Full V2 architecture reference
│   └── pdf-to-html-solutions.md  # Failure mode solutions
└── tests/
```

## Quick Start

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.api.main:app --reload --port 8000
```

Upload a PDF to `POST /api/convert`, poll `GET /api/status/{job_id}`, download from `GET /api/download/{job_id}`.

## Cost

~$0.03 per 10-page PDF (with 3 diagrams). ~40s processing time.

## Limitations

See [docs/pdf-to-html-solutions.md](docs/pdf-to-html-solutions.md) for a complete adversarial review.
