# Reddit Search & Summarization Chatbot

A local, free, and open-source project that enables you to search, index, and summarize Reddit content using Ollama for local LLM inference.

## Prerequisites

1. Python 3.8+
2. [Ollama](https://github.com/jmorganca/ollama) installed and running locally
3. Reddit API credentials (create them at https://www.reddit.com/prefs/apps)

## Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd reddit-agent
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy the environment template and fill in your credentials:
```bash
cp .env.template .env
```

5. Edit the `.env` file with your Reddit API credentials and preferred settings.

## Running the Application

1. Make sure Ollama is running and the model is downloaded:
```bash
ollama pull llama2
```

2. Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

3. Open your browser and navigate to http://localhost:8000

## Features

- Search Reddit posts by query and subreddit
- Summarize post content using local LLM
- Ask questions about specific posts
- Modern web interface built with TailwindCSS
- All processing done locally - no external API calls except Reddit

## API Endpoints

- `GET /` - Web interface
- `POST /search` - Search Reddit posts
- `POST /summarize/{post_id}` - Generate post summary
- `POST /ask` - Ask questions about a post

## Contributing

Feel free to open issues and pull requests! 