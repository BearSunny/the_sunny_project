"""
Paper Analyzer for Sunny Research Assistant
Analyzes research papers, spots issues, and takes notes
"""

import os
from datetime import datetime
from typing import Dict, Optional
from dotenv import load_dotenv
import google.generativeai as genai

from storage.database import get_database
from utils.quota_manager import get_quota_manager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class PaperAnalyzer:
    """Analyzes research papers using Gemini Pro"""
    
    def __init__(self):
        """Initialize paper analyzer"""
        self.db = get_database()
        self.quota_manager = get_quota_manager()
        
        # Gemini Pro for deep analysis (uses thought_signature)
        self.pro_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={
                "temperature": 0.3,  # Lower for more factual analysis
                "response_mime_type": "application/json"
            }
        )
    
    def analyze_paper(self, screenshot, window_title: str = "") -> Dict:
        """
        Analyze a research paper from screenshot
        
        Args:
            screenshot: PIL Image of the paper
            window_title: Current window title for context
        
        Returns:
            Dict with paper analysis including thought_signature
        """
        # Check quota
        can_call, reason = self.quota_manager.can_call_pro()
        if not can_call:
            return {"error": reason}
        
        prompt = """Analyze this research paper screenshot.
        
        Extract and provide in JSON format:
        {
            "title": "Paper title if visible",
            "authors": ["Author 1", "Author 2"],
            "year": 2024,
            "current_section": "Section name (e.g., Introduction, Methods)",
            "summary": "Brief 2-3 sentence summary of what's visible",
            "main_claims": ["Key claim 1", "Key claim 2"],
            "methodology": "Brief description of methods if visible",
            "key_findings": "Important results if visible",
            "thought_process": "Your reasoning process for this analysis"
        }
        
        Be concise and focus on what's actually visible in the screenshot.
        """
        
        try:
            response = self.pro_model.generate_content([prompt, screenshot])
            self.quota_manager.record_pro_call()
            
            # Parse JSON response
            import json
            analysis = json.loads(response.text)
            
            # Save to database
            paper_id = self.db.add_paper({
                'title': analysis.get('title', window_title),
                'authors': analysis.get('authors', []),
                'year': analysis.get('year'),
                'summary': analysis.get('summary'),
                'screenshot_path': None,  # TODO: Save screenshot
                'metadata': {
                    'main_claims': analysis.get('main_claims', []),
                    'methodology': analysis.get('methodology'),
                    'key_findings': analysis.get('key_findings')
                }
            })
            
            analysis['paper_id'] = paper_id
            return analysis
            
        except Exception as e:
            print(f"Error analyzing paper: {e}")
            return {"error": str(e)}
    
    def spot_issues(self, screenshot, paper_id: str = None, section: str = "") -> Dict:
        """
        Critique a paper section and spot potential issues
        
        Args:
            screenshot: PIL Image of the section
            paper_id: ID of the paper being critiqued
            section: Section name being analyzed
        
        Returns:
            Dict with critiques and thought_signature
        """
        # Check quota
        can_call, reason = self.quota_manager.can_call_pro()
        if not can_call:
            return {"error": reason}
        
        prompt = """Critically analyze this research paper section.
        
        Look for:
        - Logical inconsistencies or contradictions
        - Missing information or unclear explanations
        - Potential methodological issues
        - Statistical concerns
        - Overstated claims
        - Missing citations or references
        
        Provide response in JSON format:
        {
            "critiques": [
                {
                    "issue": "Brief description of the issue",
                    "severity": "low/medium/high",
                    "explanation": "Why this is a concern",
                    "location": "Where in the text (if identifiable)"
                }
            ],
            "strengths": ["Notable strength 1", "strength 2"],
            "confidence": 0.8,
            "thought_process": "Your detailed reasoning for these critiques"
        }
        
        Be constructive and specific. Only flag genuine concerns.
        """
        
        try:
            response = self.pro_model.generate_content([prompt, screenshot])
            self.quota_manager.record_pro_call()
            
            import json
            critique = json.loads(response.text)
            
            # Save critiques as notes
            if paper_id:
                for c in critique.get('critiques', []):
                    self.db.add_note({
                        'paper_id': paper_id,
                        'content': f"[{c['severity'].upper()}] {c['issue']}: {c['explanation']}",
                        'section': section,
                        'thought_signature': critique.get('thought_process'),
                        'note_type': 'ai_critique'
                    })
            
            return critique
            
        except Exception as e:
            print(f"Error spotting issues: {e}")
            return {"error": str(e)}
    
    def take_note(self, note_text: str, paper_id: str, section: str = "") -> str:
        """
        Save a user note about the paper
        
        Args:
            note_text: The note content
            paper_id: ID of the paper
            section: Section the note refers to
        
        Returns:
            Note ID
        """
        note_id = self.db.add_note({
            'paper_id': paper_id,
            'content': note_text,
            'section': section,
            'note_type': 'user'
        })
        
        print(f"Note saved: {note_text[:50]}...")
        return note_id
    
    def extract_code_from_screen(self, screenshot) -> Optional[str]:
        """
        Extract code blocks from paper screenshot
        
        Args:
            screenshot: PIL Image containing code
        
        Returns:
            Extracted code as string
        """
        # Check quota
        can_call, reason = self.quota_manager.can_call_pro()
        if not can_call:
            print(f"Cannot extract code: {reason}")
            return None
        
        prompt = """Extract all code from this image.
        
        Look for:
        - Algorithm pseudocode
        - Code snippets
        - Mathematical formulas that could be code
        
        Return the code exactly as shown, preserving formatting.
        If multiple code blocks exist, separate them with '### CODE BLOCK N ###'
        
        If no code is visible, return: NO_CODE_FOUND
        """
        
        try:
            response = self.pro_model.generate_content([prompt, screenshot])
            self.quota_manager.record_pro_call()
            
            code = response.text.strip()
            
            if code == "NO_CODE_FOUND":
                return None
            
            # Clean up JSON wrapping and escaped characters if present
            import json
            if code.startswith('{') and '"code"' in code:
                try:
                    json_obj = json.loads(code)
                    if isinstance(json_obj, dict) and 'code' in json_obj:
                        code = json_obj['code']
                except (json.JSONDecodeError, ValueError):
                    pass  # Not JSON, use raw code
            
            # Handle escaped newlines
            code = code.replace('\\n', '\n').replace('\\r', '\r')
            
            return code
            
        except Exception as e:
            print(f"Error extracting code: {e}")
            return None
    
    def get_paper_summary(self, paper_id: str) -> Dict:
        """
        Get comprehensive summary of a paper including all notes and experiments
        
        Args:
            paper_id: Paper ID
        
        Returns:
            Dict with paper info, notes, and experiments
        """
        paper = self.db.get_paper(paper_id)
        if not paper:
            return {"error": "Paper not found"}
        
        notes = self.db.get_notes_for_paper(paper_id)
        experiments = self.db.get_experiments_for_paper(paper_id)
        
        return {
            'paper': paper,
            'notes': notes,
            'experiments': experiments,
            'total_notes': len(notes),
            'total_experiments': len(experiments)
        }


def create_paper_analyzer() -> PaperAnalyzer:
    """Create paper analyzer instance"""
    return PaperAnalyzer()
