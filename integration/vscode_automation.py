"""
VS Code Automation Module
Controls VS Code for file creation and editing using keyboard automation
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional


def _press_ctrl_hotkey(key: str):
    """Send Ctrl+Key hotkey"""
    import keyboard
    keyboard.press_and_release(f'ctrl+{key}')


def _press_alt_hotkey(key: str):
    """Send Alt+Key hotkey"""
    import keyboard
    keyboard.press_and_release(f'alt+{key}')


def _type_string(text: str):
    """Type text string using keyboard"""
    import keyboard
    # Handle special characters
    text = text.replace('\\n', '\n')
    text = text.replace('\\t', '\t')
    keyboard.write(text, delay=0.01)


def _press_key(key: str):
    """Press a single key"""
    import keyboard
    keyboard.press_and_release(key)


class VSCodeAutomation:
    """Automates VS Code file creation and code writing"""
    
    def __init__(self, workspace_path: Optional[str] = None):
        """Initialize VS Code automation
        
        Args:
            workspace_path: Path to workspace directory. Defaults to ~/Sunny_Experiments
        """
        if workspace_path is None:
            workspace_path = str(Path.home() / "Sunny_Experiments")
        
        self.workspace_path = workspace_path
        self._ensure_workspace()
    
    def _ensure_workspace(self):
        """Create workspace directory if it doesn't exist"""
        Path(self.workspace_path).mkdir(parents=True, exist_ok=True)
    
    def create_file(self, filename: str) -> str:
        """Create a new file and open it in VS Code
        
        Args:
            filename: Name of file to create
        
        Returns:
            Full path to created file
        """
        filepath = os.path.join(self.workspace_path, filename)
        
        # Create empty file
        Path(filepath).touch()
        
        # Open in VS Code
        try:
            subprocess.Popen(['code', filepath])
            time.sleep(2)  # Wait for VS Code to open and focus
        except FileNotFoundError:
            print("Error: VS Code 'code' command not found. Ensure VS Code is installed and added to PATH.")
        
        return filepath
    
    def write_code(self, code: str):
        """Write code to the currently active editor in VS Code
        
        Uses clipboard paste for reliability and speed
        
        Args:
            code: Code string to write
        """
        try:
            import pyperclip
            
            # Copy code to clipboard
            pyperclip.copy(code)
            time.sleep(0.3)
            
            # Paste into editor
            _press_ctrl_hotkey('v')
            time.sleep(1)
            
            # Save file
            self.save_file()
        
        except ImportError as e:
            print(f"Error: Missing dependency for clipboard operations: {e}")
            print("Install with: pip install pyperclip")
    
    def save_file(self):
        """Save current file using Ctrl+S"""
        try:
            _press_ctrl_hotkey('s')
            time.sleep(0.5)
        except Exception as e:
            print(f"Error saving file: {e}")
    
    def format_code(self):
        """Format code using Shift+Alt+F"""
        try:
            import keyboard
            keyboard.press_and_release('shift+alt+f')
            time.sleep(0.5)
        except Exception as e:
            print(f"Warning: Could not format code: {e}")
    
    def open_terminal(self):
        """Open integrated terminal in VS Code using Ctrl+grave"""
        try:
            _press_ctrl_hotkey('grave')
            time.sleep(1)
        except Exception as e:
            print(f"Error opening terminal: {e}")
    
    def run_command_in_terminal(self, command: str):
        """Run a command in VS Code's integrated terminal
        
        Args:
            command: Command to execute (e.g., 'python script.py')
        """
        try:
            self.open_terminal()
            _type_string(command)
            _press_key('enter')
            time.sleep(2)
        
        except Exception as e:
            print(f"Error running command: {e}")
    
    def list_workspace_files(self) -> list:
        """List all files in workspace directory
        
        Returns:
            List of filenames
        """
        try:
            files = [
                f for f in os.listdir(self.workspace_path)
                if os.path.isfile(os.path.join(self.workspace_path, f))
            ]
            return files
        except Exception as e:
            print(f"Error listing files: {e}")
            return []
    
    def get_file_path(self, filename: str) -> str:
        """Get full path for a file in workspace
        
        Args:
            filename: Name of file
        
        Returns:
            Full path to file
        """
        return os.path.join(self.workspace_path, filename)


def create_vscode_automation(workspace_path: Optional[str] = None) -> VSCodeAutomation:
    """Factory function to create VS Code automation instance
    
    Args:
        workspace_path: Optional workspace path
    
    Returns:
        VSCodeAutomation instance
    """
    return VSCodeAutomation(workspace_path)
