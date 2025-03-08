import httpx
import json
from typing import Dict, Any, List
from app.config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL
import re

class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.default_model = OLLAMA_MODEL
        self.timeout = httpx.Timeout(60.0, connect=15.0)  # 60s timeout, 15s for connection
    
    async def rewrite_query(self, query: str, model: str = None) -> str:
        """Transform raw user query into optimized search keywords for better search results."""
        try:
            # Extract specific subreddit if mentioned in the query to use it later
            subreddit_match = re.search(r'(?:r/|subreddit\s+)(\w+)', query, re.IGNORECASE)
            
            # Extract time period if mentioned
            time_period = None
            if re.search(r'\b(today|yesterday|this week|this month|recent|latest|new)\b', query, re.IGNORECASE):
                time_period = "recent"
            
            # MUCH simpler prompt - the LLM is struggling with complex instructions
            prompt = f"""Extract 3-5 search keywords from: "{query}"

OUTPUT FORMAT: keyword1, keyword2, keyword3

EXAMPLES:
"What are the most recommended productivity apps according to r/productivity?"
productivity apps, recommended apps, top productivity tools

"What are the top discussions about artificial intelligence on Reddit this week?"
artificial intelligence, AI discussions, machine learning, neural networks, AI ethics"""
            
            response = await self._generate(prompt, model)
            
            # Clean and normalize the response
            cleaned = response.strip()
            
            # Extreme preprocessing - if the model output contains placeholders, reject it completely
            if re.search(r'\bterm\d\b|\bkeyword\d\b', cleaned, re.IGNORECASE) or "search terms" in cleaned.lower():
                print("Model output contains placeholders - falling back to keyword extraction")
                keywords = self._extract_keywords(query)
                return ", ".join(keywords)
            
            # Super aggressive pattern to catch ALL forms of prefixes and explanations
            prefix_patterns = [
                r"^(Sure|Here|I'll|These|Following|Best|Top|Absolutely|Certainly|Definitely|Let me|I'd|I've|I have|I think|I will|I would|Here's|Based on|As requested).+?:",
                r"^.+?(search terms|keywords|searching|search on|search in|search for|to find|finding posts|find relevant|find information).+?:",
                r"^.*?(Output|Terms|Results|Keywords).*?:",
                r"^.*?(\d+)\s*(simple|effective|useful|key|important|main|relevant|primary|essential).*:"
            ]
            
            # Apply all prefix patterns
            for pattern in prefix_patterns:
                cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
            
            # Remove any remaining text that looks like a heading or explanation
            cleaned = re.sub(r"^.*?:(\s*)", "", cleaned, flags=re.DOTALL)
            
            # Remove "Sure, " or similar at the beginning
            cleaned = re.sub(r"^(Sure\s*,?\s*|Okay\s*,?\s*|Here\s*,?\s*|Well\s*,?\s*)", "", cleaned, flags=re.IGNORECASE)
            
            # Remove numbered list formatting
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"\n+\d+[\.\)]\s*", ", ", cleaned, flags=re.MULTILINE)
            
            # Replace multiple consecutive newlines with a single comma
            cleaned = re.sub(r"\n+", ", ", cleaned)
            
            # Remove any remaining non-essential characters but preserve commas and alphanumerics
            cleaned = re.sub(r"[^\w\s,]", "", cleaned)
            
            # Remove extra whitespace around commas and standardize to comma-space format
            cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
            
            # Remove trailing comma if present
            cleaned = re.sub(r",\s*$", "", cleaned)
            
            # Ensure we don't have multiple consecutive commas
            cleaned = re.sub(r",\s*,", ",", cleaned)
            
            # Final validation - check for bad outputs
            if len(cleaned.split()) > 15 or cleaned.startswith("Sure") or "Here are" in cleaned or len(cleaned.split(",")) < 2:
                print("Model output is problematic - falling back to keyword extraction")
                keywords = self._extract_keywords(query)
                return ", ".join(keywords)
            
            # Add time period indicator if it was in the original query
            if time_period and "recent" not in cleaned.lower() and "latest" not in cleaned.lower():
                cleaned += ", recent posts"
            
            return cleaned
            
        except Exception as e:
            print(f"Error rewriting query: {str(e)}")
            return query  # Fallback to original query
            
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract meaningful keywords from a query."""
        # Remove common stop words
        stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'is', 'are', 'on', 'of', 'what', 'which', 'who', 'whom', 'whose', 'why', 'how', 'when', 'where'}
        
        # Extract subreddit if mentioned
        subreddit_match = re.search(r'(?:r/|subreddit\s+)(\w+)', query, re.IGNORECASE)
        
        # Extract words with 3 or more characters
        words = re.findall(r'\b\w{3,}\b', query.lower())
        
        # Filter out stop words
        keywords = [word for word in words if word not in stop_words]
        
        # Add specific prefixes if they appear in the query
        if any(tech in query.lower() for tech in ['ai', 'artificial intelligence', 'machine learning']):
            if 'artificial intelligence' not in keywords and 'ai' not in keywords:
                keywords.append('artificial intelligence')
                
        # Add time indicators if they appear in the query
        if re.search(r'\b(today|yesterday|this week|this month|recent|latest|new)\b', query, re.IGNORECASE):
            keywords.append('recent')
            
        # Add subreddit if it was found
        if subreddit_match and subreddit_match.group(1).lower() not in keywords:
            keywords.append(f"r/{subreddit_match.group(1).lower()}")
            
        return keywords
    
    async def synthesize_answer(self, query: str, posts: List[Dict[str, Any]], model: str = None) -> str:
        """Generate a coherent summary/answer based on the original query and relevant posts."""
        try:
            if not posts:
                return "No relevant posts found to synthesize an answer."
            
            # Build context from posts, prioritizing highly relevant ones
            context = []
            for i, post in enumerate(posts[:5], 1):
                # Include relevance score and community context
                relevance = f" (Relevance: {post.get('similarity', 0):.2%})" if 'similarity' in post else ""
                subreddit = f" from r/{post['subreddit']}" if post.get('subreddit') else ""
                context.append(f"{i}. Title: {post['title']}{relevance}{subreddit}\nContent: {post['content']}\n")
            
            prompt = """You are a helpful assistant specializing in summarizing Reddit discussions. Given the following extracted key points and top comments, produce a clear and concise summary that highlights common themes, divergent opinions, and any consensus reached. Maintain the informal tone of Reddit while ensuring clarity and brevity.

CONTEXT:
{}

REQUIREMENTS:
1. Highlight common themes and patterns
2. Note any significant disagreements or debates
3. Identify any consensus or widely supported views
4. Preserve Reddit's informal, authentic tone
5. Include relevant examples or specific experiences
6. Structure with clear sections:
   - Main Points
   - Areas of Agreement
   - Differing Views (if any)
7. Use **bold** for key insights
8. Keep it concise but informative
9. Add credibility markers (e.g., "Multiple users reported...")
10. Note if certain views are from specific subreddits""".format(chr(10).join(context))
            
            return await self._generate(prompt, model)
            
        except Exception as e:
            print(f"Error synthesizing answer: {str(e)}")
            return "Sorry, I encountered an error while trying to generate a summary."
    
    async def _generate(self, prompt: str, model: str = None) -> str:
        """Make an API call to Ollama for text generation."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model or self.default_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,  # Balance between creativity and consistency
                            "top_p": 0.9,        # Maintain natural language flow
                            "top_k": 40,         # Diverse but relevant token selection
                            "num_predict": 1000,  # Allow for comprehensive responses
                            "stop": ["[END]"]    # Clear end marker
                        }
                    }
                )
                
                if response.status_code == 200:
                    return response.json()["response"].strip()
                else:
                    print(f"Ollama API error: {response.status_code} - {response.text}")
                    raise Exception(f"Ollama API returned status code {response.status_code}")
                    
        except httpx.TimeoutException:
            print("Ollama request timed out")
            if "rewrite" in prompt.lower():
                return prompt.split('"')[1]  # Return original query
            return "I'm still processing your request. This might take a moment due to the complexity of your query. Please wait or try again with a simpler query."
                
        except Exception as e:
            print(f"Error in Ollama request: {str(e)}")
            raise 