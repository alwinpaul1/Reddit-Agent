// This is a placeholder TypeScript file to satisfy the tsconfig.json requirements
// It's not actually used in the application

/**
 * Simple interface for demonstration purposes
 */
interface RedditPost {
  id: string;
  title: string;
  content?: string;
  author: string;
  subreddit: string;
  score: number;
  url: string;
}

/**
 * Placeholder function
 */
function formatPost(post: RedditPost): string {
  return `${post.title} by u/${post.author} in r/${post.subreddit}`;
}

export { RedditPost, formatPost }; 