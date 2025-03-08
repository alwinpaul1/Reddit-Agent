import chromadb
import os
from typing import List, Dict, Any
from app.config.settings import BASE_DIR
import numpy as np
from datetime import datetime

class VectorStore:
    def __init__(self):
        """Initialize the vector store with ChromaDB for semantic search capabilities."""
        # Create data directory if it doesn't exist
        data_dir = os.path.join(BASE_DIR, "data", "chroma")
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(path=data_dir)
        
        # Configure collection with enhanced cosine similarity settings
        try:
            self.collection = self.client.get_collection("reddit_posts")
        except:
            self.collection = self.client.create_collection(
                name="reddit_posts",
                metadata={
                    "hnsw:space": "cosine",
                    "hnsw:construction_ef": 400,  # Increased for better index quality
                    "hnsw:search_ef": 200,  # Increased for better search quality
                    "hnsw:m": 64,  # Number of connections per element
                    "hnsw:ef_runtime": 100  # Runtime accuracy vs speed trade-off
                }
            )
    
    def add_posts(self, posts: List[Dict[str, Any]]) -> None:
        """Add posts to the vector store for semantic search.
        
        Args:
            posts: List of post dictionaries containing title, content, etc.
        """
        if not posts:
            return
            
        # Prepare documents, ids, and metadata
        documents = []
        ids = []
        metadatas = []
        
        for post in posts:
            # Create rich document representation for better embeddings
            doc = self._create_document_representation(post)
            documents.append(doc)
            
            # Use post ID as document ID
            ids.append(str(post['id']))
            
            # Calculate engagement metrics
            comment_count = float(post.get('num_comments', 0))
            score = float(post.get('score', 0))
            engagement_score = self._calculate_engagement_score(score, comment_count)
            
            # Parse and process timestamp
            created_at = post.get('created_at', '')
            time_relevance = self._calculate_time_relevance(created_at)
            
            # Store full post data in metadata with enhanced fields
            metadatas.append({
                'title': post['title'],
                'content': post['content'],
                'author': post['author'],
                'subreddit': post['subreddit'],
                'score': score,
                'url': post['url'],
                'created_at': created_at,
                'doc_length': len(doc.split()),
                'title_length': len(post['title'].split()),
                'engagement_score': engagement_score,
                'time_relevance': time_relevance,
                'num_comments': comment_count,
                'has_awards': bool(post.get('awards', False)),
                'is_original_content': bool(post.get('is_original_content', False))
            })
        
        # Add to collection with optimized settings
        self.collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas
        )
    
    def search_similar(self, query: str, limit: int = 5, min_similarity: float = 0.3) -> List[Dict[str, Any]]:
        """Search for posts semantically similar to the query.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0-1)
            
        Returns:
            List of post dictionaries with similarity scores
        """
        try:
            # Enhance query for better semantic matching
            enhanced_query = self._enhance_query(query)
            
            # Get more results initially for better filtering
            initial_limit = min(limit * 3, 20)
            
            # Perform semantic search with enhanced parameters
            results = self.collection.query(
                query_texts=[enhanced_query],
                n_results=initial_limit,
                include=['metadatas', 'distances', 'documents']
            )
            
            if not results['ids'][0]:  # No results found
                return []
            
            # Format and filter results with enhanced scoring
            formatted_results = []
            for i in range(len(results['ids'][0])):
                base_similarity = 1 - results['distances'][0][i]  # Convert distance to similarity
                
                # Skip results below minimum similarity threshold
                if base_similarity < min_similarity:
                    continue
                
                metadata = results['metadatas'][0][i]
                doc = results['documents'][0][i]
                
                # Apply score boosting based on various factors
                final_similarity = self._calculate_final_similarity(
                    base_similarity=base_similarity,
                    metadata=metadata,
                    query=query,
                    document=doc
                )
                
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'title': metadata.get('title', ''),
                    'content': metadata.get('content', ''),
                    'author': metadata.get('author', ''),
                    'subreddit': metadata.get('subreddit', ''),
                    'score': metadata.get('score', 0),
                    'url': metadata.get('url', ''),
                    'created_at': metadata.get('created_at', ''),
                    'similarity': final_similarity,
                    'engagement_score': metadata.get('engagement_score', 0),
                    'num_comments': metadata.get('num_comments', 0),
                    'has_awards': metadata.get('has_awards', False),
                    'is_original_content': metadata.get('is_original_content', False)
                })
            
            # Sort by final similarity score and limit results
            formatted_results.sort(key=lambda x: x['similarity'], reverse=True)
            return formatted_results[:limit]
            
        except Exception as e:
            print(f"Error searching vector store: {str(e)}")
            return []
    
    def _create_document_representation(self, post: Dict[str, Any]) -> str:
        """Create a rich document representation for better semantic embeddings."""
        # Combine fields with special tokens and weights
        doc_parts = [
            f"[TITLE] {post['title']} [/TITLE]",  # Title gets special emphasis
            f"[CONTENT] {post['content']} [/CONTENT]",
            f"[SUBREDDIT] r/{post['subreddit']} [/SUBREDDIT]",
            f"[AUTHOR] u/{post['author']} [/AUTHOR]"
        ]
        
        # Add engagement signals
        if post.get('score'):
            doc_parts.append(f"[SCORE] {post['score']} [/SCORE]")
        if post.get('num_comments'):
            doc_parts.append(f"[COMMENTS] {post['num_comments']} [/COMMENTS]")
        if post.get('awards'):
            doc_parts.append("[AWARDED] true [/AWARDED]")
        if post.get('is_original_content'):
            doc_parts.append("[OC] true [/OC]")
        
        return "\n".join(doc_parts)
    
    def _enhance_query(self, query: str) -> str:
        """Enhance the query for better semantic matching."""
        # Clean and normalize query
        query = query.strip().lower()
        
        # Remove common Reddit-specific terms that might bias the search
        query = query.replace('reddit', '').replace('subreddit', '')
        query = query.replace('r/', '').replace('u/', '')
        
        # Add context markers for better matching
        return f"[QUERY] {query} [/QUERY]"
    
    def _calculate_final_similarity(
        self,
        base_similarity: float,
        metadata: Dict[str, Any],
        query: str,
        document: str
    ) -> float:
        """Calculate final similarity score with various boosting factors."""
        score = base_similarity
        
        # Length normalization factor (penalize extremely short or long documents)
        doc_length = metadata.get('doc_length', 0)
        if doc_length > 0:
            length_factor = 1.0
            if doc_length < 20:  # Very short
                length_factor = 0.8
            elif doc_length > 1000:  # Very long
                length_factor = 0.9
            score *= length_factor
        
        # Engagement boost (combines Reddit score, comments, and awards)
        engagement_score = metadata.get('engagement_score', 0)
        if engagement_score > 0:
            engagement_boost = min(0.2, np.log1p(engagement_score) / 100)
            score = min(1.0, score * (1 + engagement_boost))
        
        # Time relevance boost
        time_relevance = metadata.get('time_relevance', 1.0)
        score *= time_relevance
        
        # Title match boost
        title = metadata.get('title', '').lower()
        query_terms = set(query.lower().split())
        title_terms = set(title.split())
        title_match_ratio = len(query_terms.intersection(title_terms)) / len(query_terms)
        if title_match_ratio > 0:
            title_boost = title_match_ratio * 0.1
            score = min(1.0, score * (1 + title_boost))
        
        # Original content boost
        if metadata.get('is_original_content', False):
            score = min(1.0, score * 1.1)  # 10% boost for OC
        
        return score
    
    def _calculate_engagement_score(self, score: float, num_comments: float) -> float:
        """Calculate a normalized engagement score combining votes and comments."""
        # Log scale to prevent extreme scores from dominating
        log_score = np.log1p(max(0, score))
        log_comments = np.log1p(max(0, num_comments))
        
        # Weighted combination (comments weighted slightly higher than score)
        return (log_score + 1.2 * log_comments) / 2.2
    
    def _calculate_time_relevance(self, created_at: str | float) -> float:
        """Calculate time relevance factor (1.0 = most recent, decreasing with age)."""
        try:
            if not created_at:
                return 1.0
            
            # Handle both string and float timestamp formats
            if isinstance(created_at, str):
                created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                # If it's a float/int timestamp, convert from Unix timestamp
                created_time = datetime.fromtimestamp(float(created_at))
                
            now = datetime.now()
            age_hours = (now - created_time).total_seconds() / 3600
            
            # Decay function: starts at 1.0, decays to 0.7 over time
            decay_rate = 0.3  # Maximum decay of 30%
            decay_period = 168  # One week in hours
            
            time_factor = 1.0 - (decay_rate * min(1.0, age_hours / decay_period))
            return max(0.7, time_factor)  # Never decay below 0.7
            
        except Exception as e:
            print(f"Error calculating time relevance: {str(e)}")
            return 1.0 