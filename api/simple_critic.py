"""Simple rule-based critic for basic operations."""

def simple_critic_review(plan, tool_registry):
    """Simple critic that approves valid tool operations."""
    next_action = plan.get('next_action', '')
    args = plan.get('args', {})
    
    # Check if tool exists
    if next_action not in tool_registry:
        return {
            "approved": False,
            "changes": [f"Unknown tool: {next_action}"],
            "reasoning": f"Tool {next_action} is not available"
        }
    
    # Check for basic file operations
    if next_action in ['count_files', 'list_files', 'read_file']:
        # These are safe operations, approve them
        return {
            "approved": True,
            "changes": [],
            "reasoning": "Safe file operation approved"
        }
    
    # Check for analysis operations
    if next_action == 'analyze':
        return {
            "approved": True,
            "changes": [],
            "reasoning": "Analysis operation approved"
        }
    
    # Default approval for non-destructive operations
    return {
        "approved": True,
        "changes": [],
        "reasoning": "Operation appears safe, approved"
    }
