"""Simple rule-based planner for common tasks."""
import json
from typing import Dict, Any

def create_simple_plan(goal: str) -> Dict[str, Any]:
    """Create a simple plan for common goals without LLM."""
    goal_lower = goal.lower()
    
    # File counting
    if "count files" in goal_lower:
        if "desktop" in goal_lower:
            dir_path = "~/Desktop"
        elif "downloads" in goal_lower:
            dir_path = "~/Downloads"
        elif "documents" in goal_lower:
            dir_path = "~/Documents"
        else:
            dir_path = "~"
        
        return {
            "subgoals": [
                "Identify target directory",
                "Count files in directory",
                "Return count result"
            ],
            "success_criteria": "Return accurate file count",
            "next_action": "count_files",
            "args": {"dir": dir_path, "limit": 0},
            "expected_observation": "Dictionary with count key",
            "rationale": "Direct file counting using filesystem tools"
        }
    
    # File listing
    elif "list files" in goal_lower:
        if "desktop" in goal_lower:
            dir_path = "~/Desktop"
        elif "downloads" in goal_lower:
            dir_path = "~/Downloads"
        else:
            dir_path = "~"
        
        return {
            "subgoals": [
                "Identify target directory",
                "List files in directory",
                "Return file list"
            ],
            "success_criteria": "Return list of files",
            "next_action": "list_files",
            "args": {"dir": dir_path, "sort": "name", "limit": 50},
            "expected_observation": "List of file dictionaries",
            "rationale": "Direct file listing using filesystem tools"
        }
    
    # Default fallback
    else:
        return {
            "subgoals": [
                "Understand the request",
                "Execute appropriate action",
                "Provide helpful response"
            ],
            "success_criteria": "Provide useful information",
            "next_action": "analyze",
            "args": {
                "prompt": f"How can I help with this request: {goal}",
                "context": "No specific context available"
            },
            "expected_observation": "Analysis response",
            "rationale": "General analysis for unclear requests"
        }
