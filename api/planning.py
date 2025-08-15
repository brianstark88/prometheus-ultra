"""Planning module with planner, critic, and verifier."""
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .utils.json_loose import loads_loose, validate_plan_json
from .utils.fallback import ModelFallbackManager
from .tools import get_tool_registry


logger = logging.getLogger(__name__)


class PlanningAgent:
    """Main planning agent with planner, critic, and verifier."""
    
    def __init__(self, fallback_manager: ModelFallbackManager, prompts_dir: str = "api/prompts"):
        self.fallback_manager = fallback_manager
        self.prompts_dir = Path(prompts_dir)
        self.tool_registry = get_tool_registry()
        
        # Load prompt templates
        self.planner_prompt = self._load_prompt("planner.txt")
        self.critic_prompt = self._load_prompt("critic.txt")
        self.verifier_prompt = self._load_prompt("verifier.txt")
    
    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file."""
        try:
            prompt_path = self.prompts_dir / filename
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Failed to load prompt {filename}: {e}")
            return "Error loading prompt template"
    
    async def plan(
        self,
        goal: str,
        session_state,
        max_repair_attempts: int = 2
    ) -> Dict[str, Any]:
        """
        Generate a plan for achieving the goal.
        
        Args:
            goal: User's goal
            session_state: Current session state
            max_repair_attempts: Maximum attempts to repair invalid JSON
            
        Returns:
            Plan dictionary with subgoals, next_action, etc.
        """
        # Build planning context
        available_tools = self._format_available_tools()
        session_context = session_state.get_context_summary()
        failed_attempts = self._format_failed_attempts(session_state)
        
        # Build prompt
        prompt = self.planner_prompt.format(
            available_tools=available_tools,
            session_context=session_context,
            failed_attempts=failed_attempts,
            goal=goal
        )
        
        # Call LLM with JSON mode
        payload = {
            "prompt": prompt,
            "options": {
                "temperature": 0.3,
                "format": "json",
                "num_predict": 1024
            }
        }
        
        for attempt in range(max_repair_attempts + 1):
            try:
                result = await self.fallback_manager.call_with_fallback(payload)
                
                if not result['success']:
                    raise Exception(f"LLM call failed: {result['error']}")
                
                response_text = result['data']['response']
                
                # Parse JSON with tolerance
                plan_data = loads_loose(response_text)
                
                # Validate and fill missing fields
                plan_data = validate_plan_json(plan_data)
                
                logger.info(f"Plan generated successfully on attempt {attempt + 1}")
                return plan_data
            
            except Exception as e:
                logger.warning(f"Plan generation attempt {attempt + 1} failed: {e}")
                
                if attempt < max_repair_attempts:
                    # Try to repair with error feedback
                    repair_prompt = f"""The previous JSON response had an error: {str(e)}

Please provide a corrected JSON response for this goal: {goal}

Use exactly this format:
{{
  "subgoals": ["goal1", "goal2", "goal3"],
  "success_criteria": "criteria",
  "next_action": "tool_name",
  "args": {{}},
  "expected_observation": "expectation",
  "rationale": "reasoning"
}}"""
                    
                    payload["prompt"] = repair_prompt
                else:
                    # Final fallback plan
                    logger.error(f"All plan generation attempts failed: {e}")
                    return self._create_fallback_plan(goal)
        
        return self._create_fallback_plan(goal)
    
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
            available_tools=available_tools,
            steps_remaining=steps_remaining,
            failed_attempts=failed_attempts,
            proposed_plan=str(proposed_plan),
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
                logger.warning(f"Critic call failed: {result['error']}")
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
            
            logger.info(f"Critic review: approved={critic_data['approved']}")
            return critic_data
        
        except Exception as e:
            logger.error(f"Critic failed: {e}")
            return {"approved": True, "changes": [], "reasoning": f"Critic error: {str(e)}"}
    
    async def verify(
        self,
        goal: str,
        recent_observations: List[str],
        max_obs: int = 8
    ) -> Dict[str, Any]:
        """
        Verify if the goal has been accomplished.
        
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
        
        # Build prompt
        prompt = self.verifier_prompt.format(
            goal=goal,
            obs_count=len(obs_to_use),
            recent_observations=obs_text
        )
        
        # Call LLM with JSON mode and fixed seed for consistency
        payload = {
            "prompt": prompt,
            "options": {
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 42,
                "format": "json",
                "num_predict": 256
            }
        }
        
        try:
            result = await self.fallback_manager.call_with_fallback(payload)
            
            if not result['success']:
                logger.warning(f"Verifier call failed: {result['error']}")
                return {"finish": False, "result": "Verification unavailable", "confidence": 0.5}
            
            response_text = result['data']['response']
            verify_data = loads_loose(response_text)
            
            # Validate verifier response
            if 'finish' not in verify_data:
                verify_data['finish'] = False
            if 'result' not in verify_data:
                verify_data['result'] = "No result provided"
            if 'confidence' not in verify_data:
                verify_data['confidence'] = 0.5
            
            # Ensure confidence is between 0 and 1
            verify_data['confidence'] = max(0.0, min(1.0, float(verify_data['confidence'])))
            
            logger.info(f"Verification: finish={verify_data['finish']}, confidence={verify_data['confidence']}")
            return verify_data
        
        except Exception as e:
            logger.error(f"Verifier failed: {e}")
            return {"finish": False, "result": f"Verification error: {str(e)}", "confidence": 0.0}
    
    def _format_available_tools(self) -> str:
        """Format available tools for prompt."""
        tool_info = self.tool_registry.get_tool_info()
        
        tools_text = []
        for name, info in tool_info.items():
            if info['enabled']:
                status = ""
                if info['destructive']:
                    status = " (DESTRUCTIVE - requires confirm=true)"
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
    
    def _create_fallback_plan(self, goal: str) -> Dict[str, Any]:
        """Create a fallback plan when LLM planning fails."""
        return {
            "subgoals": [
                "Understand the request",
                "Use available tools to gather information", 
                "Provide a helpful response"
            ],
            "success_criteria": "Provide a useful response to the user's request",
            "next_action": "analyze",
            "args": {
                "prompt": f"How can I help accomplish this goal: {goal}",
                "context": "No specific context available"
            },
            "expected_observation": "Analysis of how to approach the goal",
            "rationale": "Fallback plan due to planning system failure"
        }