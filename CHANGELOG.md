# Changelog

## [2.0.0] - 2025-10-01

### Added ✨

#### Smart Session Naming (OCR + LLM)
- **OCR text extraction** from screenshots using Tesseract
- **Local LLM integration** via Ollama for generating descriptive names
- **Smart keyword extraction** with denylist filtering (removes "localhost", "chrome", etc.)
- **Organization name detection** to boost relevant test/org names in screenshots
- **Fallback strategy**: LLM → keywords → timestamp

Example transformation:
- Before: `2025-09-01_134749_session_1`
- After: `2025-09-01_134749_webgpu_performance_tests`

CLI: `--smart-naming`

#### Session Merging 🔗
- **Keyword similarity analysis** using Jaccard similarity
- **Intelligent merging** of consecutive sessions with similar names
- **Hard 04:00 UTC cutoff**: Never merges across night boundary
- **Max 4-hour gap** for merging consideration
- **Configurable threshold** (0.0-1.0, default: 0.5)

Example merge:
- `2025-09-01_134749_webgpu_performance_tests` + `2025-09-01_160500_webgpu_rendering_tests`
- → `2025-09-01_134749_webgpu_testing` (merged)

CLI: `--merge-similar` with optional `--merge-threshold`

#### 04:00 UTC Hard Cutoff
- **Always splits** sessions at 04:00 UTC, regardless of time gap
- Respects natural work boundaries (night time)
- Prevents accidental merging across days

### Changed

- **Similarity splitting** now disabled by default (was enabled)
  - Add `--enable-similarity` to use visual similarity for splitting
  - Better for multi-system monitoring workflows
- **Session naming** defaults to timestamp-based, smart naming is opt-in

### Dependencies

- Added `pytesseract>=0.3.10` for OCR
- Requires system package: `tesseract` (via Homebrew on macOS)
- Requires Ollama with a model (e.g., `llama3.1:latest`) for LLM naming

## [1.0.0] - 2025-03-11

### Initial Release

- Time-based screenshot clustering
- Perceptual hash similarity detection
- Configurable session gaps
- Dry-run mode
- Auto-confirmation option
- Uncategorized folder handling
