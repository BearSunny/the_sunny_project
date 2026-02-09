"""
Tool Functions for Gemini Function Calling
These are the tools that Gemini can invoke to interact with the research system
"""

from typing import Optional
from storage.context_manager import get_context_manager
from utils.quota_manager import get_quota_manager
from google.generativeai import protos


class SunnyTools:
    """Container for all Gemini-callable tools"""
    
    def __init__(self, voice_handler, screen_monitor, paper_analyzer, code_executor, research_agent, vscode_automation=None):
        """Initialize tools with dependencies"""
        self.context = get_context_manager()
        self.quota_manager = get_quota_manager()
        self.voice_handler = voice_handler
        self.screen_monitor = screen_monitor
        self.paper_analyzer = paper_analyzer
        self.code_executor = code_executor
        self.research_agent = research_agent
        
        # Initialize VS Code automation
        if vscode_automation is None:
            from integration.vscode_automation import create_vscode_automation
            vscode_automation = create_vscode_automation()
        self.vscode = vscode_automation
    
    def _clean_code_for_pasting(self, code: str) -> str:
        """Clean code by removing JSON wrappers and formatting artifacts
        
        Handles:
        - JSON wrapper: {"code": "..."}
        - Escaped newlines: \\n -> \n
        - Markdown code blocks
        
        Args:
            code: Raw code that may contain wrappers
        
        Returns:
            Clean, executable code
        """
        import json
        import re
        
        code = code.strip()
        
        # Try to extract from JSON wrapper first
        if code.startswith('{') and '"code"' in code:
            try:
                json_obj = json.loads(code)
                if isinstance(json_obj, dict) and 'code' in json_obj:
                    code = json_obj['code']
            except (json.JSONDecodeError, ValueError):
                pass  # Not valid JSON, continue with raw code
        
        # Handle escaped newlines from JSON
        code = code.replace('\\n', '\n').replace('\\r', '\r').replace('\\"', '"')
        
        # Extract from markdown code blocks if present
        if '```python' in code:
            match = re.search(r'```python\n(.*?)\n```', code, re.DOTALL)
            if match:
                code = match.group(1)
        elif '```' in code:
            match = re.search(r'```\n(.*?)\n```', code, re.DOTALL)
            if match:
                code = match.group(1)
        
        return code.strip()
    
    # ========================================================================
    # PHASE 2: TOOL FUNCTIONS (Gemini-callable)
    # ========================================================================
    
    def tool_tts_speak(self, text: str):
        """Respond verbally to user request"""
        print(f"Sunny: {text}")
        self.voice_handler.speak(text)
        self.context.add_to_history('assistant', text)
    
    def tool_extract_code(self, section: str = ""):
        """Extract existing code from paper"""
        screenshot = self.screen_monitor.get_current_screenshot()
        if not screenshot:
            msg = "Could not extract code: no screenshot available"
            self.tool_tts_speak(msg)
            return msg
        
        code = self.paper_analyzer.extract_code_from_screen(screenshot)
        if code:
            print(f"[OK] Extracted {len(code)} characters of code")
            result = f"Extracted code (preview): {code[:200]}..."
            self.tool_tts_speak(result)
            return result
        else:
            msg = "No code found in current view"
            self.tool_tts_speak(msg)
            return msg
    
    def tool_run_experiment(self, code: str, figure_ref: str = ""):
        """Execute code in Gemini sandbox (isolated, safe execution)
        
        USE THIS when: User wants to verify code works, test methodology, confirm claims
        Keywords: "verify", "test", "check", "confirm", "replicate"
        
        Executes in background using Gemini's code_execution tool. Results returned as text.
        """
        # Clean code before executing
        code = self._clean_code_for_pasting(code)
        
        context = self.context.get_context()
        exp_id = self.code_executor.replicate_experiment(
            code=code,
            paper_id=context['paper_id'] or "unknown",
            figure_reference=figure_ref
        )
        print(f" Started experiment: {exp_id}")
        return f"Experiment {exp_id} started in background"
    
    def tool_remember_paper(self, title: str, details: str):
        """Persist paper metadata and findings"""
        self.context.update_title(title)
        self.context.add_memory(details)
        print(f"[OK] Remembered: {title}")
        return f"Stored paper context: {title}"
    
    def tool_verify_claim(self, claim: str):
        """Search research database for claim"""
        context = self.context.get_context()
        print(f" Verifying claim: {claim}")
        task_id = self.research_agent.verify_claim(
            claim, 
            context['paper_id']
        )
        return f"Started verification task {task_id}"
    
    def tool_analyze_section(self, section_name: str):
        """Analyze a specific paper section with depth
        
        Extracts and analyzes the requested section from the screenshot,
        providing summary, key claims, methodology if applicable, and findings.
        
        Args:
            section_name: Section to analyze (e.g., "3.2", "Introduction", "Methods")
        
        Returns:
            Analysis summary with key points
        """
        screenshot = self.screen_monitor.get_current_screenshot()
        if not screenshot:
            msg = "Could not analyze: no screenshot available"
            self.tool_tts_speak(msg)
            return msg
        
        # Check quota before making API call
        can_call, reason = self.quota_manager.can_call_pro()
        if not can_call:
            msg = f"Cannot analyze: {reason}"
            self.tool_tts_speak(msg)
            return msg
        
        try:
            # Build section-specific analysis prompt
            analyze_prompt = f"""Analyze the section '{section_name}' from this research paper.

Extract and provide in JSON format:
{{
    "section": "{section_name}",
    "title": "Section title if visible",
    "summary": "Thorough 3-4 sentence summary of this section's content",
    "key_claims": ["Important claim 1", "claim 2", "claim 3"],
    "methodology": "If this is methodology section, brief description of methods",
    "findings": "If this is results section, key findings and metrics",
    "equations_formulas": ["Any important formulas or equations in this section"],
    "technical_content": "Brief explanation of technical concepts introduced",
    "connection_to_whole": "How this section relates to the overall paper",
    "thought_process": "Your detailed analysis reasoning"
}}

Provide a thorough, easy-to-understand analysis suitable for someone learning about this topic.
Focus ONLY on the content visible in section {section_name}."""
            
            response = self.paper_analyzer.pro_model.generate_content([analyze_prompt, screenshot])
            self.quota_manager.record_pro_call()
            
            # Clean and parse JSON response
            import json
            import re
            
            response_text = response.text.strip()
            
            # Try to extract JSON from markdown code blocks if present
            if '```json' in response_text:
                json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
            elif '```' in response_text:
                json_match = re.search(r'```\n(.*?)\n```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
            
            # Clean control characters while preserving valid JSON
            response_text = response_text.encode('utf-8', 'ignore').decode('utf-8')
            
            # Try to parse JSON
            analysis = json.loads(response_text)
            
            # Build comprehensive response
            section_title = analysis.get('title', section_name)
            summary = analysis.get('summary', 'Analysis complete')
            
            # Store in context for reference
            self.context.current_context['last_analysis'] = {
                'section': section_name,
                'title': section_title,
                'summary': summary,
                'full_analysis': analysis
            }
            
            # Build verbose response for speaking
            response_text = f"{section_title}: {summary}"
            
            # Add key claims if present
            if analysis.get('key_claims'):
                response_text += f" Key claims: {', '.join(analysis['key_claims'][:2])}"
            
            # Speak the analysis to user
            print(f"[Analyzed] {section_name}: {summary[:100]}...")
            self.tool_tts_speak(response_text)
            
            return response_text
            
        except json.JSONDecodeError as e:
            # Fallback: if JSON parsing fails, try to extract text content from response
            print(f"[Warning] JSON parsing failed for section {section_name}: {e}")
            try:
                # Try to at least get a summary from the raw text
                raw_response = response.text[:500] if len(response.text) > 500 else response.text
                summary_text = raw_response.replace('\n', ' ').replace('\r', '').strip()
                
                # Speak what we could extract
                self.tool_tts_speak(f"Analysis of {section_name}: {summary_text}")
                print(f"[Analyzed] {section_name}: Partial analysis extracted")
                
                return f"{section_name}: {summary_text}..."
            except:
                error_msg = f"Could not parse analysis for section {section_name}. JSON format error."
                print(f"[Error] {error_msg}")
                self.tool_tts_speak(f"Error analyzing section {section_name}")
                return error_msg
        except Exception as e:
            error_msg = f"Error analyzing section {section_name}: {str(e)}"
            print(f"[Error] {error_msg}")
            self.tool_tts_speak(f"Could not analyze section {section_name}")
            import traceback
            traceback.print_exc()
            return error_msg
    
    def tool_write_code_from_methodology(self, section_name: str = "methodology"):
        """Generate executable code from methodology
        
        Args:
            section_name: Section to read (methodology/methods/algorithm)
        
        Returns:
            Generated Python code as string
        """
        screenshot = self.screen_monitor.get_current_screenshot()
        if not screenshot:
            msg = "Could not read paper: no screenshot available"
            self.tool_tts_speak(msg)
            return msg
        
        # Get the text from the methodology section
        prompt = f"""Extract and describe the {section_name} from this research paper.
        
        Provide:
        1. Key algorithms or procedures described
        2. Parameters and variables mentioned
        3. Step-by-step process
        4. Any mathematical formulas or equations
        
        Keep the description clear and structured."""
        
        try:
            import json
            response = self.paper_analyzer.pro_model.generate_content([prompt, screenshot])
            methodology_text = response.text
            
            # Now ask Gemini to generate code based on the methodology
            code_prompt = f"""Based on this research methodology:

{methodology_text}

Generate complete, executable Python code that implements this methodology.
Include:
- All necessary imports (numpy, scipy, pandas, etc.)
- Function definitions for key algorithms
- Clear variable names and comments
- Example usage or main execution block
- Print statements to show progress and results

Return ONLY the Python code, no explanations."""
            
            code_response = self.paper_analyzer.pro_model.generate_content(code_prompt)
            generated_code = code_response.text
            
            # Clean code (handles JSON wrappers, escaped chars, markdown blocks)
            generated_code = self._clean_code_for_pasting(generated_code)
            
            # Store in context for user to review/run
            self.context.current_context['generated_code'] = generated_code
            
            print(f"  Generated code from {section_name} section")
            result = f"Generated {len(generated_code)} characters of code. Ready to execute. Code:\n\n{generated_code[:500]}..."
            self.tool_tts_speak(result)
            return result
            
        except Exception as e:
            error_msg = f"Could not generate code: {str(e)}"
            self.tool_tts_speak(error_msg)
            return error_msg
    
    def tool_run_experiment_with_output(self, code: str = "", figure_ref: str = ""):
        """Execute code and stream output
        
        Args:
            code: Python code to execute
            figure_ref: Reference to figure in paper
        
        Returns:
            Execution summary with results
        """
        context = self.context.get_context()
        
        # Use provided code or fall back to generated code in context
        if not code or code.strip() == "":
            code = context.get('generated_code', '')
            if not code:
                return "No code provided and no generated code in context. Please provide code or generate it first."
        
        # Clean code (remove JSON wrappers, escaped chars, etc.)
        code = self._clean_code_for_pasting(code)
        
        # Define callback to stream output to user
        def on_output(line: str):
            """Called for each line of output"""
            print(f"  → {line}")
            # Optionally speak progress for long-running tasks
            # self.voice_handler.speak(line)  # Uncomment if too verbose
        
        # Execute with real-time output
        result = self.code_executor.execute_with_realtime_output(
            code=code,
            paper_id=context['paper_id'] or "unknown",
            figure_reference=figure_ref,
            on_output=on_output
        )
        
        print(f" Experiment {result['experiment_id']}: {result['status'].upper()}")
        
        if result['status'] == 'success':
            return f"Execution completed successfully. Output:\n{result.get('output', '')[:500]}"
        else:
            return f"Execution failed: {result.get('error', 'Unknown error')}"
    
    def tool_create_file_and_write_code(self, filename: str, code: str, language: str = "python"):
        """Create a new file in VS Code and write code to it
        
        Args:
            filename: Name of file to create (e.g., 'experiment.py')
            code: Code to write to file
            language: Programming language (python, javascript, etc)
        
        Returns:
            Status message with file path
        """
        try:
            # Clean code before writing
            code = self._clean_code_for_pasting(code)
            
            print(f"Creating file: {filename}")
            filepath = self.vscode.create_file(filename)
            
            print(f"Writing code to {filename}")
            self.vscode.write_code(code)
            
            print(f"Formatting code")
            self.vscode.format_code()
            
            self.voice_handler.speak(f"Created {filename} in VS Code ready to run")
            self.context.add_to_history('assistant', f"Created file {filename} with code")
            
            return f"File created and opened in VS Code: {filepath}"
        
        except Exception as e:
            error_msg = f"Error creating file: {str(e)}"
            print(error_msg)
            self.voice_handler.speak(f"Error creating file: {e}")
            return error_msg
    
    def tool_run_experiment_locally(self, code: str, filename: str = None):
        """Run Python code in VS Code terminal (interactive, visible execution)
        
        USE THIS when: User wants to see/edit code, create file for later use, interactive development
        Keywords: "show", "create", "open in VS Code", "I want to edit", "create file"
        
        Creates file in workspace, opens in VS Code, executes in terminal. 
        User can see, edit, and rerun code. More interactive than sandbox.
        
        Args:
            code: Python code to execute
            filename: Optional filename (auto-generated if not provided)
        
        Returns:
            Status message with experiment info
        """
        try:
            # Clean code before writing
            code = self._clean_code_for_pasting(code)
            
            if not filename:
                import uuid
                filename = f"exp_{str(uuid.uuid4())[:8]}.py"
            
            # Create file with code
            print(f"Creating experiment file: {filename}")
            filepath = self.vscode.create_file(filename)
            
            print(f"Writing code to {filename}")
            self.vscode.write_code(code)
            
            # Run in terminal
            print(f"Running {filename}")
            self.vscode.run_command_in_terminal(f"python {filename}")
            
            self.voice_handler.speak(f"Running {filename} check terminal for output")
            self.context.add_to_history('assistant', f"Started experiment {filename}")
            
            return f"Experiment started in terminal: {filename}"
        
        except Exception as e:
            error_msg = f"Error running experiment: {str(e)}"
            print(error_msg)
            self.voice_handler.speak(f"Error running experiment: {e}")
            return error_msg
    
    def tool_write_to_active_file(self, code: str):
        """Write code to the currently active/open file in VS Code
        
        USE THIS when: User says "I already have this file open. can you write the code here"
        
        Writes code to the currently focused editor by:
        1. Copying code to clipboard
        2. Selecting all content in active editor (Ctrl+A)
        3. Pasting code to replace it (Ctrl+V)
        4. Formatting and saving the file
        
        Args:
            code: Python code to write to active file
        
        Returns:
            Status message
        """
        try:
            import pyperclip
            import time
            
            # Clean code before writing
            code = self._clean_code_for_pasting(code)
            
            print(f"Writing code to active file")
            
            # Copy code to clipboard
            pyperclip.copy(code)
            time.sleep(0.3)
            
            # Select all content in active editor
            from integration.vscode_automation import _press_ctrl_hotkey
            _press_ctrl_hotkey('a')
            time.sleep(0.2)
            
            # Paste code (replaces selected content)
            _press_ctrl_hotkey('v')
            time.sleep(1)
            
            # Format and save
            self.vscode.format_code()
            self.vscode.save_file()
            
            msg = "Code written to active file successfully"
            self.voice_handler.speak(msg)
            self.context.add_to_history('assistant', msg)
            
            return msg
        
        except Exception as e:
            error_msg = f"Error writing to active file: {str(e)}"
            print(error_msg)
            self.voice_handler.speak(f"Error writing to active file: {e}")
            return error_msg
    
    def tool_code_pseudocode(self, pseudocode_section: str = "pseudocode"):
        """Convert pseudocode from paper into actual executable Python code
        
        CRITICAL: This generates ACTUAL CODE, not just the pseudocode text.
        Converts the pseudocode section into runnable Python implementation
        and pastes it to the active file.
        
        Args:
            pseudocode_section: Section name containing pseudocode (e.g., 'pseudocode', 'algorithm')
        
        Returns:
            Status message with code implementation details
        """
        try:
            screenshot = self.screen_monitor.get_current_screenshot()
            if not screenshot:
                msg = "Cannot see pseudocode on screen. Please display the pseudocode section."
                self.tool_tts_speak(msg)
                return msg
            
            # Step 1: Extract pseudocode from screenshot
            print(f"Extracting {pseudocode_section}...")
            extract_prompt = f"""Find and extract the {pseudocode_section} from this research paper.
            Return ONLY the exact pseudocode text, preserving all formatting, indentation, and structure."""
            
            response = self.paper_analyzer.pro_model.generate_content([extract_prompt, screenshot])
            self.quota_manager.record_pro_call()
            pseudocode_text = response.text.strip()
            
            if not pseudocode_text or "not found" in pseudocode_text.lower():
                msg = f"Could not find {pseudocode_section} in the current view"
                self.tool_tts_speak(msg)
                return msg
            
            # Step 2: Convert to actual Python implementation
            print(f"Converting to executable Python...")
            self.tool_tts_speak(f"I'm coding {pseudocode_section} into Python now")
            
            convert_prompt = f"""You are an expert Python programmer. Convert this pseudocode into ACTUAL, EXECUTABLE Python code.
            
CRITICAL RULES:
- Generate completely functional Python that runs without errors
- Implement all algorithms, loops, conditions, and operations literally from the pseudocode
- Use numpy/scipy/pandas/torch/sklearn as needed for numerical and ML operations
- Include proper imports at the top
- Add example usage in a main block or show how to use the functions
- Add comments explaining non-obvious or complex steps
- Make sure code is properly indented and syntactically correct
- Return ONLY the complete Python code in a markdown code block

Pseudocode to implement:
```
{pseudocode_text}
```

Return ONLY complete, ready-to-run Python code:"""
            
            code_response = self.paper_analyzer.pro_model.generate_content(convert_prompt)
            self.quota_manager.record_pro_call()
            actual_code = code_response.text.strip()
            
            # Clean code (handles JSON wrappers, escaped chars, markdown blocks)
            actual_code = self._clean_code_for_pasting(actual_code)
            
            # Step 3: Paste to active file
            print(f"Pasting {len(actual_code)} chars of Python code to active file...")
            import pyperclip
            import time
            
            pyperclip.copy(actual_code)
            time.sleep(0.3)
            
            # Select all content in active editor
            from integration.vscode_automation import _press_ctrl_hotkey
            _press_ctrl_hotkey('a')
            time.sleep(0.2)
            
            # Paste code (replaces selected content)
            _press_ctrl_hotkey('v')
            time.sleep(1)
            
            # Format and save
            self.vscode.format_code()
            self.vscode.save_file()
            
            msg = f"Implemented {pseudocode_section} as executable Python code in your file"
            self.tool_tts_speak(msg)
            self.context.add_to_history('assistant', msg)
            
            return f"Pseudocode converted to {len(actual_code)} characters of actual Python code and pasted to active file"
            
        except Exception as e:
            error_msg = f"Error converting pseudocode: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            self.tool_tts_speak(f"Error: {e}")
            return error_msg
    
    def tool_show_experiment_outputs(self, limit: int = 3):
        """Show recent sandbox experiment outputs in VS Code
        
        Retrieve the last N sandbox experiments and display outputs in a file.
        User can then review what the code produced without running it again.
        
        Args:
            limit: Number of recent outputs to show (default 3)
        
        Returns:
            Status message
        """
        try:
            recent_outputs = self.code_executor.get_recent_outputs(limit=limit)
            
            if not recent_outputs:
                msg = "No sandbox experiment outputs found yet. Run experiments with 'verify' to create outputs."
                self.voice_handler.speak(msg)
                return msg
            
            # Create summary file with all recent outputs
            summary_file = "sandbox_experiment_summary.txt"
            filepath = self.vscode.get_file_path(summary_file)
            
            with open(filepath, 'w') as f:
                f.write("SANDBOX EXPERIMENT OUTPUTS\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Last {limit} experiments displayed below\n\n")
                
                for filename, full_path in recent_outputs:
                    f.write(f"\nFile: {filename}\n")
                    f.write("-" * 60 + "\n")
                    try:
                        with open(full_path, 'r') as output_file:
                            f.write(output_file.read())
                    except Exception as e:
                        f.write(f"Error reading file: {e}\n")
                    f.write("\n" + "=" * 60 + "\n")
            
            # Open in VS Code
            import subprocess
            subprocess.Popen(['code', filepath])
            
            self.voice_handler.speak(f"Opening {limit} recent sandbox outputs in VS Code")
            self.context.add_to_history('assistant', f"Displayed {limit} recent experiment outputs")
            
            return f"Displayed {len(recent_outputs)} recent outputs in {summary_file}"
        
        except Exception as e:
            error_msg = f"Error showing outputs: {str(e)}"
            print(error_msg)
            self.voice_handler.speak(f"Error showing outputs: {e}")
            return error_msg
    
    def tool_show_specific_output(self, experiment_id: str):
        """Show output for a specific sandbox experiment
        
        Retrieves and displays the output from a specific experiment run.
        
        Args:
            experiment_id: ID of the experiment to display
        
        Returns:
            Status message with output content
        """
        try:
            output_path = self.code_executor.get_output_file(experiment_id)
            
            if not output_path:
                msg = f"No output found for experiment {experiment_id}"
                self.voice_handler.speak(msg)
                return msg
            
            # Open in VS Code
            import subprocess
            subprocess.Popen(['code', output_path])
            
            self.voice_handler.speak(f"Opening output for experiment {experiment_id}")
            self.context.add_to_history('assistant', f"Displayed output for experiment {experiment_id}")
            
            return f"Opened output file for experiment {experiment_id}"
        
        except Exception as e:
            error_msg = f"Error showing output: {str(e)}"
            print(error_msg)
            self.voice_handler.speak(f"Error showing output: {e}")
            return error_msg
    
    def get_tool_definitions(self):
        """Get tool definitions for Gemini function calling using proper protos objects"""
        return [
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_tts_speak",
                    description="Respond verbally to user request",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "text": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Text to speak aloud"
                            )
                        },
                        required=["text"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_extract_code",
                    description="Extract existing code from paper",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "section": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Section name to extract code from"
                            )
                        }
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_run_experiment",
                    description="Execute code in Gemini sandbox (isolated safe execution)",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "code": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Python code to execute"
                            ),
                            "figure_ref": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Reference to figure in paper"
                            )
                        },
                        required=["code"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_remember_paper",
                    description="Persist paper metadata and findings",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "title": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Paper title"
                            ),
                            "details": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Details to remember about paper"
                            )
                        },
                        required=["title", "details"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_analyze_section",
                    description="Analyze and summarize a paper section",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "section_name": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Section to analyze"
                            )
                        },
                        required=["section_name"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_verify_claim",
                    description="Verify a research claim using deep research",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "claim": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Claim to verify"
                            )
                        },
                        required=["claim"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_write_code_from_methodology",
                    description="Generate executable Python code from paper methodology",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "section_name": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Section to read (methodology/methods/algorithm)"
                            )
                        }
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_run_experiment_with_output",
                    description="Execute code and stream realtime output",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "code": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Python code to execute"
                            ),
                            "figure_ref": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Reference to figure in paper"
                            )
                        },
                        required=["code"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_create_file_and_write_code",
                    description="Create a new file in VS Code and write code to it",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "filename": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Name of file to create (e.g., 'experiment.py')"
                            ),
                            "code": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Code to write to file"
                            ),
                            "language": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Programming language (python, javascript, etc)"
                            )
                        },
                        required=["filename", "code"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_run_experiment_locally",
                    description="Run Python code in VS Code terminal with visible execution",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "code": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Python code to execute"
                            ),
                            "filename": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Optional filename for the experiment"
                            )
                        },
                        required=["code"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_write_to_active_file",
                    description="Write code to currently open/active file in VS Code",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "code": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Python code to write to active file"
                            )
                        },
                        required=["code"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_show_experiment_outputs",
                    description="Show recent sandbox experiment outputs in VS Code",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "limit": protos.Schema(
                                type_=protos.Type.INTEGER,
                                description="Number of recent outputs to show"
                            )
                        }
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_show_specific_output",
                    description="Show output from a specific sandbox experiment",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "experiment_id": protos.Schema(
                                type_=protos.Type.STRING,
                                description="ID of the experiment to display"
                            )
                        },
                        required=["experiment_id"]
                    )
                )
            ]),
            protos.Tool(function_declarations=[
                protos.FunctionDeclaration(
                    name="tool_code_pseudocode",
                    description="Convert pseudocode from paper into actual executable Python code",
                    parameters=protos.Schema(
                        type_=protos.Type.OBJECT,
                        properties={
                            "pseudocode_section": protos.Schema(
                                type_=protos.Type.STRING,
                                description="Section name containing pseudocode (e.g., 'pseudocode', 'algorithm')"
                            )
                        }
                    )
                )
            ])
        ]
    
    def get_tool_summary(self) -> str:
        """Get concise summary of available tools for prompting
        
        Returns:
            Formatted string of available tools with 7-word descriptions
        """
        tools_info = [
            "• tts_speak: Respond verbally to user request",
            "• extract_code: Extract existing code from paper",
            "• run_experiment: Execute code in background thread",
            "• write_code_from_methodology: Generate executable code from methodology",
            "• run_experiment_with_output: Execute code and stream output",
            "• remember_paper: Persist paper metadata and findings",
            "• verify_claim: Search research database for claim",
            "• analyze_section: Summarize paper section with depth",
            "• create_file_and_write_code: Create file in VS Code with code",
            "• run_experiment_locally: Run code in VS Code terminal",
            "• write_to_active_file: Write code to currently open file",
            "• code_pseudocode: Convert paper pseudocode to Python code",
            "• show_experiment_outputs: Display recent sandbox outputs in editor",
            "• show_specific_output: Display output from specific experiment"
        ]
        return "Available Tools:\n" + "\n".join(tools_info)
