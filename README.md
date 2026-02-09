# Sunny - Research Assistant

An AI research assistant for analyzing papers, replicating code, and verifying claims through voice interaction and autonomous background processing. Built with Google Gemini Pro and Flash APIs.

## Features

### Phase 1 (Current)
- Voice-first interaction - no typing required
- Screen monitoring - detects paper changes and reading context
- Paper analysis - extracts summaries, authors, key claims
- Issue detection - critiques methodology and identifies problems
- Note-taking - stores user notes and AI critiques with reasoning
- Code replication - extracts and executes code from papers
- Background experiments - runs code independently, reports completion
- Code improvement - rewrites and reruns failed experiments on request
- Deep research - verifies claims and searches for contradicting papers
- Smart suggestions - offers assistance after 20 minutes of idle time

### Phase 2 (Planned)
- Streamlit web interface for browsing analyzed papers
- Experiment dashboard with code results and statistics
- Paper relationship visualization
- Note export to Markdown/LaTeX for report generation

## Installation

### Prerequisites
- Python 3.8 or higher
- Windows, Linux, or macOS
- Gemini API key (free tier supported)

### Setup Steps

1. Clone the repository
```bash
git clone <repository-url>
cd sunny
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Configure API key
```bash
cp .env.example .env
# Edit .env and add your Gemini API key from https://aistudio.google.com/app/apikey
```

4. Run the application
```bash
python main.py
```

## Usage

### Available Voice Commands

**Paper Analysis:**
- "Hey Sunny, what's this paper about?"
- "Hey Sunny, analyze this paper"

**Note-taking:**
- "Hey Sunny, note that equation 3 looks wrong"
- "Hey Sunny, remember this methodology"

**Paper Critique:**
- "Hey Sunny, critique this section"
- "Hey Sunny, spot issues in this methodology"

**Code Execution:**
- "Hey Sunny, replicate Figure 3"
- "Hey Sunny, run this code"
- "Hey Sunny, run the experiment from Figure 2"

**Code Improvement:**
- "Hey Sunny, improve the code to fix version conflicts"
- "Hey Sunny, make that code faster"

**Research Verification:**
- "Hey Sunny, verify this claim about neural networks"
- "Hey Sunny, find contradictions to this paper"

**Status Check:**
- "Hey Sunny, how are you doing?"
- "Hey Sunny, show status"

### Workflow

1. Start the application
2. Open a research paper in any PDF viewer or browser
3. Use voice commands to interact with Sunny
4. Sunny analyzes papers and runs code in the background
5. Receive voice notifications when background tasks complete
6. All data is saved to SQLite database for later review

### Idle Assistance Feature

After 20 minutes on the same section, Sunny will ask: "You've been on this section for a while. Need help understanding something?"

This provides assistance when needed without interrupting normal reading flow.

## Architecture

```
sunny/
├── main.py                 # Application entry point
├── core/                   # Core interaction components
│   ├── voice_handler.py   # Voice input/output handling
│   └── screen_monitor.py  # Screen monitoring and context detection
├── research/              # Research-specific functionality
│   ├── paper_analyzer.py  # Paper analysis and critique
│   ├── code_executor.py   # Background code execution
│   └── research_agent.py  # Deep research and verification
├── storage/               # Data persistence
│   └── database.py        # SQLite database operations
└── utils/                 # Utility modules
    └── quota_manager.py   # API quota tracking
```

### Database Schema

SQLite database (`research_data.db`) contains:

- **papers** - Analyzed papers with metadata and summaries
- **notes** - User notes and AI critiques with timestamps
- **experiments** - Code execution results and status
- **research_tasks** - Deep research findings and related papers
- **relationships** - Connections and relationships between papers

## Troubleshooting

### Voice recognition not working
```bash
pip install RealtimeSTT
```

### Text-to-speech not working
```bash
pip install pyttsx3
```

### Screen monitoring errors
```bash
pip install Pillow pygetwindow
```

### API-related errors
- Verify API key is correctly set in `.env`
- Check that quota limits have not been exceeded
- Wait 60 seconds if rate limits are hit
- Review quota usage with "Hey Sunny, show status"

## Technology Stack

**Core Language & Framework:**
- **Python 3.8+** - High-level language for rapid development and research
- **Threading & Queue** - Built-in Python modules for async background processing

**AI & APIs:**
- **Google Gemini API** - Vision models (gemini-3.5-vision), multi-modal LLMs (gemini-2.5-flash, gemini-pro)
- **Gemini Code Execution Tool** - Sandboxed Python code execution with auto-retry logic
- **Gemini Function Calling** - Tool definitions for autonomous research agent control

**Voice & Audio:**
- **speech_recognition** - Windows native speech-to-text API (no external ML models needed)
- **gtts (Google Text-to-Speech)** - API-based voice synthesis
- **pygame.mixer** - Audio playback for TTS responses
- **RealtimeSTT** - Alternative STT library for improved recognition

**Screen & Vision:**
- **Pillow (PIL)** - Image capture and processing for screenshots
- **pygetwindow** - Window detection and context tracking
- **ImageChops** - Pixel-level image comparison for page-turn detection

**Editor Integration:**
- **VS Code** - Code editing environment for interactive development
- **pyautogui / keyboard automation** - Programmatic control of VS Code

**Data & Storage:**
- **SQLite** - Local persistent database for papers, notes, experiments, and relationships
- **python-dotenv** - Environment variable management for API keys

**Code Generation & Execution:**
- **numpy, scipy, pandas, torch, scikit-learn** - Supported libraries in sandbox execution
- **pyperclip** - Clipboard management for code transfer
- **json, re, ast** - Code parsing and cleaning

**Development & Version Control:**
- **GitHub** - Repository hosting and collaboration
- **Git** - Version control system

**Key Design Patterns:**
- **Model Orchestration** - Uses Flash for high-frequency tasks, Pro for deep analysis
- **Callback Architecture** - Event-driven completion notifications for background tasks
- **Quota Strategy** - Tracks and buffers API usage at 80% of limits for safety
- **Tool Function Calling** - 14 specialized tools exposed to Gemini for autonomous decisions

## How We Built It

Sunny was built by combining multiple Google Gemini APIs to create a seamless research experience:

1. **Vision Engine** - Uses Gemini 3.5 vision capabilities to analyze paper screenshots in real-time, extracting text, equations, and figures from any PDF viewer or browser
2. **Function Calling** - Implements tool definitions for paper analysis, code execution, and research tasks that Gemini orchestrates intelligently
3. **Code Execution Sandbox** - Leverages Gemini's built-in `code_execution` tool to safely run Python code from research papers with automatic error recovery
4. **Multi-Model Architecture** - Uses Flash for frequent screen monitoring (efficient quota usage) and Pro for deep analysis tasks
5. **Background Processing** - Implements threading and queueing system for autonomous experiment execution without blocking voice interactions
6. **Voice Integration** - Combines RealtimeSTT and pyttsx3 with Gemini's natural language understanding for hands-free research

The entire system is orchestrated through intelligent state management and quota tracking to maximize free-tier API usage.

**To make Sunny useful beyond summaries, we built three core components that work together seamlessly.** The **Screen Monitor** continuously watches the active window and captures screenshots at intervals, using image similarity hashing to detect significant page turns and scroll changes (85% similarity threshold to distinguish between meaningful page changes and minor cursor movements). When the user changes papers or sections, it automatically notifies Sunny of the context switch. The **Voice Handler** provides bidirectional audio communication—it uses Windows' native speech recognition API for hands-free input and Google Text-to-Speech with pygame for spoken responses, allowing users to interact entirely by voice without typing. The **Tools system** defines 14 research-specific functions that Gemini can autonomously invoke when needed:

**Paper Understanding & Analysis:**

- `tool_extract_code` - Pulls code snippets directly from PDFs using vision analysis
- `tool_analyze_section` - Deep analysis of specific paper sections with summaries, key claims, and technical concepts
- `tool_remember_paper` - Stores paper metadata and findings in the database for future reference

**Code Generation & Execution:**

- `tool_write_code_from_methodology` - Generates executable Python code by analyzing a paper's methodology section
- `tool_code_pseudocode` - Converts pseudocode from papers into fully functional Python implementations
- `tool_run_experiment` - Executes code in Gemini's isolated sandbox for safe verification
- `tool_run_experiment_with_output` - Runs code with real-time output streaming for interactive experimentation
- `tool_run_experiment_locally` - Creates files in VS Code and executes code in terminal for manual review and editing

**VS Code Integration:**

- `tool_create_file_and_write_code` - Creates new files in VS Code workspace with generated code
- `tool_write_to_active_file` - Writes code directly to the currently open editor for seamless workflow
- `tool_show_experiment_outputs` - Displays recent sandbox experiment results in a summary file
- `tool_show_specific_output` - Opens detailed output from any previous experiment

**Research Verification:**
- `tool_verify_claim` - Initiates claim verification by searching research database and identifying contradictions
- `tool_tts_speak` - Provides voice feedback for all operations

These tools are exposed to Gemini's function-calling API with detailed descriptions, enabling the model to intelligently choose which action to take based on what the user asks—whether they want code extracted, a methodology critiqued, an experiment replicated, or research verified. The separation between sandbox execution (background, safe) and local execution (interactive, editable) gives users control over how deeply they engage with code.

## Challenges We Ran Into

1. **Screenshot-to-Text Accuracy** - Initial vision model results had difficulty extracting code from PDFs with complex formatting. Solution: Implemented multi-pass analysis with error correction prompts.

2. **Code Execution Error Recovery** - Extracted code often failed due to missing imports or environment assumptions. Solution: Built auto-retry logic that prompts Gemini to fix and re-run code autonomously.

3. **Quota Management** - Balancing free-tier API limits while providing responsive user experience. Solution: Implemented intelligent quota tracking and Safety buffers with predictive warnings.

4. **Synchronous Voice + Asynchronous Processing** - Managing real-time voice interaction while running background experiments. Solution: Used queue-based threading architecture with completion callbacks.

5. **Context Accuracy** - Screen monitoring must distinguish between multiple papers and tabs. Solution: Window title tracking and visual content hashing for reliable context detection.

## License

MIT License

## Acknowledgments

Built with Google Gemini 3 API.


