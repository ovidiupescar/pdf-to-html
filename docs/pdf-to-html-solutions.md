# PDF Tech → HTML — Failure Mode Solutions

**Solutions for each failure mode identified in the adversarial review**, organized by category.

---

## 🔴 Category 1 — Guaranteed Failures

### 1. Hand-drawn diagrams

| Problem | Solution |
|---------|----------|
| CLIP classifies as "photo" | **Pre-processing pipeline**: deskew → contrast enhance → denoise → super-resolution before CLIP. Raises diagram confidence significantly. |
| GPT-4o struggles with irregular shapes | **Structured prompt with chain-of-thought**: *"First describe the intent of this hand-drawn diagram. Identify shapes (rectangles, diamonds, arrows) based on rough position. Then generate tidy Mermaid."* |
| Output is unusable | **Always keep original image** alongside any Mermaid output. Let the user compare. |

**Fallback**: Use a sketch-to-diagram model (Meta's Sketch2Code alternative, or tldraw's AI make-real feature) as intermediate step.

---

### 2. Circuit diagrams / electronic schematics

| Problem | Solution |
|---------|----------|
| No text-based format supports circuits | **Detect early as "circuit diagram"** → skip LLM entirely. Embed as SVG/PNG with caption. |
| Mermaid/PlantUML cannot represent | Use **Wavedrom** for timing diagrams. Use **KiCad EESchema** format if you want a text format. |
| User expects editable output | **Offer SVG download instead** — vector, infinitely zoomable, editable in Inkscape. |

**Detection**: Use a small CNN classifier trained on circuit images (or CLIP with "a circuit diagram" class).

---

### 3. Chemical structures / molecular diagrams

| Problem | Solution |
|---------|----------|
| No text representation exists | Use **OSRA** (Optical Structure Recognition) or **DECIMER** to extract **SMILES** strings. |
| LLM cannot extract reliably | **RDKit** validates SMILES syntax (like mmdc but for chemistry). |
| HTML output | Embed as: SMILES + rendered image. Use `smiles-drawer` JS library to render in-browser. |

**Pipeline**: Image → OSRA → SMILES → RDKit validate → `smiles-drawer` in HTML.

---

### 4. BPMN 2.0 diagrams

| Problem | Solution |
|---------|----------|
| Mermaid has minimal swimlane support | Use **bpmn.io** (bpmn-js) — native BPMN format with full specification support. |
| LLM produces simplified garbage | **Detect as BPMN** → generate **Camunda BPMN XML** (.bpmn file) instead of Mermaid. |
| Output format | BPMN XML is a standard. Embed with `bpmn-js` viewer in the HTML. |

**Alternative**: PlantUML has better BPMN support than Mermaid — use as intermediate fallback.

---

### 5. UML with complex relationships

| Problem | Solution |
|---------|----------|
| Mermaid classDiagram is too basic | **Use PlantUML** for UML — it supports aggregation, composition, multiplicity, stereotypes, n-ary associations. |
| Silent drop of details | **Multi-pass extraction**: First pass extracts classes, second pass extracts relationships, merge. |
| Validation | Use **PlantUML validator** (`plantuml -checkonly`). |

**Progressive format fallback**: Mermaid → PlantUML → SVG + caption.

---

### 6. UI wireframes / screen mockups

| Problem | Solution |
|---------|----------|
| No text-based format can represent | **Detect early** → skip AI. Embed as image. |
| User expects editable result | Offer two alternatives: (1) **tldraw export** (if hand-drawn wireframe), (2) **Figma plugin** detection. |

**Honest fallback**: Not every visual artifact can be represented as text-based diagram code. Wireframes are one of them. Don't force it.

---

### 7. Mathematical equations

| Problem | Solution |
|---------|----------|
| Docling doesn't extract LaTeX | **Dedicated equation pipeline**: Detect math regions → send to **MathPix API** (best, ~$0.004/page) or **LaTeX-OCR** (pix2tex, open source). |
| GPT-4o accuracy 40-60% | Use **Nougat** (Meta) for end-to-end LaTeX extraction from PDF pages. |
| HTML output | Embed as `MathJax` math delimiters: `\( ... \)` for inline, `\[ ... \]` for display. |

---

### 8. Password-protected / encrypted PDFs

| Problem | Solution |
|---------|----------|
| Pipeline stops | **Pre-validate PDF** before processing. Check encryption status with PyMuPDF (`pdf.is_encrypted`). |
| No graceful degradation | Return **clear error message**: *"This PDF is encrypted. Please upload an unencrypted version."* |
| User has password | Add optional password field in upload form → pass to PyMuPDF for decryption. |

---

## 🟠 Category 2 — Poor Quality

### 9. Dense architecture diagrams (40-55% accuracy)

| Problem | Solution |
|---------|----------|
| LLM loses track of connections | **Chunk the diagram**: Detect dense regions → process each region separately → merge results. |
| Silent failure | **Confidence scoring**: Ask GPT-4o to self-rate (0-100%). Below 70% → flag for human review. |
| User trusts incorrect output | **Element counting**: Count nodes/edges in original vs Mermaid. Warn if mismatch. |

**Advanced**: Generate 2+ alternative Mermaid versions → let user pick the best one (ensemble).

---

### 10. Color-coded diagrams

| Problem | Solution |
|---------|----------|
| Color semantics lost | **Prompt**: *"List all colors used and their meaning. Reproduce the exact color scheme in Mermaid classDef."* |
| Monochrome output | Programmatically apply Mermaid color theme from extracted color palette. |
| Meaning invisible | Add a `<figcaption>` with the color legend: *"Red=critical, Green=ok, Yellow=warning"*. |

---

### 11. Icon-based architecture diagrams (AWS/GCP/Azure)

| Problem | Solution |
|---------|----------|
| Icons silently dropped | **Prompt**: *"Do NOT use generic letters. Extract the actual service names: 'S3', 'Lambda', 'API Gateway' — not 'A', 'B', 'C'."* |
| Service identity lost | Apply Mermaid `classDef` per service type with distinct styling. |
| Visual context missing | Keep original image as a reference thumbnail alongside the Mermaid. |

---

### 12. Multi-page tables

| Problem | Solution |
|---------|----------|
| Docling splits across pages | **Post-processing merge**: Detect table fragments with identical column structure and header patterns. |
| No header on continuation pages | Use first page's header row for all continuation fragments. |
| Implementation | Simple heuristic: same column count + first row pattern matches header → merge. |

---

### 13. Non-English text / diacritics

| Problem | Solution |
|---------|----------|
| OCR fails on Romanian/German/Chinese | Set **language hint** in Docling and OCR pipeline (`docling.document_converter(ocr_lang="ro")`). |
| Diacritics dropped (ă, î, ș, ț) | **ICU normalization** in post-processing. Mermaid output: `UTF-8` encoding enforced. |
| Worse diagram understanding | Use **multilingual vision models** (Gemini 2.5 Pro is better than GPT-4o for non-English). |

---

### 14. Scanned PDFs (image-only)

| Problem | Solution |
|---------|----------|
| OCR accuracy depends on scan quality | Use **Surya** OCR (best for scanned docs). Add deskew and contrast enhancement before OCR. |
| Low DPI, stains, handwriting | **Detect scan quality early** → if too low, suggest user re-scan at 300+ DPI. |
| Deferred to V3 but still imperfect | Accept the trade-off: scanned PDF conversion is inherently lossy. Mark output as "OCR quality" with a badge. |

---

### 15. Footnotes, endnotes, cross-references

| Problem | Solution |
|---------|----------|
| Superscript not linked to footnote | **Post-processing**: Detect superscript numbers in text → find matching footnote block at page bottom. |
| Semantic connection lost | Convert to HTML: `<sup id="fnref1"><a href="#fn1">1</a></sup>` + footnote section. |
| Docling limitation | Workaround: use relative vertical position (superscript higher than body text, footnote at very bottom). |

---

## 🟡 Category 3 — Pipeline Failure Modes

### 16. GPT-4o API rate limited or down

| Problem | Solution |
|---------|----------|
| Diagram conversion hangs | **Multiple API key rotation** — round-robin across 2-3 keys. |
| User gets partial output | **Multi-model fallback**: GPT-4o → Claude Sonnet → Gemini 2.5 Pro → local Qwen2-VL. |
| No explanation | Show status in the UI: *"Diagram conversion in queue (API rate limited)"*. |

**Architecture**: Add a fallback chain in the pipeline configuration.

---

### 17. CLIP misclassification (diagram ↔ photo)

| Problem | Solution |
|---------|----------|
| Diagram → photo (missed opportunity) | **Ensemble classifier**: CLIP + small dedicated CNN trained on diagram/photo pairs. |
| Photo → diagram (wasted cost) | **Configurable threshold**: Let users tune (0.3 = aggressive, 0.8 = conservative). |
| Silent in both directions | **Show both options**: "This was classified as a photo. Is it actually a diagram? [Yes/No]" |

**Training**: Collect 20 diagram + 20 photo examples → fine-tune a ResNet-18 in under an hour.

---

### 18. LLM hallucination (SEMANTIC — most dangerous)

| Problem | Solution |
|---------|----------|
| Mermaid is syntactically valid but semantically wrong | **Round-trip testing**: Mermaid → SVG → GPT-4o "describe this SVG" → compare description with original description. |
| Completely undetectable by mmdc | **Element counting**: Extract node count, edge count, label count from both original and Mermaid. Warn on mismatch. |
| User copies wrong diagram | **Confidence self-rating**: Ask GPT-4o to output `[CONFIDENCE: 85%]` as part of structured response. |

**Most robust solution**: **Multi-model ensemble** — generate Mermaid with GPT-4o, re-generate with Gemini, compare both with a third model. If they disagree, flag for human review.

---

### 19. Docling parsing error

| Problem | Solution |
|---------|----------|
| Partial/empty DoclingDocument | **Try-catch with fallback**: If Docling fails, fall back to PyMuPDF basic extraction. |
| No error reported to user | **Pre-validate PDF**: Check file validity, page count, encryption before sending to Docling. |
| Garbled sections | Mark degraded sections with a yellow badge: *"⚠️ Low confidence extraction — verify content"*. |

---

### 20. Large PDF memory exhaustion (100+ pages)

| Problem | Solution |
|---------|----------|
| Worker crashes | **Chunked processing**: Process PDF in 10-page batches. Stream results as each chunk completes. |
| Spinning timeout | Set a **hard page limit** with clear error: "PDF exceeds 200-page limit. Split the file." |
| No meaningful error | Track progress per page in the UI. If page 23 of 100 fails, show: *"Stopped at page 23 — memory error"*. |

---

### 21. mmdc validation false negative

| Problem | Solution |
|---------|----------|
| Valid Mermaid flagged as error | Try **multiple Mermaid themes** (default, dark, neutral). Some syntax works in one theme but not another. |
| Retry loop wastes cost | Cap retries at 2. On failure, **fall back to PlantUML** instead of retrying Mermaid. |
| Valid output discarded | Use `mermaid.parse()` API directly (gives detailed error messages, not just exit code). |

---

### 22. No human-in-the-loop

| Problem | Solution |
|---------|----------|
| Every error is silent | **Review UI**: Side-by-side original image vs generated Mermaid. Thumbs up/down per diagram. |
| Wrong output = correct output | Show **confidence badge** next to each diagram (high/medium/low). User decides. |
| No feedback | Store feedback → use as few-shot examples for next similar diagram. |

---

## 🔶 Category 4 — Systemic Weaknesses

### 23. No semantic validation

| Problem | Solution |
|---------|----------|
| mmdc checks syntax, not correctness | **SSIM comparison**: Render original diagram region and Mermaid SVG → compute structural similarity index. |
| Best defense: multi-model ensemble | gpt-4o mermaid → gemini mermaid → claude "are these equivalent?" |
| Implementation complexity | Start simple: **element counting** (node count, edge count). Price of implementation is ~50 lines of Python. |

---

### 24. No confidence scoring

| Problem | Solution |
|---------|----------|
| User can't triage which diagrams need review | **Self-confidence**: Ask LLM to output `confidence: <0-100>` in structured JSON response. |
| No signal per diagram | **Iteration count**: 0 retries = high confidence, 3 retries = low confidence. Simple and free. |
| Known vs novel types | **Type-based baseline**: Flowchart → starting 85%, circuit → always 0% (skip). |

---

### 25. Cold start per document type

| Problem | Solution |
|---------|----------|
| 100th document is no better than 1st | **Document type detection** → cache successful prompts per type. |
| No learning | **Store few-shot examples**: When user corrects a diagram, store the correction as a few-shot example for next similar diagram. |
| Simple implementation | Use semantic similarity on page layout: same column count + same figure density → likely same type. |

---

### 26. English bias

| Problem | Solution |
|---------|----------|
| Worse OCR and diagram understanding | Set **language explicitly** in ALL API calls (`lang="ro"` for Docling, `language: Romanian` in GPT-4o). |
| Degraded for European languages | Test with target languages early. **Romanian** is supported well by both Docling and GPT-4o. |
| Asian languages are harder | Use **Gemini 2.5 Pro** for non-European languages (better multilingual performance). |

---

### 27. No iterative refinement

| Problem | Solution |
|---------|----------|
| Single pass → if garbage, user gets garbage | **"Regenerate this diagram" button** per element. Second pass gets context: "Previous attempt was: X. Errors: Y." |
| No feedback loop | **Correction prompt**: User edits the Mermaid → system stores both versions as training pair. |
| Quick win | Even a single retry with error context improves quality by ~20% for marginal cases. |

---

### 28. No user correction loop

| Problem | Solution |
|---------|----------|
| System never learns | **Thumbs up/down per diagram** → store corrected versions. |
| Same mistakes repeated | Periodically fine-tune on corrected data, or use as few-shot examples. |
| Implementation | Add a simple API: `POST /api/feedback { job_id, diagram_id, correct_mermaid }`. Even without retraining, this data is gold for debugging. |

---

## Summary: Priority Matrix

| # | Solution | Effort | Impact | Category |
|---|----------|--------|--------|----------|
| 1 | **Diagram type detection** (before sending to LLM) | Low | 🔴 High | Kills Category 1 failures early |
| 2 | **Confidence scoring** (LLM self-rating + element counting) | Low | 🔴 High | Makes silent failures visible |
| 3 | **Multi-model fallback chain** | Medium | 🔴 High | Eliminates single-API dependency |
| 4 | **Round-trip verification** (Mermaid → SVG → describe → compare) | High | 🔴 High | Detects semantic hallucination |
| 5 | **Configurable CLIP threshold** + ensemble | Low | 🟠 Medium | Fixes most misclassification |
| 6 | **Document type caching** (few-shot per type) | Medium | 🟠 Medium | Solves cold start |
| 7 | **PDF pre-validation** (encryption, size, scanned) | Low | 🟠 Medium | Fail fast with clear messages |
| 8 | **User feedback API** | Medium | 🔶 Medium | Long-term improvement loop |
| 9 | **MathPix/LaTeX-OCR integration** | Low | 🔴 High | Solves equation extraction |
| 10 | **Progressive format fallback** (Mermaid→PlantUML→Graphviz→image) | Medium | 🟠 Medium | Best-effort degradation |