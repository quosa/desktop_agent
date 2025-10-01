#!/usr/bin/env python3
"""
Screenshot Organizer - Automatically organize screenshots into session folders

Groups screenshots by time proximity and visual similarity using perceptual hashing.
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import shutil
import subprocess
import re
from collections import Counter

from PIL import Image
import imagehash

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


@dataclass
class Screenshot:
    """Represents a screenshot file with metadata."""
    path: Path
    created_at: datetime
    file_size: int
    phash: Optional[imagehash.ImageHash] = None

    def __post_init__(self):
        """Calculate display name."""
        self.display_name = self.path.name

    @property
    def time_str(self) -> str:
        """Format timestamp for display."""
        return self.created_at.strftime("%H:%M:%S")


@dataclass
class Session:
    """Represents a group of related screenshots."""
    screenshots: List[Screenshot] = field(default_factory=list)
    folder_name: str = ""

    @property
    def start_time(self) -> datetime:
        """Get earliest screenshot time."""
        return min(s.created_at for s in self.screenshots) if self.screenshots else datetime.min

    @property
    def end_time(self) -> datetime:
        """Get latest screenshot time."""
        return max(s.created_at for s in self.screenshots) if self.screenshots else datetime.min

    @property
    def count(self) -> int:
        """Number of screenshots in session."""
        return len(self.screenshots)

    def add_screenshot(self, screenshot: Screenshot):
        """Add a screenshot to this session."""
        self.screenshots.append(screenshot)


# ============================================================================
# Smart Naming Configuration
# ============================================================================

# Denylist of words that rarely provide meaningful context
DENYLIST = {
    # Generic web/tech terms
    'localhost', 'https', 'http', 'chrome', 'firefox', 'safari', 'browser',
    'window', 'tab', 'page', 'site', 'web', 'www', 'com', 'org', 'net',
    # Common UI terms
    'button', 'click', 'menu', 'toolbar', 'sidebar', 'header', 'footer',
    'navigation', 'search', 'filter', 'sort', 'view', 'show', 'hide',
    # Generic words
    'text', 'content', 'data', 'item', 'field', 'value', 'type', 'name',
    'info', 'details', 'settings', 'options', 'preferences', 'config',
}

# Common stopwords for keyword extraction
STOPWORDS = {
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her',
    'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how',
    'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did',
    'man', 'way', 'will', 'with', 'that', 'this', 'have', 'from', 'they',
    'been', 'more', 'than', 'into', 'just', 'like', 'some', 'time', 'very',
    'when', 'your', 'about', 'after', 'before', 'other', 'such', 'there',
    'these', 'would', 'their', 'which', 'what', 'where', 'while', 'should',
    'could', 'then', 'also', 'each', 'them', 'only', 'under', 'over'
}

# Pattern to extract potential org/test names
ORG_NAME_PATTERNS = [
    r'\b([A-Z][A-Za-z0-9\-]{3,30})\b',  # PascalCase or specific named entities
    r'"([^"]{5,40})"',                   # Quoted strings
    r'\b(SIT|UAT|DEV|PROD|TEST)[\s\-]([A-Za-z0-9\-\s]{3,30})\b',  # Environment prefixes
]


# ============================================================================
# Module 1: File Discovery
# ============================================================================

def find_screenshots(desktop_path: Path) -> List[Screenshot]:
    """
    Scan desktop for screenshot files and extract metadata.

    Args:
        desktop_path: Path to desktop directory

    Returns:
        List of Screenshot objects with metadata
    """
    if not desktop_path.exists():
        print(f"Error: Desktop path does not exist: {desktop_path}")
        return []

    screenshot_extensions = {'.png', '.jpg', '.jpeg'}
    screenshots = []

    for file_path in desktop_path.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in screenshot_extensions:
            continue

        # Get file stats
        stat = file_path.stat()

        # Use birth time (creation time) on macOS, ctime on others
        # Fall back to mtime if birth time not available
        if hasattr(stat, 'st_birthtime'):
            created_at = datetime.fromtimestamp(stat.st_birthtime)
        else:
            created_at = datetime.fromtimestamp(stat.st_ctime)

        screenshot = Screenshot(
            path=file_path,
            created_at=created_at,
            file_size=stat.st_size
        )
        screenshots.append(screenshot)

    # Sort by creation time
    screenshots.sort(key=lambda s: s.created_at)

    return screenshots


# ============================================================================
# Module 2: Time-Based Clustering
# ============================================================================

def crossed_4am_utc_boundary(time1: datetime, time2: datetime) -> bool:
    """
    Check if two timestamps cross the 04:00 UTC boundary.

    Args:
        time1: Earlier timestamp
        time2: Later timestamp

    Returns:
        True if 04:00 UTC boundary was crossed
    """
    # Convert to UTC if needed (assuming local time for now)
    # For production, you might want to handle timezone conversion
    hour1 = time1.hour
    hour2 = time2.hour

    # If we went from before 4am to after 4am (or next day)
    if time1.date() != time2.date():
        # Different days - check if we crossed 4am
        if time2.hour >= 4:
            return True

    # Same day - check if we crossed from <4am to >=4am
    if hour1 < 4 <= hour2:
        return True

    return False


def cluster_by_time(screenshots: List[Screenshot], gap_minutes: int = 15) -> List[Session]:
    """
    Group screenshots into sessions based on time proximity.

    HARD RULE: Always split at 04:00 UTC boundary, regardless of gap.

    Args:
        screenshots: List of screenshots sorted by time
        gap_minutes: Maximum gap in minutes between screenshots in same session

    Returns:
        List of Session objects
    """
    if not screenshots:
        return []

    sessions = []
    current_session = Session()
    current_session.add_screenshot(screenshots[0])

    for i in range(1, len(screenshots)):
        current = screenshots[i]
        previous = screenshots[i - 1]

        time_gap = current.created_at - previous.created_at
        crossed_4am = crossed_4am_utc_boundary(previous.created_at, current.created_at)

        # Hard split at 04:00 UTC boundary
        if crossed_4am:
            sessions.append(current_session)
            current_session = Session()
            current_session.add_screenshot(current)
        elif time_gap <= timedelta(minutes=gap_minutes):
            # Same session
            current_session.add_screenshot(current)
        else:
            # Start new session due to time gap
            sessions.append(current_session)
            current_session = Session()
            current_session.add_screenshot(current)

    # Add final session
    if current_session.screenshots:
        sessions.append(current_session)

    return sessions


# ============================================================================
# Module 3: Perceptual Hash Analysis
# ============================================================================

def calculate_phash(image_path: Path, hash_size: int = 8) -> Optional[imagehash.ImageHash]:
    """
    Calculate perceptual hash for an image.

    Args:
        image_path: Path to image file
        hash_size: Size of hash (default 8x8)

    Returns:
        ImageHash object or None if error
    """
    try:
        with Image.open(image_path) as img:
            return imagehash.phash(img, hash_size=hash_size)
    except Exception as e:
        print(f"Warning: Could not calculate hash for {image_path.name}: {e}")
        return None


def refine_sessions_by_similarity(
    sessions: List[Session],
    threshold: int = 10,
    verbose: bool = False
) -> List[Session]:
    """
    Split sessions based on visual similarity using perceptual hashing.

    Args:
        sessions: List of time-based sessions
        threshold: Hash difference threshold (higher = more different)
        verbose: Print similarity scores

    Returns:
        Refined list of sessions
    """
    refined_sessions = []

    for session in sessions:
        # Single screenshot sessions don't need refinement
        if session.count <= 1:
            refined_sessions.append(session)
            continue

        # Calculate hashes for all screenshots
        for screenshot in session.screenshots:
            if screenshot.phash is None:
                screenshot.phash = calculate_phash(screenshot.path)

        # Split session based on similarity
        current_refined = Session()
        current_refined.add_screenshot(session.screenshots[0])

        for i in range(1, len(session.screenshots)):
            current = session.screenshots[i]
            previous = session.screenshots[i - 1]

            # Skip if either hash calculation failed
            if current.phash is None or previous.phash is None:
                current_refined.add_screenshot(current)
                continue

            # Calculate hash difference
            hash_diff = current.phash - previous.phash

            if verbose:
                print(f"  {previous.display_name} <-> {current.display_name}: "
                      f"diff={hash_diff} ({'same' if hash_diff <= threshold else 'split'})")

            if hash_diff <= threshold:
                # Similar enough, same session
                current_refined.add_screenshot(current)
            else:
                # Different context, split session
                refined_sessions.append(current_refined)
                current_refined = Session()
                current_refined.add_screenshot(current)

        # Add final refined session
        if current_refined.screenshots:
            refined_sessions.append(current_refined)

    return refined_sessions


# ============================================================================
# Module 4: Session Naming
# ============================================================================

def extract_text_from_screenshot(screenshot_path: Path) -> str:
    """Extract text from screenshot using OCR."""
    if not PYTESSERACT_AVAILABLE:
        return ""

    try:
        img = Image.open(screenshot_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        return ""


def extract_org_names(text: str) -> list:
    """Extract potential organization/test names from text."""
    org_names = set()

    for pattern in ORG_NAME_PATTERNS:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple):
                org_names.update([m for m in match if m])
            else:
                org_names.add(match)

    # Filter out common words and very short names
    org_names = {name for name in org_names if len(name) > 3 and name.lower() not in DENYLIST}

    return list(org_names)


def extract_keywords(text: str, min_length: int = 4, top_n: int = 30) -> list:
    """Extract keywords from text with denylist filtering."""
    # Convert to lowercase and split into words
    words = re.findall(r'\b[a-zA-Z]{' + str(min_length) + r',}\b', text.lower())

    # Filter stopwords and denylist
    filtered_words = [w for w in words if w not in STOPWORDS and w not in DENYLIST]
    word_counts = Counter(filtered_words)

    return word_counts.most_common(top_n)


def call_llm_for_name(keywords: list, org_names: list, model: str = "llama3.1:latest") -> Optional[str]:
    """
    Call local LLM (Ollama) to generate a session name.

    Args:
        keywords: List of (word, count) tuples
        org_names: List of potential organization names
        model: Ollama model to use

    Returns:
        Suggested session name (3-4 words, snake_case) or None
    """
    if not keywords:
        return None

    # Prepare keyword list (top 20)
    keyword_str = ", ".join([f"{word} ({count})" for word, count in keywords[:20]])

    # Prepare org names
    org_str = ", ".join(org_names[:10]) if org_names else "None found"

    prompt = f"""Based on these extracted keywords from test screenshots, suggest a concise, descriptive session name.

Keywords: {keyword_str}

Potential organization/test names found: {org_str}

Requirements:
- 2-4 words maximum
- Use snake_case format (e.g., unity_store_testing)
- Prioritize organization names and specific technical terms over generic words
- Focus on what is being tested or monitored
- Be specific and descriptive

Respond with ONLY the session name, no explanation."""

    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=30
        )

        if result.returncode == 0:
            suggested_name = result.stdout.strip()
            # Clean up the response
            suggested_name = suggested_name.lower()
            suggested_name = re.sub(r'[^a-z0-9_]', '_', suggested_name)
            suggested_name = re.sub(r'_+', '_', suggested_name).strip('_')
            # Limit length
            parts = suggested_name.split('_')[:4]
            return '_'.join(parts)
        else:
            return None
    except Exception:
        return None


def generate_smart_session_name(session: Session, session_index: int, verbose: bool = False) -> str:
    """
    Generate smart session name using OCR and LLM.

    Args:
        session: Session to name
        session_index: Index of session for that day
        verbose: Print progress

    Returns:
        Smart session name or timestamp-based fallback
    """
    timestamp = session.start_time.strftime("%Y-%m-%d_%H%M%S")

    if not PYTESSERACT_AVAILABLE:
        return f"{timestamp}_session_{session_index}"

    # Extract text from sample screenshots (max 3 to avoid slowness)
    sample_screenshots = session.screenshots[:3]
    all_text = []
    all_org_names = set()

    if verbose:
        print(f"  Analyzing {len(sample_screenshots)} screenshots for session naming...")

    for screenshot in sample_screenshots:
        text = extract_text_from_screenshot(screenshot.path)
        if text.strip():
            all_text.append(text)
            org_names = extract_org_names(text)
            all_org_names.update(org_names)

    if not all_text:
        return f"{timestamp}_session_{session_index}"

    # Extract keywords
    combined_text = '\n'.join(all_text)
    keywords = extract_keywords(combined_text, min_length=4, top_n=30)

    # Try LLM-based naming
    llm_name = call_llm_for_name(keywords, list(all_org_names))

    if llm_name:
        return f"{timestamp}_{llm_name}"
    else:
        # Fallback: use top 3 keywords
        top_words = [word for word, _ in keywords[:3]]
        if top_words:
            keyword_name = '_'.join(top_words)
            return f"{timestamp}_{keyword_name}"
        else:
            return f"{timestamp}_session_{session_index}"


def generate_session_names(sessions: List[Session], use_smart_naming: bool = False, verbose: bool = False) -> None:
    """
    Generate folder names for sessions based on timestamp (and optionally OCR+LLM).

    Args:
        sessions: List of sessions to name (modified in place)
        use_smart_naming: Use OCR and LLM for descriptive names
        verbose: Print progress
    """
    # Group sessions by date
    sessions_by_date = {}
    for session in sessions:
        date_str = session.start_time.strftime("%Y-%m-%d")
        if date_str not in sessions_by_date:
            sessions_by_date[date_str] = []
        sessions_by_date[date_str].append(session)

    # Generate names with session numbers per date
    for date_str, date_sessions in sessions_by_date.items():
        for idx, session in enumerate(date_sessions, start=1):
            if use_smart_naming:
                session.folder_name = generate_smart_session_name(session, idx, verbose=verbose)
            else:
                time_str = session.start_time.strftime("%H%M%S")
                session.folder_name = f"{date_str}_{time_str}_session_{idx}"


# ============================================================================
# Module 4.5: Session Merging
# ============================================================================

def calculate_keyword_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity between two session names based on shared keywords.

    Args:
        name1: First session name
        name2: Second session name

    Returns:
        Similarity score (0.0 to 1.0)
    """
    # Extract keywords from names (ignore timestamp and session number)
    def extract_keywords(name: str) -> set:
        # Remove timestamp prefix (YYYY-MM-DD_HHMMSS)
        parts = name.split('_')
        if len(parts) > 2:
            # Skip date and time parts
            keywords = parts[2:]
        else:
            keywords = parts
        # Remove 'session' and numbers
        keywords = [k for k in keywords if k != 'session' and not k.isdigit()]
        return set(keywords)

    keywords1 = extract_keywords(name1)
    keywords2 = extract_keywords(name2)

    if not keywords1 or not keywords2:
        return 0.0

    # Calculate Jaccard similarity
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)

    return intersection / union if union > 0 else 0.0


def merge_similar_sessions(
    sessions: List[Session],
    similarity_threshold: float = 0.5,
    verbose: bool = False
) -> List[Session]:
    """
    Merge consecutive sessions with similar names.

    Args:
        sessions: List of sessions to potentially merge
        similarity_threshold: Minimum similarity to merge (0.0-1.0)
        verbose: Print merge decisions

    Returns:
        List of merged sessions
    """
    if len(sessions) <= 1:
        return sessions

    merged = []
    current = sessions[0]

    for i in range(1, len(sessions)):
        next_session = sessions[i]

        # Calculate similarity between folder names
        similarity = calculate_keyword_similarity(
            current.folder_name,
            next_session.folder_name
        )

        # Calculate time gap
        time_gap = next_session.start_time - current.end_time

        # Merge criteria:
        # 1. High similarity (>= threshold)
        # 2. Same day or reasonable gap (< 4 hours)
        # 3. Not crossing 04:00 UTC boundary
        should_merge = (
            similarity >= similarity_threshold and
            time_gap <= timedelta(hours=4) and
            not crossed_4am_utc_boundary(current.end_time, next_session.start_time)
        )

        if should_merge:
            if verbose:
                print(f"  Merging: {current.folder_name} + {next_session.folder_name}")
                print(f"    Similarity: {similarity:.2f}, Gap: {time_gap}")

            # Merge screenshots into current session
            current.screenshots.extend(next_session.screenshots)
            # Keep the first session's folder name (with earliest timestamp)
        else:
            # No merge - add current to merged list and start new
            merged.append(current)
            current = next_session

    # Add final session
    merged.append(current)

    if verbose and len(merged) < len(sessions):
        print(f"  Merged {len(sessions)} sessions → {len(merged)} sessions")

    return merged


# ============================================================================
# Module 5: Uncategorized Handler
# ============================================================================

def identify_uncategorized(sessions: List[Session]) -> tuple[List[Session], List[Screenshot]]:
    """
    Identify isolated screenshots for uncategorized folder.

    Args:
        sessions: List of all sessions

    Returns:
        Tuple of (regular_sessions, uncategorized_screenshots)
    """
    regular_sessions = []
    uncategorized = []

    for session in sessions:
        if session.count == 1:
            # Single screenshot session -> uncategorized
            uncategorized.extend(session.screenshots)
        else:
            # Multi-screenshot session
            regular_sessions.append(session)

    return regular_sessions, uncategorized


# ============================================================================
# Module 6: CLI & Display
# ============================================================================

def display_organization_plan(
    sessions: List[Session],
    uncategorized: List[Screenshot]
) -> None:
    """
    Display formatted preview of proposed organization.

    Args:
        sessions: List of sessions
        uncategorized: List of uncategorized screenshots
    """
    total_screenshots = sum(s.count for s in sessions) + len(uncategorized)

    print(f"\nFound {total_screenshots} screenshots\n")
    print("Proposed organization:")
    print("━" * 60)

    if sessions:
        for session in sessions:
            print(f"\nSession: {session.folder_name} ({session.count} screenshots)")
            for screenshot in session.screenshots:
                size_kb = screenshot.file_size / 1024
                print(f"  📸 {screenshot.display_name:<50} [{screenshot.time_str}] {size_kb:.1f}KB")

    if uncategorized:
        print(f"\nUncategorized ({len(uncategorized)} screenshots)")
        for screenshot in uncategorized:
            size_kb = screenshot.file_size / 1024
            print(f"  📸 {screenshot.display_name:<50} [{screenshot.time_str}] {size_kb:.1f}KB")

    if not sessions and not uncategorized:
        print("\nNo screenshots to organize!")

    print("\n" + "━" * 60)


def confirm_action() -> bool:
    """
    Prompt user for confirmation.

    Returns:
        True if user confirms, False otherwise
    """
    try:
        response = input("\nProceed with organization? [y/N]: ").strip().lower()
        return response in ('y', 'yes')
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return False


# ============================================================================
# Module 7: File Operations
# ============================================================================

def execute_organization(
    sessions: List[Session],
    uncategorized: List[Screenshot],
    desktop_path: Path,
    dry_run: bool = False
) -> bool:
    """
    Create folders and move screenshots.

    Args:
        sessions: List of sessions to create
        uncategorized: List of uncategorized screenshots
        desktop_path: Path to desktop
        dry_run: If True, only show what would be done

    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        print("\n[DRY RUN - No files will be moved]\n")

    try:
        # Create session folders and move files
        for session in sessions:
            folder_path = desktop_path / session.folder_name

            if dry_run:
                print(f"Would create: {folder_path}")
            else:
                folder_path.mkdir(exist_ok=True)
                print(f"Created: {folder_path}")

            for screenshot in session.screenshots:
                dest_path = folder_path / screenshot.path.name

                if dry_run:
                    print(f"  Would move: {screenshot.path.name}")
                else:
                    shutil.move(str(screenshot.path), str(dest_path))
                    print(f"  Moved: {screenshot.path.name}")

        # Handle uncategorized
        if uncategorized:
            uncategorized_folder = desktop_path / "uncategorized"

            if dry_run:
                print(f"\nWould create: {uncategorized_folder}")
            else:
                uncategorized_folder.mkdir(exist_ok=True)
                print(f"\nCreated: {uncategorized_folder}")

            for screenshot in uncategorized:
                dest_path = uncategorized_folder / screenshot.path.name

                if dry_run:
                    print(f"  Would move: {screenshot.path.name}")
                else:
                    shutil.move(str(screenshot.path), str(dest_path))
                    print(f"  Moved: {screenshot.path.name}")

        if not dry_run:
            print("\n✅ Organization complete!")

        return True

    except Exception as e:
        print(f"\n❌ Error during organization: {e}")
        return False


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for screenshot organizer."""
    parser = argparse.ArgumentParser(
        description="Organize screenshots into session folders based on time and similarity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                           # Basic time-based organization
  %(prog)s --dry-run                                 # Preview without moving files
  %(prog)s --smart-naming                            # Use OCR + LLM for descriptive names
  %(prog)s --smart-naming --merge-similar            # Smart naming + merge similar sessions
  %(prog)s --session-gap 30 --merge-similar          # 30 min gaps + merging
  %(prog)s --desktop-path ~/Downloads --auto-confirm # Organize different folder
        """
    )

    parser.add_argument(
        '--desktop-path',
        type=Path,
        default=Path.home() / 'Desktop',
        help='Path to desktop or folder to organize (default: ~/Desktop)'
    )

    parser.add_argument(
        '--session-gap',
        type=int,
        default=15,
        metavar='MINUTES',
        help='Maximum gap in minutes between screenshots in same session (default: 15)'
    )

    parser.add_argument(
        '--smart-naming',
        action='store_true',
        help='Use OCR and LLM to generate descriptive session names (requires pytesseract and ollama)'
    )

    parser.add_argument(
        '--merge-similar',
        action='store_true',
        help='Merge consecutive sessions with similar names (requires --smart-naming for best results)'
    )

    parser.add_argument(
        '--merge-threshold',
        type=float,
        default=0.5,
        metavar='THRESHOLD',
        help='Similarity threshold for merging sessions (0.0-1.0, default: 0.5)'
    )

    parser.add_argument(
        '--enable-similarity',
        action='store_true',
        help='Enable visual similarity splitting (disabled by default for multi-system monitoring)'
    )

    parser.add_argument(
        '--similarity-threshold',
        type=int,
        default=10,
        metavar='N',
        help='Perceptual hash difference threshold for splitting sessions (default: 10, only used with --enable-similarity)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without moving files'
    )

    parser.add_argument(
        '--auto-confirm',
        action='store_true',
        help='Skip confirmation prompt and proceed automatically'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed output including similarity scores (if enabled)'
    )

    args = parser.parse_args()

    # Validate desktop path
    if not args.desktop_path.exists():
        print(f"Error: Path does not exist: {args.desktop_path}")
        return 1

    print(f"Screenshot Organizer")
    print(f"Scanning: {args.desktop_path}")
    print(f"Session gap: {args.session_gap} minutes")
    if args.enable_similarity:
        print(f"Similarity splitting: ENABLED (threshold: {args.similarity_threshold})")
    else:
        print(f"Similarity splitting: DISABLED (use --enable-similarity to enable)")

    # Step 1: Find screenshots
    screenshots = find_screenshots(args.desktop_path)

    if not screenshots:
        print("\nNo screenshots found!")
        return 0

    print(f"Found {len(screenshots)} screenshots")

    # Step 2: Cluster by time
    sessions = cluster_by_time(screenshots, gap_minutes=args.session_gap)
    print(f"Time-based clustering: {len(sessions)} sessions")

    # Step 3: Refine by similarity (optional)
    if args.enable_similarity:
        if args.verbose:
            print("\nCalculating perceptual hashes and similarities...")

        sessions = refine_sessions_by_similarity(
            sessions,
            threshold=args.similarity_threshold,
            verbose=args.verbose
        )
        print(f"After similarity refinement: {len(sessions)} sessions")

    # Step 4: Generate session names
    if args.smart_naming:
        if not PYTESSERACT_AVAILABLE:
            print("⚠️  Warning: pytesseract not available. Falling back to timestamp-based naming.")
            print("   Install with: pip install pytesseract")
        else:
            print("\n🤖 Generating smart session names with OCR + LLM...")
    generate_session_names(sessions, use_smart_naming=args.smart_naming, verbose=args.verbose)

    # Step 4.5: Merge similar sessions (optional)
    if args.merge_similar:
        if not args.smart_naming:
            print("⚠️  Warning: --merge-similar works best with --smart-naming enabled")
        print(f"\n🔗 Merging similar sessions (threshold: {args.merge_threshold})...")
        sessions = merge_similar_sessions(
            sessions,
            similarity_threshold=args.merge_threshold,
            verbose=args.verbose
        )

    # Step 5: Identify uncategorized
    regular_sessions, uncategorized = identify_uncategorized(sessions)

    # Step 6: Display plan
    display_organization_plan(regular_sessions, uncategorized)

    # Step 7: Confirm and execute
    if args.dry_run:
        execute_organization(regular_sessions, uncategorized, args.desktop_path, dry_run=True)
        return 0

    if not args.auto_confirm:
        if not confirm_action():
            print("Cancelled.")
            return 0

    success = execute_organization(regular_sessions, uncategorized, args.desktop_path)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
