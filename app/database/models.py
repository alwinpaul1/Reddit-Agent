from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class RedditPost(Base):
    __tablename__ = 'posts'
    
    id = Column(String, primary_key=True)
    title = Column(String)
    content = Column(Text)
    subreddit = Column(String)
    author = Column(String)
    score = Column(Integer)
    url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    comments = relationship("RedditComment", back_populates="post")

class RedditComment(Base):
    __tablename__ = 'comments'
    
    id = Column(String, primary_key=True)
    post_id = Column(String, ForeignKey('posts.id'))
    content = Column(Text)
    author = Column(String)
    score = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    post = relationship("RedditPost", back_populates="comments") 