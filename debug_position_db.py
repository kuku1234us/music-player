#!/usr/bin/env python3
"""
Debug script to check for duplicate entries in the position database and optionally remove them.
"""
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from qt_base_app.models.settings_manager import SettingsManager, SettingType

# Define constants directly to avoid circular import issues
PREF_WORKING_DIR_KEY = 'preferences/working_dir'
DEFAULT_WORKING_DIR = os.path.expanduser("~")

def find_database_path():
    """Find the position database file."""
    # Try to find the database in common locations
    possible_locations = [
        # Current directory
        os.path.join(os.getcwd(), "playback_positions.db"),
        # Project root
        os.path.join(project_root, "playback_positions.db"),
        # User home directory
        os.path.join(os.path.expanduser("~"), "playback_positions.db"),
        # Documents folder
        os.path.join(os.path.expanduser("~"), "Documents", "playback_positions.db"),
    ]
    
    # Try to get the configured working directory
    try:
        SettingsManager.initialize("MusicPlayer", "MusicPlayer")
        settings = SettingsManager.instance()
        working_dir = settings.get(PREF_WORKING_DIR_KEY, DEFAULT_WORKING_DIR, SettingType.PATH)
        # Convert Path object to string if needed
        if hasattr(working_dir, '__str__'):
            working_dir = str(working_dir)
        configured_db_path = os.path.join(working_dir, "playback_positions.db")
        possible_locations.insert(0, configured_db_path)  # Check configured location first
        print(f"Configured working directory: {working_dir}")
    except Exception as e:
        print(f"Could not load settings: {e}")
    
    db_path = None
    for path in possible_locations:
        print(f"Checking: {path}")
        if os.path.exists(path):
            db_path = path
            print(f"✓ Found database at: {db_path}")
            break
        else:
            print(f"✗ Not found")
    
    if not db_path:
        print(f"\nDatabase not found in any of the checked locations:")
        for path in possible_locations:
            print(f"  - {path}")
        print(f"\nTry running the music player app first to create the database.")
        return None
    
    return db_path

def find_duplicates(db_path):
    """Find duplicate entries in the database."""
    duplicates = []
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Get all entries
        cursor.execute("SELECT file_path, position_ms, duration_ms, playback_rate, last_updated FROM playback_positions ORDER BY file_path")
        rows = cursor.fetchall()
        
        print(f"Total entries: {len(rows)}\n")
        
        # Group by basename to find potential duplicates
        basenames = {}
        
        for row in rows:
            file_path, position_ms, duration_ms, playback_rate, last_updated = row
            basename = os.path.basename(file_path)
            
            if basename not in basenames:
                basenames[basename] = []
            basenames[basename].append(row)
        
        # Find actual duplicates (same file, different paths)
        for basename, entries in basenames.items():
            if len(entries) > 1:
                # Check if any of these are real duplicates
                # For each pair, check if they might be the same file
                duplicate_groups = []
                processed_indices = set()
                
                for i, entry1 in enumerate(entries):
                    if i in processed_indices:
                        continue
                        
                    file_path1 = entry1[0]
                    duplicate_group = [entry1]
                    group_indices = {i}
                    
                    for j, entry2 in enumerate(entries[i+1:], i+1):
                        if j in processed_indices:
                            continue
                            
                        file_path2 = entry2[0]
                        
                        # Check if these might be the same file
                        if are_same_file(file_path1, file_path2, basename):
                            duplicate_group.append(entry2)
                            group_indices.add(j)
                    
                    # If we found duplicates, add them to the list
                    if len(duplicate_group) > 1:
                        # Use the most normalized path as the identifier
                        normalized_path = get_best_normalized_path([entry[0] for entry in duplicate_group])
                        duplicates.append((basename, normalized_path, duplicate_group))
                        processed_indices.update(group_indices)
    
    return duplicates

def are_same_file(path1, path2, basename):
    """Check if two paths likely refer to the same file."""
    # If paths are identical, they're the same
    if path1 == path2:
        return True
    
    # Try standard normalization first
    try:
        norm1 = os.path.abspath(path1)
        norm2 = os.path.abspath(path2)
        if norm1 == norm2:
            return True
    except Exception:
        pass
    
    # Normalize slashes for comparison
    def normalize_slashes(path):
        return path.replace('/', '\\')
    
    path1_norm = normalize_slashes(path1)
    path2_norm = normalize_slashes(path2)
    
    # Handle network path vs mapped drive scenarios
    # Extract the relative path after the root
    def extract_relative_path(path):
        """Extract the relative path part for comparison."""
        # Normalize slashes first
        path = normalize_slashes(path)
        
        # Handle different path formats
        if path.startswith('\\\\'):
            # UNC path: \\server\share\folder\file.ext
            parts = path.split('\\')
            if len(parts) >= 4:
                # Skip \\server\share, keep the rest
                return '\\'.join(parts[4:])
        elif len(path) >= 3 and path[1] == ':':
            # Drive letter: Z:\folder\file.ext
            return path[3:]  # Skip Z:\
        elif path.startswith('\\'):
            # Unix-style path or just backslash path
            return path[1:]  # Skip leading \
        
        return path
    
    rel1 = extract_relative_path(path1_norm)
    rel2 = extract_relative_path(path2_norm)
    
    # If the relative paths are the same, they're likely the same file
    if rel1 == rel2 and rel1:
        return True
    
    # As a final check, see if they end with the same substantial path
    # (more than just the filename)
    def get_path_suffix(path, depth=3):
        """Get the last 'depth' components of a path."""
        path = normalize_slashes(path)
        parts = path.split('\\')
        # Filter out empty parts
        parts = [p for p in parts if p]
        if len(parts) <= depth:
            return '\\'.join(parts)
        return '\\'.join(parts[-depth:])
    
    suffix1 = get_path_suffix(path1_norm)
    suffix2 = get_path_suffix(path2_norm)
    
    # If they have the same suffix with at least 2 path components, they're likely the same
    if suffix1 == suffix2 and suffix1.count('\\') >= 1:
        return True
    
    return False

def get_best_normalized_path(paths):
    """Get the best normalized path from a list of equivalent paths."""
    # Prefer paths that can be normalized successfully
    for path in paths:
        try:
            normalized = os.path.abspath(path)
            # Prefer paths that don't start with \\ (UNC) if we have alternatives
            if not normalized.startswith('\\\\'):
                return normalized
        except Exception:
            continue
    
    # If all are UNC or couldn't normalize, just return the first one
    return paths[0] if paths else ""

def remove_duplicates(db_path, duplicates, dry_run=True):
    """Remove duplicate entries, keeping the most recent one."""
    if not duplicates:
        print("No duplicates to remove.")
        return 0
    
    removed_count = 0
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        for basename, normalized_path, duplicate_entries in duplicates:
            print(f"\nProcessing duplicates for: {basename}")
            print(f"Normalized path: {normalized_path}")
            
            # Sort by last_updated to keep the most recent
            sorted_entries = sorted(duplicate_entries, key=lambda x: x[4], reverse=True)
            keep_entry = sorted_entries[0]
            remove_entries = sorted_entries[1:]
            
            print(f"  Keeping: {keep_entry[0]} (updated: {keep_entry[4]})")
            
            for entry in remove_entries:
                file_path, position_ms, duration_ms, playback_rate, last_updated = entry
                print(f"  {'Would remove' if dry_run else 'Removing'}: {file_path} (updated: {last_updated})")
                
                if not dry_run:
                    cursor.execute("DELETE FROM playback_positions WHERE file_path = ?", (file_path,))
                    removed_count += 1
        
        if not dry_run:
            conn.commit()
            print(f"\nRemoved {removed_count} duplicate entries.")
        else:
            print(f"\nDry run complete. Would remove {len([entry for _, _, entries in duplicates for entry in entries[1:]])} duplicate entries.")
    
    return removed_count

def clear_all_entries(db_path):
    """Remove all entries from the position database."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get count before deletion
            cursor.execute("SELECT COUNT(*) FROM playback_positions")
            total_before = cursor.fetchone()[0]
            
            # Delete all entries
            cursor.execute("DELETE FROM playback_positions")
            conn.commit()
            
            print(f"Successfully removed all {total_before} entries from the position database.")
            return True
            
    except sqlite3.Error as e:
        print(f"Error clearing database: {e}")
        return False

def check_position_database():
    """Check for duplicate entries in the position database."""
    print("=== Position Database Checker ===\n")
    
    db_path = find_database_path()
    if not db_path:
        return
    
    print(f"Database location: {db_path}")
    print(f"Database size: {os.path.getsize(db_path)} bytes\n")
    
    try:
        duplicates = find_duplicates(db_path)
        
        if duplicates:
            print("=== DUPLICATES FOUND ===")
            for basename, normalized_path, entries in duplicates:
                print(f"\nFile: {basename}")
                print(f"Normalized path: {normalized_path}")
                for i, entry in enumerate(entries):
                    file_path, position_ms, duration_ms, playback_rate, last_updated = entry
                    print(f"  {i+1}. {file_path}")
                    print(f"     Position: {position_ms}ms, Duration: {duration_ms}ms, Rate: {playback_rate}x")
                    print(f"     Last updated: {last_updated}")
            
            print(f"\n=== SUMMARY ===")
            print(f"Found {len(duplicates)} duplicate groups")
            
            # Ask user if they want to remove duplicates
            response = input("\nWould you like to remove duplicates? (y/n): ").lower().strip()
            if response == 'y':
                print("\nRemoving duplicates...")
                success = remove_duplicates(db_path, duplicates, dry_run=False)
                if success:
                    print("Duplicates removed successfully!")
                else:
                    print("Failed to remove some duplicates.")
        else:
            print("No duplicates found!")
        
        # Ask if user wants to clear all entries
        print("\n" + "="*50)
        response = input("Would you like to CLEAR ALL ENTRIES from the database? (y/n): ").lower().strip()
        if response == 'y':
            confirm = input("Are you sure? This will delete ALL saved positions! (y/n): ").lower().strip()
            if confirm == 'y':
                print("\nClearing all entries...")
                success = clear_all_entries(db_path)
                if success:
                    print("Database cleared successfully! Starting fresh.")
                else:
                    print("Failed to clear database.")
            else:
                print("Clear operation cancelled.")
        
        # Ask if user wants to view all entries (only if not cleared)
        if not (response == 'y' and confirm == 'y'):
            print("\n" + "="*50)
            view_response = input("Would you like to view all entries? (y/n): ").lower().strip()
            if view_response == 'y':
                show_all_entries(db_path)
                
    except Exception as e:
        print(f"Error checking database: {e}")

def show_all_entries(db_path):
    """Show all database entries for debugging."""
    print("\n=== ALL ENTRIES ===")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, position_ms, duration_ms, playback_rate, last_updated FROM playback_positions ORDER BY last_updated DESC")
        rows = cursor.fetchall()
        
        for i, row in enumerate(rows, 1):
            file_path, position_ms, duration_ms, playback_rate, last_updated = row
            basename = os.path.basename(file_path)
            print(f"{i:2d}. {basename}")
            print(f"     Path: {file_path}")
            print(f"     Position: {position_ms}ms, Duration: {duration_ms}ms, Rate: {playback_rate}x")
            print(f"     Updated: {last_updated}")
            print()

if __name__ == "__main__":
    check_position_database() 