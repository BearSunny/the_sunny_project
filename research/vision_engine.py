"""
Vision Engine for Sunny Research Assistant
Core screen-aware reasoning loop - Phase 1 implementation
Captures screenshots, sends to Gemini with tools, executes responses
"""

import os
import time
from typing import Optional, Dict
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import (
    ResourceExhausted, 
    InternalServerError, 
    InvalidArgument,
    FailedPrecondition,
    ServiceUnavailable
)

from storage.context_manager import get_context_manager
from research.tools import SunnyTools
from integration.vscode_automation import create_vscode_automation
from utils.quota_manager import get_quota_manager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Error handling constants
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2.0
API_TIMEOUT = 30  # seconds


class VisionEngine:
    """Core screen-aware reasoning engine with task-specific prompting"""
    
    def __init__(self, voice_handler, screen_monitor, paper_analyzer, code_executor, research_agent):
        """Initialize vision engine"""
        self.context = get_context_manager()
        self.voice_handler = voice_handler
        self.screen_monitor = screen_monitor
        self.quota_manager = get_quota_manager()
        
        # Initialize VS Code automation
        vscode_automation = create_vscode_automation()
        
        # Initialize tools with all dependencies
        self.tools = SunnyTools(
            voice_handler=voice_handler,
            screen_monitor=screen_monitor,
            paper_analyzer=paper_analyzer,
            code_executor=code_executor,
            research_agent=research_agent,
            vscode_automation=vscode_automation
        )
        
        # Core screen-aware model with task-appropriate config
        # Lower temperature for precise analysis, higher for creative code generation
        self.screen_aware_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=self.context.get_system_instruction(),
            generation_config={
                "temperature": 0.3,  # Conservative for tool selection
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2000
            }
        )
    
    def _get_task_config(self, user_input: str) -> Dict:
        """Get generation config based on task type"""
        prompt_lower = user_input.lower()
        
        # Code generation tasks need higher temperature for creativity
        if any(word in prompt_lower for word in ['generate', 'write', 'implement', 'create code']):
            return {"temperature": 0.7, "top_p": 0.95}
        
        # Analysis tasks need lower temperature for accuracy
        if any(word in prompt_lower for word in ['analyze', 'explain', 'what', 'how', 'why']):
            return {"temperature": 0.2, "top_p": 0.9}
        
        # Code execution needs precision
        if any(word in prompt_lower for word in ['run', 'execute', 'experiment', 'replicate']):
            return {"temperature": 0.1, "top_p": 0.85}
        
        # Default middle ground
        return {"temperature": 0.3, "top_p": 0.95}
    
    def _emit_working_notification(self, user_input: str) -> bool:
        """Emit working status notification for coding tasks
        
        Provides immediate feedback when user initiates code generation or execution tasks.
        Helps users understand that work is in progress before actual tool execution.
        
        Args:
            user_input: The user's request text
        
        Returns:
            True if notification was emitted, False otherwise
        """
        prompt_lower = user_input.lower()
        
        # Detect coding/generation keywords
        has_code_keyword = any(word in prompt_lower for word in ['code', 'implement', 'write', 'generate', 'create', 'run', 'build'])
        
        if not has_code_keyword:
            return False
        
        # Extract specific context clues for more targeted messages
        if 'denseNet' in prompt_lower or 'densenet' in prompt_lower:
            if 'yoga' in prompt_lower:
                self.voice_handler.speak("I'm coding the DenseNet classification pipeline on Yoga-82 now")
            else:
                self.voice_handler.speak("I'm implementing the DenseNet model now")
            return True
        
        if 'pipeline' in prompt_lower:
            if 'classification' in prompt_lower:
                self.voice_handler.speak("I'm coding the classification pipeline now")
            else:
                self.voice_handler.speak("I'm building the pipeline now")
            return True
        
        if any(word in prompt_lower for word in ['pseudocode', 'algorithm', 'pseudocode 1', 'pseudocode 2']):
            self.voice_handler.speak("I'm converting the pseudocode to Python now")
            return True
        
        if 'changed my mind' in prompt_lower or 'run only' in prompt_lower:
            self.voice_handler.speak("I'm coding your updated request now")
            return True
        
        # Generic fallback for other code tasks
        if has_code_keyword:
            self.voice_handler.speak("I'm writing the code for you")
            return True
        
        return False
    
    def screen_aware_respond(self, user_input: str, retry_count: int = 0, recursion_depth: int = 0):
        """
        PHASE 1: Central analysis function with robust error handling
        Captures screenshot + context, sends to Gemini with tools
        Gemini calls appropriate tools, then recursively analyzes until done
        
        Args:
            user_input: Text from user (voice or keyboard)
            retry_count: Current retry attempt
            recursion_depth: Depth of recursion for tool-not-called retry (max 3)
        """
        # Prevent infinite recursion when no tool is called
        if recursion_depth > 3:
            self.voice_handler.speak("I'm having trouble understanding this request. Please try again.")
            return
        try:
            # Capture current state
            screenshot = self.screen_monitor.get_current_screenshot()
            if screenshot is None:
                self.voice_handler.speak("I can't see your screen right now")
                return
            
            self.context.update_screenshot(screenshot)
            
            # Get window info with fallback
            import pygetwindow as gw
            try:
                window_title = gw.getActiveWindow().title if gw.getActiveWindow() else "Unknown"
                self.context.update_window(window_title)
            except Exception as e:
                print(f"[Warning] Could not get window title: {e}")
                self.context.update_window("Unknown")
            
            # Emit working notification for code tasks (immediate feedback to user)
            self._emit_working_notification(user_input)
            
            # Build context prompt
            context_prompt = self.context.get_context_prompt(user_input)
            
            # Get task-specific generation config
            task_config = self._get_task_config(user_input)
            
            # Check quota BEFORE making API call
            can_call, reason = self.quota_manager.can_call_flash()
            if not can_call:
                print(f"[Quota Block] {reason}")
                self.voice_handler.speak(f"I've reached my API quota. {reason}. Please try again later.")
                return
            
            try:
                # Send to Gemini with screenshot and tools, using task-specific config
                response = self.screen_aware_model.generate_content(
                    [context_prompt, screenshot],
                    tools=self.tools.get_tool_definitions(),
                    generation_config=task_config  # Use task-specific settings
                )
                
                # Record the API call for quota tracking
                self.quota_manager.record_flash_call()
                
                print(f"[DEBUG] Response type: {type(response)}")
                print(f"[DEBUG] Response: {response}")
                
                # Execute any tool calls from Gemini
                tool_was_called = False
                try:
                    for part in response.parts:
                        print(f"[DEBUG] Part type: {type(part)}, Part: {part}")
                        if hasattr(part, 'function_call'):
                            fn = part.function_call
                            if fn is not None:
                                tool_was_called = True
                                self._execute_tool_call(fn)
                except (KeyError, AttributeError) as e:
                    print(f"[Error] Error processing response parts: {e}")
                    import traceback
                    traceback.print_exc()
                    self.voice_handler.speak(f"Error processing response: {e}")
                    return
                
                # If no tool was called, retry with delay (Gemini should always call a tool)
                if not tool_was_called:
                    # Don't retry if near recursion limit
                    if recursion_depth >= 2:
                        print(f"[Warning] No tool called after {recursion_depth} attempts. Stopping recursion.")
                        self.voice_handler.speak("I wasn't able to process this request properly. Please try rephrasing.")
                        return
                    
                    # Check quota before recursing
                    can_call, reason = self.quota_manager.can_call_flash()
                    if not can_call:
                        print(f"[Quota Block during recursion] {reason}")
                        self.voice_handler.speak("I've reached my API quota. Unable to retry.")
                        return
                    
                    print(f"[Warning] No tool called, analyzing more carefully (attempt {recursion_depth + 1}/3)")
                    self.voice_handler.speak("Let me analyze that more carefully")
                    self.screen_aware_respond(user_input, recursion_depth=recursion_depth + 1)
                    
            except ResourceExhausted as e:
                print(f"[API Error] Rate limit exceeded: {e}")
                self.voice_handler.speak("I've hit my API rate limit. Please wait a minute before trying again.")
                return
                
            except (InternalServerError, ServiceUnavailable) as e:
                # Retry with exponential backoff
                if retry_count < MAX_RETRIES:
                    wait_time = BASE_RETRY_DELAY * (RETRY_BACKOFF_MULTIPLIER ** retry_count)
                    print(f"[API Error - Attempt {retry_count + 1}/{MAX_RETRIES}] Server error: {e}")
                    print(f"[Info] Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    self.screen_aware_respond(user_input, retry_count + 1)
                else:
                    print(f"[Error] API server error after {MAX_RETRIES} retries")
                    self.voice_handler.speak("Google's servers are temporarily unavailable. Please try again in a moment.")
                    return
                    
            except InvalidArgument as e:
                print(f"[Fatal Error] Invalid request: {e}")
                self.voice_handler.speak("There was a problem with how I'm using the API. Please check the logs.")
                return
                
            except FailedPrecondition as e:
                print(f"[Fatal Error] Precondition failed (API key/billing issue): {e}")
                self.voice_handler.speak("There's an issue with the API configuration. Please check your API key and billing settings.")
                return
                
        except KeyboardInterrupt:
            print("[Info] User interrupted operation")
            self.voice_handler.speak("Operation cancelled.")
            return
            
        except Exception as e:
            print(f"[Unexpected Error] {type(e).__name__}: {e}")
            self.voice_handler.speak(f"I encountered an unexpected error: {type(e).__name__}. Please try again.")
            # Log to context for debugging
            self.context.add_memory(f"ERROR: {type(e).__name__}: {str(e)}")
    
    def _execute_tool_call(self, fn):
        """
        Execute a tool call from Gemini with robust error handling
        
        Args:
            fn: FunctionCall object from Gemini response
        """
        try:
            func_name = fn.name
            print(f"[DEBUG] Function name: {func_name}")
            print(f"[DEBUG] Function args type: {type(fn.args)}")
            
            # Handle different types of args - try dict-like conversion first
            kwargs = {}
            if isinstance(fn.args, dict):
                # Already a dict
                kwargs = fn.args
            elif hasattr(fn.args, 'items') and callable(getattr(fn.args, 'items')):
                # Dict-like object with items() method (MapComposite, proto-plus types)
                try:
                    kwargs = dict(fn.args.items())
                except Exception as e:
                    print(f"[DEBUG] Could not use items() method: {e}")
                    kwargs = {}
            elif hasattr(fn.args, '__dict__'):
                # Last resort: try vars() and filter out private attributes
                kwargs = {k: v for k, v in vars(fn.args).items() if not k.startswith('_')}
            else:
                # Try to convert
                try:
                    kwargs = dict(fn.args)
                except (TypeError, ValueError) as e:
                    print(f"[DEBUG] Could not convert args to dict: {e}")
                    print(f"[DEBUG] Args content: {fn.args}")
                    kwargs = {}
            
            # Unwrap protobuf Value messages to get actual Python values
            unwrapped_kwargs = {}
            for k, v in kwargs.items():
                if v is None or v == "":
                    continue  # Skip None and empty strings
                # Check if it's a protobuf Value message with string_value, number_value, etc.
                if hasattr(v, 'string_value') and v.string_value:
                    unwrapped_kwargs[k] = v.string_value
                elif hasattr(v, 'number_value'):
                    unwrapped_kwargs[k] = v.number_value
                elif hasattr(v, 'bool_value'):
                    unwrapped_kwargs[k] = v.bool_value
                elif hasattr(v, 'list_value'):
                    unwrapped_kwargs[k] = list(v.list_value.values)
                elif hasattr(v, 'struct_value'):
                    unwrapped_kwargs[k] = dict(v.struct_value.fields)
                else:
                    # Not a protobuf Value, keep as is (skip private attributes)
                    if not str(k).startswith('_'):
                        unwrapped_kwargs[k] = v
            kwargs = unwrapped_kwargs
            
            # Filter out None values and empty strings
            kwargs = {k: v for k, v in kwargs.items() if v is not None and v != ""}
            print(f"[DEBUG] Kwargs: {kwargs}")
            
            print(f"Calling tool: {func_name}")
            
            # Tool names from Gemini already include "tool_" prefix
            # so use them directly without adding another prefix
            if hasattr(self.tools, func_name):
                tool_method = getattr(self.tools, func_name)
                
                try:
                    result = tool_method(**kwargs)
                    print(f"[OK] Tool {func_name} executed successfully")
                    return result
                    
                except TypeError as e:
                    print(f"[WARN] Tool argument error in {func_name}: {e}")
                    self.voice_handler.speak(f"Tool {func_name} had an argument error. Check the logs.")
                    self.context.add_memory(f"TOOL_ERROR: {func_name} - {str(e)}")
                    
                except Exception as e:
                    print(f"[WARN] Tool execution error in {func_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    self.voice_handler.speak(f"Tool {func_name} encountered an error while executing.")
                    self.context.add_memory(f"TOOL_ERROR: {func_name} - {type(e).__name__}: {str(e)}")
            else:
                print(f"[WARN] Tool not found: {func_name}")
                self.voice_handler.speak(f"Tool {func_name} is not available.")
                
        except Exception as e:
            print(f"[Critical] Error in tool execution setup: {e}")
            import traceback
            traceback.print_exc()
            self.voice_handler.speak("Critical error executing tool. Check the logs.")
    
    def update_system_instruction(self):
        """Update system instruction with latest context"""
        self.screen_aware_model.system_instruction = self.context.get_system_instruction()
