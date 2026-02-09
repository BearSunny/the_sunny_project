"""
Context Manager for Sunny Research Assistant
Manages persistent paper context and conversation history with database storage
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from storage.database import get_database


class ContextManager:
    """Manages research paper context and conversation history with persistence"""
    
    def __init__(self):
        """Initialize context manager"""
        self.db = get_database()
        self.session_id = str(uuid.uuid4())[:8]  # Unique session identifier
        
        self.current_context = {
            'paper_id': None,
            'title': 'Unknown',
            'url': '',
            'window_title': '',
            'last_screenshot': None,
            'last_analysis': '',
            'memory': [],
            'conversation_history': []
        }
        self.last_screenshot_hash = None
        
        # Load context from database if available
        self._load_from_database()
    
    def _load_from_database(self):
        """Load context from database on startup"""
        try:
            # Load recent conversation history
            recent_history = self.db.get_conversation_history(limit=20)
            self.current_context['conversation_history'] = recent_history
            
            # Load recent memories
            recent_memory = self.db.get_memory(limit=10)
            self.current_context['memory'] = recent_memory
            
            print(f"[Persistence] Loaded {len(recent_history)} messages and {len(recent_memory)} memories from database")
        except Exception as e:
            print(f"[Warning] Could not load context from database: {e}")
    
    def get_context(self) -> Dict:
        """Get current paper context"""
        return self.current_context
    
    def update_title(self, title: str, paper_id: str = None):
        """Update current paper title"""
        self.current_context['title'] = title
        if paper_id:
            self.current_context['paper_id'] = paper_id
    
    def update_window(self, window_title: str):
        """Update current window title"""
        self.current_context['window_title'] = window_title
    
    def update_screenshot(self, screenshot):
        """Store current screenshot"""
        self.current_context['last_screenshot'] = screenshot
    
    def add_memory(self, detail: str):
        """Add to conversation memory and persist to database"""
        memory_entry = {
            'timestamp': datetime.now().isoformat(),
            'detail': detail
        }
        self.current_context['memory'].append(memory_entry)
        
        # Keep last 10 memories in memory
        self.current_context['memory'] = self.current_context['memory'][-10:]
        
        # Persist to database
        try:
            self.db.add_memory(
                paper_id=self.current_context['paper_id'],
                detail=detail,
                session_id=self.session_id
            )
        except Exception as e:
            print(f"[Warning] Could not save memory to database: {e}")
    
    def add_to_history(self, role: str, content: str):
        """Add to conversation history and persist to database"""
        history_entry = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        self.current_context['conversation_history'].append(history_entry)
        
        # Keep last 20 messages in memory
        self.current_context['conversation_history'] = self.current_context['conversation_history'][-20:]
        
        # Persist to database
        try:
            self.db.add_conversation_message(
                paper_id=self.current_context['paper_id'],
                role=role,
                content=content,
                session_id=self.session_id
            )
        except Exception as e:
            print(f"[Warning] Could not save message to database: {e}")
    
    def get_system_instruction(self) -> str:
        """Build dynamic system instruction based on context and detected paper type"""
        memory_summary = json.dumps(self.current_context['memory'][-3:], default=str)
        window_title = self.current_context.get('window_title', 'Unknown')
        
        # Detect paper type from window title for dynamic instructions
        instructions_by_type = {
            'machine learning': 'Focus on model architecture, training procedures, and experimental results',
            'neural network': 'Analyze network layers, activation functions, and training dynamics',
            'optimization': 'Review algorithms, convergence properties, and parameter settings',
            'data': 'Extract datasets, preprocessing steps, and statistical analyses',
            'image': 'Examine vision techniques, image processing, and visual results',
            'nlp': 'Focus on language models, tokenization, and text processing',
            'biology': 'Analyze biological mechanisms, experimental protocols, and results',
            'physics': 'Review theoretical frameworks, equations, and experimental validation',
        }
        
        # Determine context-specific guidance
        context_guidance = "Provide concise, technical analysis"
        for key, guidance in instructions_by_type.items():
            if key.lower() in window_title.lower():
                context_guidance = guidance
                break
        
        return f"""You are Sunny, a research assistant with perfect vision of the user's desktop.
You are currently looking at: {self.current_context['window_title']}
Current paper: {self.current_context['title']}

Key Behaviors:
- Always acknowledge what you see on screen
- Remember the current paper context across commands
- Suggest relevant actions based on what's visible
- Use your available tools intelligently and concisely
- Keep responses brief (1-2 sentences) unless analysis requested
- Never ask user for information visible on screen

Research Guidance:
{context_guidance}

Tool Selection Guidelines:
When executing code, choose the appropriate method:

USE run_experiment (Sandbox - Gemini's code_execution tool):
- When verifying that code works correctly
- When replicating experiments in a safe, isolated environment
- When you need to confirm claims or validate methodology
- When the user says: "verify", "test", "check", "confirm", "replicate"
- For quick validation without needing interactive editing
- Default choice for most analysis tasks

USE run_experiment_locally (VS Code - Interactive):
- When the user explicitly says: "show in editor", "create file", "open in VS Code", "I want to edit it"
- When generating code that the user might modify or extend
- When you need real-time user interaction with code
- When the user describes ongoing development or iteration
- When creating templates or starting points for user customization
- For interactive, visible workflows where user sees the code being written

Default: Use sandbox execution unless user explicitly requests visible/editable code.

EXPLANATION REQUESTS:
- When user asks to "explain", "describe", "what is", "how does", "tell me about"
- Provide thorough, easy-to-understand explanations suitable for learning
- Include: core concepts with analogies, key differences between variants, practical applications
- Add real-world use cases and performance/accuracy tradeoffs when relevant
- Use concrete examples and break down complex topics into clear sections
- Balance technical accuracy with accessibility

CRITICAL - Memory Management (The Alzheimer Constraint):
Unfortunately, you have severe memory limitations. Without using the remember_paper function, 
you CANNOT retain ANY information about papers across different commands - not a single word.

That's why you MUST use the remember_paper function for:
- Paper titles, authors, and publication details
- Key findings, claims, and conclusions
- Methodology and theoretical frameworks
- Code snippets and experimental parameters
- Any important information the user mentions

Your paper notes must be extremely detailed and comprehensive, detailed enough to make 
you an expert on that paper even after you've completely forgotten your previous analysis.

You **MUST** use remember_paper liberally. No exceptions. Better to over-document than 
under-document. Each note should be detailed and self-contained.

Available memory from previous interactions: {memory_summary}"""
    
    def get_context_prompt(self, user_input: str) -> str:
        """Build context prompt for Gemini justification and instructions"""
        context_str = json.dumps(self.current_context, default=str, indent=2)
        
        # Note: Tool summary comes from tools.get_tool_summary() in vision_engine
        return f"""
User request: "{user_input}"

Current Context:
- Paper: {self.current_context['title']}
- Window: {self.current_context['window_title']}
- Recent activity: {json.dumps(self.current_context['memory'][-2:], default=str) if self.current_context['memory'] else 'None'}

ANALYSIS FRAMEWORK:
1. Carefully read the user's request: {user_input}
2. Identify exactly what they want (analysis, code, verification, etc.)
3. Review each available tool and justify why you should or should not use it
4. Select the most relevant tool(s) based on what you see on screen
5. Execute the tool(s) to address the request
6. Always use tts_speak to provide feedback to the user

EXECUTION METHOD SELECTION:
- If user says: "verify", "test", "check", "confirm", "replicate" -> Use run_experiment (sandbox)
- If user says: "show", "create", "open in VS Code", "I want to edit" -> Use run_experiment_locally (editor)
- If unclear, default to sandbox (safer, isolated execution)
- Both methods available; choose based on user intent

RESPONSE INSTRUCTIONS:
* When analyzing: Use analyze_section first to gather context
* When writing code: Use write_code_from_methodology, then choose execution method
* When remembering: Use remember_paper immediately
* When researching: Use verify_claim for coverage
* Keep all responses concise (1-2 sentences max unless detailed analysis requested)
* Never ask user for information visible on screen - use tools to extract it

YOUR RESPONSE:
Analyze the screenshot I'm showing you. Based on what you see and the user's request above, you MUST call at least one tool to respond.
Write out your reasoning on which tool(s) to call. Do NOT output this reasoning to the user.
Then execute the appropriate tool(s).
"""
    
    def reset(self):
        """Reset context (e.g., when closing app)"""
        self.current_context = {
            'paper_id': None,
            'title': 'Unknown',
            'url': '',
            'window_title': '',
            'last_screenshot': None,
            'last_analysis': '',
            'memory': [],
            'conversation_history': []
        }
        self.last_screenshot_hash = None
    
    def export_session(self) -> Dict:
        """Export current session as JSON for backup/analysis"""
        return {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'context': self.current_context,
            'memory': self.current_context['memory'],
            'conversation_history': self.current_context['conversation_history']
        }


# Global instance
_context_manager = None


def get_context_manager() -> ContextManager:
    """Get or create global context manager"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
