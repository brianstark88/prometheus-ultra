"""Core web tools for fetching and processing web content."""
import httpx
import asyncio
from bs4 import BeautifulSoup
import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin, urlparse


logger = logging.getLogger(__name__)


async def web_get(
    url: str,
    article_mode: bool = True,
    timeout: int = 20,
    user_agent: str = "BrAIn/1.0"
) -> str:
    """
    Fetch web page content with optional article extraction.
    
    Args:
        url: URL to fetch
        article_mode: Extract main article content vs full page
        timeout: Request timeout in seconds
        user_agent: User agent string
        
    Returns:
        Processed web page content as string
        
    Raises:
        Exception: If request fails or content cannot be processed
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")
    
    url = url.strip()
    
    # Basic URL validation
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL format: {url}")
    
    if parsed.scheme not in ['http', 'https']:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
    
    try:
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers
        ) as client:
            
            logger.info(f"Fetching URL: {url}")
            response = await client.get(url)
            
            # Check response status
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.reason_phrase}")
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                raise Exception(f"Non-HTML content type: {content_type}")
            
            html_content = response.text
            
            # Process HTML content
            if article_mode:
                processed_content = extract_article_content(html_content, url)
            else:
                processed_content = extract_full_page_content(html_content)
            
            # Validate and clean result
            if not processed_content or len(processed_content.strip()) < 10:
                raise Exception("No meaningful content extracted from page")
            
            # Limit content size
            max_chars = 8000
            if len(processed_content) > max_chars:
                processed_content = processed_content[:max_chars] + "... [content clipped]"
            
            logger.info(f"Successfully fetched {len(processed_content)} chars from {url}")
            return processed_content
    
    except httpx.TimeoutException:
        raise Exception(f"Request timeout after {timeout}s")
    except httpx.ConnectError:
        raise Exception(f"Connection failed to {url}")
    except Exception as e:
        logger.error(f"web_get failed for {url}: {e}")
        raise


def extract_article_content(html: str, base_url: str) -> str:
    """
    Extract main article content from HTML.
    
    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links
        
    Returns:
        Cleaned article text
    """
    try:
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 
                                     'aside', 'advertisement', 'ads']):
            element.decompose()
        
        # Try to find main content using common patterns
        main_content = None
        
        # Strategy 1: Look for semantic HTML5 elements
        for tag in ['main', 'article']:
            main_content = soup.find(tag)
            if main_content:
                break
        
        # Strategy 2: Look for common content div patterns
        if not main_content:
            content_selectors = [
                'div[class*="content"]',
                'div[class*="article"]',
                'div[class*="post"]',
                'div[class*="story"]',
                'div[id*="content"]',
                'div[id*="article"]',
                'div[id*="main"]'
            ]
            
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    # Pick the largest element
                    main_content = max(elements, key=lambda x: len(x.get_text()))
                    break
        
        # Strategy 3: Fall back to body
        if not main_content:
            main_content = soup.find('body') or soup
        
        # Extract and clean text
        text_content = main_content.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text_content.split('\n')]
        lines = [line for line in lines if line and len(line) > 5]  # Remove short lines
        
        cleaned_text = '\n'.join(lines)
        
        # Add title if available
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            if title and title not in cleaned_text[:200]:
                cleaned_text = f"Title: {title}\n\n{cleaned_text}"
        
        return cleaned_text
    
    except Exception as e:
        logger.warning(f"Article extraction failed: {e}")
        # Fall back to simple text extraction
        return extract_full_page_content(html)


def extract_full_page_content(html: str) -> str:
    """
    Extract all text content from HTML page.
    
    Args:
        html: Raw HTML content
        
    Returns:
        Full page text content
    """
    try:
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove unwanted elements
        for element in soup.find_all(['script', 'style']):
            element.decompose()
        
        # Get all text
        text_content = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text_content.split('\n')]
        lines = [line for line in lines if line]
        
        return '\n'.join(lines)
    
    except Exception as e:
        logger.error(f"Full page extraction failed: {e}")
        return f"Content extraction failed: {str(e)}"


def web_get_sync(url: str, **kwargs) -> str:
    """Synchronous wrapper for web_get."""
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we need to use a different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, web_get(url, **kwargs))
                return future.result()
        else:
            return loop.run_until_complete(web_get(url, **kwargs))
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(web_get(url, **kwargs))


# Export the synchronous version as the main function
# This is what gets registered in the tool registry
def web_get_tool(url: str, article_mode: bool = True, timeout: int = 20) -> str:
    """Tool wrapper for web_get with synchronous interface."""
    return web_get_sync(url, article_mode=article_mode, timeout=timeout)