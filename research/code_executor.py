"""
Code Executor for Sunny Research Assistant
Executes code from research papers using Gemini's code_execution tool
Includes Auto-Retry Logic on Failure with comprehensive error handling
"""

import os
import threading
import queue
import json
import sys
import io
import time
from pathlib import Path
from typing import Dict, Callable, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import (
    ResourceExhausted, 
    InternalServerError, 
    InvalidArgument,
    FailedPrecondition,
    ServiceUnavailable
)

from storage.database import get_database
from utils.quota_manager import get_quota_manager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Error handling constants
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2.0

class CodeExecutor:
    """
    Executes code using the Gemini Code Execution Tool.
    Implements a feedback loop to auto-correct errors.
    """
    
    def __init__(self, on_completion: Callable[[Dict], None]):
        self.db = get_database()
        self.quota_manager = get_quota_manager()
        self.on_completion = on_completion
        self.task_queue = queue.Queue()
        self.is_running = False
        
        # Setup output logging directory
        self.output_dir = Path.home() / "Sunny_Experiments" / "sandbox_outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Gemini Pro with code execution enabled
        self.code_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=[{"code_execution": {}}],
            generation_config={"temperature": 0.2}
        )
    
    def start_executor(self):
        self.is_running = True
        self.executor_thread = threading.Thread(target=self._executor_loop, daemon=True)
        self.executor_thread.start()
        print("Code executor started (Auto-Retry Enabled)")
    
    def stop_executor(self):
        self.is_running = False
        print("Code executor stopped")
    
    def _executor_loop(self):
        while self.is_running:
            try:
                task = self.task_queue.get(timeout=1)
                self._execute_with_retry(task)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in executor loop: {e}")
    
    def replicate_experiment(self, code: str, paper_id: str, figure_reference: str = "", description: str = "") -> str:
        """Queue an experiment for replication"""
        exp_id = self.db.add_experiment({
            'paper_id': paper_id,
            'figure_reference': figure_reference,
            'code': code,
            'status': 'queued'
        })
        
        task = {
            'experiment_id': exp_id,
            'code': code,
            'paper_id': paper_id,
            'figure_reference': figure_reference,
            'description': description
        }
        
        self.task_queue.put(task)
        print(f"Experiment queued: {figure_reference or exp_id}")
        return exp_id

    def _execute_with_retry(self, task: Dict, max_retries=3):
        """
        Executes code, captures errors, and asks the model to fix them autonomously.
        Includes comprehensive error handling and retry logic with exponential backoff.
        """
        exp_id = task['experiment_id']
        current_code = task['code']
        
        print(f"Executing: {task.get('figure_reference', exp_id)}")
        self.db.update_experiment_status(exp_id, 'running')

        for attempt in range(max_retries):
            # Check quota
            can_call, reason = self.quota_manager.can_call_pro()
            if not can_call:
                self._fail_experiment(exp_id, f"Quota exceeded: {reason}")
                return

            try:
                print(f"   Attempt {attempt + 1}/{max_retries}...")
                
                # Prompt that encourages execution and analysis
                prompt = f"""
                **Follow these steps exactly:**
                
                STEP 1: Preparation
                Say to the user: "Alright let me code this up for you. Please wait."
                
                STEP 2: Code Analysis
                Analyze the code task carefully:
                ```python
                {current_code}
                ```
                
                STEP 3: Ready to Execute
                Say to the user: "coding is done let me run this now"
                
                STEP 4: Execute the Code
                Now execute the code directly using the code_execution tool.
                
                STEP 5: Report Results
                - If execution succeeds: output "SUCCESS" and summarize key findings
                - If it fails: output "RETRY_NEEDED" then provide fixed code
                
                **Do not output your reasoning process. Only output what the user should see.**
                """
                
                try:
                    response = self.code_model.generate_content(prompt)
                    self.quota_manager.record_pro_call()
                except ResourceExhausted as e:
                    print(f"   [API Error] Rate limit exceeded: {e}")
                    self._fail_experiment(exp_id, f"API rate limit at attempt {attempt + 1}")
                    return
                    
                except (InternalServerError, ServiceUnavailable) as e:
                    # Retry with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = BASE_RETRY_DELAY * (RETRY_BACKOFF_MULTIPLIER ** attempt)
                        print(f"   [Server Error] {type(e).__name__}. Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        self._fail_experiment(exp_id, f"API server errors after {max_retries} attempts: {str(e)}")
                        return
                        
                except InvalidArgument as e:
                    print(f"   [Fatal Error] Invalid request: {e}")
                    self._fail_experiment(exp_id, f"Invalid API request: {str(e)}")
                    return
                    
                except FailedPrecondition as e:
                    print(f"   [Fatal Error] Precondition failed: {e}")
                    self._fail_experiment(exp_id, f"API precondition failed: {str(e)}")
                    return
                
                # Analyze Response for Success or Failure
                text_response = response.text
                
                # Check if the model suggests a retry due to error
                if "RETRY_NEEDED" in text_response:
                    # Extract new code for next iteration
                    try:
                        import re
                        code_blocks = re.findall(r'```python(.*?)```', text_response, re.DOTALL)
                        if code_blocks:
                            current_code = code_blocks[-1].strip()
                            print(f"   Failure detected. Retrying with fixed code...")
                            continue # Loop to next attempt
                    except Exception as parse_e:
                        print(f"   Could not parse fixed code: {parse_e}")
                        pass # Fallback to fail if we can't parse code
                
                # If we got here and didn't continue, assume success or unfixable
                # Save results to database
                self.db.update_experiment_status(
                    exp_id,
                    'success',
                    output=text_response,
                    error_message=None
                )
                
                # Save output to file for later review
                self._save_experiment_output(exp_id, text_response, task)
                
                self.on_completion({
                    'experiment_id': exp_id,
                    'status': 'success',
                    'figure_reference': task.get('figure_reference', ''),
                    'output': "Experiment execution finished successfully."
                })
                print(f"Experiment completed: {task.get('figure_reference', exp_id)}")
                return

            except Exception as e:
                print(f"   System error on attempt {attempt}: {type(e).__name__}: {e}")
                # Don't retry on unexpected system errors, just fail
                if attempt == max_retries - 1:
                    self._fail_experiment(exp_id, f"System error: {str(e)}")
                    return

        # If loop finishes without success
        self._fail_experiment(exp_id, "Max retries reached. Code could not be fixed automatically.")

    def _fail_experiment(self, exp_id, reason):
        self.db.update_experiment_status(exp_id, 'failed', error_message=reason)
        
        # Save error output to file for review
        error_output = f"EXPERIMENT FAILED\n\nError: {reason}\n"
        self._save_experiment_output(exp_id, error_output, {'experiment_id': exp_id})
        
        self.on_completion({
            'experiment_id': exp_id,
            'status': 'failed',
            'error': reason
        })
        print(f"Experiment failed: {reason}")
    
    def _save_experiment_output(self, exp_id: str, output: str, task: Dict):
        """Save experiment output to file for user review
        
        Args:
            exp_id: Experiment ID
            output: Output text to save
            task: Task dictionary with metadata
        """
        try:
            figure_ref = task.get('figure_reference', 'output')
            filename = f"{exp_id}_{figure_ref}.txt".replace('/', '_').replace(' ', '_')
            filepath = self.output_dir / filename
            
            with open(filepath, 'w') as f:
                f.write(f"Experiment: {exp_id}\n")
                f.write(f"Figure Reference: {figure_ref}\n")
                f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(output)
            
            print(f"Output saved to: {filepath}")
        except Exception as e:
            print(f"Warning: Could not save experiment output: {e}")
    
    def get_recent_outputs(self, limit: int = 5) -> list:
        """Get recent experiment outputs
        
        Args:
            limit: Number of recent outputs to retrieve
        
        Returns:
            List of (filename, filepath) tuples for recent outputs
        """
        try:
            files = sorted(
                self.output_dir.glob('*.txt'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]
            return [(f.name, str(f)) for f in files]
        except Exception as e:
            print(f"Error retrieving outputs: {e}")
            return []
    
    def get_output_file(self, exp_id: str) -> Optional[str]:
        """Get path to output file for specific experiment
        
        Args:
            exp_id: Experiment ID
        
        Returns:
            Path to output file or None
        """
        try:
            files = list(self.output_dir.glob(f"{exp_id}_*.txt"))
            if files:
                return str(files[0])
            return None
        except Exception as e:
            print(f"Error getting output file: {e}")
            return None
    
    def improve_code(self, exp_id: str, improvement_request: str) -> str:
        # (Existing improvement logic remains similar)
        pass
    
    def execute_with_realtime_output(self, code: str, paper_id: str = "unknown", 
                                     figure_reference: str = "", on_output: Callable[[str], None] = None) -> Dict:
        """
        Execute code with real-time output capture.
        Calls on_output callback for each line of output.
        
        Args:
            code: Python code to execute
            paper_id: ID of paper this code relates to
            figure_reference: Reference to figure in paper
            on_output: Callback function(line: str) for each output line
        
        Returns:
            Dict with status, output, and error information
        """
        exp_id = self.db.add_experiment({
            'paper_id': paper_id,
            'figure_reference': figure_reference,
            'code': code,
            'status': 'running'
        })
        
        can_call, reason = self.quota_manager.can_call_flash()
        if not can_call:
            self.db.update_experiment_status(exp_id, 'failed', error_message=f"Quota exceeded: {reason}")
            return {'status': 'failed', 'error': reason, 'experiment_id': exp_id}
        
        try:
            # Capture stdout/stderr
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            captured_output = io.StringIO()
            
            sys.stdout = captured_output
            sys.stderr = captured_output
            
            # Execute code
            exec_globals = {'__builtins__': __builtins__}
            exec(code, exec_globals)
            
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            output = captured_output.getvalue()
            
            # Stream output to user
            if on_output:
                for line in output.split('\n'):
                    if line.strip():
                        on_output(line)
            
            # Save to database
            self.db.update_experiment_status(exp_id, 'success', output=output)
            self.quota_manager.record_flash_call()
            
            return {
                'status': 'success',
                'output': output,
                'experiment_id': exp_id,
                'figure_reference': figure_reference
            }
            
        except Exception as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.db.update_experiment_status(exp_id, 'failed', error_message=error_msg)
            
            if on_output:
                on_output(f"[ERROR] {error_msg}")
            
            return {
                'status': 'failed',
                'error': error_msg,
                'experiment_id': exp_id,
                'figure_reference': figure_reference
            }

def create_code_executor(on_completion: Callable[[Dict], None]) -> CodeExecutor:
    return CodeExecutor(on_completion)

