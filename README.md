# Screenshot Organizer

Automatically organize test screenshots on your desktop into session folders based on time proximity and visual similarity.

## Features

- **Time-based clustering**: Groups screenshots taken within a configurable time window (default: 15 minutes)
  - **Hard cutoff at 04:00 UTC**: Always splits sessions at 4am, even if you continue working
- **Smart session naming** (NEW! ✨): Uses OCR + local LLM to generate descriptive names
  - Example: `2025-09-01_143000_webgpu_performance_tests` instead of `session_1`
  - Extracts text from screenshots using Tesseract OCR
  - Uses Ollama (local LLM) to generate meaningful names from keywords
  - Filters out generic terms (localhost, chrome, etc.) with smart denylist
  - Boosts organization/test names found in screenshots
- **Session merging** (NEW! 🔗): Intelligently merges similar sessions
  - Merges consecutive sessions with high keyword similarity
  - Respects 04:00 UTC cutoff (never merges across night boundary)
  - Max 4-hour gap for merging
  - Example: Merges `webgpu_performance_tests` + `webgpu_rendering_tests` → `webgpu_testing`
- **Visual similarity detection** (optional): Uses perceptual hashing to detect context switches - disabled by default for multi-system monitoring
- **Uncategorized handling**: Isolated screenshots moved to separate `uncategorized/` folder
- **Preview mode**: Shows proposed groupings before moving any files
- **Dry-run support**: Test without actually moving files

## Installation

### Prerequisites

- Python 3.13.0 (managed via pyenv)
- pyenv installed on your system

### Setup

1. Clone or navigate to this directory:
```bash
cd /opt/UnitySrc/personal/desktop_assistant
```

2. The virtual environment is already configured with `.python-version` file. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Organize screenshots on your desktop with default settings (15-minute session gap):
```bash
./screenshot_organizer.py
```

### Dry Run (Preview Only)

See what would happen without moving any files:
```bash
./screenshot_organizer.py --dry-run
```

### Custom Session Gap

Use a 30-minute gap between sessions:
```bash
./screenshot_organizer.py --session-gap 30
```

### Organize Different Folder

Organize screenshots in a different location:
```bash
./screenshot_organizer.py --desktop-path ~/Downloads
```

### Auto-Confirm

Skip confirmation prompt and proceed automatically:
```bash
./screenshot_organizer.py --auto-confirm
```

### Smart Naming (Recommended! ✨)

Use OCR + LLM for descriptive session names:
```bash
./screenshot_organizer.py --smart-naming
```

### Smart Naming + Session Merging (Best! 🔥)

Combine smart naming with intelligent merging:
```bash
./screenshot_organizer.py --smart-naming --merge-similar
```

This will:
1. Extract text from screenshots using OCR
2. Generate descriptive names using local LLM
3. Merge similar consecutive sessions automatically
4. Respect 04:00 UTC cutoff

### Adjust Merge Threshold

Control how aggressively sessions are merged (0.0-1.0):
```bash
./screenshot_organizer.py --smart-naming --merge-similar --merge-threshold 0.7
```
- Lower (0.3-0.4): More aggressive merging
- Default (0.5): Balanced
- Higher (0.7-0.8): More conservative, only merge very similar sessions

### Verbose Mode

Show detailed progress and merge decisions:
```bash
./screenshot_organizer.py --smart-naming --merge-similar --verbose
```

### Enable Similarity Splitting (Optional)

Use visual similarity to split sessions (not recommended for multi-system monitoring):
```bash
./screenshot_organizer.py --enable-similarity --similarity-threshold 15
```

### Complete Example

Full-featured organization with all bells and whistles:
```bash
./screenshot_organizer.py --smart-naming --merge-similar --session-gap 20 --verbose --dry-run
```

## CLI Options

```
Options:
  --desktop-path PATH           Path to organize (default: ~/Desktop)
  --session-gap MINUTES         Max gap between screenshots in same session (default: 15)
  --smart-naming                Use OCR + LLM for descriptive names (requires tesseract + ollama)
  --merge-similar               Merge consecutive sessions with similar names
  --merge-threshold THRESHOLD   Similarity threshold for merging (0.0-1.0, default: 0.5)
  --enable-similarity           Enable visual similarity splitting (disabled by default)
  --similarity-threshold N      Perceptual hash difference threshold (default: 10)
  --dry-run                     Preview without moving files
  --auto-confirm                Skip confirmation prompt
  --verbose                     Show detailed output
  -h, --help                    Show help message
```

## How It Works

### 1. File Discovery
Scans the specified directory for image files (`.png`, `.jpg`, `.jpeg`) and extracts metadata including creation time.

### 2. Time-Based Clustering
Groups consecutive screenshots within the specified time gap (default: 15 minutes).

### 3. Perceptual Hash Analysis (Optional - Disabled by Default)
**Note**: For multi-system monitoring, similarity splitting is disabled by default since checking different systems naturally creates visual differences.

When enabled with `--enable-similarity`, calculates perceptual hashes for each screenshot and detects visual dissimilarity within time-based sessions. If consecutive screenshots look significantly different (hash difference > threshold), the session is split.

Use cases for similarity splitting:
- Single application/system monitoring where context switches are meaningful
- Testing scenarios where you want to detect workflow changes
- **NOT recommended** for multi-system monitoring (Kubernetes, Grafana, logs, etc.)

### 4. Session Naming
Generates folder names based on the earliest screenshot timestamp:
- Format: `YYYY-MM-DD_HHMMSS_session_N`
- Example: `2025-10-01_143000_session_1`

**Coming Soon**: Smart naming with OCR and CLIP
- OCR-based: Extract keywords from text in screenshots → `2025-10-01_143000_kubernetes_logs`
- CLIP-based: Classify visual content → `2025-10-01_143000_monitoring_dashboard`

### 5. Uncategorized Detection
Single isolated screenshots (no neighbors within time window) are moved to an `uncategorized/` folder.

### 6. Preview & Confirmation
Displays the proposed organization and asks for confirmation before moving files (unless `--auto-confirm` is used).

### 7. File Operations
Creates folders and moves files to their new locations safely (no deletions, only moves).

## Example Output

```
Screenshot Organizer
Scanning: /Users/username/Desktop
Session gap: 15 minutes
Similarity splitting: DISABLED (use --enable-similarity to enable)
Found 23 screenshots
Time-based clustering: 5 sessions

Found 23 screenshots

Proposed organization:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Session: 2025-10-01_143000_session_1 (5 screenshots)
  📸 Screenshot 2025-10-01 at 14.30.15.png                   [14:30:15] 234.5KB
  📸 Screenshot 2025-10-01 at 14.32.48.png                   [14:32:48] 189.2KB
  📸 Screenshot 2025-10-01 at 14.35.22.png                   [14:35:22] 267.8KB
  📸 Screenshot 2025-10-01 at 14.38.01.png                   [14:38:01] 201.3KB
  📸 Screenshot 2025-10-01 at 14.40.33.png                   [14:40:33] 198.7KB

Session: 2025-10-01_160500_session_2 (8 screenshots)
  📸 Screenshot 2025-10-01 at 16.05.12.png                   [16:05:12] 312.4KB
  ...

Uncategorized (2 screenshots)
  📸 old_screenshot.png                                      [10:23:45] 145.2KB
  📸 random_image.jpg                                        [14:15:22] 89.6KB

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Proceed with organization? [y/N]:
```

## Configuration Tips

### Session Gap
- **Shorter gap (5-10 min)**: More granular sessions, good for rapid testing
- **Default (15 min)**: Balanced for typical workflows
- **Longer gap (30+ min)**: Fewer, larger sessions for extended work periods

### Similarity Threshold (only relevant with --enable-similarity)
- **Lower threshold (5-8)**: More sensitive to visual differences, creates more sessions
- **Default (10)**: Balanced detection of context switches
- **Higher threshold (15+)**: Only splits on very different screenshots

**Recommendation**: For multi-system monitoring, keep similarity splitting disabled (default behavior) to avoid false splits.

## Safety

- **Non-destructive**: Only moves files, never deletes
- **Confirmation required**: By default, asks before moving files
- **Dry-run available**: Test without making changes
- **Folder creation**: Creates folders safely with `exist_ok=True`

## Troubleshooting

### "No screenshots found"
- Check that image files exist in the specified directory
- Verify file extensions are `.png`, `.jpg`, or `.jpeg`
- Try specifying the path explicitly with `--desktop-path`

### Permission errors
- Ensure you have read/write access to the directory
- Check that files aren't locked by other applications

### Hash calculation warnings
- Some corrupt or unusual image formats may fail hash calculation
- The script will continue but won't use similarity detection for those files

## Future Enhancements

See `PLAN.md` for planned features:
- CLIP-based semantic naming (smart folder names based on content)
- OCR integration for text-heavy screenshots
- Duplicate detection
- Archive management
- Web UI for interactive organization

## License

MIT

## Contributing

Issues and pull requests welcome!
