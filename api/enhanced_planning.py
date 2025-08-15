"""Enhanced LLM-driven planning with tool chaining intelligence."""

async def llm_driven_plan(goal: str, session_state, available_tools: Dict) -> Dict:
    """Use LLM to create intelligent multi-step plans."""
    
    # Build rich context including successful patterns
    context = build_planning_context(session_state, available_tools)
    
    # Use few-shot examples for common patterns
    examples = get_planning_examples()
    
    prompt = f"""You are an expert AI planning agent. Create an intelligent plan to accomplish: "{goal}"

{context}

SUCCESSFUL PATTERNS:
{examples}

Create a plan that uses tool chaining and intelligent decomposition.
Respond with valid JSON only."""

    # Implement with retry and repair logic
    return await llm_plan_with_repair(prompt)
