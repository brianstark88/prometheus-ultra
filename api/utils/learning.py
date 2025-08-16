# api/utils/learning.py
"""Learning system for agent auto-improvement and pattern recognition."""
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class SessionOutcome:
    """Record of a complete session outcome."""
    session_id: str
    goal: str
    goal_type: str
    success: bool
    confidence: float
    steps_taken: int
    duration_seconds: float
    tool_chain: List[str]
    final_result: str
    error_types: List[str]
    timestamp: float
    
    # Performance metrics
    avg_step_time: float
    total_tool_calls: int
    unique_tools_used: int
    
    # Planning metrics
    planner_type: str  # "simple" or "llm" or "enhanced"
    critic_interventions: int
    plan_modifications: int


@dataclass
class LearningInsights:
    """Insights derived from learning analysis."""
    successful_patterns: Dict[str, List[str]]
    failure_patterns: Dict[str, List[str]]
    optimal_temperatures: Dict[str, float]
    tool_success_rates: Dict[str, float]
    avg_completion_times: Dict[str, float]
    recommended_improvements: List[str]


class LearningSystem:
    """Self-improvement system that learns from agent sessions."""
    
    def __init__(self, data_dir: str = ".ultra"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.learning_file = self.data_dir / "learning.ndjson"
        self.insights_file = self.data_dir / "insights.json"
        self.tuning_file = self.data_dir / "tuning.json"
        
        # In-memory caches
        self._session_outcomes: List[SessionOutcome] = []
        self._current_insights: Optional[LearningInsights] = None
        self._load_existing_data()
    
    def _load_existing_data(self):
        """Load existing learning data from disk."""
        try:
            if self.learning_file.exists():
                with open(self.learning_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            outcome = SessionOutcome(**data)
                            self._session_outcomes.append(outcome)
                
                logger.info(f"Loaded {len(self._session_outcomes)} session outcomes")
            
            if self.insights_file.exists():
                with open(self.insights_file, 'r') as f:
                    insights_data = json.load(f)
                    self._current_insights = LearningInsights(**insights_data)
                    logger.info("Loaded existing insights")
        
        except Exception as e:
            logger.error(f"Failed to load learning data: {e}")
    
    def log_session_outcome(
        self,
        session_id: str,
        goal: str,
        session_state,
        session_metrics,
        final_result: str,
        success: bool,
        confidence: float
    ):
        """Log the outcome of a completed session."""
        try:
            # Extract metrics from session
            duration = time.time() - (session_metrics.start_time if hasattr(session_metrics, 'start_time') else time.time())
            steps_taken = len(session_state.step_ledger)
            
            # Analyze tool usage
            tool_chain = [entry.action for entry in session_state.step_ledger if entry.status == "ok"]
            all_tools = [entry.action for entry in session_state.step_ledger]
            unique_tools = len(set(all_tools))
            
            # Extract error patterns
            error_types = [entry.error_class for entry in session_state.step_ledger if entry.error_class]
            
            # Calculate performance metrics
            step_times = getattr(session_metrics, 'step_times', [1.0])
            avg_step_time = statistics.mean(step_times) if step_times else 1.0
            
            # Classify goal type
            goal_type = self._classify_goal_type(goal)
            
            # Determine planner type used (would need to track this in session)
            planner_type = "enhanced"  # Default assumption
            
            # Create outcome record
            outcome = SessionOutcome(
                session_id=session_id,
                goal=goal,
                goal_type=goal_type,
                success=success,
                confidence=confidence,
                steps_taken=steps_taken,
                duration_seconds=duration,
                tool_chain=tool_chain,
                final_result=final_result,
                error_types=error_types,
                timestamp=time.time(),
                avg_step_time=avg_step_time,
                total_tool_calls=len(all_tools),
                unique_tools_used=unique_tools,
                planner_type=planner_type,
                critic_interventions=0,  # Would need to track this
                plan_modifications=0     # Would need to track this
            )
            
            # Add to memory and persist
            self._session_outcomes.append(outcome)
            self._persist_outcome(outcome)
            
            # Update insights periodically
            if len(self._session_outcomes) % 10 == 0:
                self._update_insights()
            
            logger.info(f"Logged session outcome: {session_id} (success={success})")
        
        except Exception as e:
            logger.error(f"Failed to log session outcome: {e}")
    
    def _persist_outcome(self, outcome: SessionOutcome):
        """Persist session outcome to NDJSON file."""
        try:
            with open(self.learning_file, 'a') as f:
                json.dump(asdict(outcome), f)
                f.write('\n')
        except Exception as e:
            logger.error(f"Failed to persist outcome: {e}")
    
    def _classify_goal_type(self, goal: str) -> str:
        """Classify goal into types for pattern recognition."""
        goal_lower = goal.lower()
        
        if any(word in goal_lower for word in ['count', 'how many', 'number of']):
            return "counting"
        elif any(word in goal_lower for word in ['find', 'search', 'locate', 'recent']):
            return "file_finding"
        elif any(word in goal_lower for word in ['analyze', 'examine', 'explain', 'what is']):
            return "analysis"
        elif any(word in goal_lower for word in ['compare', 'difference', 'vs', 'versus']):
            return "comparison"
        elif any(word in goal_lower for word in ['web', 'website', 'url', 'http']):
            return "web_research"
        elif any(word in goal_lower for word in ['read', 'content', 'show me']):
            return "file_reading"
        else:
            return "general"
    
    def _update_insights(self):
        """Update learning insights based on accumulated data."""
        try:
            # Analyze successful patterns by goal type
            successful_patterns = defaultdict(list)
            failure_patterns = defaultdict(list)
            
            for outcome in self._session_outcomes:
                if outcome.success and outcome.confidence > 0.7:
                    successful_patterns[outcome.goal_type].append(outcome.tool_chain)
                elif not outcome.success or outcome.confidence < 0.4:
                    failure_patterns[outcome.goal_type].append(outcome.tool_chain)
            
            # Find most common successful patterns
            pattern_summary = {}
            for goal_type, chains in successful_patterns.items():
                # Count pattern frequencies
                chain_strs = [" → ".join(chain) for chain in chains]
                common_patterns = Counter(chain_strs).most_common(3)
                pattern_summary[goal_type] = [pattern for pattern, count in common_patterns]
            
            # Calculate tool success rates
            tool_successes = defaultdict(int)
            tool_attempts = defaultdict(int)
            
            for outcome in self._session_outcomes:
                for tool in outcome.tool_chain:
                    tool_attempts[tool] += 1
                    if outcome.success:
                        tool_successes[tool] += 1
            
            tool_success_rates = {
                tool: tool_successes[tool] / tool_attempts[tool]
                for tool in tool_attempts if tool_attempts[tool] >= 3
            }
            
            # Calculate optimal temperatures by goal type
            temp_by_type = defaultdict(list)
            for outcome in self._session_outcomes:
                if outcome.success and outcome.confidence > 0.8:
                    # Would need to track temperature used
                    temp_by_type[outcome.goal_type].append(0.3)  # Default assumption
            
            optimal_temps = {
                goal_type: statistics.mean(temps) if temps else 0.3
                for goal_type, temps in temp_by_type.items()
            }
            
            # Calculate average completion times
            time_by_type = defaultdict(list)
            for outcome in self._session_outcomes:
                if outcome.success:
                    time_by_type[outcome.goal_type].append(outcome.duration_seconds)
            
            avg_times = {
                goal_type: statistics.mean(times) if times else 30.0
                for goal_type, times in time_by_type.items()
            }
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                pattern_summary, tool_success_rates, avg_times
            )
            
            # Create insights object
            self._current_insights = LearningInsights(
                successful_patterns=pattern_summary,
                failure_patterns={},  # Could analyze failure patterns too
                optimal_temperatures=optimal_temps,
                tool_success_rates=tool_success_rates,
                avg_completion_times=avg_times,
                recommended_improvements=recommendations
            )
            
            # Persist insights
            with open(self.insights_file, 'w') as f:
                json.dump(asdict(self._current_insights), f, indent=2)
            
            logger.info("Updated learning insights")
        
        except Exception as e:
            logger.error(f"Failed to update insights: {e}")
    
    def _generate_recommendations(
        self,
        patterns: Dict[str, List[str]],
        success_rates: Dict[str, float],
        avg_times: Dict[str, float]
    ) -> List[str]:
        """Generate actionable recommendations based on data."""
        recommendations = []
        
        # Tool performance recommendations
        low_success_tools = [tool for tool, rate in success_rates.items() if rate < 0.7]
        if low_success_tools:
            recommendations.append(f"Consider improving prompts for: {', '.join(low_success_tools)}")
        
        # Pattern recommendations
        if 'counting' in patterns and patterns['counting']:
            most_successful = patterns['counting'][0]
            recommendations.append(f"For counting tasks, use pattern: {most_successful}")
        
        # Performance recommendations
        slow_types = [t for t, time in avg_times.items() if time > 60]
        if slow_types:
            recommendations.append(f"Optimize performance for: {', '.join(slow_types)}")
        
        # General recommendations
        total_sessions = len(self._session_outcomes)
        recent_success_rate = sum(1 for o in self._session_outcomes[-20:] if o.success) / min(20, total_sessions)
        
        if recent_success_rate < 0.8:
            recommendations.append("Consider more conservative planning to improve success rate")
        
        return recommendations
    
    def get_insights(self) -> Optional[LearningInsights]:
        """Get current learning insights."""
        return self._current_insights
    
    def get_pattern_for_goal_type(self, goal_type: str) -> Optional[List[str]]:
        """Get most successful pattern for a goal type."""
        if not self._current_insights:
            return None
        
        patterns = self._current_insights.successful_patterns.get(goal_type, [])
        if patterns:
            # Return first (most common) pattern as list
            return patterns[0].split(" → ")
        return None
    
    def get_optimal_temperature(self, goal_type: str) -> float:
        """Get optimal temperature for a goal type."""
        if not self._current_insights:
            return 0.3
        
        return self._current_insights.optimal_temperatures.get(goal_type, 0.3)
    
    def get_tool_success_rate(self, tool_name: str) -> float:
        """Get success rate for a specific tool."""
        if not self._current_insights:
            return 0.5
        
        return self._current_insights.tool_success_rates.get(tool_name, 0.5)
    
    def auto_tune_parameters(self) -> Dict[str, Any]:
        """Auto-tune agent parameters based on learning data."""
        if not self._current_insights:
            return {}
        
        tuning = {
            "temperature_by_goal_type": self._current_insights.optimal_temperatures,
            "recommended_tools_by_type": {},
            "retry_budgets": {},
            "performance_thresholds": {}
        }
        
        # Calculate recommended retry budgets based on failure rates
        for tool, success_rate in self._current_insights.tool_success_rates.items():
            if success_rate > 0.9:
                tuning["retry_budgets"][tool] = 1  # High confidence tools
            elif success_rate > 0.7:
                tuning["retry_budgets"][tool] = 2  # Medium confidence
            else:
                tuning["retry_budgets"][tool] = 3  # Low confidence tools need more retries
        
        # Save tuning parameters
        with open(self.tuning_file, 'w') as f:
            json.dump(tuning, f, indent=2)
        
        logger.info("Auto-tuned agent parameters")
        return tuning
    
    def get_stats(self) -> Dict[str, Any]:
        """Get learning system statistics."""
        if not self._session_outcomes:
            return {}
        
        total_sessions = len(self._session_outcomes)
        successful_sessions = sum(1 for o in self._session_outcomes if o.success)
        
        return {
            "total_sessions": total_sessions,
            "success_rate": successful_sessions / total_sessions,
            "avg_confidence": statistics.mean(o.confidence for o in self._session_outcomes),
            "avg_steps_per_session": statistics.mean(o.steps_taken for o in self._session_outcomes),
            "most_used_tools": Counter(
                tool for o in self._session_outcomes for tool in o.tool_chain
            ).most_common(5),
            "goal_type_distribution": Counter(o.goal_type for o in self._session_outcomes),
            "insights_last_updated": self.insights_file.stat().st_mtime if self.insights_file.exists() else None
        }