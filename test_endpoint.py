from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def test_stream():
    """Simple test stream."""
    # Send a simple count files result
    yield f"event: status\ndata: {json.dumps({'status': 'starting'})}\n\n"
    await asyncio.sleep(0.1)
    
    yield f"event: exec\ndata: {json.dumps({'tool': 'count_files', 'args': {'dir': '~/Desktop'}})}\n\n"
    await asyncio.sleep(0.1)
    
    yield f"event: obs\ndata: {json.dumps({'observation': '{\"count\": 42}', 'signature': 'dict[keys=count]'})}\n\n"
    await asyncio.sleep(0.1)
    
    yield f"event: final\ndata: {json.dumps({'result': 'There are 42 files in your Desktop directory', 'success': True, 'confidence': 0.9})}\n\n"

@app.get("/test/stream")
async def test_sse():
    return StreamingResponse(
        test_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
