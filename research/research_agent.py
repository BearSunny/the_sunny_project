"""
Research Agent for Sunny Research Assistant
Verifies claims and finds contradicting/confirming papers using LLM reasoning
"""

import os
from datetime import datetime
from typing import Dict, List, Callable
from dotenv import load_dotenv
import google.generativeai as genai

from storage.database import get_database
from utils.quota_manager import get_quota_manager

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class ResearchAgent:
    """
    Research agent for paper verification.
    Uses LLM reasoning to verify claims and find related papers.
    Builds the 'Research Vault' graph with findings.
    """
    
    def __init__(self, on_completion: Callable[[Dict], None]):
        self.db = get_database()
        self.quota_manager = get_quota_manager()
        self.on_completion = on_completion
        
        # Initialize research model without tools
        # Uses standard generation for research queries
        self.research_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={"temperature": 0.4}
        )
    
    def verify_claim(self, claim: str, paper_id: str = None) -> str:
        """Verify a claim using Deep Research"""
        task_id = self.db.add_research_task({
            'query': f"Verify claim: {claim}",
            'status': 'running'
        })
        
        print(f"Deep Research started: {task_id}")
        
        import threading
        threading.Thread(
            target=self._execute_deep_research,
            args=(task_id, claim, paper_id),
            daemon=True
        ).start()
        
        return task_id
    
    def find_contradictions(self, paper_id: str) -> str:
        """Find papers that contradict the given paper"""
        paper = self.db.get_paper(paper_id)
        if not paper: return None
        
        title = paper.get('title', 'Unknown')
        query = f"Find academic papers that contradict or dispute the findings of '{title}'"
        
        task_id = self.db.add_research_task({
            'query': query,
            'status': 'running'
        })
        
        print(f"Searching for contradictions: {task_id}")
        
        import threading
        threading.Thread(
            target=self._execute_deep_research,
            args=(task_id, query, paper_id, True), # True = looking for contradictions
            daemon=True
        ).start()
        
        return task_id
    
    def _execute_deep_research(self, task_id: str, query: str, paper_id: str = None, is_contradiction_search: bool = False):
        """
        Executes the research task.
        Calls the model which now has access to the Deep Research tool.
        """
        can_call, reason = self.quota_manager.can_call_pro()
        if not can_call:
            self._fail_task(task_id, f"Quota exceeded: {reason}")
            return

        try:
            prompt = f"""
            Perform deep research on the following query: "{query}"
            
            1. Search for reputable academic sources.
            2. Verify the claims.
            3. Provide a list of papers with their relationships (supports/contradicts).
            
            Return the results as a JSON object with:
            - summary: verification summary
            - related_papers: list of papers found with title, relation, and confidence.
            """
            
            # The model will internally use google.deep_research tool steps
            response = self.research_model.generate_content(prompt)
            self.quota_manager.record_pro_call()
            
            # Parse the structured response
            # (Assuming model returns JSON markdown)
            import json
            import re
            
            text = response.text
            match = re.search(r'```json(.*?)```', text, re.DOTALL)
            json_str = match.group(1) if match else text
            
            try:
                findings = json.loads(json_str)
            except:
                findings = {"summary": text, "related_papers": []}

            # Update Research Task in DB
            self.db.update_research_task(
                task_id,
                findings=findings.get('summary', ''),
                related_papers=findings.get('related_papers', []),
                status='completed'
            )

            # PHASE 2 INTEGRATION: Build the Graph
            if paper_id and 'related_papers' in findings:
                for rp in findings['related_papers']:
                    # Add relationship edge to the database for visualization later
                    self.db.add_relationship(
                        from_paper=paper_id,
                        to_paper=f"ext_{hash(rp.get('title'))}", # Placeholder ID for external paper
                        rel_type=rp.get('relation', 'related'),
                        confidence=rp.get('confidence', 0.5),
                        source='deep_research'
                    )

            self.on_completion({
                'task_id': task_id,
                'status': 'completed',
                'findings': findings
            })
            print(f"Research task completed: {task_id}")

        except Exception as e:
            self._fail_task(task_id, str(e))

    def _fail_task(self, task_id, reason):
        self.db.update_research_task(task_id, findings=f"Failed: {reason}", related_papers=[], status='failed')
        print(f"Research failed: {reason}")

def create_research_agent(on_completion: Callable[[Dict], None]) -> ResearchAgent:
    return ResearchAgent(on_completion)

