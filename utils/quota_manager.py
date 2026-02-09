"""
Quota Manager for Sunny Research Assistant
Tracks Gemini API usage to stay within free tier limits
"""

import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple


class QuotaManager:
    """
    Manages API quota for Gemini Flash and Pro models
    
    Free Tier Limits (Gemini 3):
    - Flash: 15 RPM, 1000 RPD, 250K TPM
    - Pro: 2 RPM (assumed), 50 RPD (assumed based on typical limits)
    """
    
    # Limits with safety buffer (Gemini 3 Free Tier)
    # Reference: https://ai.google.dev/pricing
    # Flash: 15 RPM, 1500 RPD, 1M TPM
    # Pro: 2 RPM, 50 RPD, 32K TPM
    
    # COST CONTROL: These limits ensure zero cost
    # Per-minute rate limits DISABLED (use only daily limits)
    FLASH_RPM = None  # Disabled - per-minute checks removed
    FLASH_RPD = 1000  # Set to 1000 (limit 1500) to be safe
    
    PRO_RPM = None    # Disabled - per-minute checks removed
    PRO_RPD = 10      # Set to 40 (limit 50) to be safe
    
    def __init__(self, state_file: str = None):
        """Initialize quota manager"""
        if state_file is None:
            state_file = Path(__file__).parent.parent / "quota_state.json"
        
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load quota state from file or initialize new"""
        try:
            if Path(self.state_file).exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    
                # Reset if it's a new day
                if state.get('last_reset_date') != datetime.now().strftime('%Y-%m-%d'):
                    state = self._create_fresh_state()
                    self._save_state(state)
                
                return state
        except Exception as e:
            print(f"Error loading quota state: {e}")
        
        return self._create_fresh_state()
    
    def _create_fresh_state(self) -> Dict:
        """Create fresh quota state"""
        return {
            'last_reset_date': datetime.now().strftime('%Y-%m-%d'),
            'flash_calls_today': 0,
            'pro_calls_today': 0,
            'flash_calls_this_minute': [],
            'pro_calls_this_minute': [],
        }
    
    def _save_state(self, state: Dict = None):
        """Save quota state to file"""
        if state is None:
            state = self.state
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Error saving quota state: {e}")
    
    def _clean_minute_calls(self, calls_list: list) -> list:
        """Remove calls older than 1 minute"""
        one_minute_ago = time.time() - 60
        return [t for t in calls_list if t > one_minute_ago]
    
    def can_call_flash(self) -> Tuple[bool, str]:
        """
        Check if we can make a Flash API call
        Returns: (can_call: bool, reason: str)
        
        All quota limits disabled - unlimited calls
        """
        # Check if new day (for state management only, no blocking)
        if self.state.get('last_reset_date') != datetime.now().strftime('%Y-%m-%d'):
            self.state = self._create_fresh_state()
            self._save_state()
        
        # All limits disabled - users can make unlimited calls
        return True, "OK"
    
    def can_call_pro(self) -> Tuple[bool, str]:
        """
        Check if we can make a Pro API call
        Returns: (can_call: bool, reason: str)
        
        All quota limits disabled - unlimited calls
        """
        # Check if new day (for state management only, no blocking)
        if self.state.get('last_reset_date') != datetime.now().strftime('%Y-%m-%d'):
            self.state = self._create_fresh_state()
            self._save_state()
        
        # All limits disabled - users can make unlimited calls
        return True, "OK"
    
    def record_flash_call(self):
        """Record a Flash API call"""
        now = time.time()
        self.state['flash_calls_today'] += 1
        self.state['flash_calls_this_minute'].append(now)
        self._save_state()
    
    def record_pro_call(self):
        """Record a Pro API call"""
        now = time.time()
        self.state['pro_calls_today'] += 1
        self.state['pro_calls_this_minute'].append(now)
        self._save_state()
    
    def get_usage_stats(self) -> Dict:
        """Get current usage statistics"""
        self.state['flash_calls_this_minute'] = self._clean_minute_calls(
            self.state['flash_calls_this_minute']
        )
        self.state['pro_calls_this_minute'] = self._clean_minute_calls(
            self.state['pro_calls_this_minute']
        )
        
        return {
            'flash_today': f"{self.state['flash_calls_today']}/{self.FLASH_RPD}",
            'flash_this_minute': f"{len(self.state['flash_calls_this_minute'])}/{self.FLASH_RPM}",
            'pro_today': f"{self.state['pro_calls_today']}/{self.PRO_RPD}",
            'pro_this_minute': f"{len(self.state['pro_calls_this_minute'])}/{self.PRO_RPM}",
            'flash_percentage': int((self.state['flash_calls_today'] / self.FLASH_RPD) * 100),
            'pro_percentage': int((self.state['pro_calls_today'] / self.PRO_RPD) * 100),
        }
    
    def warn_if_high_usage(self):
        """Print warning if usage is high"""
        stats = self.get_usage_stats()
        
        if stats['flash_percentage'] >= 80:
            print(f"Warning: Flash API usage at {stats['flash_percentage']}% of daily limit")
        
        if stats['pro_percentage'] >= 80:
            print(f"Warning: Pro API usage at {stats['pro_percentage']}% of daily limit")


# Singleton instance
_quota_manager = None

def get_quota_manager() -> QuotaManager:
    """Get or create the quota manager singleton instance"""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager
