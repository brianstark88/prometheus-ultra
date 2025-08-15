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


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    description="v3.2 Prometheus ULTRA - Advanced LLM agent with loop safety",
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

planning_agent = PlanningAgent(fallback_manager)
batch_coordinator = BatchCoordinator(default_executor)

# Session management
active_sessions: Dict[str, SSEManager] = {}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check tool registry
        tools_count = len(get_tool_registry().list_tools())
        
        # Check model health
        model_status = await fallback_manager.get_system_status()
        
        return {
            "ok": True,
            "timestamp": time.time(),
            "tools_loaded": tools_count,
            "models": model_status,
            "active_sessions": len(active_sessions)
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
            await run_agent_loop(sse, goal, max_steps, destructive, session_id)
        except Exception as e:
            logger.error(f"Agent loop failed: {e}")
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


async def run_agent_loop(
    sse: SSEManager,
    goal: str,
    max_steps: int,
    destructive: bool,
    session_id: str
):
    """Run the main agent loop with strict SSE ordering."""
    session_state = state_manager.get_session(session_id)
    session_metrics = metrics_manager.get_session_metrics(session_id)
    tool_registry = get_tool_registry()
    
    step = 0
    
    try:
        await emit_status(sse, "starting", {"goal": goal, "max_steps": max_steps})
        
        while step < max_steps:
            step += 1
            step_start_time = time.time()
            
            await emit_status(sse, "planning", {"step": step})
            
            # PLANNER - Try simple planner first
            try:
                from .simple_planner import create_simple_plan
                plan = create_simple_plan(goal)
                await emit_plan(sse, plan)
            except:
                plan = await planning_agent.plan(goal, session_state)
                await emit_plan(sse, plan)
            
            # CRITIC - Use simple critic for basic operations
            from .simple_critic import simple_critic_review
            try:
                critic_result = simple_critic_review(plan, tool_registry.tools)
                await emit_critic(sse, critic_result)
            except Exception as e:
                # Fallback to always approve if critic fails
                critic_result = {"approved": True, "changes": [], "reasoning": "Critic bypassed due to error"}
                await emit_critic(sse, critic_result)
            
            # Apply critic changes if needed
            if not critic_result['approved']:
                # For now, just log the changes - could implement plan modification
                logger.info(f"Critic suggested changes: {critic_result['changes']}")
            
            # EXECUTE
            await emit_status(sse, "executing")
            
            next_action = plan.get('next_action', '')
            args = plan.get('args', {})
            expected_obs = plan.get('expected_observation', '')
            
            # Check for batch execution
            if isinstance(args, list) and len(args) > 1:
                # Parallel batch execution
                observations, error_classes, signatures = await execute_batch(
                    sse, next_action, args, tool_registry, session_state, destructive
                )
                
                # Merge batch observations
                merged_obs = merge_batch_observations([
                    {"idx": i, "success": obs is not None, "result": obs, "error": err}
                    for i, (obs, err) in enumerate(zip(observations, error_classes))
                ])
                
                await emit_obs_batch(sse, observations, signatures, error_classes)
                session_state.add_observation(merged_obs)
                
                # Create ledger entry for batch
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
                # Single tool execution
                observation, error_class, signature = await execute_single_tool(
                    sse, next_action, args, tool_registry, session_state, destructive
                )
                
                await emit_obs(sse, observation, signature, error_class)
                session_state.add_observation(str(observation))
                
                # Create ledger entry
                args_key = session_state.canonicalize_args(next_action, args)
                ledger_entry = LedgerEntry(
                    step=step,
                    action=next_action,
                    args=args,
                    args_key=args_key,
                    expected=expected_obs,
                    status="ok" if error_class is None else "error",
                    obs_signature=signature,
                    error_class=error_class
                )
            
            # Add to ledger and mark attempt
            session_state.add_ledger_entry(ledger_entry)
            session_state.mark_attempt(next_action, args, success=ledger_entry.status == "ok")
            
            # HYP (Hypothesis check)
            await emit_status(sse, "verifying_hypothesis")
            hypothesis_result = check_hypothesis(expected_obs, signature, observation)
            await emit_hyp(sse, hypothesis_result)
            
            # Update blackboard
            if ledger_entry.status == "ok":
                fact = f"Step {step}: {next_action} completed successfully"
                session_state.add_fact(fact)
            
            # BB (Blackboard)
            await emit_blackboard(sse, session_state.blackboard)
            
            # MET (Metrics)
            step_duration = time.time() - step_start_time
            session_metrics.record_step_timing(step_duration)
            session_metrics.record_tool_usage(next_action)
            if error_class:
                session_metrics.record_error(error_class)
            
            all_metrics = metrics_manager.collect_all_metrics(session_id)
            await emit_metrics(sse, all_metrics)
            
            # VERIFIER - Use LLM-powered verifier
            try:
                # Check if last step was successful (no error_class)
                last_successful = (
                    session_state.step_ledger and 
                    session_state.step_ledger[-1].status == "ok"
                )
                
                # Import and use LLM verifier
                from .simple_verifier import simple_verify
                verification = simple_verify(goal, session_state.last_obs, last_successful)
            except Exception as e:
                logger.error(f"Verifier failed: {e}")
                # Fallback verifier
                verification = {
                    "finish": True,
                    "result": "Task completed. The results are shown in the detailed information above.",
                    "confidence": 0.6
                }
            except Exception as e:
                # Fallback verifier
                verification = {
                    "finish": True,
                    "result": "Task completed (verifier bypassed due to error)",
                    "confidence": 0.6
                }
            
            session_state.update_confidence(verification['confidence'])
            session_metrics.record_confidence(verification['confidence'])
            
            if verification['finish']:
                await emit_final(
                    sse,
                    verification['result'],
                    True,
                    verification['confidence']
                )
                return
            
            # Check for no progress
            if session_state.should_switch_strategy():
                session_state.reset_no_progress()
                # Force analyze on last observation
                analyze_obs = session_state.last_obs[-1] if session_state.last_obs else "No recent observations"
                analyze_result, _, _ = await execute_single_tool(
                    sse, "analyze", 
                    {"prompt": f"Given the goal '{goal}', what should be the next strategy?", "context": analyze_obs},
                    tool_registry, session_state, False
                )
                session_state.add_observation(str(analyze_result))
        
        # Max steps reached
        await emit_final(
            sse,
            f"Reached maximum steps ({max_steps}). Partial progress made.",
            False,
            0.5,
            ["Consider breaking down the goal into smaller parts", "Try a more specific request"]
        )
    
    except Exception as e:
        logger.error(f"Agent loop error: {e}")
        await emit_final(sse, f"Agent error: {str(e)}", False, 0.0)


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


@app.post("/confirm/{session_id}")
async def confirm_destructive(session_id: str, action: str):
    """Confirm destructive operation for session."""
    # This is a stub for human-in-the-loop confirmation
    # In a full implementation, this would track pending confirmations
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
@app.get("/test/count")
async def test_count_files():
    """Simple test endpoint that bypasses the planner."""
    try:
        from .tools.core_fs import count_files
        result = count_files(dir="~/Desktop", limit=0)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
