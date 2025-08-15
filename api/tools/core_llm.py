"""Core LLM tools for analysis and summarization."""
import httpx
import asyncio
import json
import logging
from typing import Dict, Any, Optional
import os


logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with Ollama LLM."""
    
    def __init__(self, base_url: str = None, default_model: str = None):
        self.base_url = base_url or os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')
        self.default_model = default_model or os.getenv('LLM_MODEL', 'gpt-oss:20b')
        self.timeout = 60.0
    
    async def generate(
        self,
        prompt: str,
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        system_prompt: str = None
    ) -> Dict[str, Any]:
        """
        Generate response using Ollama API.
        
        Args:
            prompt: Input prompt
            model: Model name (uses default if not specified)
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            
        Returns:
            Dictionary with response and metadata
        """
        model = model or self.default_model
        
        # Build request payload
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "stop": ["Human:", "Assistant:", "\n\nHuman:", "\n\nAssistant:"]
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                
                if response.status_code != 200:
                    raise Exception(f"LLM API error: {response.status_code} - {response.text}")
                
                data = response.json()
                
                return {
                    'success': True,
                    'response': data.get('response', '').strip(),
                    'model': model,
                    'total_duration': data.get('total_duration', 0),
                    'load_duration': data.get('load_duration', 0),
                    'prompt_eval_count': data.get('prompt_eval_count', 0),
                    'eval_count': data.get('eval_count', 0)
                }
        
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': 'INSUFFICIENT'  # Standard fallback response
            }
    
    def generate_sync(self, *args, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for generate."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.generate(*args, **kwargs))
                    return future.result()
            else:
                return loop.run_until_complete(self.generate(*args, **kwargs))
        except RuntimeError:
            return asyncio.run(self.generate(*args, **kwargs))


# Global LLM client instance
llm_client = LLMClient()


def analyze(
    prompt: str,
    context: str,
    model: str = None,
    temperature: float = 0.1
) -> str:
    """
    Analyze provided context using LLM reasoning.
    
    Args:
        prompt: Analysis instruction/question
        context: Context data to analyze
        model: Optional model override
        temperature: Generation temperature
        
    Returns:
        Analysis result or "INSUFFICIENT" if context is inadequate
    """
    if not prompt or not prompt.strip():
        return "INSUFFICIENT - No analysis prompt provided"
    
    if not context or not context.strip():
        return "INSUFFICIENT - No context provided for analysis"
    
    # Limit context size
    max_context_chars = 6000
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "... [context truncated]"
    
    # Build analysis prompt
    system_prompt = """You are a precise analytical assistant. Analyze the provided context and respond to the user's request. Be concise but thorough. If the context is insufficient to answer the question, respond with exactly "INSUFFICIENT"."""
    
    full_prompt = f"""Context:
{context}

Analysis Request:
{prompt}

Analysis:"""
    
    try:
        result = llm_client.generate_sync(
            prompt=full_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=1024
        )
        
        if result['success']:
            response = result['response'].strip()
            
            # Handle insufficient context
            if not response or response.upper().startswith('INSUFFICIENT'):
                return "INSUFFICIENT"
            
            logger.info(f"Analysis completed: {len(response)} chars")
            return response
        else:
            logger.error(f"Analysis failed: {result.get('error')}")
            return "INSUFFICIENT"
    
    except Exception as e:
        logger.error(f"analyze tool failed: {e}")
        return "INSUFFICIENT"


def summarize(
    content: str,
    target_length: str = "medium",
    focus: str = None,
    model: str = None
) -> str:
    """
    Summarize content with hierarchical/semantic compression.
    
    Args:
        content: Content to summarize
        target_length: "short" (1-2 sentences), "medium" (1 paragraph), "long" (2-3 paragraphs)
        focus: Optional focus area for summarization
        model: Optional model override
        
    Returns:
        Summarized content
    """
    if not content or not content.strip():
        return "No content to summarize"
    
    # Determine target word count based on length
    length_targets = {
        "short": 50,
        "medium": 150,
        "long": 300
    }
    
    target_words = length_targets.get(target_length, 150)
    
    # If content is already short enough, return as-is
    if len(content.split()) <= target_words:
        return content.strip()
    
    # Build summarization prompt
    system_prompt = f"""You are a skilled summarization assistant. Create a {target_length} summary of the provided content. Focus on the most important information and maintain key details."""
    
    focus_instruction = f" Pay special attention to: {focus}." if focus else ""
    
    prompt = f"""Summarize the following content in approximately {target_words} words{focus_instruction}

Content:
{content}

Summary:"""
    
    try:
        result = llm_client.generate_sync(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=0.2,
            max_tokens=target_words * 2  # Allow some buffer
        )
        
        if result['success']:
            summary = result['response'].strip()
            
            if summary:
                logger.info(f"Summarized {len(content)} chars to {len(summary)} chars")
                return summary
            else:
                return "Summarization failed - no output generated"
        else:
            logger.error(f"Summarization failed: {result.get('error')}")
            return f"Summarization failed: {result.get('error', 'Unknown error')}"
    
    except Exception as e:
        logger.error(f"summarize tool failed: {e}")
        return f"Summarization failed: {str(e)}"


def extract_key_points(content: str, max_points: int = 5) -> str:
    """
    Extract key points from content as bullet list.
    
    Args:
        content: Content to extract points from
        max_points: Maximum number of points to extract
        
    Returns:
        Bullet-formatted key points
    """
    if not content or not content.strip():
        return "No content provided"
    
    system_prompt = f"You are an expert at extracting key information. Extract the {max_points} most important points from the provided content and format them as a clear bullet list."
    
    prompt = f"""Extract the {max_points} most important key points from this content:

{content}

Key Points:"""
    
    try:
        result = llm_client.generate_sync(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=512
        )
        
        if result['success']:
            points = result['response'].strip()
            return points if points else "No key points extracted"
        else:
            return "Key point extraction failed"
    
    except Exception as e:
        logger.error(f"extract_key_points failed: {e}")
        return f"Key point extraction failed: {str(e)}"


def get_llm_client() -> LLMClient:
    """Get the global LLM client instance."""
    return llm_client