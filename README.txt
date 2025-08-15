# 🔱 GOD-MODE Deep-Research Agent v3.2 "Prometheus ULTRA"

A local, stateful LLM agent for macOS (Apple Silicon) that runs **Planner → Critic → Execute → Verifier** loops with live SSE streaming to a ChatGPT-5-like UI.

## ✨ Features

### 🧠 Core Agent Loop
- **Loop-safe execution** with duplicate detection and retry budgets
- **JSON-mode planning** with tolerant parsing and auto-repair
- **Critic review** system to prevent dead-ends and duplicates
- **Verifier-driven completion** with confidence scoring
- **Strategy switching** on no-progress detection

### 🛠️ Tool Ecosystem
- **Core tools**: File operations, web fetching, LLM analysis
- **Multimodal plugins**: Image/audio processing (OpenCV, FFmpeg)
- **External APIs**: Weather, stocks, custom integrations
- **Plugin system**: YAML-configurable with security policies

### ⚡ Advanced Features
- **Parallel execution** of independent batch operations
- **Model fallback** chain with health monitoring
- **Self-improvement** learning with auto-tuning
- **Resource monitoring** with eco mode and throttling
- **Ethics/bias** guardrails with configurable strictness

### 🎨 Modern UI
- **ChatGPT-5-like interface** with dark/light themes
- **Live Thinking Panel** showing planning, critique, and execution
- **Metrics dashboard** with CPU/GPU monitoring
- **Voice I/O support** with Web Speech API
- **Internationalization** (i18n) with multiple languages
- **Session management** with export/import capabilities

## 🚀 Quick Start

### Prerequisites
- **macOS** (Apple Silicon recommended)
- **Python 3.11+**
- **Node.js 18+**
- **Ollama** (auto-installed by bootstrap script)

### One-Command Setup
```bash
git clone <repository>
cd agent_gptoss20b
chmod +x scripts/dev_bootstrap.sh
./scripts/dev_bootstrap.sh
```

This will:
1. ✅ Install and start Ollama
2. 📦 Pull `gpt-oss:20b` and fallback models
3. 🐍 Create Python virtual environment
4. 📦 Install all dependencies
5. 🚀 Start backend (port 8000) and frontend (port 5173)

### Manual Setup
```bash
# Backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend  
cd ui
npm install
npm run dev

# Ollama
ollama serve
ollama pull gpt-oss:20b
```

## 🧪 Testing

Run comprehensive smoke tests:
```bash
./scripts/smoke_tests.sh
```

Test specific workflows:
```bash
# Count files (happy path)
curl -iN "http://127.0.0.1:8000/auto/stream?goal=Count files in ~"

# Most recent Desktop file
curl -iN "http://127.0.0.1:8000/auto/stream?goal=Most recent NON-DIRECTORY file in ~/Desktop"

# Web headlines
curl -iN "http://127.0.0.1:8000/auto/stream?goal=CNN headlines as 10 bullets with URLs"

# Parallel batch
curl -iN "http://127.0.0.1:8000/auto/stream?goal=In parallel: count files in ~ and count dirs in ~"
```

## 📁 Project Structure

```
agent_gptoss20b/
├─ api/                     # FastAPI backend
│  ├─ app.py               # Main application
│  ├─ planning.py          # Planner/Critic/Verifier
│  ├─ tools/               # Tool registry and implementations
│  │  ├─ core_fs.py        # File system tools
│  │  ├─ core_web.py       # Web fetching tools
│  │  ├─ core_llm.py       # LLM analysis tools
│  │  └─ mm_*.py           # Multimodal plugins
│  └─ utils/               # Core utilities
│     ├─ sse.py            # Server-Sent Events
│     ├─ state.py          # Session state management
│     ├─ parallel.py       # Batch execution
│     └─ fallback.py       # Model fallback chain
├─ ui/                     # React frontend
│  ├─ src/
│  │  ├─ components/       # UI components
│  │  ├─ lib/              # API client, SSE, store
│  │  └─ types.ts          # TypeScript definitions
│  └─ package.json
├─ configs/                # Configuration files
│  ├─ plugins.yml          # Tool policies
│  └─ agent.yml            # Agent behavior
└─ scripts/                # Setup and testing scripts
```

## ⚙️ Configuration

### Tool Configuration (`configs/plugins.yml`)
```yaml
tools:
  list_files:
    enabled: true
    max_limit: 500
  
  delete_files:
    enabled: false
    require_confirm: true
  
  image_info:
    enabled: false
    module: "api.tools.mm_image"
```

### Agent Behavior (`configs/agent.yml`)
```yaml
agent:
  max_steps: 15
  parallel_enabled: true
  eco_mode: false

ethics:
  enabled: true
  strictness: "medium"
  blocked_topics:
    - "illegal activities"
    - "harmful content"
```

### Environment Variables (`.env`)
```bash
OLLAMA_HOST=http://127.0.0.1:11434
LLM_MODEL=gpt-oss:20b
FALLBACK_MODELS=llama2:7b,mistral:7b
MAX_STEPS=15
ENABLE_MULTIMODAL=false
```

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health check |
| `/auto/stream` | GET | Main agent SSE stream |
| `/tools` | GET | Available tools list |
| `/metrics` | GET | System metrics |
| `/sessions/{id}/export` | GET | Export session data |
| `/sessions/{id}` | DELETE | Cancel session |

### SSE Event Order
Every agent step follows strict SSE ordering:
```
status → plan → critic → exec → obs → hyp → bb → met → [final]
```

## 🎯 Example Usage

### Basic File Operations
```
Goal: "Count files in my home directory"
→ count_files(dir='~', limit=0)
→ Result: {"count": 1247}
```

### Web Research + Analysis
```
Goal: "Get CNN headlines and summarize top 3"
→ web_get(url='https://cnn.com')
→ analyze(prompt="Extract top 3 headlines", context="$LAST_OBS")
→ Result: "1. Breaking news... 2. Politics update... 3. Tech story..."
```

### Multimodal Analysis
```
Goal: "Describe the image on my desktop"
→ list_files(dir='~/Desktop', pattern='*.png', sort='mtime')
→ image_info(path='~/Desktop/screenshot.png')
→ analyze(prompt="Describe key details", context="$LAST_OBS")
```

### Parallel Batch Operations
```
Goal: "Count both files and directories in Documents"
→ Parallel batch:
   - count_files(dir='~/Documents')
   - count_dirs(dir='~/Documents')
→ Merged results with timing
```

## 🛡️ Security Features

### Sandbox Enforcement
- All file operations restricted to `$HOME`
- Path traversal prevention
- Dotfile protection (configurable)

### Destructive Operation Guards
- Explicit confirmation required
- Policy-based enablement
- UI confirmation modals

### Content Filtering
- Configurable ethics rules
- Bias detection and disclaimers
- Blocked topic enforcement

## 🚨 Troubleshooting

### Common Issues

**No final event emitted**
```bash
# Check SSE ordering in logs
tail -f logs/agent.log | grep "SSE"
```

**JSON parse errors**
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
```

**Ollama connection failed**
```bash
# Restart Ollama
pkill ollama
ollama serve &
```

**High CPU/memory usage**
```bash
# Enable eco mode
curl -X POST http://127.0.0.1:8000/settings -d '{"eco_mode": true}'
```

### Performance Optimization

1. **Eco Mode**: Reduces ensemble size and disables heavy plugins
2. **Parallel Limits**: Adjust `max_parallel_tasks` in config
3. **Context Compression**: Automatic when approaching token limits
4. **Model Fallback**: Lighter models for non-critical operations

## 🔮 Advanced Features

### Self-Improvement
The agent automatically learns from successful patterns:
```bash
# Learning data stored in:
.ultra/learning.ndjson

# Auto-tuning adjusts:
- Temperature ranges
- Ensemble sizes  
- Tool selection patterns
```

### Observability
```bash
# Export logs for analysis
curl http://127.0.0.1:8000/sessions/{id}/export > session.json

# NDJSON stream for dashboards
tail -f dashboards/exporter.ndjson
```

### Voice Integration
```javascript
// Enable in UI settings
settings.enableVoiceInput = true;
settings.enableVoiceOutput = true;
```

## 📊 Metrics & Monitoring

### System Metrics
- CPU/GPU usage and temperature
- Memory consumption
- Performance scoring
- Eco mode recommendations

### Session Metrics  
- Step timing and latency
- Tool usage frequency
- Error classification
- Confidence trends

### Dashboard Integration
Optional Grafana dashboard setup:
```bash
# Import NDJSON logs
cat dashboards/exporter.ndjson | grafana-import
```

## 🤝 Contributing

### Development Setup
```bash
# Install dev dependencies
pip install -r requirements-dev.txt
npm install --save-dev

# Run tests
pytest tests/backend/
npm run test

# Code formatting
black api/
prettier --write ui/src/
```

### Adding New Tools
1. Implement in `api/tools/custom_tool.py`
2. Register in `configs/plugins.yml`
3. Add tests in `tests/backend/test_tools.py`
4. Update documentation

### Plugin Development
```python
# api/tools/my_plugin.py
def my_tool(arg1: str, arg2: int = 42) -> dict:
    """Custom tool implementation."""
    return {"result": f"Processed {arg1} with {arg2}"}
```

```yaml
# configs/plugins.yml
tools:
  my_tool:
    enabled: true
    module: "api.tools.my_plugin"
    fn: "my_tool"
    max_arg2: 100
```

## 📜 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- **Ollama** for local LLM serving
- **FastAPI** for high-performance async API
- **React + Zustand** for modern UI state management
- **Tailwind CSS** for beautiful styling

## 🆘 Support

- 📖 **Documentation**: Check this README and inline code comments
- 🐛 **Issues**: Report bugs with reproduction steps
- 💬 **Discussions**: Share use cases and feature requests
- 🧪 **Testing**: Run smoke tests before reporting issues

---

**Ready to enter GOD-MODE? 🧠⚡**

```bash
./scripts/dev_bootstrap.sh
# Open http://127.0.0.1:5173
# Ask: "What can you help me with today?"
```