"""Core filesystem tools with sandbox enforcement."""
import os
import fnmatch
import time
from pathlib import Path
from typing import List, Dict, Any, Union
import logging

from ..utils.sandbox import PathValidator, SandboxError, get_safe_glob_pattern, sanitize_filename


logger = logging.getLogger(__name__)
path_validator = PathValidator()


def list_files(
    dir: str = "~",
    pattern: str = "*",
    sort: str = "name",
    limit: int = 200
) -> List[Dict[str, Any]]:
    """
    List files and directories with sorting and filtering.
    
    Args:
        dir: Directory path to list
        pattern: Glob pattern for filtering
        sort: Sort order (name, mtime, size)
        limit: Maximum number of items to return
        
    Returns:
        List of file/directory information dictionaries
        
    Raises:
        SandboxError: If path is outside sandbox or invalid
    """
    try:
        # Validate and resolve directory path
        dir_path = path_validator.validate_path(dir)
        
        if not dir_path.is_dir():
            raise SandboxError(f"Not a directory: {dir_path}")
        
        # Sanitize pattern
        safe_pattern = get_safe_glob_pattern(pattern)
        
        # Collect items
        items = []
        try:
            for item_path in dir_path.iterdir():
                # Check if item matches pattern
                if not fnmatch.fnmatch(item_path.name, safe_pattern):
                    continue
                
                try:
                    stat = item_path.stat()
                    items.append({
                        'name': item_path.name,
                        'path': str(item_path),
                        'is_dir': item_path.is_dir(),
                        'mtime': stat.st_mtime,
                        'size': stat.st_size if item_path.is_file() else 0
                    })
                except (OSError, PermissionError) as e:
                    logger.warning(f"Cannot stat {item_path}: {e}")
                    continue
        
        except PermissionError:
            raise SandboxError(f"Permission denied: {dir_path}")
        
        # Sort items
        if sort == "mtime":
            items.sort(key=lambda x: x['mtime'], reverse=True)
        elif sort == "size":
            items.sort(key=lambda x: x['size'], reverse=True)
        else:  # default to name
            items.sort(key=lambda x: x['name'].lower())
        
        # Apply limit
        if limit > 0:
            items = items[:limit]
        
        logger.info(f"Listed {len(items)} items from {dir_path}")
        return items
    
    except Exception as e:
        logger.error(f"list_files failed: {e}")
        raise


def read_file(
    path: str,
    offset: int = 0,
    length: int = 65536
) -> str:
    """
    Read file content with offset and length limits.
    
    Args:
        path: File path to read
        offset: Byte offset to start reading
        length: Maximum bytes to read
        
    Returns:
        File content as string
        
    Raises:
        SandboxError: If path is outside sandbox or invalid
    """
    try:
        # Validate file path
        file_path = path_validator.validate_path(path)
        
        if not file_path.is_file():
            raise SandboxError(f"Not a file: {file_path}")
        
        # Check file size
        file_size = file_path.stat().st_size
        if offset >= file_size:
            return ""
        
        # Clamp length to reasonable bounds
        max_length = min(length, 1024 * 1024)  # 1MB max
        actual_length = min(max_length, file_size - offset)
        
        # Read file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(offset)
                content = f.read(actual_length)
            
            logger.info(f"Read {len(content)} chars from {file_path}")
            return content
        
        except UnicodeDecodeError:
            # Try binary mode for non-text files
            with open(file_path, 'rb') as f:
                f.seek(offset)
                binary_content = f.read(actual_length)
                # Convert to readable representation
                content = f"[Binary file: {len(binary_content)} bytes]"
                if len(binary_content) < 1000:
                    # Show hex for small binary files
                    hex_content = binary_content.hex()
                    content += f"\nHex: {hex_content}"
                return content
    
    except Exception as e:
        logger.error(f"read_file failed: {e}")
        raise


def count_files(
    dir: str = "~",
    needle: str = "",
    limit: int = 0
) -> Dict[str, int]:
    """
    Count files in directory, optionally filtering by name.
    
    Args:
        dir: Directory path to search
        needle: Optional substring to filter filenames
        limit: Maximum files to count (0 = unlimited)
        
    Returns:
        Dictionary with count result
    """
    try:
        # Validate directory path
        dir_path = path_validator.validate_path(dir)
        
        if not dir_path.is_dir():
            raise SandboxError(f"Not a directory: {dir_path}")
        
        count = 0
        try:
            for item_path in dir_path.iterdir():
                if item_path.is_file():
                    # Apply needle filter if specified
                    if needle and needle.lower() not in item_path.name.lower():
                        continue
                    
                    count += 1
                    
                    # Apply limit if specified
                    if limit > 0 and count >= limit:
                        break
        
        except PermissionError:
            raise SandboxError(f"Permission denied: {dir_path}")
        
        logger.info(f"Counted {count} files in {dir_path}")
        return {"count": count}
    
    except Exception as e:
        logger.error(f"count_files failed: {e}")
        raise


def count_dirs(
    dir: str = "~",
    needle: str = "",
    limit: int = 0
) -> Dict[str, int]:
    """
    Count directories in directory, optionally filtering by name.
    
    Args:
        dir: Directory path to search
        needle: Optional substring to filter directory names
        limit: Maximum directories to count (0 = unlimited)
        
    Returns:
        Dictionary with count result
    """
    try:
        # Validate directory path
        dir_path = path_validator.validate_path(dir)
        
        if not dir_path.is_dir():
            raise SandboxError(f"Not a directory: {dir_path}")
        
        count = 0
        try:
            for item_path in dir_path.iterdir():
                if item_path.is_dir():
                    # Skip dotfiles unless explicitly requested
                    if path_validator.is_dotfile(item_path) and not needle.startswith('.'):
                        continue
                    
                    # Apply needle filter if specified
                    if needle and needle.lower() not in item_path.name.lower():
                        continue
                    
                    count += 1
                    
                    # Apply limit if specified
                    if limit > 0 and count >= limit:
                        break
        
        except PermissionError:
            raise SandboxError(f"Permission denied: {dir_path}")
        
        logger.info(f"Counted {count} directories in {dir_path}")
        return {"count": count}
    
    except Exception as e:
        logger.error(f"count_dirs failed: {e}")
        raise


def delete_files(
    dir: str,
    needle: str,
    confirm: bool = False,
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Delete files matching pattern (DESTRUCTIVE - requires confirmation).
    
    Args:
        dir: Directory path to search
        needle: Substring that must be in filename
        confirm: Must be True to proceed
        limit: Maximum files to delete
        
    Returns:
        Dictionary with deletion results
        
    Raises:
        SandboxError: If not confirmed or validation fails
    """
    if not confirm:
        raise SandboxError("delete_files requires confirm=True")
    
    if not needle or len(needle) < 2:
        raise SandboxError("delete_files requires needle with at least 2 characters")
    
    try:
        # Validate directory path
        dir_path = path_validator.validate_path(dir)
        
        if not dir_path.is_dir():
            raise SandboxError(f"Not a directory: {dir_path}")
        
        # Find matching files
        files_to_delete = []
        try:
            for item_path in dir_path.iterdir():
                if item_path.is_file() and needle.lower() in item_path.name.lower():
                    files_to_delete.append(item_path)
                    
                    if len(files_to_delete) >= limit:
                        break
        
        except PermissionError:
            raise SandboxError(f"Permission denied: {dir_path}")
        
        if not files_to_delete:
            return {
                "deleted": 0,
                "files": [],
                "errors": [],
                "message": f"No files found matching '{needle}'"
            }
        
        # Delete files
        deleted_files = []
        errors = []
        
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted_files.append(str(file_path))
                logger.info(f"Deleted file: {file_path}")
            except Exception as e:
                error_msg = f"{file_path}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Failed to delete {file_path}: {e}")
        
        result = {
            "deleted": len(deleted_files),
            "files": deleted_files,
            "errors": errors,
            "message": f"Deleted {len(deleted_files)} files"
        }
        
        if errors:
            result["message"] += f", {len(errors)} errors"
        
        return result
    
    except Exception as e:
        logger.error(f"delete_files failed: {e}")
        raise