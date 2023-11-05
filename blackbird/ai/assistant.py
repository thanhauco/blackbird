"""
AI Assistant for Code

Provides AI-powered code assistance including:
- Natural language search
- Code explanation
- Code generation
- Refactoring suggestions
"""

from typing import List, Dict, Optional, Any, Generator
from dataclasses import dataclass, field
from enum import Enum
import json
import re
import structlog

logger = structlog.get_logger()

# Try to import OpenAI
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class AssistantRole(Enum):
    """Role in the conversation"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """Chat message"""
    role: AssistantRole
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeContext:
    """Context about the code being discussed"""
    file_path: str
    language: str
    content: str
    selection: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    symbols: List[str] = field(default_factory=list)


@dataclass
class AssistantResponse:
    """Response from the AI assistant"""
    content: str
    code_blocks: List[Dict[str, str]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    confidence: float = 1.0


class PromptTemplates:
    """Prompt templates for different tasks"""
    
    SYSTEM_PROMPT = """You are an expert code assistant integrated into the Blackbird code search engine. 
You help developers understand, search, and improve their code.

Your capabilities:
1. Explain code in clear, concise language
2. Answer questions about code functionality
3. Suggest improvements and best practices
4. Help find relevant code using natural language
5. Generate code based on descriptions

When explaining code:
- Start with a high-level summary
- Explain key components and their interactions
- Highlight potential issues or improvements

When generating code:
- Follow the style of the surrounding code
- Include helpful comments
- Consider edge cases and error handling
"""
    
    CODE_EXPLAIN = """Explain the following {language} code:

```{language}
{code}
```

Provide:
1. A brief summary of what this code does
2. Explanation of key components
3. Any potential issues or improvements
"""
    
    CODE_SEARCH = """Convert this natural language query into a code search query:

User Query: "{query}"

Context: The user is searching a codebase that contains {languages}.

Return a JSON object with:
- "search_terms": List of specific code patterns to search for
- "filters": Optional filters like language, file type
- "explanation": Brief explanation of the search strategy
"""
    
    CODE_GENERATE = """Generate code based on this description:

Description: {description}
Language: {language}
Context:
```{language}
{context}
```

Requirements:
- Follow the existing code style
- Include error handling
- Add helpful comments
"""
    
    CODE_REVIEW = """Review the following code and provide suggestions:

```{language}
{code}
```

Focus on:
1. Code quality and readability
2. Potential bugs or issues
3. Performance considerations
4. Security concerns
5. Best practices for {language}
"""
    
    REFACTOR = """Suggest refactoring for this code:

```{language}
{code}
```

Consider:
1. Simplifying complex logic
2. Extracting reusable functions
3. Improving naming
4. Reducing duplication
5. Following {language} best practices
"""


class AIAssistant:
    """
    AI-powered code assistant using LLM.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4",
        temperature: float = 0.3,
        max_tokens: int = 2000
    ):
        """
        Initialize the AI assistant.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (gpt-4, gpt-3.5-turbo, etc.)
            temperature: Response creativity (0-1)
            max_tokens: Maximum response length
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = None
        
        if OPENAI_AVAILABLE and api_key:
            self.client = openai.OpenAI(api_key=api_key)
            logger.info("AI assistant initialized with OpenAI")
        else:
            logger.warning("OpenAI not available, using mock responses")
        
        # Conversation history per session
        self.conversations: Dict[str, List[Message]] = {}
    
    def _get_completion(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> str:
        """Get completion from the LLM"""
        if not self.client:
            return self._mock_response(messages[-1]["content"])
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=stream
            )
            
            if stream:
                return response  # Return generator
            else:
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error("LLM API error", error=str(e))
            return f"Error: {str(e)}"
    
    def _mock_response(self, query: str) -> str:
        """Generate mock response when API is not available"""
        if "explain" in query.lower():
            return "This code appears to be a function that processes data. Without the actual API connection, I can provide limited analysis."
        elif "search" in query.lower():
            return '{"search_terms": ["function", "class"], "filters": {}, "explanation": "Searching for common patterns"}'
        elif "generate" in query.lower():
            return "```python\n# Generated code placeholder\ndef example():\n    pass\n```"
        else:
            return "I understand your question. With the full API integration, I could provide more detailed assistance."
    
    def explain_code(
        self,
        code: str,
        language: str = "python",
        context: Optional[CodeContext] = None
    ) -> AssistantResponse:
        """
        Explain what a piece of code does.
        """
        prompt = PromptTemplates.CODE_EXPLAIN.format(
            language=language,
            code=code
        )
        
        messages = [
            {"role": "system", "content": PromptTemplates.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self._get_completion(messages)
        
        return AssistantResponse(
            content=response,
            code_blocks=self._extract_code_blocks(response)
        )
    
    def natural_language_search(self, query: str, languages: List[str] = None) -> Dict[str, Any]:
        """
        Convert natural language query to code search.
        """
        languages = languages or ["Python", "JavaScript", "TypeScript"]
        
        prompt = PromptTemplates.CODE_SEARCH.format(
            query=query,
            languages=", ".join(languages)
        )
        
        messages = [
            {"role": "system", "content": PromptTemplates.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self._get_completion(messages)
        
        # Parse JSON from response
        try:
            # Find JSON in response
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        # Fallback: extract simple terms
        return {
            "search_terms": [query],
            "filters": {},
            "explanation": "Direct search"
        }
    
    def generate_code(
        self,
        description: str,
        language: str = "python",
        context: str = ""
    ) -> AssistantResponse:
        """
        Generate code from natural language description.
        """
        prompt = PromptTemplates.CODE_GENERATE.format(
            description=description,
            language=language,
            context=context
        )
        
        messages = [
            {"role": "system", "content": PromptTemplates.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self._get_completion(messages)
        code_blocks = self._extract_code_blocks(response)
        
        return AssistantResponse(
            content=response,
            code_blocks=code_blocks
        )
    
    def review_code(
        self,
        code: str,
        language: str = "python"
    ) -> AssistantResponse:
        """
        Review code and provide suggestions.
        """
        prompt = PromptTemplates.CODE_REVIEW.format(
            language=language,
            code=code
        )
        
        messages = [
            {"role": "system", "content": PromptTemplates.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self._get_completion(messages)
        suggestions = self._extract_suggestions(response)
        
        return AssistantResponse(
            content=response,
            suggestions=suggestions
        )
    
    def suggest_refactoring(
        self,
        code: str,
        language: str = "python"
    ) -> AssistantResponse:
        """
        Suggest code refactoring.
        """
        prompt = PromptTemplates.REFACTOR.format(
            language=language,
            code=code
        )
        
        messages = [
            {"role": "system", "content": PromptTemplates.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self._get_completion(messages)
        
        return AssistantResponse(
            content=response,
            code_blocks=self._extract_code_blocks(response),
            suggestions=self._extract_suggestions(response)
        )
    
    def chat(
        self,
        session_id: str,
        message: str,
        context: Optional[CodeContext] = None
    ) -> AssistantResponse:
        """
        Continue a conversation with context.
        """
        if session_id not in self.conversations:
            self.conversations[session_id] = [
                Message(AssistantRole.SYSTEM, PromptTemplates.SYSTEM_PROMPT)
            ]
        
        # Add context if provided
        if context:
            context_msg = f"Current file: {context.file_path}\n"
            context_msg += f"Language: {context.language}\n"
            if context.selection:
                context_msg += f"Selected code:\n```{context.language}\n{context.selection}\n```\n"
            message = context_msg + "\n" + message
        
        self.conversations[session_id].append(
            Message(AssistantRole.USER, message)
        )
        
        # Build messages for API
        messages = [
            {"role": m.role.value, "content": m.content}
            for m in self.conversations[session_id]
        ]
        
        response = self._get_completion(messages)
        
        self.conversations[session_id].append(
            Message(AssistantRole.ASSISTANT, response)
        )
        
        return AssistantResponse(
            content=response,
            code_blocks=self._extract_code_blocks(response)
        )
    
    def _extract_code_blocks(self, text: str) -> List[Dict[str, str]]:
        """Extract code blocks from markdown text"""
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        return [
            {"language": lang or "text", "code": code.strip()}
            for lang, code in matches
        ]
    
    def _extract_suggestions(self, text: str) -> List[str]:
        """Extract numbered suggestions from text"""
        pattern = r'\d+\.\s+(.+?)(?=\n\d+\.|\n\n|$)'
        matches = re.findall(pattern, text, re.DOTALL)
        return [m.strip() for m in matches]


class CodeAgentTool:
    """
    Tool interface for AI coding agent integration.
    
    Compatible with function-calling LLMs and agent frameworks.
    """
    
    def __init__(self, assistant: AIAssistant):
        self.assistant = assistant
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get tool schemas for function calling"""
        return [
            {
                "name": "search_code",
                "description": "Search for code in the codebase using natural language or code patterns",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "language": {"type": "string", "description": "Filter by language"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "explain_code",
                "description": "Explain what a piece of code does",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to explain"},
                        "language": {"type": "string", "description": "Programming language"}
                    },
                    "required": ["code"]
                }
            },
            {
                "name": "generate_code",
                "description": "Generate code from a description",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "What to generate"},
                        "language": {"type": "string", "description": "Target language"}
                    },
                    "required": ["description"]
                }
            },
            {
                "name": "review_code",
                "description": "Review code for issues and improvements",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to review"},
                        "language": {"type": "string", "description": "Programming language"}
                    },
                    "required": ["code"]
                }
            }
        ]
    
    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool and return result"""
        if name == "search_code":
            result = self.assistant.natural_language_search(
                arguments["query"],
                [arguments.get("language")] if arguments.get("language") else None
            )
            return json.dumps(result)
        
        elif name == "explain_code":
            result = self.assistant.explain_code(
                arguments["code"],
                arguments.get("language", "python")
            )
            return result.content
        
        elif name == "generate_code":
            result = self.assistant.generate_code(
                arguments["description"],
                arguments.get("language", "python")
            )
            return result.content
        
        elif name == "review_code":
            result = self.assistant.review_code(
                arguments["code"],
                arguments.get("language", "python")
            )
            return result.content
        
        return f"Unknown tool: {name}"
