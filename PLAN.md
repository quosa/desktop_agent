# Screenshot Organizer - Implementation Plan

## Overview
Automatically organize test screenshots on desktop into session folders based on time proximity and visual similarity.

## Project Structure
```
desktop_assistant/
├── PLAN.md                      # This detailed plan
├── requirements.txt             # Python dependencies
├── screenshot_organizer.py      # Main script
├── .python-version             # Pyenv version file
└── README.md                   # Usage instructions
```

## Phase 1: Environment Setup

### 1.1 Virtual Environment
- Create pyenv virtual environment `desktop_assistant` with Python 3.13.0
- Command: `pyenv virtualenv 3.13.0 desktop_assistant`
- Set local version: `pyenv local desktop_assistant`

### 1.2 Dependencies
Install via pip:
- **Pillow** (>=10.0.0) - Image processing and loading
- **imagehash** (>=4.3.0) - Perceptual hashing for similarity detection
- **Optional for future**: transformers, torch, clip-by-openai (for CLIP-based naming)

## Phase 2: Core Functionality

### Module 1: File Discovery
**Purpose**: Find all screenshot files on desktop

**Implementation**:
- Use `pathlib.Path` for cross-platform compatibility
- Scan for extensions: `.png`, `.jpg`, `.jpeg` (case-insensitive)
- Extract metadata:
  - Creation time (`st_birthtime` on macOS, `st_ctime` on other platforms)
  - Modification time (`st_mtime` as fallback)
  - File size
  - Full path
- Return list of `Screenshot` objects with metadata

**Key Functions**:
```python
def find_screenshots(desktop_path: Path) -> List[Screenshot]:
    """Scan desktop for screenshot files and extract metadata."""
```

### Module 2: Time-Based Clustering
**Purpose**: Group screenshots into sessions based on temporal proximity

**Algorithm**:
1. Sort all screenshots by creation timestamp (ascending)
2. Initialize first session with first screenshot
3. For each subsequent screenshot:
   - Calculate time gap from previous screenshot
   - If gap ≤ session_gap_minutes: add to current session
   - If gap > session_gap_minutes: start new session
4. Return list of session candidates

**Configuration**:
- Default session gap: 15 minutes
- Configurable via CLI argument `--session-gap`

**Key Functions**:
```python
def cluster_by_time(screenshots: List[Screenshot],
                    gap_minutes: int = 15) -> List[Session]:
    """Group screenshots by time proximity."""
```

### Module 3: Perceptual Hash Analysis (OPTIONAL - Disabled by Default)
**Purpose**: Detect context switches within time-based sessions using visual similarity

**⚠️ NOTE**: For multi-system monitoring, similarity splitting is often counterproductive as checking different systems naturally creates visual differences. **This module is now optional and disabled by default.**

**Algorithm** (when enabled with `--enable-similarity`):
1. For each screenshot, calculate perceptual hash (phash) using imagehash
2. Within each time-based session:
   - Compute pairwise hash differences between consecutive screenshots
   - Identify "context breaks" where difference > threshold
   - Split session at context breaks
3. Return refined session list

**Use Cases**:
- Single application/system monitoring where context switches are meaningful
- Testing scenarios where you want to detect workflow changes
- NOT recommended for multi-system monitoring

**Key Functions**:
```python
def calculate_phash(image_path: Path) -> imagehash.ImageHash:
    """Calculate perceptual hash for an image."""

def refine_sessions_by_similarity(sessions: List[Session],
                                  threshold: int = 10) -> List[Session]:
    """Split sessions based on visual similarity."""
```

### Module 4: Smart Session Naming (NEW PRIORITY)
**Purpose**: Generate descriptive folder names using content analysis

**Phase 1 - Time-based (Current MVP)**:
- Format: `YYYY-MM-DD_HHMMSS_session_N`
- Use timestamp of **earliest** screenshot in session
- N = session number for that day (if multiple sessions same day)

**Phase 2 - OCR-based Enhancement (Next)**:
- Extract text from screenshots using pytesseract or easyocr
- Identify common keywords/patterns across session
- Generate names like: `2025-10-01_143000_api_testing` or `2025-10-01_160500_dashboard_monitoring`

**Phase 3 - CLIP-based Semantic Analysis (Future)**:
- Use CLIP model to understand visual content
- Classify screenshots by category (code, dashboard, logs, documentation, etc.)
- Generate semantic names: `2025-10-01_code_review`, `2025-10-01_grafana_metrics`

**Examples**:
- Basic: `2025-10-01_143000_session_1`
- With OCR: `2025-10-01_143000_kubernetes_logs`
- With CLIP: `2025-10-01_143000_monitoring_dashboard`
- Uncategorized: `uncategorized`

**Key Functions**:
```python
def generate_session_name(session: Session, session_index: int) -> str:
    """Generate folder name for a session."""

def extract_text_from_screenshots(screenshots: List[Screenshot]) -> List[str]:
    """Extract text using OCR for naming hints."""

def classify_screenshot_content(screenshot: Screenshot) -> str:
    """Use CLIP to classify screenshot content."""
```

**OCR Implementation Options**:
1. **pytesseract** (Tesseract wrapper) - Most accurate, requires Tesseract installation
2. **easyocr** - Pure Python, GPU-accelerated, good for mixed languages
3. **paddleocr** - Fast, good accuracy, lightweight

**CLIP Implementation**:
- Use `transformers` with OpenAI CLIP model
- Categories: code, terminal, dashboard, documentation, logs, database, api, web, design, other
- Batch process for efficiency

### Module 5: Uncategorized Handler
**Purpose**: Handle isolated screenshots that don't belong to any session

**Criteria for Uncategorized**:
- Screenshot has no neighbors within session gap window
- Single-screenshot sessions
- Optionally: very old screenshots (> 30 days)

**Implementation**:
- Create `uncategorized/` folder on desktop
- Move isolated screenshots there
- Preserve original filename

**Key Functions**:
```python
def identify_uncategorized(sessions: List[Session]) -> List[Screenshot]:
    """Find isolated screenshots for uncategorized folder."""
```

### Module 6: CLI & Confirmation
**Purpose**: Interactive interface with preview and confirmation

**Display Format**:
```
Found 23 screenshots on desktop

Proposed organization:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Session 1: 2025-10-01_143000 (5 screenshots)
  📸 Screenshot 2025-10-01 at 14.30.15.png  [14:30:15]
  📸 Screenshot 2025-10-01 at 14.32.48.png  [14:32:48]
  📸 Screenshot 2025-10-01 at 14.35.22.png  [14:35:22]
  📸 Screenshot 2025-10-01 at 14.38.01.png  [14:38:01]
  📸 Screenshot 2025-10-01 at 14.40.33.png  [14:40:33]

Session 2: 2025-10-01_160500 (8 screenshots)
  📸 Screenshot 2025-10-01 at 16.05.12.png  [16:05:12]
  ...

Uncategorized (2 screenshots)
  📸 Old_screenshot.png  [2025-09-15 10:23:45]
  📸 Random_image.jpg   [2025-09-20 14:15:22]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Proceed with organization? [y/N]:
```

**Key Functions**:
```python
def display_organization_plan(sessions: List[Session],
                             uncategorized: List[Screenshot]):
    """Print formatted preview of proposed organization."""

def confirm_action() -> bool:
    """Prompt user for confirmation."""
```

**CLI Arguments**:
- `--desktop-path PATH`: Custom desktop location (default: ~/Desktop)
- `--session-gap MINUTES`: Time gap for sessions (default: 15)
- `--similarity-threshold N`: Hash difference threshold (default: 10)
- `--dry-run`: Show plan without moving files
- `--auto-confirm`: Skip confirmation prompt
- `--verbose`: Show detailed similarity scores

## Phase 3: File Operations

### Safe File Moving
**Implementation**:
- Create session folders only after confirmation
- Use `shutil.move()` for atomic operations
- Handle naming conflicts (add suffix if folder exists)
- Preserve file metadata where possible
- Error handling with rollback capability

**Key Functions**:
```python
def execute_organization(sessions: List[Session],
                        uncategorized: List[Screenshot],
                        desktop_path: Path,
                        dry_run: bool = False):
    """Create folders and move screenshots."""
```

## Data Structures

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import imagehash

@dataclass
class Screenshot:
    path: Path
    created_at: datetime
    file_size: int
    phash: Optional[imagehash.ImageHash] = None

@dataclass
class Session:
    screenshots: List[Screenshot]
    start_time: datetime
    end_time: datetime
    folder_name: str = ""
```

## Implementation Order

### Phase 1: MVP (Completed ✅)
1. ✅ **Create PLAN.md** with this content
2. ✅ **Set up pyenv environment** - Create virtual env and activate
3. ✅ **Create requirements.txt** - List all dependencies
4. ✅ **Implement file discovery module** - Scan and extract metadata
5. ✅ **Implement time-based clustering** - Group by time proximity
6. ✅ **Add perceptual hash similarity** - Optional refinement (now disabled by default)
7. ✅ **Build CLI interface with preview** - Display proposed organization
8. ✅ **Add confirmation & file moving logic** - Execute organization
9. ✅ **Create README** with usage examples and documentation

### Phase 2: Smart Naming (Next Priority)
10. 🔄 **Add OCR capability** - Extract text from screenshots
11. 🔄 **Implement keyword extraction** - Find common terms across session
12. 🔄 **Add smart naming** - Generate descriptive folder names from keywords
13. 🔄 **Update CLI** - Add options for naming strategies
14. 🔄 **Test with real screenshots** - Validate naming accuracy

### Phase 3: CLIP Integration (Future)
15. ⏳ **Add CLIP model** - Load and initialize
16. ⏳ **Implement content classification** - Categorize screenshots
17. ⏳ **Enhance naming** - Use semantic categories
18. ⏳ **Add caching** - Cache classifications for performance

## Testing Strategy

### Unit Tests (Future)
- Test time clustering with various gaps
- Test hash similarity detection
- Test session naming edge cases

### Manual Testing
1. Create test screenshots with known timestamps
2. Verify correct session grouping
3. Test edge cases:
   - No screenshots on desktop
   - Single screenshot
   - Large gaps between screenshots
   - Visually similar vs. dissimilar consecutive screenshots

## Future Enhancements (Post-MVP)

### 1. CLIP-based Semantic Naming
- Use OpenAI CLIP model to understand screenshot content
- Generate descriptive names: `2025-10-01_code_review`, `2025-10-01_design_mockups`
- Requires: `transformers`, `torch`, `clip-by-openai`

### 2. OCR Integration
- Extract text from screenshots using Tesseract or cloud OCR
- Use text for naming or searching
- Useful for documentation screenshots

### 3. Duplicate Detection
- Identify exact or near-duplicate screenshots
- Offer to delete/archive duplicates

### 4. Archive Management
- Auto-archive sessions older than N days
- Compress old sessions to save space

### 5. Web UI
- Flask/FastAPI web interface
- Drag-and-drop to reassign screenshots
- Visual preview of sessions

### 6. Smart Filters
- Exclude specific patterns (e.g., "CleanShot*.png")
- Only process screenshots matching certain criteria
- Ignore already-organized folders

## Performance Considerations

- **Lazy loading**: Only load images for hash calculation when needed
- **Parallel processing**: Use multiprocessing for hash calculation on large batches
- **Caching**: Cache hashes to avoid recomputation
- **Memory**: Process in batches if thousands of screenshots

## Security & Safety

- **No destructive operations**: Always move, never delete
- **Dry-run default**: Consider making dry-run the default mode
- **Backup reminder**: Suggest user backup before first run
- **Undo capability**: Log all moves to enable rollback

## Configuration File (Future)

`~/.screenshot_organizer.yaml`:
```yaml
desktop_path: ~/Desktop
session_gap_minutes: 15
similarity_threshold: 10
auto_confirm: false
exclude_patterns:
  - "CleanShot*"
  - "temp_*"
```
