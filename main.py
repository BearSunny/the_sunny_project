"""
Sunny - Research Assistant
Main application loop orchestrating all components
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import google.generativeai as genai

from core.voice_handler import create_voice_handler
from core.screen_monitor import create_screen_monitor
from research.paper_analyzer import create_paper_analyzer
from research.code_executor import create_code_executor
from research.research_agent import create_research_agent
from research.vision_engine import VisionEngine
from storage.database import get_database
from storage.context_manager import get_context_manager
from utils.quota_manager import get_quota_manager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class SunnyAssistant:
    """
    Main Sunny Research Assistant
    Orchestrates all components: voice, vision, database, experimentation
    """
    
    def __init__(self):
        """Initialize Sunny"""
        print("=" * 60)
        print("SUNNY - Research Assistant")
        print("=" * 60)
        
        self.db = get_database()
        self.quota_manager = get_quota_manager()
        self.context = get_context_manager()
        self.is_running = False
        self.is_active = False
        self.last_command_time = time.time()
        
        # Initialize components
        print("\nInitializing components...")
        
        self.voice_handler = create_voice_handler(
            on_user_speech=self.handle_user_speech
        )
        
        self.screen_monitor = create_screen_monitor(
            on_context_change=self.handle_context_change
        )
        
        self.paper_analyzer = create_paper_analyzer()
        
        self.code_executor = create_code_executor(
            on_completion=self.handle_experiment_completion
        )
        
        self.research_agent = create_research_agent(
            on_completion=self.handle_research_completion
        )
        
        # Initialize vision engine (Phase 1-3 all in one place)
        self.vision_engine = VisionEngine(
            voice_handler=self.voice_handler,
            screen_monitor=self.screen_monitor,
            paper_analyzer=self.paper_analyzer,
            code_executor=self.code_executor,
            research_agent=self.research_agent
        )
        
        print("All components initialized\n")
    
    def handle_user_speech(self, text: str):
        """Handle user voice input - delegate to vision engine"""
        print(f"\n You: {text}")
        
        # Check if it's a wake phrase to activate the agent
        wake_phrases = ['hey sunny', 'ok sunny', 'sunny', 'hi', 'hey']
        text_lower = text.lower().strip()
        
        # Check for wake phrase
        wake_detected = any(wake in text_lower for wake in wake_phrases)
        
        if wake_detected:
            # Extract command after wake phrase
            for wake in wake_phrases:
                if wake in text_lower:
                    text = text_lower.replace(wake, '').strip()
                    break
            
            # Activate the agent
            self.is_active = True
            self.last_command_time = time.time()
            
            if not text:
                # Just the wake phrase, no command
                self.voice_handler.speak("Yes, I'm listening. What do you need?")
                return
            
            # Process the command that came with the wake phrase
            print(f"Activated! Processing: {text}")
            self.quota_manager.warn_if_high_usage()
            self.vision_engine.screen_aware_respond(text)
            return
        
        # If not a wake phrase, check if agent is currently active
        if not self.is_active:
            print("(Say 'Hey Sunny' to activate me)")
            return
        
        # Agent is active, process command directly
        self.last_command_time = time.time()
        print(f"💬 Processing: {text}")
        self.quota_manager.warn_if_high_usage()
        self.vision_engine.screen_aware_respond(text)
    
    def handle_context_change(self, context: Dict):
        """Handle screen context changes (from screen monitor)"""
        # Context changes are now handled by autonomous perception loop
        # This callback is kept for compatibility but doesn't need to do much
        pass
    
    
    def _show_status(self):
        """Show current status"""
        stats = self.db.get_stats()
        quota = self.quota_manager.get_usage_stats()
        
        print("\n" + "=" * 60)
        print("CURRENT STATUS")
        print(f"Papers analyzed: {stats['total_papers']}")
        print(f"Notes taken: {stats['total_notes']}")
        print(f"Experiments: {stats['successful_experiments']} success, {stats['failed_experiments']} failed, {stats['running_experiments']} running")
        print(f"\n  API Usage (Today):")
        print(f"  Flash: {quota['flash_today']} ({quota['flash_percentage']}%)")
        print(f"  Pro: {quota['pro_today']} ({quota['pro_percentage']}%)")
        print("=" * 60)
        print("\n Say something to start (e.g., 'Hey Sunny, what's this paper about?')")
        print("=" * 60 + "\n")
    
    def stop(self):
        """Stop Sunny assistant"""
        self.is_running = False
        self.voice_handler.stop()
        self.screen_monitor.stop_monitoring()
        self.code_executor.stop_executor()
        self.db.close()
        print("Goodbye!")
    
    def start(self):
        """Start Sunny assistant"""
        self.is_running = True
        
        # Start background components
        self.code_executor.start_executor()
        self.screen_monitor.start_monitoring()
        
        # Start voice interaction
        self.voice_handler.start_listening()
        
        # Show status
        self._show_status()
        
        # Keep main thread alive
        print("💡 Sunny is running. Say 'Hey Sunny' to wake me up. Say 'Sunny, stop' to exit.\n")
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nKeyboard interrupt detected. Shutting down gracefully...")
            self.is_running = False
        
        # Cleanup when done
        self.stop()
    
    def handle_experiment_completion(self, result: Dict):
        """Handle when background experiment completes"""
        status = result.get('status')
        figure_ref = result.get('figure_reference', 'The experiment')
        
        if status == 'success':
            output = result.get('output', '')
            message = f"{figure_ref} completed successfully"
            if output:
                message += f". {output}"
        else:
            error = result.get('error', 'unknown error')
            message = f"{figure_ref} failed due to {error}"
        
        print(f"\n[OK] Experiment Update: {message}")
        self.voice_handler.speak(message)
    
    def handle_research_completion(self, result: Dict):
        """Handle when research task completes"""
        query = result.get('query', 'Research')
        findings = result.get('findings', {})
        
        if isinstance(findings, dict):
            conclusion = findings.get('conclusion', 'Research completed')
        else:
            conclusion = str(findings)
        
        message = f"Research on {query} is done. {conclusion}"
        
        print(f"\n🔍 Research Update: {message}")
        self.voice_handler.speak(message)


def main():
    """Main entry point"""
    try:
        # Check for API key
        if not os.getenv("GEMINI_API_KEY"):
            print("Error: GEMINI_API_KEY not found in .env file")
            print("Please create a .env file with your Gemini API key")
            return
        
        # Create and start Sunny
        sunny = SunnyAssistant()
        sunny.start()
        
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
