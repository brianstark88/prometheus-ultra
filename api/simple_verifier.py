"""LLM-powered verifier that creates natural conversational responses."""
import re
import json
import asyncio
from .tools.core_llm import get_llm_client

def simple_verify(goal, recent_observations, last_step_successful=True):
    """Use LLM to create natural responses based on the goal and observations."""
    if not recent_observations:
        return {
            "finish": False,
            "result": "I need to gather some information first to help you with that.",
            "confidence": 0.0
        }
    
    last_obs = recent_observations[-1] if recent_observations else ""
    
    # Check if we have meaningful results
    if not last_step_successful or len(last_obs) < 10:
        return {
            "finish": False,
            "result": "I'm still working on that. Let me gather more information.",
            "confidence": 0.4
        }
    
    # Use LLM to generate a natural response
    try:
        llm_client = get_llm_client()
        
        # Create a prompt for the LLM to respond naturally
        prompt = f"""You are a helpful AI assistant. A user asked: "{goal}"

You executed some tools and got this result: {last_obs}

Please provide a natural, conversational response to the user based on these results. Be helpful, friendly, and extract the key information they care about. If there are specific numbers, file names, or data, include them in your response.

Keep your response concise but informative. Respond as if you're having a natural conversation."""

        result = llm_client.generate_sync(
            prompt=prompt,
            temperature=0.3,
            max_tokens=200
        )
        
        if result['success'] and result['response'] != 'INSUFFICIENT':
            response_text = result['response'].strip()
            
            # Make sure it's not too long
            if len(response_text) > 500:
                response_text = response_text[:500] + "..."
            
            return {
                "finish": True,
                "result": response_text,
                "confidence": 0.8
            }
    
    except Exception as e:
        print(f"LLM verifier failed: {e}")
    
    # Fallback to rule-based extraction if LLM fails
    return _extract_key_info(goal, last_obs)

def _extract_key_info(goal, observation):
    """Fallback extractor for key information."""
    goal_lower = goal.lower()
    
    # File counting
    if "count" in goal_lower:
        count_match = re.search(r'"count":\s*(\d+)', observation)
        if count_match:
            count = count_match.group(1)
            return {
                "finish": True,
                "result": f"I found {count} files.",
                "confidence": 0.7
            }
    
    # File listing  
    elif "list" in goal_lower:
        len_match = re.search(r'len=(\d+)', observation)
        if len_match:
            count = len_match.group(1)
            return {
                "finish": True,
                "result": f"I found {count} files in the directory.",
                "confidence": 0.7
            }
    
    # Generic fallback
    return {
        "finish": True,
        "result": "Task completed! The detailed results are shown above.",
        "confidence": 0.6
    }
