"""Enhanced planning module with intelligent tool chaining."""
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .utils.json_loose import loads_loose, validate_plan_json
from .utils.fallback import ModelFallbackManager
from .tools import get_tool_registry


logger = logging.getLogger(__name__)


class EnhancedPlanningAgent:
    """Enhanced planning agent with tool chaining intelligence."""
    
    def __init__(self, fallback_manager: ModelFallbackManager, prompts_dir: str = "api/prompts"):
        self.fallback_manager = fallback_manager
        self.prompts_dir = Path(prompts_dir)
        self.tool_registry = get_tool_registry()
        
        # Load enhanced prompt templates
        self.planner_prompt = self._load_prompt("enhanced_planner.txt")
        self.critic_prompt = self._load_prompt("enhanced_critic.txt") 
        self.verifier_prompt = self._load_prompt("enhanced_verifier.txt")
        self.chain_detector_prompt = self._load_prompt("chain_detector.txt")
        
        # Tool chaining patterns (learned from successful sequences)
        self.successful_chains = self._load_successful_chains()
    
    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file."""
        try:
            prompt_path = self.prompts_dir / filename
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Failed to load prompt {filename}: {e}")
            # Return fallback prompts
            if "planner" in filename:
                return self._get_fallback_planner_prompt()
            elif "critic" in filename:
                return self._get_fallback_critic_prompt()
            elif "verifier" in filename:
                return self._get_fallback_verifier_prompt()
            return "Error loading prompt template"
    
    def _get_fallback_planner_prompt(self) -> str:
        """Fallback planner prompt."""
        return """You are an expert AI planning agent. Create an intelligent plan for this goal:

Goal: "{goal}"

Available tools:
{available_tools}

Session context:
{session_context}

Failed attempts to avoid:
{failed_attempts}

Create a plan with intelligent tool chaining. Respond in JSON format:
{{
  "subgoals": ["goal1", "goal2", "goal3"],
  "success_criteria": "criteria",
  "next_action": "tool_name",
  "args": {{}},
  "expected_observation": "expectation",
  "rationale": "reasoning",
  "tool_chain": ["tool1", "tool2", "tool3"],
  "confidence": 0.8
}}"""
    
    def _get_fallback_critic_prompt(self) -> str:
        """Fallback critic prompt."""
        return """Review this plan for safety, efficiency, and success probability:

Plan: {proposed_plan}

Available tools: {available_tools}
Steps remaining: {steps_remaining}
Failed attempts: {failed_attempts}

Respond in JSON format:
{{
  "approved": true/false,
  "changes": [],
  "reasoning": "detailed analysis"
}}"""
    
    def _get_fallback_verifier_prompt(self) -> str:
        """Fallback verifier prompt."""
        return """Determine if this goal has been accomplished:

Goal: "{goal}"

Recent observations ({obs_count} items):
{recent_observations}

Respond in JSON format:
{{
  "finish": true/false,
  "result": "clear summary",
  "confidence": 0.8
}}"""
    
    def _load_successful_chains(self) -> Dict[str, List[str]]:
        """Load successful tool chain patterns from learning data."""
        # This would load from .ultra/learning.ndjson in production
        return {
            "file_analysis": ["list_files", "read_file", "analyze"],
            "web_research": ["web_get", "analyze", "summarize"],
            "comparison_task": ["list_files", "read_file", "read_file", "analyze"],
            "counting_task": ["count_files", "analyze"],
            "recent_file": ["list_files:mtime", "read_file", "analyze"],
            "batch_counting": ["count_files", "count_dirs", "analyze"],
            "knowledge_question": ["analyze"]
        }
    
    async def plan_with_chaining(
        self,
        goal: str,
        session_state,
        max_steps_ahead: int = 3
    ) -> Dict[str, Any]:
        """
        Generate intelligent multi-step plans with tool chaining.
        
        Args:
            goal: User's goal
            session_state: Current session state
            max_steps_ahead: Maximum steps to plan ahead
            
        Returns:
            Enhanced plan with multi-step chain and alternatives
        """
        # Step 1: Detect goal type and suggest tool chains
        goal_analysis = await self._analyze_goal_type(goal, session_state)
        
        # Step 2: Generate multi-step plan with chaining
        chain_plan = await self._generate_chain_plan(goal, goal_analysis, session_state, max_steps_ahead)
        
        # Step 3: Add fallback strategies
        chain_plan['fallback_strategies'] = await self._generate_fallbacks(goal, chain_plan)
        
        return chain_plan
    
    async def _analyze_goal_type(self, goal: str, session_state) -> Dict[str, Any]:
        """Analyze goal to determine type and suggest tool chains."""
        
        # Build context for goal analysis
        available_tools = self._format_available_tools()
        recent_context = session_state.get_context_summary()
        
        prompt = f"""Analyze this user goal and determine the best approach:

Goal: "{goal}"

Available Tools:
{available_tools}

Recent Context:
{recent_context}

Known Successful Patterns:
- File analysis: list_files → read_file → analyze
- Web research: web_get → analyze → summarize  
- Counting tasks: count_files/count_dirs → analyze
- Recent files: list_files(sort=mtime) → read_file → analyze
- Comparisons: multiple read_file → analyze
- Batch operations: parallel count_files + count_dirs → merge → analyze
- Knowledge questions: analyze (direct answer)

Respond in JSON format:
{{
  "goal_type": "file_analysis|web_research|counting|comparison|batch|knowledge_question|other",
  "suggested_chain": ["tool1", "tool2", "tool3"],
  "key_entities": ["file", "directory", "website", "etc"],
  "complexity": "simple|medium|complex",
  "parallel_possible": true/false,
  "reasoning": "why this approach"
}}"""

        payload = {
            "prompt": prompt,
            "options": {
                "temperature": 0.2,
                "format": "json",
                "num_predict": 512
            }
        }
        
        try:
            result = await self.fallback_manager.call_with_fallback(payload)
            if result['success']:
                return loads_loose(result['data']['response'])
        except Exception as e:
            logger.warning(f"Goal analysis failed: {e}")
        
        # Fallback analysis
        goal_type = "knowledge_question" if self._is_knowledge_question(goal) else "other"
        return {
            "goal_type": goal_type,
            "suggested_chain": ["analyze"],
            "key_entities": [],
            "complexity": "medium",
            "parallel_possible": False,
            "reasoning": "Fallback analysis due to LLM failure"
        }
    
    async def _generate_chain_plan(
        self, 
        goal: str, 
        goal_analysis: Dict[str, Any], 
        session_state, 
        max_steps: int
    ) -> Dict[str, Any]:
        """Generate a multi-step plan with tool chaining."""
        
        available_tools = self._format_available_tools()
        session_context = session_state.get_context_summary()
        failed_attempts = self._format_failed_attempts(session_state)
        
        # Use enhanced prompt with chaining context
        prompt = self.planner_prompt.format(
            goal=goal,
            available_tools=available_tools,
            session_context=session_context,
            failed_attempts=failed_attempts
        )
        
        payload = {
            "prompt": prompt,
            "options": {
                "temperature": 0.3,
                "format": "json",
                "num_predict": 1024
            }
        }
        
        try:
            result = await self.fallback_manager.call_with_fallback(payload)
            if result['success']:
                plan_data = loads_loose(result['data']['response'])
                
                # Ensure required fields exist
                if 'next_action' not in plan_data and plan_data.get('step_chain'):
                    first_step = plan_data['step_chain'][0]
                    plan_data['next_action'] = first_step['action']
                    plan_data['args'] = first_step['args']
                    plan_data['expected_observation'] = first_step['expected_output']
                
                # Use goal analysis insights
                if 'tool_chain' not in plan_data:
                    plan_data['tool_chain'] = goal_analysis.get('suggested_chain', ['analyze'])
                
                return plan_data
        except Exception as e:
            logger.error(f"Chain planning failed: {e}")
        
        # Fallback to single step
        return await self._create_fallback_chain_plan(goal, goal_analysis)
    
    async def _generate_fallbacks(self, goal: str, primary_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate fallback strategies if primary plan fails."""
        
        fallbacks = []
        
        # Strategy 1: Simplify to analyze-only
        fallbacks.append({
            "strategy": "analyze_only",
            "action": "analyze", 
            "args": {
                "prompt": f"Help me understand how to approach this goal: {goal}",
                "context": "Primary plan failed, need alternative approach"
            },
            "rationale": "Fallback to LLM analysis when tools fail"
        })
        
        # Strategy 2: Break down goal
        if len(goal.split()) > 3:
            fallbacks.append({
                "strategy": "goal_breakdown",
                "action": "analyze",
                "args": {
                    "prompt": f"Break down this complex goal into simpler steps: {goal}",
                    "context": "Complex goal needs decomposition"
                },
                "rationale": "Decompose complex goals into manageable parts"
            })
        
        # Strategy 3: Use successful pattern from analysis
        primary_action = primary_plan.get('next_action', '')
        if primary_action in self.successful_chains:
            pattern = self.successful_chains[primary_action]
            if len(pattern) > 1:
                fallbacks.append({
                    "strategy": "known_pattern",
                    "action": pattern[1],  # Second step in known pattern
                    "args": {},
                    "rationale": f"Use proven pattern: {' → '.join(pattern)}"
                })
        
        return fallbacks[:2]  # Limit to 2 fallbacks
    
    async def _create_fallback_chain_plan(self, goal: str, goal_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create fallback plan when LLM planning fails."""
        
        # Use suggested chain from goal analysis
        suggested_chain = goal_analysis.get('suggested_chain', ['analyze'])
        first_action = suggested_chain[0]
        
        # Create args based on action type
        if first_action == 'list_files':
            args = {"dir": "~", "sort": "mtime", "limit": 20}
        elif first_action == 'count_files':
            args = {"dir": "~", "limit": 0}
        elif first_action == 'web_get':
            args = {"url": "https://example.com"}  # Would need goal parsing
        else:
            args = {
                "prompt": f"How can I help with this goal: {goal}",
                "context": "Fallback planning due to LLM failure"
            }
        
        return {
            "strategy": "fallback_single_step",
            "subgoals": ["Complete the user's request"],
            "success_criteria": "Provide useful information to help user",
            "next_action": first_action,
            "args": args,
            "expected_observation": f"Output from {first_action}",
            "confidence": 0.6,
            "rationale": "Fallback plan due to enhanced planning failure",
            "tool_chain": suggested_chain
        }
    
    async def critique(
        self,
        proposed_plan: Dict[str, Any],
        session_state,
        steps_remaining: int
    ) -> Dict[str, Any]:
        """
        Critique and potentially modify the proposed plan.
        
        Args:
            proposed_plan: Plan to review
            session_state: Current session state
            steps_remaining: Remaining steps in budget
            
        Returns:
            Critic result with approval and any changes
        """
        # Build critic context
        available_tools = self._format_available_tools()
        session_context = session_state.get_context_summary()
        failed_attempts = self._format_failed_attempts(session_state)
        
        # Build prompt
        prompt = self.critic_prompt.format(
            proposed_plan=str(proposed_plan),
            available_tools=available_tools,
            steps_remaining=steps_remaining,
            failed_attempts=failed_attempts,
            session_context=session_context
        )
        
        # Call LLM with JSON mode
        payload = {
            "prompt": prompt,
            "options": {
                "temperature": 0.2,
                "format": "json",
                "num_predict": 512
            }
        }
        
        try:
            result = await self.fallback_manager.call_with_fallback(payload)
            
            if not result['success']:
                logger.warning(f"Enhanced critic call failed: {result['error']}")
                return {"approved": True, "changes": [], "reasoning": "Critic unavailable, approving plan"}
            
            response_text = result['data']['response']
            critic_data = loads_loose(response_text)
            
            # Validate critic response
            if 'approved' not in critic_data:
                critic_data['approved'] = True
            if 'changes' not in critic_data:
                critic_data['changes'] = []
            if 'reasoning' not in critic_data:
                critic_data['reasoning'] = "No reasoning provided"
            
            logger.info(f"Enhanced critic review: approved={critic_data['approved']}")
            return critic_data
        
        except Exception as e:
            logger.error(f"Enhanced critic failed: {e}")
            return {"approved": True, "changes": [], "reasoning": f"Critic error: {str(e)}"}
    
    async def verify(self, goal: str, recent_observations: List[str], max_obs: int = 8) -> Dict[str, Any]:
    """
    Verify if the goal has been accomplished using enhanced LLM verification.
    
    Args:
        goal: Original user goal
        recent_observations: List of recent observations
        max_obs: Maximum observations to consider
        
    Returns:
        Verification result with finish decision and confidence
    """
    # Limit observations
    obs_to_use = recent_observations[-max_obs:] if recent_observations else []
    
    # Format observations for prompt
    obs_text = "\n".join(f"{i+1}. {obs}" for i, obs in enumerate(obs_to_use))
    if not obs_text:
        obs_text = "No observations available"
    
    # Get the most recent observation as the potential result
    last_observation = obs_to_use[-1] if obs_to_use else "No result available"
    
    # Enhanced verification prompt for knowledge questions
    if self._is_knowledge_question(goal):
        # For knowledge questions, check if we have a proper answer
        if obs_to_use and len(obs_to_use) > 0:
            # The last observation should be the answer
            answer = str(last_observation)
            
            # Quick validation - if it looks like a real answer, we're done
            if len(answer) > 20 and "error" not in answer.lower():
                return {
                    "finish": True,
                    "result": answer,  # Use the actual answer
                    "confidence": 0.95,
                    "success_level": "complete",
                    "reasoning": "Knowledge question answered successfully"
                }
        
        # If no good answer yet, need to continue
        return {
            "finish": False,
            "result": "Still gathering information",
            "confidence": 0.3,
            "success_level": "partial",
            "reasoning": "Knowledge question not yet fully answered"
        }
    
    # For action tasks, check if the action was completed
    if obs_to_use:
        # Check for success indicators in the last observation
        if isinstance(last_observation, str):
            obs_lower = last_observation.lower()
            
            # Check for completion indicators
            if any(indicator in obs_lower for indicator in ['found', 'complete', 'success', 'count']):
                if 'error' not in obs_lower and 'failed' not in obs_lower:
                    return {
                        "finish": True,
                        "result": last_observation,  # Use actual observation
                        "confidence": 0.9,
                        "success_level": "complete",
                        "reasoning": "Task completed successfully based on observation"
                    }
        
        # Check if it's a dict with results
        elif isinstance(last_observation, dict):
            if 'count' in last_observation or 'result' in last_observation:
                return {
                    "finish": True,
                    "result": str(last_observation),
                    "confidence": 0.9,
                    "success_level": "complete",
                    "reasoning": "Task completed with structured result"
                }
    
    # Try LLM verification as fallback
    prompt = f"""Verify if this goal has been accomplished:

Goal: "{goal}"

Recent observations:
{obs_text}

Respond in JSON format:
{{
  "finish": true/false,
  "result": "clear result or status",
  "confidence": 0.0-1.0,
  "success_level": "complete|partial|failed",
  "reasoning": "why this conclusion"
}}"""
    
    # Call LLM with JSON mode
    payload = {
        "prompt": prompt,
        "options": {
            "temperature": 0.1,
            "format": "json",
            "num_predict": 512
        }
    }
    
    try:
        result = await self.fallback_manager.call_with_fallback(payload)
        
        if result['success']:
            response_text = result['data']['response']
            from .utils.json_loose import loads_loose
            verify_data = loads_loose(response_text)
            
            # Use actual observation as result if LLM didn't provide one
            if 'result' not in verify_data or verify_data['result'] == "No result provided":
                verify_data['result'] = last_observation
            
            # Validate other fields
            verify_data['finish'] = verify_data.get('finish', False)
            verify_data['confidence'] = max(0.0, min(1.0, float(verify_data.get('confidence', 0.5))))
            
            logger.info(f"LLM verification: finish={verify_data['finish']}, confidence={verify_data['confidence']}")
            return verify_data
            
    except Exception as e:
        logger.error(f"LLM verification failed: {e}")
    
    # Final fallback - use simple heuristics
    if obs_to_use and 'error' not in str(last_observation).lower():
        return {
            "finish": True,
            "result": last_observation,
            "confidence": 0.6,
            "success_level": "partial",
            "reasoning": "Assuming completion based on presence of observations"
        }
    else:
        return {
            "finish": False,
            "result": "Task in progress",
            "confidence": 0.3,
            "success_level": "partial",
            "reasoning": "No clear completion indicator found"
        }
    
    def _is_knowledge_question(self, goal: str) -> bool:
        """Check if this is a knowledge question."""
        knowledge_indicators = [
            'how many', 'what is', 'what are', 'who is', 'when did', 'where is',
            'why does', 'explain', 'define', 'what does', 'how does',
            'stars in the solar system', 'planets in', 'capital of'
        ]
        return any(indicator in goal.lower() for indicator in knowledge_indicators)
    
    def _create_fallback_verification(self, goal: str, observations: List[str]) -> Dict[str, Any]:
        """Create fallback verification when LLM fails."""
        if observations and len(observations) > 0:
            # If we have observations, assume some progress was made
            return {
                "finish": True,
                "result": observation,
                "confidence": 0.6
            }
        else:
            return {
                "finish": False,
                "result": "No results obtained",
                "confidence": 0.3
            }
    
    def _format_available_tools(self) -> str:
        """Format available tools for prompt."""
        tool_info = self.tool_registry.get_tool_info()
        
        tools_text = []
        for name, info in tool_info.items():
            if info['enabled']:
                status = ""
                if info['destructive']:
                    status = " (DESTRUCTIVE)"
                elif info['requires_confirm']:
                    status = " (requires confirmation)"
                
                tools_text.append(f"- {name}{status}")
        
        return "\n".join(tools_text) if tools_text else "No tools available"
    
    def _format_failed_attempts(self, session_state) -> str:
        """Format failed attempts for prompt."""
        failed_entries = [
            entry for entry in session_state.step_ledger
            if entry.status in ['error', 'duplicate_blocked']
        ]
        
        if not failed_entries:
            return "None"
        
        attempts_text = []
        for entry in failed_entries[-5:]:  # Last 5 failures
            attempts_text.append(f"- {entry.action}({entry.args_key}): {entry.error_class or entry.status}")
        
        return "\n".join(attempts_text)