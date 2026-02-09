# Sunny Research Assistant - Architecture Documentation

## System Overview

Sunny is a voice-first AI research assistant built on Gemini 3 APIs. It monitors screens for academic papers, analyzes them using vision, executes code experiments, and verifies research claims—all orchestrated through intelligent function calling.

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SUNNY ASSISTANT                                 │
│                           (main.py - Orchestrator)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  VOICE HANDLER   │         │ SCREEN MONITOR   │         │  VISION ENGINE   │
│  (core/)         │         │  (core/)         │         │  (research/)     │
├──────────────────┤         ├──────────────────┤         ├──────────────────┤
│ • Speech-to-Text │         │ • Screen capture │         │ • Gemini vision  │
│ • Text-to-Speech │         │ • Page detection │         │ • Tool dispatch  │
│ • Wake phrases   │         │ • Context track  │         │ • Error handling │
└──────────────────┘         └──────────────────┘         └──────────────────┘
        │                              │                              │
        │◄─────────User voice input────┴──────Screen context ────────┤
        │                              │                              │
        └──────────────────────────────┼──────────────────────────────┘
                                       │
                                       ▼
                      ┌──────────────────────────────┐
                      │   VISION ENGINE CORE         │
                      │ (vision_engine.py)           │
                      ├──────────────────────────────┤
                      │ • Captures screenshots       │
                      │ • Sends to Gemini 3 with:    │
                      │   - User prompt              │
                      │   - Screenshot image         │
                      │   - Window context           │
                      │   - Tool definitions         │
                      │ • Receives function calls    │
                      │ • Executes tools             │
                      │ • Recursive until complete   │
                      └──────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│ PAPER ANALYZER   │         │ CODE EXECUTOR    │         │ RESEARCH AGENT   │
│ (research/)      │         │ (research/)      │         │ (research/)      │
├──────────────────┤         ├──────────────────┤         ├──────────────────┤
│ • Extract text   │         │ • Run code via   │         │ • Verify claims  │
│ • Analyze paper  │         │   Gemini exec    │         │ • Find papers    │
│ • Extract code   │         │ • Auto-retry     │         │ • Search DB      │
│ • JSON output    │         │ • Background     │         │ • Threading      │
│ • Screenshot     │         │   threading      │         │                  │
└──────────────────┘         └──────────────────┘         └──────────────────┘
        │                              │                              │
        └──────────────────────────────┼──────────────────────────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │                                           │
                 ▼                                           ▼
        ┌──────────────────┐                         ┌──────────────────┐
        │   STORAGE LAYER  │                         │   GEMINI 3 APIs  │
        │ (storage/)       │                         │   (Google Cloud) │
        ├──────────────────┤                         ├──────────────────┤
        │ • Database       │                         │ • gemini-3-      │
        │   (SQLite)       │                         │   flash-preview  │
        │ • Papers         │                         │ • Vision API     │
        │ • Notes          │                         │ • Code Execute   │
        │ • Experiments    │                         │ • Function Call  │
        │ • Research tasks │                         │ • Deep Research  │
        │ • Context cache  │                         └──────────────────┘
        │ • Quota tracking │
        └──────────────────┘
```

## Component Deep Dive

### 1. **Voice Handler** (`core/voice_handler.py`)
**Purpose**: Enables voice-first interaction without typing
- **Input**: Microphone audio → `speech_recognition` library
- **Processing**: Captures natural language voice commands
- **Output**: Text prompts to Vision Engine
- **TTS**: Uses `gtts` (Google Text-to-Speech) + pygame for spoken responses
- **Wake Phrases**: Detects "Hey Sunny", "OK Sunny", etc.

### 2. **Screen Monitor** (`core/screen_monitor.py`)
**Purpose**: Contextually aware by monitoring the user's screen
- **Monitoring**: Checks screen every 2 seconds
- **Page Turn Detection**: Uses image similarity hashing (85% threshold)
- **Context Extraction**: Identifies active window, detects paper changes
- **Smart Triggering**: Accumulates changes before analysis to avoid spam
- **Cooldown System**: Waits 0.8s after last change before triggering analysis

### 3. **Vision Engine** (`research/vision_engine.py`)
**Purpose**: Central AI reasoning loop with multimodal perception
- **Input**: User text + Screenshot + Window context
- **Gemini Call**: Sends to `gemini-3-flash-preview` with:
  - Context prompt (paper details, conversation history)
  - Screenshot image (multimodal understanding)
  - Available tools definitions
  - Task-specific generation config (temperature adjusted)
- **Function Calling**: Parses Gemini's tool invocations
- **Tool Execution**: Delegates to appropriate handlers
- **Recursion**: Loops until Gemini indicates task completion
- **Error Handling**: Exponential backoff retry for transient failures

### 4. **Paper Analyzer** (`research/paper_analyzer.py`)
**Purpose**: Extracts knowledge from academic papers
- **Screenshot Analysis**: Sends paper screenshot to Gemini
- **JSON Extraction**: Returns structured data:
  - Title, authors, year, current section
  - Summary, main claims, methodology, findings
  - Thought process reasoning
- **Code Extraction**: Identifies and extracts code blocks
- **Quota-Aware**: Checks API quota before premium calls

### 5. **Code Executor** (`research/code_executor.py`)
**Purpose**: Replicates experiments by executing paper code
- **Execution Method**: Uses Gemini's native `code_execution` tool
- **Queue System**: Background thread processes experiments asynchronously
- **Auto-Retry Logic**: 
  - Captures execution errors
  - Asks Gemini to fix and re-run
  - Up to 3 retry attempts with exponential backoff
- **Result Storage**: Saves output, duration, status to database
- **Threading**: Non-blocking background processing

### 6. **Research Agent** (`research/research_agent.py`)
**Purpose**: Verifies claims and discovers related papers
- **Deep Research**: Uses LLM reasoning for claim verification
- **Database Queries**: Searches stored papers for contradictions
- **Background Tasks**: Threading for long-running searches
- **JSON Results**: Returns papers with relationships (supports/contradicts)
- **Quota Aware**: Respects API limits

### 7. **Gemini Tools** (`research/tools.py`)
**Purpose**: Tools that Gemini can invoke via function calling
- `tool_tts_speak()`: Verbal responses
- `tool_extract_code()`: Code from current paper
- `tool_run_experiment()`: Queue code execution
- `tool_remember_paper()`: Save paper context
- `tool_verify_claim()`: Launch research task
- `tool_analyze_section()`: Deep paper analysis
- `tool_write_code_from_methodology()`: Generate code from methodology descriptions

### 8. **Storage Layer** (`storage/`)

#### Database (`storage/database.py`)
- **SQLite**: Persistent local storage
- **Tables**:
  - `papers`: Paper metadata and references
  - `notes`: User notes and AI critiques
  - `experiments`: Code execution history and results
  - `research_tasks`: Deep research queries and findings
  - `memory`: Long-term context and insights

#### Context Manager (`storage/context_manager.py`)
- **Session State**: Current paper, conversation history
- **Persistence**: Loads/saves to database
- **History**: Maintains conversation context for multi-turn interactions
- **Memory Bank**: Stores insights and references for future use
- **System Instructions**: Dynamic prompting based on context

### 9. **Quota Manager** (`utils/quota_manager.py`)
**Purpose**: Manages Gemini API quota (free tier constraints)
- **Pro Calls**: Tracks expensive API calls
- **Rate Limiting**: Prevents quota exhaustion
- **Fallback**: Routes to Flash model when quota insufficient
- **Logging**: Records all API usage for debugging

## Data Flow Diagram

```
User Voice Input
       │
       ▼
[Voice Handler] ──► STT conversion ──► Text command
       │
       ▼
[Vision Engine] ◄── [Screen Monitor] captures current screen
       │                    │
       │                    └─ Detects context changes
       │
       ├─► Screenshot captured
       │
       ├─► Prompt building (with conversation history)
       │
       ├─► [GEMINI 3 API CALL]
       │   ├─ multimodal: text + image input
       │   ├─ tools: function definitions
       │   └─ generation_config: task-specific tuning
       │
       ▼
   [Function Calls received from Gemini]
       │
       ├───┬──────┬──────┬──────┬──────┬──────┐
       │   │      │      │      │      │      │
       ▼   ▼      ▼      ▼      ▼      ▼      ▼
     Speak Extract Run  Remember Verify Analyze Write
           Code   Exp   Paper   Claim  Section Code
           │      │     │       │      │      │
           │      ▼     │       ▼      ▼      │
           │   [Code    │   [Research  [Paper │
           │    Executor]   Agent]   Analyzer]│
           │      │         │          │      │
           ▼      ▼         ▼          ▼      ▼
       [TTS]   [Exec] [Database]  [Analysis] [Model]
       Output  Results  Query      Output    Output
           │      │        │          │      │
           └──────┴────────┴──────────┴──────┘
                  │
                  ▼
          [Context Manager]
          Store state & results
                  │
                  ▼
            [Database]
          Persist knowledge
                  │
                  ▼
          [Return to Vision Engine]
          Continue or complete task
```

## Key Gemini 3 Integration Points

### 1. **Multimodal Vision**
```python
response = self.screen_aware_model.generate_content(
    [context_prompt, screenshot],  # Text + image
    tools=self.tools.get_tool_definitions(),
    generation_config=task_config
)
```
- Sends both text and image (screenshot of paper)
- Processes visual information alongside textual queries

### 2. **Function Calling**
```python
for part in response.parts:
    if fn := part.function_call:
        self._execute_tool_call(fn)  # Execute Gemini's tool request
```
- Gemini selects which tool to invoke
- System executes the tool and feeds results back
- Recursive loop: Gemini reasons about results and calls next tool

### 3. **Code Execution Tool**
```python
self.code_model = genai.GenerativeModel(
    model_name="gemini-3-flash-preview",
    tools=[{"code_execution": {}}]  # Native code execution
)
```
- Directly executes Python code via Gemini
- Captures stdout/stderr for error feedback
- Auto-correction loop for failed experiments

### 4. **Task-Aware Generation**
```python
generation_config = {
    "temperature": 0.2,  # Precise for analysis
    # or
    "temperature": 0.7   # Creative for code generation
}
```
- Adjusts model behavior based on task type
- Lower temperature (0.1-0.2) for analysis and code execution
- Higher temperature (0.7) for creative code generation

### 5. **Structured Output**
```python
self.pro_model = genai.GenerativeModel(
    generation_config={
        "response_mime_type": "application/json"
    }
)
```
- Paper analysis returns structured JSON
- Enables reliable parsing and database storage

## Execution Flow: Complete Example

**User says**: "Analyze this paper's methodology and replicate the experiment"

```
1. VoiceHandler detects speech
   └─► "Analyze this paper's methodology and replicate the experiment"

2. VisionEngine.screen_aware_respond() called
   ├─ Captures screenshot (current paper on screen)
   ├─ Builds context prompt with paper history
   └─ Calls Gemini with [prompt + screenshot + tools]

3. Gemini analyzes and returns function calls:
   ├─ tool_analyze_section("methodology")
   └─ tool_write_code_from_methodology("methodology")

4. Vision Engine executes tools:
   ├─ PaperAnalyzer.analyze_paper() 
   │  └─ Returns: {summary, methodology, code snippets}
   │
   └─ SunnyTools.tool_write_code_from_methodology()
      ├─ Extracts methodology text
      ├─ Asks Gemini to generate Python code
      └─ Returns: executable code string

5. Tools return results to Gemini
   ├─ Gemini receives code and analysis
   ├─ Decides: "Now run the experiment"
   └─ Calls: tool_run_experiment(generated_code)

6. CodeExecutor.replicate_experiment() queued
   └─ Background thread executes code via Gemini exec tool
      ├─ Captures output/errors
      ├─ If fails: Auto-retry with error feedback
      └─ Stores results in database

7. CodeExecutor.on_completion() fires
   └─ Updates UI: "Experiment complete, results saved"

8. VisionEngine loops
   └─ Checks if task complete, speaks final summary
```

## Technology Stack

| Layer | Component | Technology |
|-------|-----------|------------|
| **AI Core** | Language Model | Gemini 3 Flash Preview |
| **AI Capabilities** | Vision | Gemini Multimodal |
| **AI Tools** | Function Calling | Gemini Native |
| **AI Tools** | Code Execution | Gemini Native |
| **Voice I/O** | Speech Recognition | speech_recognition library |
| **Voice I/O** | Text-to-Speech | Google Text-to-Speech (gtts) |
| **Voice I/O** | Audio Output | pygame mixer |
| **Screen Capture** | Display Monitoring | PIL + Pillow |
| **Screen Context** | Window Info | pygetwindow |
| **Storage** | Database | SQLite3 |
| **State Mgmt** | Configuration | python-dotenv |
| **Async** | Threading | Python threading + queue |

## Critical Design Patterns

### 1. **Tool-Driven Orchestration**
Instead of hardcoding logic, tools define what Gemini can do. Gemini autonomously selects tools based on the task—enabling flexible, emergent behavior.

### 2. **Multimodal Context**
Every Gemini call includes text (prompt + history) AND image (screenshot). This dual-channel input drives accurate understanding.

### 3. **Error Recovery Loop**
Code executor catches execution errors and feeds them back to Gemini with the original code. Gemini auto-fixes and reruns—creating a self-improving system.

### 4. **Quota-Aware Routing**
Different models for different costs:
- `gemini-3-flash-preview`: Fast, cheap, for most operations
- Premium APIs: Only when quota allows, routed by quota manager

### 5. **Background Async Processing**
Long tasks (code execution, research) run in background threads, keeping the UI responsive.

### 6. **Persistent Context**
Conversation history, memories, and experiment results persist in SQLite. Sunny learns and improves across sessions.

## Deployment Considerations

### API Keys
- Requires `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com)
- Stored in `.env` file (not committed to git)

### Dependencies
- Python 3.8+
- All requirements in `requirements.txt`
- Windows/Linux/macOS compatible

### Free Tier Limitations
- Rate limits on API calls
- Quota manager prevents overages
- Falls back gracefully when limits hit

### Local vs Cloud
- All processing is local (privacy-preserving)
- Only API calls to Gemini go to cloud
- Database and files stored locally
