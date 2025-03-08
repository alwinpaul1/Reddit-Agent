from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from app.utils.reddit_client import RedditClient
from app.utils.ollama_client import OllamaClient
from app.utils.vector_store import VectorStore
from datetime import datetime
import os
import re

app = FastAPI(title="Reddit Search & Summarization")

# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create static files directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Favicon endpoint
@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(static_dir, "favicon.ico")
    
    # Create a default favicon if it doesn't exist
    if not os.path.exists(favicon_path):
        import base64
        # Default Reddit-like favicon (base64 encoded)
        favicon_b64 = "AAABAAEAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAIAAAAAAAAAQAAMMOAADDDgAAAAAAAAAAAAD9/f3/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//9/f3/+/v7//n5+f/5+fn/+fn5//n5+f/5+fn/+fn5//n5+f/5+fn/+fn5//n5+f/5+fn/+fn5//n5+f/5+fn/+/v7//v7+//5+fn/9vb2//Hx8f/v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//7+/v//Hx8f/29vb/+fn5//v7+//7+/v/+fn5//b29v/m5ub/3Nzc/9zc3P/c3Nz/3Nzc/9zc3P/c3Nz/3Nzc/9zc3P/m5ub/9vb2//n5+f/7+/v/+/v7//n5+f/29vb/5ubm/9zc3P/c3Nz/3Nzc/9zc3P/c3Nz/3Nzc/9zc3P/c3Nz/5ubm//b29v/5+fn/+/v7//v7+//5+fn/9vb2/+bm5v/c3Nz/3Nzc/9zc3P/c3Nz/3Nzc/9zc3P/c3Nz/3Nzc/+bm5v/29vb/+fn5//v7+//7+/v/+fn5//b29v/m5ub/3Nzc/9zc3P/c3Nz/3Nzc/9zc3P/c3Nz/3Nzc/9zc3P/m5ub/9vb2//n5+f/7+/v/+/v7//n5+f/29vb/8fHx/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//8fHx//b29v/5+fn/+/v7//v7+//5+fn/+fn5//n5+f/5+fn/+fn5//n5+f/5+fn/+fn5//n5+f/5+fn/+fn5//n5+f/5+fn/+fn5//v7+//9/f3/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//7+/v/+/v7//v7+//9/f3/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
        with open(favicon_path, "wb") as f:
            f.write(base64.b64decode(favicon_b64))
    
    return FileResponse(favicon_path)

# Initialize clients
reddit_client = RedditClient()
ollama_client = OllamaClient()
vector_store = VectorStore()

# Add startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize clients and resources on application startup."""
    print("Starting up Reddit Agent application...")
    # Clients are already initialized, no additional action needed

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on application shutdown."""
    print("Shutting down Reddit Agent application...")
    # Properly close the Reddit client session
    await reddit_client.close()
    print("Resources cleaned up successfully")

# Templates
templates = Jinja2Templates(directory="app/templates")

class SearchRequest(BaseModel):
    query: str
    subreddit: Optional[str] = None
    limit: Optional[int] = 10
    model: Optional[str] = "llama2"

class SearchResponse(BaseModel):
    original_query: str
    rewritten_query: str
    posts: List[dict]
    summary: str

class QuestionRequest(BaseModel):
    post_id: str
    question: str

@app.get("/", response_class=HTMLResponse)
async def home():
    try:
        homepage_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "homepage.html")
        if os.path.exists(homepage_path):
            return FileResponse(homepage_path)
        else:
            return f"""
            <html>
                <head><title>Error</title></head>
                <body>
                    <h1>Error loading homepage</h1>
                    <p>File not found: {homepage_path}</p>
                </body>
            </html>
            """
    except Exception as e:
        return f"""
    <html>
            <head><title>Error</title></head>
        <body>
                <h1>Error loading homepage</h1>
                <p>{str(e)}</p>
        </body>
    </html>
    """

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Search Reddit posts and generate a comprehensive summary.
    
    This endpoint provides:
    1. Efficient content discovery through optimized search
    2. Enhanced relevance using semantic search
    3. Time-saving summaries of discussions
    4. Privacy-conscious local processing
    """
    try:
        # Extract subreddit from query if specified but not provided as a parameter
        subreddit_from_query = None
        if not request.subreddit:
            # Look for subreddit mentions with case preservation
            subreddit_match = re.search(r'(?:r/|subreddit\s+)(\w+)', request.query, re.IGNORECASE)
            if subreddit_match:
                # Get the original capitalization from the match
                subreddit_from_query = subreddit_match.group(1)
                # For the special case of "cooking", capitalize to "Cooking" which is the correct Reddit name
                if subreddit_from_query.lower() == "cooking":
                    subreddit_from_query = "Cooking"
                print(f"Extracted subreddit from query: r/{subreddit_from_query}")
        
        # Extract time period from query for time-sensitive searches
        time_period = None
        if re.search(r'\b(today|yesterday|this week|this month|recent|latest|new)\b', request.query, re.IGNORECASE):
            time_match = re.search(r'\b(today|yesterday|this week|this month|recent|latest|new)\b', request.query, re.IGNORECASE)
            if time_match:
                time_period = time_match.group(1).lower()
                print(f"Detected time period in query: {time_period}")
        
        # 1. Rewrite the query using LLM for better content discovery
        print(f"Optimizing search query using {request.model}...")
        rewritten_query = await ollama_client.rewrite_query(request.query, model=request.model)
        print(f"Using search terms: \"{rewritten_query}\"")
        
        # 2. Fetch posts from Reddit with enhanced metadata
        print("Discovering relevant content from Reddit...")
        posts = await reddit_client.search_posts(
            query=rewritten_query,
            subreddit=request.subreddit or subreddit_from_query,
            limit=request.limit,
            time_filter=time_period
        )
        print(f"Found {len(posts)} relevant discussions")
        
        if not posts:
            return {
                "original_query": request.query,
                "rewritten_query": rewritten_query,
                "posts": [],
                "summary": "No relevant discussions found. Try adjusting your search terms or exploring a different subreddit."
            }
        
        # 3. Process posts through vector store for semantic relevance
        print("Analyzing content relevance...")
        try:
            # Store posts with enhanced metadata
            vector_store.add_posts(posts)
            
            # Find semantically similar posts with improved ranking
            print("Finding most relevant discussions...")
            similar_posts = vector_store.search_similar(rewritten_query)
            print(f"Identified {len(similar_posts)} highly relevant discussions")
            
            # Use similar posts if available, otherwise use top posts
            posts_for_summary = similar_posts if similar_posts else posts[:5]
            
            # Sort posts by engagement and relevance
            posts_for_summary.sort(
                key=lambda x: (
                    x.get('similarity', 0) * 0.6 +  # 60% weight on semantic similarity
                    x.get('engagement_score', 0) * 0.3 +  # 30% weight on engagement
                    x.get('time_relevance', 0) * 0.1  # 10% weight on recency
                ),
                reverse=True
            )
            
        except Exception as e:
            print(f"Vector store processing error: {str(e)}")
            # Fallback to basic post ranking if vector store fails
            posts_for_summary = sorted(
                posts[:5],
                key=lambda x: float(x.get('score', 0)) + float(x.get('num_comments', 0)) * 2,
                reverse=True
            )
        
        # 4. Generate comprehensive summary using LLM
        print(f"Synthesizing insights using {request.model}...")
        summary = await ollama_client.synthesize_answer(
            request.query,
            posts_for_summary,
            model=request.model
        )
        
        # 5. Return enhanced response with metadata
        return {
            "original_query": request.query,
            "rewritten_query": rewritten_query,
            "posts": [
                {
                    **post,
                    "relevance_score": post.get('similarity', 0),
                    "engagement_score": post.get('engagement_score', 0),
                    "time_relevance": post.get('time_relevance', 1.0),
                    "is_original_content": post.get('is_original_content', False),
                    "has_awards": post.get('has_awards', False)
                }
                for post in posts_for_summary
            ],
            "summary": summary,
            "metadata": {
                "total_posts_found": len(posts),
                "processing_approach": "semantic_search" if similar_posts else "basic_ranking",
                "subreddit": request.subreddit,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        print(f"Search error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your search. Please try again."
        )

@app.post("/summarize/{post_id}")
async def summarize_post(post_id: str):
    try:
        post = await reddit_client.reddit.submission(id=post_id)
        summary = await ollama_client.generate_summary(post.selftext)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    try:
        post = await reddit_client.reddit.submission(id=request.post_id)
        context = f"Title: {post.title}\n\nContent: {post.selftext}"
        answer = await ollama_client.answer_question(context, request.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test", response_class=HTMLResponse)
async def test():
    return """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Test Page</h1>
            <p>This is a test page to check if the server is working correctly.</p>
        </body>
    </html>
    """

# If running this file directly, start the server
if __name__ == "__main__":
    import uvicorn
    import argparse
    import socket
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run the Reddit Search & Summarization API")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the server to")
    parser.add_argument("--public", action="store_true", help="Make the server publicly accessible")
    
    args = parser.parse_args()
    
    # If --public flag is used, bind to all interfaces
    if args.public:
        host = "0.0.0.0"
        print(f"⚠️  WARNING: Running in public mode. Your API will be accessible to anyone on your network.")
        print(f"⚠️  For security, consider using a reverse proxy with authentication for production use.")
        
        # Get local IP for easier access
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = '127.0.0.1'
        finally:
            s.close()
            
        print(f"🔗 Access locally at: http://{local_ip}:{args.port}")
        print(f"🔗 For external access, set up port forwarding to {local_ip}:{args.port}")
    else:
        host = args.host
        print(f"🚀 Starting server at http://{host}:{args.port}")
    
    uvicorn.run("app.main:app", host=host, port=args.port, reload=True) 