"""Tolerant JSON parser for LLM responses."""
import json
import re
from typing import Any, Dict


def loads_loose(text: str) -> Dict[str, Any]:
    """
    Tolerant JSON parsing with multiple fallback strategies.
    """
    if not text or not text.strip():
        raise ValueError("Empty or whitespace-only input")
    
    text = text.strip()
    
    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Strip markdown code blocks
    if "```" in text:
        # Find content between ```json and ``` or just between ```
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
    
    # Strategy 3: Extract first complete JSON object
    brace_count = 0
    start_idx = None
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx is not None:
                json_slice = text[start_idx:i+1]
                try:
                    return json.loads(json_slice)
                except json.JSONDecodeError:
                    pass
                break
    
    # Strategy 4: Try to fix common issues
    text_fixed = text
    
    # Remove leading/trailing whitespace and newlines
    text_fixed = text_fixed.strip()
    
    # Fix trailing commas
    text_fixed = re.sub(r',(\s*[}\]])', r'\1', text_fixed)
    
    # Fix unquoted keys (common LLM mistake)
    text_fixed = re.sub(r'(\w+)(\s*:)', r'"\1"\2', text_fixed)
    
    # Fix single quotes to double quotes
    text_fixed = text_fixed.replace("'", '"')
    
    # Try again
    try:
        return json.loads(text_fixed)
    except json.JSONDecodeError:
        pass
    
    # Strategy 5: Create a minimal valid response
    print(f"JSON parse failed, creating fallback. Original text: {text[:200]}...")
    return {
        "subgoals": ["Understand the request", "Execute the task", "Provide results"],
        "success_criteria": "Complete the requested task",
        "next_action": "count_files",
        "args": {"dir": "~/Desktop", "limit": 0},
        "expected_observation": "Dictionary with count key",
        "rationale": "Fallback plan due to JSON parsing error"
    }


def validate_plan_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate planner JSON structure and fill missing fields."""
    required_fields = {
        'subgoals': list,
        'success_criteria': str,
        'next_action': str,
        'args': dict,
        'expected_observation': str,
        'rationale': str
    }
    
    for field, expected_type in required_fields.items():
        if field not in data:
            if field == 'subgoals':
                data[field] = ["Complete the task", "Verify results"]
            elif field == 'args':
                data[field] = {}
            else:
                data[field] = ""
        
        if not isinstance(data[field], expected_type):
            if expected_type == str:
                data[field] = str(data[field])
            elif expected_type == list:
                data[field] = [] if not data[field] else list(data[field])
            elif expected_type == dict:
                data[field] = {} if not data[field] else dict(data[field])
    
    # Ensure subgoals has at least 2 items
    if len(data['subgoals']) < 2:
        data['subgoals'] = data['subgoals'] + ["Complete the task", "Verify results"]
    elif len(data['subgoals']) > 7:
        data['subgoals'] = data['subgoals'][:7]
    
    return data
