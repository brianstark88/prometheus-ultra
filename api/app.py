"""Main FastAPI application for the GOD-MODE agent with smart intent routing."""
import asyncio
import logging
import os
import time
import uuid
from typing import Dict, Any, Optional, List
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


def determine_intent(goal: str) -> str:
    """
    Determine user intent: 'conversational', 'direct_action', or 'agent_task'
    This is the key to making the agent behave intelligently.
    """
    goal_lower = goal.lower()
    
    # PRIORITY 1: Direct file/system operations (these are ALWAYS actions)
    action_verbs = ['count', 'list', 'find', 'delete', 'create', 'read', 'check', 'show', 'get', 'search']
    system_targets = ['file', 'folder', 'directory', 'document', 'desktop', 'home', '~/', '/users/', 
                      'my computer', 'my documents', 'my downloads', 'in my', 'on my']
    
    has_action_verb = any(verb in goal_lower for verb in action_verbs)
    has_system_target = any(target in goal_lower for target in system_targets)
    
    if has_action_verb and has_system_target:
        logger.info(f"Intent: DIRECT_ACTION - User wants to DO something with files/system")
        return 'direct_action'
    
    # PRIORITY 2: Multi-step or complex operations
    complex_indicators = [
        'and then', 'after that', 'followed by', 'next',
        'analyze and', 'compare', 'find.*and.*tell',
        'research', 'investigate', 'compile'
    ]
    
    if any(indicator in goal_lower for indicator in complex_indicators):
        logger.info(f"Intent: AGENT_TASK - Complex multi-step operation needed")
        return 'agent_task'
    
    # PRIORITY 3: Knowledge and conversational queries
    knowledge_patterns = [
        'what is', 'what are', 'who is', 'who are', 'who was',
        'when did', 'when was', 'when is', 'where is', 'where are',
        'why does', 'why is', 'why are', 'how does', 'how do',
        'explain', 'define', 'describe', 'tell me about',
        'what\'s the', 'who\'s the', 'when\'s the', 'where\'s the'
    ]
    
    # Check for knowledge patterns WITHOUT system targets
    if any(pattern in goal_lower for pattern in knowledge_patterns) and not has_system_target:
        logger.info(f"Intent: CONVERSATIONAL - User wants information/knowledge")
        return 'conversational'
    
    # PRIORITY 4: Questions about facts (not files)
    if goal.strip().endswith('?') and not has_system_target:
        logger.info(f"Intent: CONVERSATIONAL - Question about knowledge")
        return 'conversational'
    
    # DEFAULT: If ambiguous, prefer action (safer to use tools than to guess)
    logger.info(f"Intent: DIRECT_ACTION (default) - Ambiguous, assuming action needed")
    return 'direct_action'


def extract_path_from_goal(goal: str) -> str:
    """Extract the path from a goal string."""
    goal_lower = goal.lower()
    
    # Common path mappings
    if 'home' in goal_lower or 'home directory' in goal_lower:
        return '~'
    elif 'desktop' in goal_lower:
        return '~/Desktop'
    elif 'documents' in goal_lower:
        return '~/Documents'
    elif 'downloads' in goal_lower:
        return '~/Downloads'
    
    # Look for explicit paths
    import re
    path_match = re.search(r'[~/][\w/.-]+', goal)
    if path_match:
        return path_match.group()
    
    # Default to home
    return '~'


def determine_tool_for_action(goal: str) -> tuple[str, Dict[str, Any]]:
    """Determine which tool to use for a direct action."""
    goal_lower = goal.lower()
    
    if 'count' in goal_lower and 'file' in goal_lower:
        path = extract_path_from_goal(goal)
        return 'count_files', {'dir': path, 'limit': 0}
    
    elif 'count' in goal_lower and ('folder' in goal_lower or 'director' in goal_lower):
        path = extract_path_from_goal(goal)
        return 'count_dirs', {'dir': path, 'limit': 0}
    
    elif 'list' in goal_lower and 'file' in goal_lower:
        path = extract_path_from_goal(goal)
        return 'list_files', {'dir': path, 'pattern': '*', 'limit': 100}
    
    elif 'read' in goal_lower:
        # This would need more complex parsing to get the file path
        return 'read_file', {'path': extract_path_from_goal(goal)}
    
    else:
        # Default to listing files
        path = extract_path_from_goal(goal)
        return 'list_files', {'dir': path, 'pattern': '*', 'limit': 50}


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
    description="v3.2 Prometheus ULTRA - Advanced LLM agent with intelligent intent routing",
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
    """Main agent streaming endpoint with intelligent routing."""
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
            await run_intelligent_agent(sse, goal, max_steps, destructive, session_id)
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


async def run_intelligent_agent(
    sse: SSEManager,
    goal: str,
    max_steps: int,
    destructive: bool,
    session_id: str
):
    """Intelligent agent that routes based on intent."""
    session_state = state_manager.get_session(session_id)
    session_metrics = metrics_manager.get_session_metrics(session_id)
    session_metrics.start_time = time.time()
    tool_registry = get_tool_registry()
    
    try:
        await emit_status(sse, "starting", {"goal": goal})
        await emit_thinking(sse, f"🎯 Understanding your request: {goal}", "intent_analysis")
        
        # DETERMINE INTENT - This is the key decision point
        intent = determine_intent(goal)
        await emit_thinking(sse, f"📊 Intent classified as: {intent.upper()}", "intent_classification")
        
        # ============ ROUTE BASED ON INTENT ============
        
        if intent == 'conversational':
            # CONVERSATIONAL MODE - Direct LLM response
            await emit_thinking(sse, "💬 This is a knowledge/conversational query - I'll answer directly", "conversational_mode")
            await emit_status(sse, "answering")
            
            # Use LLM directly
            from .tools.core_llm import analyze
            
            try:
                answer = await analyze(
                    prompt=f"Answer this question accurately and completely: {goal}",
                    context="Provide a direct, helpful, and factual answer."
                )
                
                if isinstance(answer, str) and len(answer) > 10:
                    await emit_obs(sse, answer, "conversational_response", None)
                    session_state.add_observation(answer)
                    
                    await emit_thinking(sse, "✅ Response complete!", "completion")
                    await complete_session_with_learning(
                        sse, session_id, goal, session_state, session_metrics,
                        answer, True, 0.95
                    )
                    return
                else:
                    raise Exception("Invalid LLM response")
                    
            except Exception as e:
                logger.error(f"Conversational mode failed: {e}")
                await emit_thinking(sse, f"⚠️ Direct answer failed, switching to agent mode", "fallback")
                intent = 'agent_task'  # Fall through to agent mode
        
        if intent == 'direct_action':
            # DIRECT ACTION MODE - Single tool execution
            await emit_thinking(sse, "🔧 This requires a specific action - executing directly", "direct_action_mode")
            await emit_status(sse, "executing")
            
            # Determine the right tool
            tool_name, args = determine_tool_for_action(goal)
            await emit_thinking(sse, f"🛠️ Using tool: {tool_name} with args: {args}", "tool_selection")
            
            # Execute the tool
            observation, error_class, signature = await execute_single_tool(
                sse, tool_name, args, tool_registry, session_state, destructive
            )
            
            if error_class is None:
                # Format the result nicely
                result_msg = format_tool_result(tool_name, observation)
                
                await emit_obs(sse, result_msg, signature, None)
                session_state.add_observation(result_msg)
                
                await emit_thinking(sse, "✅ Action completed successfully!", "completion")
                await complete_session_with_learning(
                    sse, session_id, goal, session_state, session_metrics,
                    result_msg, True, 0.95
                )
                return
            else:
                # Tool failed, fall through to agent mode
                await emit_thinking(sse, f"⚠️ Direct action failed: {error_class}", "action_error")
                intent = 'agent_task'
        
        if intent == 'agent_task':
            # AGENT MODE - Multi-step planning and execution
            await emit_thinking(sse, "🤖 This requires multiple steps - entering full agent mode", "agent_mode")
            await run_full_agent_loop(sse, goal, max_steps, destructive, session_id, session_state, session_metrics, tool_registry)
            
    except Exception as e:
        logger.error(f"Intelligent agent error: {e}")
        await emit_thinking(sse, f"💥 Unexpected error: {str(e)}", "system_error")
        await complete_session_with_learning(
            sse, session_id, goal, session_state, session_metrics,
            f"Agent error: {str(e)}", False, 0.0
        )


def format_tool_result(tool_name: str, observation: Any) -> str:
    """Format tool results in a user-friendly way."""
    
    # Handle string responses from analyze tool
    if isinstance(observation, str):
        return observation
    
    # Handle dict responses
    if isinstance(observation, dict):
        if 'count' in observation:
            count = observation['count']
            if tool_name == 'count_files':
                return f"I found {count} files in the specified directory."
            elif tool_name == 'count_dirs':
                return f"I found {count} directories in the specified location."
        elif 'result' in observation:
            return str(observation['result'])
    
    # Handle list responses
    if isinstance(observation, list):
        if len(observation) == 0:
            return "No items found."
        elif tool_name == 'list_files':
            items_str = "\n".join([f"  • {item.get('name', 'unknown')}" for item in observation[:10]])
            more = f"\n  ... and {len(observation) - 10} more" if len(observation) > 10 else ""
            return f"Found {len(observation)} items:\n{items_str}{more}"
    
    # Default
    return str(observation)


async def run_full_agent_loop(
    sse: SSEManager,
    goal: str,
    max_steps: int,
    destructive: bool,
    session_id: str,
    session_state,
    session_metrics,
    tool_registry
):
    """Full agent loop for complex multi-step tasks."""
    
    step = 0
    while step < max_steps:
        step += 1
        step_start_time = time.time()
        
        await emit_status(sse, "planning", {"step": step})
        await emit_thinking(sse, f"📋 Step {step}: Planning next action...", "planning")
        
        # Get plan
        try:
            if ENHANCED_MODE and enhanced_planning_agent:
                plan = await enhanced_planning_agent.plan_with_chaining(
                    goal, session_state, max_steps_ahead=3
                )
            else:
                plan = await planning_agent.plan(goal, session_state)
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            # Use simple plan as fallback
            plan = create_simple_plan(goal)
            if not plan:
                await emit_thinking(sse, "❌ Planning failed completely", "planning_error")
                break
        
        await emit_plan(sse, plan)
        
        # Execute plan
        next_action = plan.get('next_action', '')
        args = plan.get('args', {})
        
        await emit_thinking(sse, f"🔨 Executing: {next_action}", "execution")
        await emit_status(sse, "executing")
        
        # Execute tool
        observation, error_class, signature = await execute_single_tool(
            sse, next_action, args, tool_registry, session_state, destructive
        )
        
        await emit_obs(sse, observation, signature, error_class)
        session_state.add_observation(str(observation))
        
        # Record in ledger
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
        session_state.add_ledger_entry(ledger_entry)
        
        # Update metrics
        step_duration = time.time() - step_start_time
        session_metrics.record_step_timing(step_duration)
        session_metrics.record_tool_usage(next_action)
        
        # Check if complete
        await emit_thinking(sse, "🎯 Checking if goal is accomplished...", "verification")
        
        try:
            if ENHANCED_MODE and enhanced_planning_agent:
                # Make sure verify method exists and uses correct parameters
                if hasattr(enhanced_planning_agent, 'verify'):
                    verification = await enhanced_planning_agent.verify(goal, session_state.last_obs)
                else:
                    # Fallback verification
                    verification = {
                        "finish": step >= 3 or (error_class is None and "complete" in str(observation).lower()),
                        "result": str(observation),
                        "confidence": 0.7
                    }
            else:
                # Simple verification
                verification = {
                    "finish": error_class is None and step >= 2,
                    "result": str(observation),
                    "confidence": 0.8
                }
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            verification = {
                "finish": True,
                "result": f"Task completed with result: {observation}",
                "confidence": 0.6
            }
        
        if verification['finish']:
            await emit_thinking(sse, f"🎉 Goal accomplished! Confidence: {verification['confidence']:.1%}", "completion")
            await complete_session_with_learning(
                sse, session_id, goal, session_state, session_metrics,
                verification['result'], True, verification['confidence']
            )
            return
        
        # Check for no progress
        if session_state.should_switch_strategy():
            await emit_thinking(sse, "🔄 Switching strategy due to lack of progress", "strategy_switch")
            session_state.reset_no_progress()
    
    # Max steps reached
    await emit_thinking(sse, f"⏰ Reached maximum steps ({max_steps})", "max_steps_reached")
    await complete_session_with_learning(
        sse, session_id, goal, session_state, session_metrics,
        f"Reached maximum steps. Last result: {session_state.last_obs[-1] if session_state.last_obs else 'None'}",
        False, 0.5
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


# API Endpoints remain the same...
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


# Serve static files for UI (if built)
try:
    app.mount("/", StaticFiles(directory="ui/dist", html=True), name="static")
except:
    logger.info("No UI build found, skipping static file serving")


if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )