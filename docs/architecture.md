# PDF Tech → HTML — V2 Architecture

## Overview

Convert technical PDFs to faithful HTML — preserving text as structured HTML, tables as semantic `<table>` elements, and diagrams as live Mermaid/PlantUML code.

## Pipeline (V2)

```
PDF Upload → Pre-Validation Gate → Docling Parse → Element List
  → Diagram Type Classifier → Format-Specific Pipeline
  → Jinja2 Assembly → HTML + Assets
```

### 1. Pre-Validation Gate

Check PDF before processing:
- **Encrypted?** → Return error: "Please decrypt"
- **>200 pages?** → Return error: "Split file"
- **Scanned?** → Route to Surya OCR + deskew
- **Native PDF** → Route to Docling

### 2. Docling Parse

- Extract text blocks (with reading order, multi-column)
- Extract tables (as Pandas DataFrames)
- Detect figures (bounding boxes + cropped images)
- Output: unified `DoclingDocument`

### 3. Diagram Type Classifier

CLIP + fine-grained classifier to detect:
- `flowchart / block` → Mermaid pipeline
- `UML` → PlantUML pipeline
- `BPMN` → BPMN XML pipeline
- `circuit / schematic` → SVG (skip AI)
- `wireframe / UI` → Image (skip AI)
- `chemical` → SMILES pipeline (OSRA/DECIMER)
- `unknown` → Mermaid pipeline (best effort)

### 4. Mermaid Pipeline

```
GPT-4o Vision (+ CoT prompt)
  → Confidence Scoring (self-rate 0-100% + element count)
  → ≥70%: Round-Trip Verify (Mermaid→SVG→describe→compare)
  → <70%: Fallback Chain (Claude → Gemini → local Qwen2-VL)
  → Re-score → Round-Trip Verify
  → mmdc Validate
  → Fail: Progressive Fallback (→PlantUML→Graphviz→caption+image)
  → Pass: Jinja2 Assembly
```

### 5. HTML Assembly (Jinja2)

| Docling Element | Output |
|----------------|--------|
| Text block | `<p>`, `<h2>`, `<h3>` |
| Multi-column | CSS flex layout |
| Table | `<table>` with `<thead>`/`<tbody>` |
| Diagram | `<div class="mermaid">...` |
| Photo | `<img src="...">` |
| Equation | MathJax `\(...\)` |
| BPMN | bpmn-js viewer |

### 6. Included Assets

- Mermaid CDN (`mermaid.js`) for live rendering
- MathJax for equations
- bpmn-js for BPMN diagrams
- `smiles-drawer` for chemical structures
- User feedback UI (thumbs up/down per diagram)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python FastAPI |
| PDF Parsing | Docling (IBM, MIT) |
| OCR Fallback | Surya |
| Figure Classif. | CLIP (zero-shot) |
| Diagram AI | GPT-4o → Claude → Gemini → Qwen2-VL |
| Mermaid Valid. | mermaid-cli (mmdc) |
| HTML Templates | Jinja2 |
| Task Queue | Celery + Redis |
| Storage | Local FS / S3 |
| Diagram Render | mermaid.js CDN |
| Equations | MathPix / LaTeX-OCR |
| Chemical | OSRA / DECIMER + RDKit |
| BPMN | bpmn-js |
| Frontend | Next.js + React |

## Project Structure

```
pdf-to-html/
├── backend/
│   ├── api/
│   │   ├── main.py           # FastAPI app
│   │   ├── routes.py         # Upload, status, download endpoints
│   │   └── schemas.py        # Pydantic models
│   ├── pipeline/
│   │   ├── pre_validation.py # PDF gate (encrypted, size, scanned)
│   │   ├── parser.py         # Docling wrapper
│   │   ├── classifier.py     # Diagram type detection (CLIP)
│   │   ├── mermaid/
│   │   │   ├── converter.py  # GPT-4o vision → Mermaid
│   │   │   ├── scorer.py     # Confidence scoring
│   │   │   ├── verifier.py   # Round-trip verification
│   │   │   └── fallback.py   # Multi-model fallback chain
│   │   ├── plantuml/
│   │   │   └── converter.py  # UML-specific conversion
│   │   ├── bpmn/
│   │   │   └── converter.py  # BPMN XML conversion
│   │   ├── chemical/
│   │   │   └── converter.py  # OSRA/DECIMER → SMILES
│   │   ├── equations/
│   │   │   └── extractor.py  # MathPix/LaTeX-OCR
│   │   ├── tables/
│   │   │   └── merger.py     # Multi-page table detection
│   │   └── html/
│   │       ├── assembler.py  # Jinja2 assembly
│   │       └── templates/    # HTML templates
│   ├── models/               # ML model cache
│   ├── output/               # Generated HTML
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── package.json
│   ├── pages/
│   │   ├── index.tsx         # Upload page
│   │   ├── progress.tsx      # Processing status
│   │   └── preview.tsx       # HTML preview
│   └── components/
├── docs/
│   ├── pdf-to-html-solutions.md  # Failure mode solutions
│   └── architecture.md           # This file
├── tests/
├── README.md
└── .gitignore
```

## Cost Estimates

- ~$0.03 per 10-page PDF (with 3 diagrams)
- ~$20/month for 1,000 PDFs
- ~40s processing time per PDF

## Known Limitations

See `docs/pdf-to-html-solutions.md` for complete adversarial review.
Key unsolved problems:
- Hand-drawn diagrams (best-effort only)
- Chemical structure accuracy on complex molecules
- Semantic hallucination (multi-model ensemble reduces but doesn't eliminate)