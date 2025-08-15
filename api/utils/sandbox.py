"""Filesystem sandbox utilities for secure path operations."""
import os
import fnmatch
from pathlib import Path
from typing import List, Optional, Dict, Any


class SandboxError(Exception):
    """Raised when sandbox validation fails."""
    pass


class PathValidator:
    """Validates and sanitizes filesystem paths within sandbox."""
    
    def __init__(self, sandbox_root: Optional[str] = None):
        if sandbox_root:
            self.sandbox_root = Path(os.path.expanduser(os.path.expandvars(sandbox_root))).resolve()
        else:
            self.sandbox_root = Path.home().resolve()
    
    def validate_path(self, path_str: str, allow_create: bool = False) -> Path:
        """
        Validate and resolve path within sandbox.
        
        Args:
            path_str: Input path string
            allow_create: Whether to allow non-existent paths
        
        Returns:
            Resolved Path object
            
        Raises:
            SandboxError: If path is outside sandbox or invalid
        """
        if not path_str or not path_str.strip():
            raise SandboxError("Empty path")
        
        # Expand user and environment variables
        expanded = os.path.expanduser(os.path.expandvars(path_str.strip()))
        
        try:
            # Resolve to absolute path
            resolved = Path(expanded).resolve()
            
            # Check if within sandbox
            try:
                resolved.relative_to(self.sandbox_root)
            except ValueError:
                raise SandboxError(f"Path outside sandbox: {resolved}")
            
            # Check existence if required
            if not allow_create and not resolved.exists():
                raise SandboxError(f"Path does not exist: {resolved}")
            
            return resolved
            
        except (OSError, ValueError) as e:
            raise SandboxError(f"Invalid path: {path_str} - {str(e)}")
    
    def is_dotfile(self, path: Path) -> bool:
        """Check if path is a dotfile/hidden file."""
        return any(part.startswith('.') for part in path.parts[len(self.sandbox_root.parts):])
    
    def filter_dotfiles(self, paths: List[Path], allow_dotfiles: bool = False) -> List[Path]:
        """Filter out dotfiles unless explicitly allowed."""
        if allow_dotfiles:
            return paths
        return [p for p in paths if not self.is_dotfile(p)]


def validate_tool_args(tool_name: str, args: Dict[str, Any], policies: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate tool arguments against security policies.
    
    Args:
        tool_name: Name of the tool
        args: Tool arguments
        policies: Security policies from config
        
    Returns:
        Validated arguments
        
    Raises:
        SandboxError: If validation fails
    """
    tool_policy = policies.get('tools', {}).get(tool_name, {})
    
    # Check if tool is enabled
    if not tool_policy.get('enabled', True):
        raise SandboxError(f"Tool {tool_name} is disabled")
    
    validated_args = args.copy()
    
    # Validate specific argument types and limits
    if tool_name in ['list_files', 'count_files', 'count_dirs']:
        if 'limit' in args:
            max_limit = tool_policy.get('max_limit', 500)
            if args['limit'] > max_limit:
                validated_args['limit'] = max_limit
    
    elif tool_name == 'read_file':
        if 'length' in args:
            max_length = tool_policy.get('max_length', 65536)
            if args['length'] > max_length:
                validated_args['length'] = max_length
    
    elif tool_name == 'web_get':
        if 'url' not in args:
            raise SandboxError("web_get requires url argument")
        
        # Basic URL validation
        url = args['url'].strip()
        if not url.startswith(('http://', 'https://')):
            raise SandboxError("Invalid URL scheme")
        
        # Check against blocked domains
        blocked_domains = tool_policy.get('blocked_domains', [])
        for domain in blocked_domains:
            if domain in url:
                raise SandboxError(f"Blocked domain: {domain}")
    
    elif tool_name == 'delete_files':
        # Destructive tool requires special handling
        if not args.get('confirm', False):
            raise SandboxError("delete_files requires confirm=true")
        
        if not tool_policy.get('require_confirm', True):
            raise SandboxError("Destructive operations require confirmation")
    
    return validated_args


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem operations."""
    # Remove or replace dangerous characters
    sanitized = "".join(c for c in filename if c.isalnum() or c in "._- ")
    
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    
    # Limit length
    if len(sanitized) > 255:
        sanitized = sanitized[:255]
    
    # Ensure not empty
    if not sanitized:
        sanitized = "unnamed"
    
    return sanitized


def get_safe_glob_pattern(pattern: str) -> str:
    """Sanitize glob pattern to prevent directory traversal."""
    # Remove dangerous patterns
    dangerous = ['..', '/', '\\', '~']
    for danger in dangerous:
        pattern = pattern.replace(danger, '')
    
    # Default to safe pattern if empty
    if not pattern.strip():
        pattern = '*'
    
    return pattern.strip()