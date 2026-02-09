"""
Screen Monitor for Sunny Research Assistant
Monitors screen for paper reading activity using Gemini Computer Use tool
Includes smart page-turn detection and scroll threshold filtering
"""

import os
import time
import threading
import hashlib
from typing import Callable, Optional, Dict
from datetime import datetime
from PIL import ImageGrab, ImageChops
import pygetwindow as gw
from dotenv import load_dotenv
import google.generativeai as genai

from utils.quota_manager import get_quota_manager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class ScreenMonitor:
    """
    Monitors active window for research paper reading
    Detects context changes and important events using Computer Use tool.
    Includes smart page-turn detection using similarity threshold.
    """
    
    def __init__(self, 
                 on_context_change: Callable[[Dict], None],
                 monitoring_interval: int = 2):  # Check every 2s (hybrid approach)
        self.on_context_change = on_context_change
        self.monitoring_interval = monitoring_interval
        self.is_running = False
        self.last_window_title = None
        self.last_screenshot = None
        self.last_screenshot_hash = None
        self.quota_manager = get_quota_manager()
        
        # Page-turn detection parameters
        self.similarity_threshold = 0.85  # 85% similar = page didn't turn, <85% = page turned
        self.minor_change_threshold = 0.98  # 98% similar = ignore (minor scroll/cursor movement)
        self.page_turn_cooldown = 0.8  # Don't trigger analysis until 0.8s of no changes
        self.last_significant_change_time = None
        
        # Configure model with Computer Use tool (High Resolution for text)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            #tools=[{"google_computer_use": {"media_resolution": "high"}}],
            system_instruction="""You are an autonomous research partner capable of 'seeing' the user's screen.
            Your role is to detect when the user is reading a research paper and identifying the specific section.
            If you see complex charts or equations, offer to analyze them.
            Be extremely concise."""
        )
    
    def start_monitoring(self):
        """Start monitoring the screen"""
        self.is_running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, 
            daemon=True
        )
        self.monitoring_thread.start()
        print(f"Screen monitoring started (checking every {self.monitoring_interval}s)")
    
    def stop_monitoring(self):
        self.is_running = False
        print("Screen monitoring stopped")
    
    def _monitoring_loop(self):
        while self.is_running:
            try:
                self._autonomous_perception_check()  # Check for page turns
                self._check_screen_context()  # Check for window changes
                
                # Check if cooldown timer expired - time to analyze accumulated changes
                if self.last_significant_change_time is not None:
                    time_since_change = time.time() - self.last_significant_change_time
                    if time_since_change >= self.page_turn_cooldown:
                        # Changes have stabilized, time to analyze
                        self._analyze_screen(self.last_window_title)
                        self.last_significant_change_time = None
                        
            except Exception as e:
                print(f"Error in screen monitoring: {e}")
            time.sleep(self.monitoring_interval)
    
    def _calculate_image_similarity(self, img1, img2) -> float:
        """
        Calculate similarity between two images using pixel-level comparison.
        Returns: float between 0.0 and 1.0 where 1.0 = identical
        
        Uses ImageChops to compute difference and checks if image content is similar
        """
        if img1 is None or img2 is None:
            return 1.0
        
        try:
            # Ensure same size
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)
            
            # Calculate difference
            diff = ImageChops.difference(img1, img2)
            
            # Count different pixels
            stat = diff.convert('L').getextrema()
            if stat[1] == 0:  # No difference
                return 1.0
            
            # Calculate similarity ratio
            # More efficient: sample histogram
            hist = diff.histogram()
            different_pixels = sum(hist[1:])  # Exclude 0 (identical pixels)
            total_pixels = img1.size[0] * img1.size[1]
            
            similarity = 1.0 - (different_pixels / (total_pixels * 256))
            return max(0.0, min(1.0, similarity))
            
        except Exception as e:
            print(f"Error calculating image similarity: {e}")
            return 1.0
    
    def _autonomous_perception_check(self):
        """
        PHASE 3: Autonomous perception - detect page turns and significant scrolling
        Uses image similarity to detect when user has scrolled/turned pages.
        Ignores minor changes (cursor movements, small scrolls) but catches page turns.
        """
        try:
            screenshot = self.get_current_screenshot()
            if screenshot is None:
                return
            
            # First time - just store
            if self.last_screenshot is None:
                self.last_screenshot = screenshot
                self.last_screenshot_hash = hashlib.md5(screenshot.tobytes()).hexdigest()
                return
            
            # Calculate similarity to detect changes
            similarity = self._calculate_image_similarity(self.last_screenshot, screenshot)
            
            # Ignore tiny changes (cursor, typing, minor scrolling)
            if similarity > self.minor_change_threshold:
                return  # Less than 2% change, ignore
            
            # Significant change detected (could be page turn or major scroll)
            if similarity <= self.similarity_threshold:
                # This is a page turn or major scroll!
                self.last_screenshot = screenshot
                self.last_significant_change_time = time.time()
                
                print(f"[Page Turn Detected] Similarity: {similarity:.1%} - Analyzing after stabilization...")
                
                # Don't call API yet, wait for cooldown
                # This batches rapid scrolls into single analysis
                
        except Exception as e:
            # Silent fail for perception loop
            pass
    
    def _check_screen_context(self):
        """
        Check screen context using Computer Use.
        Instead of just passively waiting for window changes, we actively look
        for research opportunities.
        """
        try:
            active_window = gw.getActiveWindow()
            if not active_window:
                return
            
            # Simple heuristic to avoid spamming the API on non-paper windows
            current_title = active_window.title
            is_relevant = any(k in current_title.lower() for k in ['.pdf', 'arxiv', 'paper', 'reader'])
            
            if is_relevant:
                # Check quota before visual analysis
                can_call, reason = self.quota_manager.can_call_flash() # Fallback to flash check for frequency
                if can_call and self._should_analyze(current_title):
                    self._analyze_screen(current_title)
                    self.quota_manager.record_flash_call() # Logging as flash for now
                    self.last_window_title = current_title

        except Exception as e:
            # print(f"Screen check skipped: {e}")
            pass

    def _should_analyze(self, title):
        """Determine if we should trigger a fresh analysis"""
        # Analyze if window changed
        if title != self.last_window_title:
            self.last_window_title = title
            return True
        return False

    def _analyze_screen(self, window_title):
        """
        Analyze current screen content - triggered after page turn or window change.
        Uses the model to understand what section user is reading.
        """
        if window_title is None:
            return
            
        try:
            # Check quota before visual analysis
            can_call, reason = self.quota_manager.can_call_flash()
            if not can_call:
                print(f"[Quota] Skipping analysis: {reason}")
                return
            
            # In a real Computer Use implementation, we pass the screen stream.
            # Here we capture the frame to send to the multimodal model.
            active_window = gw.getActiveWindow()
            screenshot = ImageGrab.grab(bbox=(
                active_window.left, active_window.top,
                active_window.left + active_window.width, active_window.top + active_window.height
            ))
            
            # Use Jayu's vision technique: explicit instruction to look carefully
            prompt = """Give me a detailed description of what you see in this paper section.
Focus on:
1. What section/subsection is this? (e.g., Methods, Results, Introduction)
2. What are the main points or findings on this page?
3. Are there any important equations, figures, or data?
4. What should be noted or remembered from this section?

Keep your response concise but comprehensive."""
            
            # This call uses the configured model
            response = self.model.generate_content([prompt, screenshot])
            self.quota_manager.record_flash_call()
            
            context = {
                'event': 'page_analyzed',
                'window_title': window_title,
                'section_analysis': response.text,
                'screenshot': screenshot,
                'timestamp': datetime.now().isoformat()
            }
            self.on_context_change(context)
            
            print(f"[Analysis] Page content analyzed from {window_title[:50]}")
            
        except Exception as e:
            print(f"[Vision Error] Analysis failed: {e}")

    def get_current_screenshot(self):
        try:
            active_window = gw.getActiveWindow()
            if not active_window: return None
            return ImageGrab.grab(bbox=(
                active_window.left, active_window.top,
                active_window.left + active_window.width, active_window.top + active_window.height
            ))
        except: return None

def create_screen_monitor(on_context_change: Callable[[Dict], None]) -> ScreenMonitor:
    return ScreenMonitor(on_context_change)

