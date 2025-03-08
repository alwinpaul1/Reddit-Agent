import asyncpraw
import aiohttp
import json
import random
import time
from typing import List, Dict, Any, Tuple
import traceback
from app.config.settings import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
from bs4 import BeautifulSoup
import asyncio
import re

class RedditClient:
    def __init__(self):
        print(f"Initializing Reddit client with ID: {REDDIT_CLIENT_ID}")
        self.reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            read_only=True  # Enable read-only mode
        )
        
        # List of realistic user agents
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.2365.66"
        ]
        
        # Request timing
        self.last_request_time = 0
        self.min_request_delay = 2  # Minimum seconds between requests
        
        # Initialize session to None - will be created when needed
        self.session = None
    
    async def close(self):
        """Close all client resources properly."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        
        # Close the PRAW Reddit instance if needed
        if hasattr(self.reddit, 'close') and callable(self.reddit.close):
            await self.reddit.close()
    
    async def search_posts(self, query: str, subreddit: str = None, limit: int = 10, time_filter: str = None) -> List[Dict[str, Any]]:
        try:
            # If subreddit specified, prioritize it
            if subreddit:
                print(f"Searching specifically in subreddit: r/{subreddit}")
                discovered_subreddits = [subreddit]
            else:
                # Otherwise, try to find relevant subreddits 
                discovered_subreddits = await self._discover_subreddits(query)
                print(f"Discovered subreddits: {discovered_subreddits}")
                
                # If still no subreddits found, try some popular ones as fallback
                if not discovered_subreddits:
                    print("No relevant subreddits found, using fallbacks")
                    # Extract potential topic keywords from query
                    keywords = re.findall(r'\b\w{4,}\b', query.lower())
                    if any(kw in ['productivity', 'producti'] for kw in keywords):
                        discovered_subreddits = ['productivity']
                    elif any(kw in ['programming', 'code', 'software', 'developer'] for kw in keywords):
                        discovered_subreddits = ['programming']
                    else:
                        discovered_subreddits = ['AskReddit'] 
            
            # Map time filter to Reddit API parameter
            reddit_time_filter = None
            if time_filter:
                time_mapping = {
                    'today': 'day',
                    'yesterday': 'day',  # Reddit API doesn't have 'yesterday'
                    'this week': 'week',
                    'this month': 'month',
                    'recent': 'month',
                    'latest': 'month', 
                    'new': 'week'
                }
                reddit_time_filter = time_mapping.get(time_filter.lower())
                if reddit_time_filter:
                    print(f"Using time filter: {reddit_time_filter}")
            
            all_posts = []
            tasks = []
            
            # Search in each discovered subreddit
            for sub in discovered_subreddits[:5]:  # Increased to top 5 subreddits for better coverage
                tasks.append(self._search_subreddit(query, sub, limit, reddit_time_filter))
            
            # Run searches in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Combine and deduplicate results
            seen_ids = set()
            for posts in results:
                if isinstance(posts, list):
                    for post in posts:
                        if post['id'] not in seen_ids:
                            all_posts.append(post)
                            seen_ids.add(post['id'])
            
            # Sort by score and limit
            all_posts.sort(key=lambda x: x.get('score', 0), reverse=True)
            return all_posts[:limit]
            
        except Exception as e:
            print(f"Error in search_posts: {str(e)}")
            print(traceback.format_exc())
            return []
    
    async def _discover_subreddits(self, query: str) -> List[str]:
        """
        Find relevant subreddits using two methods:
        1. Reddit's subreddit search API
        2. Two-stage discovery (find posts first, then extract their subreddits)
        """
        try:
            # First check for direct r/ references in query
            direct_subreddits = []
            subreddit_matches = re.findall(r'r/(\w+)', query, re.IGNORECASE)
            if subreddit_matches:
                direct_subreddits = [sub for sub in subreddit_matches]
                print(f"Directly mentioned subreddits in query: {direct_subreddits}")
                if direct_subreddits:
                    return direct_subreddits
            
            discovered_subreddits = set()
            query_lower = query.lower()
            
            # Method 1: Use Reddit's subreddit search API directly
            try:
                headers = {'User-Agent': random.choice(self.user_agents)}
                async with aiohttp.ClientSession(headers=headers) as local_session:
                    url = f"https://www.reddit.com/subreddits/search.json?q={query}&limit=5"
                    
                    await self._delay_request()
                    async with local_session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            for child in data.get('data', {}).get('children', []):
                                subreddit = child.get('data', {}).get('display_name')
                                if subreddit and self._validate_subreddit(subreddit):
                                    discovered_subreddits.add(subreddit)
                            
                            print(f"Subreddits found via Reddit API search: {discovered_subreddits}")
                        
            except Exception as e:
                print(f"Error searching subreddits via API: {e}")
            
            # Method 2: Two-stage discovery - Find posts first, then extract their subreddits
            if len(discovered_subreddits) < 5:  # If we need more subreddits
                try:
                    # Search for posts across all of Reddit
                    search_url = f"https://www.reddit.com/search.json?q={query}&sort=relevance&limit=10"
                    
                    # Create a dedicated session for this specific search
                    headers = {'User-Agent': random.choice(self.user_agents)}
                    async with aiohttp.ClientSession(headers=headers) as local_session2:
                        await self._delay_request()
                        async with local_session2.get(search_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                for child in data.get('data', {}).get('children', []):
                                    subreddit = child.get('data', {}).get('subreddit')
                                    if subreddit and self._validate_subreddit(subreddit):
                                        discovered_subreddits.add(subreddit)
                                
                                print(f"Additional subreddits found via post search: {list(discovered_subreddits)[len(list(discovered_subreddits)) - 5:]}")
                except Exception as e:
                    print(f"Error in two-stage discovery: {e}")
            
            # If no subreddits found from either method, use fallback
            if not discovered_subreddits:
                # Detect specific topic areas to provide better fallback options
                food_terms = ['food', 'recipe', 'cook', 'meal', 'dish', 'pasta', 'pizza', 'dinner', 'lunch', 'breakfast', 'kitchen', 'chef']
                if any(term in query_lower for term in food_terms):
                    discovered_subreddits = {'Cooking', 'food', 'recipes', 'AskCulinary', 'EatCheapAndHealthy'}
                    print(f"Using food-related fallback subreddits: {discovered_subreddits}")
                else:
                    discovered_subreddits = {'AskReddit', 'explainlikeimfive', 'NoStupidQuestions'}
                    print(f"Using general fallback subreddits: {discovered_subreddits}")
            
            return list(discovered_subreddits)[:5]  # Return top 5 unique subreddits
            
        except Exception as e:
            print(f"Error discovering subreddits: {str(e)}")
            traceback.print_exc()
            return ['AskReddit']
    
    def _validate_subreddit(self, subreddit: str) -> bool:
        """Validate subreddit name and filter out NSFW/meme subreddits."""
        # Basic validation
        if not re.match(r'^[A-Za-z0-9_]+$', subreddit):
            return False
        
        # Filter out common NSFW subreddits and meme-focused ones
        nsfw_or_meme_patterns = [
            r'nsfw', r'porn', r'gonewild', r'memes', r'dankmemes', 
            r'circlejerk', r'shitpost', r'funny', r'onlyfans'
        ]
        
        subreddit_lower = subreddit.lower()
        return not any(re.search(pattern, subreddit_lower) for pattern in nsfw_or_meme_patterns)
    
    async def _search_subreddit(self, query: str, subreddit: str, limit: int, time_filter: str = None) -> List[Dict[str, Any]]:
        """Search within a specific subreddit with retries and error handling."""
        try:
            # First try Reddit API
            posts = await self._search_with_api(query, subreddit, limit, time_filter)
            if posts:
                return posts
            
            # If API fails, try web scraping
            print(f"No results from API for r/{subreddit}, trying web scraping...")
            return await self._search_with_scraping(query, subreddit, limit, time_filter)
            
        except Exception as e:
            print(f"Error searching subreddit {subreddit}: {str(e)}")
            return []
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a session with a random user agent."""
        if self.session is None or self.session.closed:
            headers = {'User-Agent': random.choice(self.user_agents)}
            self.session = aiohttp.ClientSession(headers=headers)
        return self.session
    
    async def _delay_request(self):
        """Implement random delay between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_delay:
            delay = self.min_request_delay - time_since_last + random.random()
            await asyncio.sleep(delay)
        
        self.last_request_time = time.time()
    
    async def _search_with_api(self, query: str, subreddit: str = None, limit: int = 10, time_filter: str = None) -> List[Dict[str, Any]]:
        try:
            print(f"Starting Reddit API search with query: {query}, subreddit: {subreddit}")
            
            # Use the existing Reddit instance instead of creating a new one
            reddit = self.reddit
            
            results = []
            
            # Different search approach based on whether a subreddit is specified
            if subreddit:
                print(f"Searching in specific subreddit: {subreddit}")
                
                # Handle common case sensitivity issues for known subreddits
                if subreddit.lower() == "cooking":
                    subreddit = "Cooking"
                
                subreddit_obj = await reddit.subreddit(subreddit)
                
                # Add time filter if specified
                if time_filter:
                    search_generator = subreddit_obj.search(query, limit=limit, sort="relevance", time_filter=time_filter)
                else:
                    search_generator = subreddit_obj.search(query, limit=limit, sort="relevance")
            else:
                print("Searching across Reddit")
                subreddit_obj = await reddit.subreddit("all")
                
                # Add time filter if specified
                if time_filter:
                    search_generator = subreddit_obj.search(query, limit=limit, sort="relevance", time_filter=time_filter)
                else:
                    search_generator = subreddit_obj.search(query, limit=limit, sort="relevance")
            
            async for post in search_generator:
                try:
                    if len(results) >= limit:
                        break
                    formatted_post = await self._format_post(post)
                    results.append(formatted_post)
                    print(f"Found post via API: {post.title}")
                except Exception as post_error:
                    print(f"Error formatting post: {str(post_error)}")
                    continue
            
            print(f"API search completed. Found {len(results)} posts")
            return results
            
        except Exception as e:
            print(f"API search error: {str(e)}")
            return []
            
    async def _search_with_scraping(self, query: str, subreddit: str = None, limit: int = 10, time_filter: str = None) -> List[Dict[str, Any]]:
        """Fallback search using scraping when the API fails."""
        try:
            print(f"Using scraping fallback for search with query: {query}, subreddit: {subreddit}")
            
            # Build the search URL with time filter if specified
            time_param = ""
            if time_filter:
                # Map our time filter to Reddit's t parameter
                time_mapping = {
                    'hour': 'hour',
                    'day': 'day',
                    'week': 'week',
                    'month': 'month',
                    'year': 'year',
                    'all': 'all'
                }
                time_param = f"&t={time_mapping.get(time_filter, 'all')}"
            
            # Construct the search URL
            if subreddit:
                # Handle common case sensitivity issues for known subreddits
                if subreddit.lower() == "cooking":
                    subreddit = "Cooking"
                
                url = f"https://www.reddit.com/r/{subreddit}/search.json?q={query}&limit={limit}&restrict_sr=1{time_param}"
            else:
                url = f"https://www.reddit.com/search.json?q={query}&limit={limit}{time_param}"
            
            # Create a dedicated session for this specific scraping operation
            # This prevents issues with concurrent operations affecting each other
            headers = {'User-Agent': random.choice(self.user_agents)}
            async with aiohttp.ClientSession(headers=headers) as local_session:
                await self._delay_request()
                
                async with local_session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Process the search results
                        posts = []
                        for child in data.get('data', {}).get('children', []):
                            try:
                                post_data = child.get('data', {})
                                
                                # Format the post data
                                post = {
                                    'id': post_data.get('id'),
                                    'title': post_data.get('title'),
                                    'author': post_data.get('author'),
                                    'subreddit': post_data.get('subreddit'),
                                    'score': post_data.get('score', 0),
                                    'upvote_ratio': post_data.get('upvote_ratio', 0),
                                    'url': f"https://www.reddit.com{post_data.get('permalink')}",
                                    'created_utc': post_data.get('created_utc', 0),
                                    'num_comments': post_data.get('num_comments', 0),
                                    'content': post_data.get('selftext', ''),
                                    'is_self': post_data.get('is_self', False),
                                    'link_flair_text': post_data.get('link_flair_text'),
                                    'domain': post_data.get('domain')
                                }
                                
                                # Only add the post if it has meaningful content
                                if post['content'] or not post['is_self']:
                                    posts.append(post)
                                    
                                if len(posts) >= limit:
                                    break
                                    
                            except Exception as post_error:
                                print(f"Error processing scraped post: {str(post_error)}")
                                continue
                        
                        print(f"Scraping search completed. Found {len(posts)} posts")
                        return posts
            
            return []
            
        except Exception as e:
            print(f"Error in scraping search: {str(e)}")
            return []
    
    async def _format_post(self, post) -> Dict[str, Any]:
        try:
            return {
                'id': post.id,
                'title': post.title,
                'content': post.selftext[:1000] if post.selftext else "",
                'subreddit': post.subreddit.display_name,
                'author': str(post.author),
                'score': post.score,
                'url': f"https://reddit.com{post.permalink}",
                'created_at': post.created_utc
            }
        except Exception as e:
            print(f"Error formatting post {post.id if hasattr(post, 'id') else 'unknown'}: {str(e)}")
            raise
    
    async def get_post_comments(self, post_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            submission = await self.reddit.submission(id=post_id)
            await submission.comments.replace_more(limit=0)
            return [await self._format_comment(comment) for comment in submission.comments[:limit]]
        except Exception as e:
            print(f"Error getting comments: {str(e)}")
            return []
    
    async def _format_comment(self, comment) -> Dict[str, Any]:
        return {
            'id': comment.id,
            'content': comment.body,
            'author': str(comment.author),
            'score': comment.score,
            'created_at': comment.created_utc
        } 