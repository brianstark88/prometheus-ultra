"""Main FastAPI application for the GOD-MODE agent."""
import asyncio
import logging
import os
import time
import uuid
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

from .planning import PlanningAgent
from .simple_planner import create_simple_plan
from .tools import initialize_tools, get_tool_registry
from .utils.sse import SSEManager, emit_status, emit_plan, emit_critic, emit_exec, emit_obs, emit_obs_batch, emit_hyp, emit_blackboard, emit_metrics, emit_final
from .utils.state import state_manager, LedgerEntry, create_observation_signature
from .utils.metrics import metrics_manager
from .utils.fallback import create_fallback_manager
from .utils.parallel import default_executor, create_batch_tasks, merge_batch_observations, validate_batch_safety, BatchCoordinator
from .utils.sandbox import validate_tool_args

# Enhanced imports for GOD-MODE
try:
    from .planning_enhanced import EnhancedPlanningAgent
    from .utils.learning import LearningSystem
    ENHANCED_MODE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Enhanced planning not available - using standard mode")
    ENHANCED_MODE = False


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Enhanced SSE functions for reasoning
async def emit_thinking(sse_manager: SSEManager, thought: str, step_type: str = "general"):
    """Emit a thinking step with human-readable content."""
    data = {
        "thought": thought,
        "step_type": step_type,
        "timestamp": time.time()
    }
    await sse_manager.emit("thinking", data)


async def emit_reasoning(sse_manager: SSEManager, step: str, reasoning: str, details: Dict = None):
    """Emit human-readable reasoning step."""
    data = {
        "step": step,
        "reasoning": reasoning,
        "timestamp": time.time()
    }
    if details:
        data["details"] = details
    
    await sse_manager.emit("reasoning", data)


def is_knowledge_question(goal: str) -> bool:
    """Detect if this is a knowledge question that doesn't need tools."""
    knowledge_indicators = [
        'how many', 'what is', 'what are', 'who is', 'when did', 'where is',
        'why does', 'explain', 'define', 'what does', 'how does',
        'stars in the solar system', 'planets in', 'capital of',
        'who invented', 'when was', 'how tall', 'how old'
    ]
    
    goal_lower = goal.lower()
    return any(indicator in goal_lower for indicator in knowledge_indicators)


def create_knowledge_plan(goal: str) -> Dict[str, Any]:
    """Create a plan that uses analyze tool for knowledge questions."""
    return {
        "strategy": "knowledge_response",
        "subgoals": ["Answer the knowledge question directly"],
        "success_criteria": "Provide accurate, helpful information",
        "next_action": "analyze",
        "args": {
            "prompt": f"Answer this question accurately and completely: {goal}",
            "context": "This is a knowledge question that requires a direct factual answer."
        },
        "expected_observation": "Direct answer to the knowledge question",
        "confidence": 0.9,
        "rationale": "Knowledge question detected - using analyze tool for direct response",
        "tool_chain": ["analyze"]
    }


def is_simple_goal(goal: str) -> bool:
    """Check if goal can be handled by simple planner."""
    simple_patterns = [
        'count files', 'list files', 'count dirs',
        'how many', 'show me files', 'number of'
    ]
    return any(pattern in goal.lower() for pattern in simple_patterns)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    logger.info("Starting GOD-MODE Agent...")
    
    # Initialize tools
    tools_config = os.getenv('TOOLS_CONFIG', 'configs/plugins.yml')
    initialize_tools(tools_config)
    
    logger.info(f"Initialized {len(get_tool_registry().list_tools())} tools")
    
    yield
    
    # Shutdown
    logger.info("Shutting down GOD-MODE Agent...")


# Create FastAPI app
app = FastAPI(
    title="GOD-MODE Deep-Research Agent",
    description="v3.2 Prometheus ULTRA - Advanced LLM agent with loop safety and learning",
    version="3.2.0",
    lifespan=lifespan
)

# CORS middleware
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
fallback_manager = create_fallback_manager(
    primary=os.getenv('LLM_MODEL', 'gpt-oss:20b'),
    fallbacks=os.getenv('FALLBACK_MODELS', 'llama2:7b,mistral:7b').split(','),
    host=os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')
)

# Initialize both standard and enhanced planning agents
planning_agent = PlanningAgent(fallback_manager)
if ENHANCED_MODE:
    enhanced_planning_agent = EnhancedPlanningAgent(fallback_manager)
    learning_system = LearningSystem()
    logger.info("Enhanced GOD-MODE features enabled")
else:
    enhanced_planning_agent = None
    learning_system = None

batch_coordinator = BatchCoordinator(default_executor)

# Session management
active_sessions: Dict[str, SSEManager] = {}


async def enhanced_planning_step(goal: str, session_state, sse: SSEManager) -> Dict[str, Any]:
    """Enhanced planning with intelligent tool chaining."""
    
    # Handle knowledge questions directly
    if is_knowledge_question(goal):
        await emit_thinking(sse, "🧠 This is a knowledge question - I can answer this directly using my training data", "goal_classification")
        knowledge_plan = create_knowledge_plan(goal)
        await emit_plan(sse, knowledge_plan)
        return knowledge_plan
    
    # Try simple planner for basic operations first (keep fast path)
    simple_plan = None
    try:
        simple_plan = create_simple_plan(goal)
        
        # Check if simple plan is sufficient
        if is_simple_goal(goal) and simple_plan.get('confidence', 0) > 0.8:
            await emit_thinking(sse, "⚡ This is a simple file operation - I'll use fast tools", "goal_classification")
            await emit_plan(sse, simple_plan)
            return simple_plan
    except Exception as e:
        logger.info(f"Simple planner skipped: {e}")
    
    # Use enhanced LLM planning for complex goals
    if ENHANCED_MODE and enhanced_planning_agent:
        try:
            await emit_thinking(sse, "🔄 This is a complex task - I'll plan multiple steps", "goal_classification")
            enhanced_plan = await enhanced_planning_agent.plan_with_chaining(
                goal, session_state, max_steps_ahead=3
            )
            
            # Use learning insights to improve plan
            if learning_system:
                goal_type = learning_system._classify_goal_type(goal)
                learned_pattern = learning_system.get_pattern_for_goal_type(goal_type)
                
                if learned_pattern and 'tool_chain' not in enhanced_plan:
                    enhanced_plan['tool_chain'] = learned_pattern
                    enhanced_plan['rationale'] = enhanced_plan.get('rationale', '') + f" (Using learned pattern: {' → '.join(learned_pattern)})"
                    await emit_thinking(sse, f"🧠 Applied learned pattern: {' → '.join(learned_pattern)}", "learning_applied")
            
            await emit_plan(sse, enhanced_plan)
            return enhanced_plan
        
        except Exception as e:
            logger.error(f"Enhanced planning failed: {e}")
            await emit_thinking(sse, f"⚠️ Enhanced planning failed: {str(e)}", "planning_error")
    
    # Fallback to standard LLM planning
    try:
        await emit_thinking(sse, "🔄 Using standard LLM planning", "fallback_planning")
        standard_plan = await planning_agent.plan(goal, session_state)
        await emit_plan(sse, standard_plan)
        return standard_plan
    except Exception as e:
        logger.error(f"Standard planning failed: {e}")
        await emit_thinking(sse, f"⚠️ Standard planning failed: {str(e)}", "planning_error")
    
    # Final fallback
    if simple_plan:
        await emit_thinking(sse, "🔄 Using simple plan as final fallback", "final_fallback")
        await emit_plan(sse, simple_plan)
        return simple_plan
    else:
        await emit_thinking(sse, "🔄 Creating emergency fallback plan", "emergency_fallback")
        fallback_plan = planning_agent._create_fallback_plan(goal)
        await emit_plan(sse, fallback_plan)
        return fallback_plan


async def complete_session_with_learning(
    sse: SSEManager,
    session_id: str,
    goal: str,
    session_state,
    session_metrics,
    final_result: str,
    success: bool,
    confidence: float
):
    """Complete session and log learning data."""
    
    # Emit final result
    await emit_final(sse, final_result, success, confidence)
    
    # Log to learning system if available
    if ENHANCED_MODE and learning_system:
        try:
            learning_system.log_session_outcome(
                session_id=session_id,
                goal=goal,
                session_state=session_state,
                session_metrics=session_metrics,
                final_result=final_result,
                success=success,
                confidence=confidence
            )
            
            # Auto-tune parameters periodically
            if len(learning_system._session_outcomes) % 25 == 0:
                tuning_params = learning_system.auto_tune_parameters()
                logger.info(f"Auto-tuned parameters: {tuning_params}")
        
        except Exception as e:
            logger.error(f"Learning system error: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check tool registry
        tools_count = len(get_tool_registry().list_tools())
        
        # Check model health
        model_status = await fallback_manager.get_system_status()
        
        # Learning system status
        learning_status = None
        if ENHANCED_MODE and learning_system:
            try:
                stats = learning_system.get_stats()
                learning_status = {
                    "enabled": True,
                    "sessions_logged": stats.get("total_sessions", 0),
                    "success_rate": stats.get("success_rate", 0.0)
                }
            except:
                learning_status = {"enabled": True, "error": "Failed to get stats"}
        else:
            learning_status = {"enabled": False}
        
        return {
            "ok": True,
            "timestamp": time.time(),
            "tools_loaded": tools_count,
            "models": model_status,
            "active_sessions": len(active_sessions),
            "enhanced_mode": ENHANCED_MODE,
            "learning_system": learning_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auto/stream")
async def auto_stream(
    request: Request,
    goal: str,
    max_steps: Optional[int] = None,
    destructive: bool = False,
    session_id: Optional[str] = None
):
    """Main agent streaming endpoint."""
    # Validate inputs
    if not goal or len(goal.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Invalid goal")
    
    goal = goal.strip()
    max_steps = max_steps or int(os.getenv('MAX_STEPS', 15))
    session_id = session_id or str(uuid.uuid4())
    
    # Create SSE manager
    sse = SSEManager(session_id)
    active_sessions[session_id] = sse
    
    # Handle client disconnect
    async def cleanup():
        active_sessions.pop(session_id, None)
        state_manager.cleanup_session(session_id)
        metrics_manager.cleanup_session(session_id)
    
    # Start the agent loop
    async def agent_loop():
        try:
            await run_enhanced_agent_loop(sse, goal, max_steps, destructive, session_id)
        except Exception as e:
            logger.error(f"Agent loop failed: {e}")
            await emit_thinking(sse, f"💥 Unexpected error: {str(e)}", "system_error")
            await emit_final(sse, f"Agent failed: {str(e)}", False, 0.0, ["Check logs for details"])
        finally:
            await cleanup()
    
    # Start agent loop in background
    asyncio.create_task(agent_loop())
    
    # Return streaming response
    return StreamingResponse(
        sse.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        }
    )


async def run_enhanced_agent_loop(
    sse: SSEManager,
    goal: str,
    max_steps: int,
    destructive: bool,
    session_id: str
):
    """Enhanced agent loop with visible reasoning."""
    session_state = state_manager.get_session(session_id)
    session_metrics = metrics_manager.get_session_metrics(session_id)
    session_metrics.start_time = time.time()
    tool_registry = get_tool_registry()
    
    step = 0
    
    try:
        await emit_status(sse, "starting", {"goal": goal, "max_steps": max_steps})
        await emit_thinking(sse, f"🎯 Goal: {goal}", "goal_analysis")
        
        while step < max_steps:
            step += 1
            step_start_time = time.time()
            
            await emit_status(sse, "planning", {"step": step})
            await emit_thinking(sse, f"📋 Step {step}: Planning my approach...", "planning")
            
            # ENHANCED PLANNING with reasoning
            plan = await enhanced_planning_step(goal, session_state, sse)
            
            # Emit reasoning about the plan
            next_action = plan.get('next_action', '')
            plan_rationale = plan.get('rationale', 'No rationale provided')
            
            await emit_thinking(sse, f"💡 Plan: I'll use the '{next_action}' tool", "plan_decision")
            await emit_thinking(sse, f"🤔 Reasoning: {plan_rationale}", "plan_reasoning")
            
            # Show tool chain if available
            if plan.get('tool_chain') and len(plan['tool_chain']) > 1:
                await emit_thinking(sse, f"🔗 Tool chain: {' → '.join(plan['tool_chain'])}", "tool_chain")
            
            # ENHANCED CRITIC with reasoning
            await emit_thinking(sse, "🔍 Reviewing my plan for safety and efficiency...", "critic_review")
            
            try:
                if ENHANCED_MODE and enhanced_planning_agent:
                    critic_result = await enhanced_planning_agent.critique(plan, session_state, max_steps - step)
                else:
                    from .simple_critic import simple_critic_review
                    critic_result = simple_critic_review(plan, tool_registry.tools)
                
                if critic_result.get('approved', True):
                    await emit_thinking(sse, "✅ Plan approved - proceeding with execution", "critic_approval")
                else:
                    changes = critic_result.get('changes', [])
                    await emit_thinking(sse, f"⚠️ Plan needs changes: {changes}", "critic_changes")
                
                await emit_critic(sse, critic_result)
            except Exception as e:
                await emit_thinking(sse, f"⚠️ Critic review failed, proceeding anyway: {str(e)}", "critic_error")
                critic_result = {"approved": True, "changes": [], "reasoning": f"Critic bypassed due to error: {str(e)}"}
                await emit_critic(sse, critic_result)
            
            # Apply critic changes if needed
            if not critic_result['approved']:
                logger.info(f"Critic suggested changes: {critic_result['changes']}")
            
            # EXECUTE with reasoning
            await emit_status(sse, "executing")
            args = plan.get('args', {})
            
            await emit_thinking(sse, f"🔨 Executing: {next_action} with args {args}", "execution_start")
            
            # Check for batch execution
            if isinstance(args, list) and len(args) > 1:
                await emit_thinking(sse, f"⚡ Running {len(args)} operations in parallel", "batch_execution")
                
                observations, error_classes, signatures = await execute_batch(
                    sse, next_action, args, tool_registry, session_state, destructive
                )
                
                # Batch result reasoning
                success_count = sum(1 for obs in observations if obs is not None)
                await emit_thinking(sse, f"📊 Batch completed: {success_count}/{len(observations)} operations successful", "batch_result")
                
                merged_obs = merge_batch_observations([
                    {"idx": i, "success": obs is not None, "result": obs, "error": err}
                    for i, (obs, err) in enumerate(zip(observations, error_classes))
                ])
                
                await emit_obs_batch(sse, observations, signatures, error_classes)
                session_state.add_observation(merged_obs)
                
                ledger_entry = LedgerEntry(
                    step=step,
                    action=f"{next_action}_batch",
                    args={"batch_size": len(args)},
                    args_key=f"batch_{step}",
                    expected=f"batch results for {len(args)} operations",
                    status="ok" if any(obs for obs in observations) else "error",
                    obs_signature=f"batch[{len(observations)}]",
                    error_class=error_classes[0] if any(error_classes) else None
                )
                
            else:
                # Single tool execution with reasoning
                observation, error_class, signature = await execute_single_tool(
                    sse, next_action, args, tool_registry, session_state, destructive
                )
                
                if error_class:
                    await emit_thinking(sse, f"❌ Tool execution failed: {error_class}", "execution_error")
                else:
                    await emit_thinking(sse, f"✅ Tool executed successfully, got: {signature}", "execution_success")
                
                await emit_obs(sse, observation, signature, error_class)
                session_state.add_observation(str(observation))
                
                args_key = session_state.canonicalize_args(next_action, args)
                ledger_entry = LedgerEntry(
                    step=step,
                    action=next_action,
                    args=args,
                    args_key=args_key,
                    expected=plan.get('expected_observation', ''),
                    status="ok" if error_class is None else "error",
                    obs_signature=signature,
                    error_class=error_class
                )
            
            # Add to ledger and mark attempt
            session_state.add_ledger_entry(ledger_entry)
            session_state.mark_attempt(next_action, args, success=ledger_entry.status == "ok")
            
            # HYP (Hypothesis check) with reasoning
            await emit_status(sse, "verifying_hypothesis")
            await emit_thinking(sse, "🔍 Checking if results match expectations...", "hypothesis_check")
            
            expected_obs = plan.get('expected_observation', '')
            hypothesis_result = check_hypothesis(expected_obs, signature, observation)
            
            if hypothesis_result.get('expected_match'):
                await emit_thinking(sse, "✅ Results match expectations", "hypothesis_success")
            else:
                await emit_thinking(sse, "⚠️ Results differ from expectations, but may still be useful", "hypothesis_mismatch")
            
            await emit_hyp(sse, hypothesis_result)
            
            # Update blackboard with reasoning
            if ledger_entry.status == "ok":
                fact = f"Step {step}: {next_action} completed successfully"
                session_state.add_fact(fact)
                await emit_thinking(sse, f"📝 Added to knowledge: {fact}", "blackboard_update")
            
            await emit_blackboard(sse, session_state.blackboard)
            
            # MET (Metrics)
            step_duration = time.time() - step_start_time
            session_metrics.record_step_timing(step_duration)
            session_metrics.record_tool_usage(next_action)
            if error_class:
                session_metrics.record_error(error_class)
            
            all_metrics = metrics_manager.collect_all_metrics(session_id)
            await emit_metrics(sse, all_metrics)
            
            # ENHANCED VERIFIER with reasoning
            await emit_thinking(sse, "🎯 Checking if I've accomplished the goal...", "verification_start")
            
            try:
                last_successful = (
                    session_state.step_ledger and 
                    session_state.step_ledger[-1].status == "ok"
                )
                
                if ENHANCED_MODE and enhanced_planning_agent:
                    verification = await enhanced_planning_agent.verify(goal, session_state.last_obs)
                    
                    # Apply learning-based confidence adjustment
                    if learning_system:
                        base_confidence = verification['confidence']
                        overall_success_rate = learning_system.get_tool_success_rate('overall') or 0.5
                        adjusted_confidence = min(1.0, base_confidence * (1 + overall_success_rate - 0.5))
                        verification['confidence'] = adjusted_confidence
                        await emit_thinking(sse, f"🧠 Adjusted confidence based on learning: {base_confidence:.2f} → {adjusted_confidence:.2f}", "confidence_adjustment")
                else:
                    from .simple_verifier import simple_verify
                    verification = simple_verify(goal, session_state.last_obs, last_successful)
                    
            except Exception as e:
                logger.error(f"Verifier failed: {e}")
                await emit_thinking(sse, f"⚠️ Verification failed, using fallback: {str(e)}", "verification_error")
                verification = {
                    "finish": True,
                    "result": "Task completed. The results are shown in the detailed information above.",
                    "confidence": 0.6
                }
            
            session_state.update_confidence(verification['confidence'])
            session_metrics.record_confidence(verification['confidence'])
            
            # Reasoning about completion
            if verification['finish']:
                await emit_thinking(sse, f"🎉 Goal accomplished! Confidence: {verification['confidence']:.1%}", "completion_success")
                await emit_thinking(sse, f"📋 Final result: {verification['result']}", "final_result")
                
                await complete_session_with_learning(
                    sse, session_id, goal, session_state, session_metrics,
                    verification['result'], True, verification['confidence']
                )
                return
            else:
                await emit_thinking(sse, "🔄 Goal not yet complete, continuing...", "continue_processing")
            
            # Check for no progress
            if session_state.should_switch_strategy():
                await emit_thinking(sse, "🔄 Switching strategy due to lack of progress", "strategy_switch")
                session_state.reset_no_progress()
                
                analyze_obs = session_state.last_obs[-1] if session_state.last_obs else "No recent observations"
                analyze_result, _, _ = await execute_single_tool(
                    sse, "analyze", 
                    {"prompt": f"Given the goal '{goal}', what should be the next strategy?", "context": analyze_obs},
                    tool_registry, session_state, False
                )
                session_state.add_observation(str(analyze_result))
        
        # Max steps reached
        await emit_thinking(sse, f"⏰ Reached maximum steps ({max_steps})", "max_steps_reached")
        await complete_session_with_learning(
            sse, session_id, goal, session_state, session_metrics,
            f"Reached maximum steps ({max_steps}). Partial progress made.",
            False, 0.5
        )
    
    except Exception as e:
        logger.error(f"Agent loop error: {e}")
        await emit_thinking(sse, f"💥 Unexpected error: {str(e)}", "system_error")
        await complete_session_with_learning(
            sse, session_id, goal, session_state, session_metrics,
            f"Agent error: {str(e)}", False, 0.0
        )


async def execute_single_tool(
    sse: SSEManager,
    tool_name: str,
    args: Dict[str, Any],
    tool_registry,
    session_state,
    destructive: bool
) -> tuple[Any, Optional[str], str]:
    """Execute a single tool and return observation, error_class, signature."""
    try:
        # Get tool function
        tool_func = tool_registry.get_tool(tool_name)
        if not tool_func:
            return f"Unknown tool: {tool_name}", "unknown_tool", "error"
        
        # Check if tool is enabled
        if not tool_registry.is_enabled(tool_name):
            return f"Tool {tool_name} is disabled", "tool_disabled", "error"
        
        # Validate args
        try:
            validated_args = tool_registry.validate_args(tool_name, args)
        except Exception as e:
            return f"Argument validation failed: {str(e)}", "validation_error", "error"
        
        # Check destructive operations
        if tool_name == 'delete_files' and not destructive:
            return "Destructive operations require explicit permission", "destructive_blocked", "error"
        
        # Check for duplicates
        if session_state.is_duplicate_attempt(tool_name, validated_args):
            return "Duplicate attempt blocked", "duplicate_blocked", "error"
        
        # Emit execution event
        await emit_exec(sse, tool_name, validated_args)
        
        # Execute tool
        if asyncio.iscoroutinefunction(tool_func):
            result = await tool_func(**validated_args)
        else:
            # Run in thread pool for sync functions
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: tool_func(**validated_args))
        
        signature = create_observation_signature(result)
        return result, None, signature
    
    except Exception as e:
        error_class = classify_tool_error(e)
        logger.error(f"Tool {tool_name} failed: {e}")
        return f"Tool execution failed: {str(e)}", error_class, "error"


async def execute_batch(
    sse: SSEManager,
    tool_name: str,
    args_list: list,
    tool_registry,
    session_state,
    destructive: bool
) -> tuple[list, list, list]:
    """Execute batch of operations in parallel."""
    try:
        # Create batch tasks
        tasks = []
        for i, args in enumerate(args_list):
            args_key = session_state.canonicalize_args(tool_name, args)
            task = create_batch_tasks([{"action": tool_name, "args": args}], session_state)[0]
            task.idx = i
            tasks.append(task)
        
        # Validate batch safety
        safety_errors = validate_batch_safety(tasks)
        if safety_errors:
            error_msg = "; ".join(safety_errors)
            return [error_msg], ["batch_validation_error"], ["error"]
        
        # Execute batch
        results, summary = await batch_coordinator.execute_with_streaming(
            tasks, tool_registry.tools, session_state, sse
        )
        
        # Extract results
        observations = []
        error_classes = []
        signatures = []
        
        for result in results:
            if result.success:
                observations.append(result.result)
                error_classes.append(None)
                signatures.append(result.signature)
            else:
                observations.append(result.error)
                error_classes.append(result.error_class)
                signatures.append("error")
        
        return observations, error_classes, signatures
    
    except Exception as e:
        logger.error(f"Batch execution failed: {e}")
        return [f"Batch execution failed: {str(e)}"], ["batch_error"], ["error"]


def check_hypothesis(expected: str, actual_signature: str, observation: Any) -> Dict[str, Any]:
    """Check if observation matches expected hypothesis."""
    try:
        # Simple pattern matching for now
        expected_lower = expected.lower()
        actual_lower = actual_signature.lower()
        
        expected_match = False
        
        # Check for key patterns
        if "list" in expected_lower and "list" in actual_lower:
            expected_match = True
        elif "dict" in expected_lower and "dict" in actual_lower:
            expected_match = True
        elif "str" in expected_lower and "str" in actual_lower:
            expected_match = True
        elif "int" in expected_lower or "count" in expected_lower:
            expected_match = "count" in actual_lower or actual_signature.startswith("dict")
        
        return {
            "expected_match": expected_match,
            "actual_signature": actual_signature,
            "expected_signature": expected,
            "notes": f"Pattern match: {expected_match}"
        }
    
    except Exception as e:
        return {
            "expected_match": False,
            "actual_signature": actual_signature,
            "expected_signature": expected,
            "notes": f"Hypothesis check failed: {str(e)}"
        }


def classify_tool_error(error: Exception) -> str:
    """Classify tool execution errors."""
    error_msg = str(error).lower()
    error_type = type(error).__name__
    
    if "permission" in error_msg or "access" in error_msg:
        return "access_denied"
    elif "timeout" in error_msg:
        return "timeout"
    elif "connection" in error_msg or "network" in error_msg:
        return "network_error"
    elif "file not found" in error_msg or "no such file" in error_msg:
        return "file_not_found"
    elif "json" in error_msg or "parse" in error_msg:
        return "json_parse_error"
    elif error_type in ["ValueError", "TypeError"]:
        return "validation_error"
    else:
        return "execution_error"


# Learning System API Endpoints (GOD-MODE)
@app.get("/learning/stats")
async def get_learning_stats():
    """Get learning system statistics."""
    if not ENHANCED_MODE or not learning_system:
        raise HTTPException(status_code=501, detail="Learning system not available")
    
    try:
        stats = learning_system.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Learning stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/learning/insights")
async def get_learning_insights():
    """Get current learning insights."""
    if not ENHANCED_MODE or not learning_system:
        raise HTTPException(status_code=501, detail="Learning system not available")
    
    try:
        insights = learning_system.get_insights()
        if insights:
            return {"success": True, "insights": insights.__dict__}
        else:
            return {"success": False, "message": "No insights available yet"}
    except Exception as e:
        logger.error(f"Learning insights failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/learning/patterns/{goal_type}")
async def get_patterns_for_goal_type(goal_type: str):
    """Get successful patterns for a specific goal type."""
    if not ENHANCED_MODE or not learning_system:
        raise HTTPException(status_code=501, detail="Learning system not available")
    
    try:
        pattern = learning_system.get_pattern_for_goal_type(goal_type)
        if pattern:
            return {"success": True, "pattern": pattern}
        else:
            return {"success": False, "message": f"No patterns found for {goal_type}"}
    except Exception as e:
        logger.error(f"Pattern lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learning/force-update")
async def force_learning_update():
    """Force update of learning insights."""
    if not ENHANCED_MODE or not learning_system:
        raise HTTPException(status_code=501, detail="Learning system not available")
    
    try:
        learning_system._update_insights()
        return {"success": True, "message": "Insights updated"}
    except Exception as e:
        logger.error(f"Force update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Existing API endpoints
@app.post("/confirm/{session_id}")
async def confirm_destructive(session_id: str, action: str):
    """Confirm destructive operation for session."""
    return {"confirmed": True, "session_id": session_id, "action": action}


@app.get("/sessions/{session_id}/export")
async def export_session(session_id: str):
    """Export session data as JSON."""
    try:
        session_data = state_manager.export_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")
        
        metrics_data = metrics_manager.session_metrics.get(session_id)
        if metrics_data:
            session_data['metrics'] = metrics_data.to_dict()
        
        return session_data
    
    except Exception as e:
        logger.error(f"Export failed for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def cancel_session(session_id: str):
    """Cancel active session."""
    try:
        if session_id in active_sessions:
            sse = active_sessions[session_id]
            sse.cancel()
            return {"cancelled": True, "session_id": session_id}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    
    except Exception as e:
        logger.error(f"Cancel failed for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
async def list_tools():
    """List available tools and their configuration."""
    try:
        tool_registry = get_tool_registry()
        return {
            "tools": tool_registry.get_tool_info(),
            "count": len(tool_registry.list_tools())
        }
    except Exception as e:
        logger.error(f"List tools failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_system_metrics():
    """Get current system metrics."""
    try:
        system_metrics = metrics_manager.system_collector.collect()
        return {
            "cpu_percent": system_metrics.cpu_percent,
            "memory_percent": system_metrics.memory_percent,
            "gpu_temp": system_metrics.gpu_temp,
            "available_memory_gb": system_metrics.available_memory_gb,
            "performance_score": metrics_manager.system_collector.get_performance_score(),
            "under_load": metrics_manager.system_collector.is_under_load(),
            "eco_mode_recommended": metrics_manager.system_collector.should_enable_eco_mode()
        }
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/test/count")
async def test_count_files():
    """Simple test endpoint that bypasses the planner."""
    try:
        from .tools.core_fs import count_files
        result = count_files(dir="~/Desktop", limit=0)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Serve static files for UI (if built)
try:
    app.mount("/", StaticFiles(directory="ui/dist", html=True), name="static")
except Exception:
    logger.info("No UI build found, skipping static file serving")


if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )