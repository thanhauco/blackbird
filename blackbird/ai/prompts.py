"""
Prompt Engineering for AI Assistant

Provides optimized prompts and context management.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class PromptContext:
    """Context for AI prompts"""
    file_path: str = ""
    language: str = ""
    code_snippet: str = ""
    cursor_position: int = 0
    visible_symbols: List[str] = None
    imports: List[str] = None
    
    def __post_init__(self):
        self.visible_symbols = self.visible_symbols or []
        self.imports = self.imports or []


class PromptBuilder:
    """Builds optimized prompts for AI tasks"""
    
    MAX_CONTEXT_LENGTH = 4000
    
    def __init__(self):
        self.templates = {
            "explain": self._explain_template,
            "generate": self._generate_template,
            "review": self._review_template,
            "refactor": self._refactor_template,
            "debug": self._debug_template,
        }
    
    def build(
        self,
        task: str,
        user_input: str,
        context: Optional[PromptContext] = None
    ) -> str:
        """Build prompt for a task"""
        template_fn = self.templates.get(task, self._default_template)
        return template_fn(user_input, context)
    
    def _explain_template(self, code: str, context: Optional[PromptContext]) -> str:
        lang = context.language if context else "code"
        return f"""Explain the following {lang} code in detail:

```{lang}
{code}
```

Provide:
1. A high-level summary
2. Step-by-step explanation
3. Key concepts used
4. Potential improvements"""
    
    def _generate_template(self, description: str, context: Optional[PromptContext]) -> str:
        lang = context.language if context else "python"
        existing = context.code_snippet if context else ""
        
        prompt = f"""Generate {lang} code for: {description}

Requirements:
- Follow best practices
- Include error handling
- Add comments for clarity"""
        
        if existing:
            prompt += f"\n\nExisting code context:\n```{lang}\n{existing}\n```"
        
        return prompt
    
    def _review_template(self, code: str, context: Optional[PromptContext]) -> str:
        lang = context.language if context else "code"
        return f"""Review this {lang} code for issues:

```{lang}
{code}
```

Check for:
1. Bugs and logic errors
2. Security vulnerabilities
3. Performance issues
4. Code style and readability
5. Best practice violations"""
    
    def _refactor_template(self, code: str, context: Optional[PromptContext]) -> str:
        lang = context.language if context else "code"
        return f"""Suggest refactoring for this {lang} code:

```{lang}
{code}
```

Focus on:
1. Reducing complexity
2. Improving readability
3. Extracting reusable functions
4. Better naming
5. Following SOLID principles"""
    
    def _debug_template(self, code: str, context: Optional[PromptContext]) -> str:
        lang = context.language if context else "code"
        return f"""Help debug this {lang} code:

```{lang}
{code}
```

Analyze for:
1. Common bug patterns
2. Edge cases
3. Variable scope issues
4. Type errors
5. Logic errors"""
    
    def _default_template(self, user_input: str, context: Optional[PromptContext]) -> str:
        prompt = f"User request: {user_input}"
        
        if context and context.code_snippet:
            prompt += f"\n\nCode context:\n```{context.language}\n{context.code_snippet}\n```"
        
        return prompt
    
    def truncate_context(self, text: str) -> str:
        """Truncate context to fit token limits"""
        if len(text) <= self.MAX_CONTEXT_LENGTH:
            return text
        
        # Keep beginning and end
        half = self.MAX_CONTEXT_LENGTH // 2
        return text[:half] + "\n... [truncated] ...\n" + text[-half:]


class ConversationManager:
    """Manages conversation history for AI sessions"""
    
    MAX_HISTORY = 10
    
    def __init__(self):
        self.sessions: Dict[str, List[Dict]] = {}
    
    def add_message(self, session_id: str, role: str, content: str):
        """Add message to session history"""
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        
        self.sessions[session_id].append({
            "role": role,
            "content": content
        })
        
        # Trim old messages
        if len(self.sessions[session_id]) > self.MAX_HISTORY * 2:
            self.sessions[session_id] = self.sessions[session_id][-self.MAX_HISTORY:]
    
    def get_history(self, session_id: str) -> List[Dict]:
        """Get session history"""
        return self.sessions.get(session_id, [])
    
    def clear_session(self, session_id: str):
        """Clear session history"""
        if session_id in self.sessions:
            del self.sessions[session_id]
