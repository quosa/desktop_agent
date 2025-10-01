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

from PIL import Image
import imagehash


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

def cluster_by_time(screenshots: List[Screenshot], gap_minutes: int = 15) -> List[Session]:
    """
    Group screenshots into sessions based on time proximity.

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

        if time_gap <= timedelta(minutes=gap_minutes):
            # Same session
            current_session.add_screenshot(current)
        else:
            # Start new session
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

def generate_session_names(sessions: List[Session]) -> None:
    """
    Generate folder names for sessions based on timestamp.

    Args:
        sessions: List of sessions to name (modified in place)
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
            time_str = session.start_time.strftime("%H%M%S")
            session.folder_name = f"{date_str}_{time_str}_session_{idx}"


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
  %(prog)s                                    # Organize ~/Desktop with defaults
  %(prog)s --dry-run                          # Preview without moving files
  %(prog)s --session-gap 30                   # Use 30 minute session gap
  %(prog)s --desktop-path ~/Downloads         # Organize different folder
  %(prog)s --auto-confirm --verbose           # Auto-confirm with detailed output
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
    generate_session_names(sessions)

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
