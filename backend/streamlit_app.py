"""
Streamlit UI for Data Center News Chatbot
Run with: streamlit run streamlit_app.py
"""
import streamlit as st
import requests
import os
from datetime import datetime
import time

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Page configuration
st.set_page_config(
    page_title="Data Center News Chatbot",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A5F;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
    }
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .source-link {
        padding: 0.5rem;
        background: #f0f2f6;
        border-radius: 5px;
        margin: 0.3rem 0;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .user-message {
        background: #e3f2fd;
        border-left: 4px solid #2196F3;
    }
    .bot-message {
        background: #f5f5f5;
        border-left: 4px solid #4CAF50;
    }
</style>
""", unsafe_allow_html=True)


def get_stats():
    """Fetch statistics from the API"""
    try:
        response = requests.get(f"{API_URL}/api/stats", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.warning(f"Could not fetch stats: {e}")
    return None


def chat(query: str):
    """Send a chat query to the API"""
    try:
        response = requests.post(
            f"{API_URL}/api/chat",
            json={"query": query},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"answer": f"Error: {response.status_code} - {response.text}", "sources": []}
    except requests.exceptions.ConnectionError:
        return {
            "answer": "⚠️ Cannot connect to the API server. Please make sure the FastAPI backend is running on " + API_URL,
            "sources": []
        }
    except Exception as e:
        return {"answer": f"Error: {str(e)}", "sources": []}


def trigger_scrape():
    """Trigger a manual scrape"""
    try:
        response = requests.post(f"{API_URL}/api/scrape", timeout=5)
        return response.status_code == 200
    except:
        return False


# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_stats_fetch" not in st.session_state:
    st.session_state.last_stats_fetch = 0
    st.session_state.cached_stats = None


# Header
st.markdown('<p class="main-header">🏢 Data Center News Chatbot</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Ask questions about the latest data center industry news and trends</p>', unsafe_allow_html=True)

# Sidebar with stats and info
with st.sidebar:
    st.header("📊 Knowledge Base Stats")
    
    # Fetch stats with caching
    current_time = time.time()
    if current_time - st.session_state.last_stats_fetch > 30:  # Refresh every 30 seconds
        st.session_state.cached_stats = get_stats()
        st.session_state.last_stats_fetch = current_time
    
    stats = st.session_state.cached_stats
    
    if stats:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📰 Total Articles", stats.get("total_articles", 0))
        with col2:
            st.metric("🔍 Indexed", stats.get("articles_with_embeddings", 0))
        
        st.metric("🗄️ Vector Store Size", stats.get("vector_store_size", 0))
        
        if stats.get("is_free"):
            st.success("✅ Using free AI providers")
        else:
            cost_stats = stats.get("cost_stats")
            if cost_stats:
                st.info(f"💰 Today's cost: ${cost_stats.get('daily_cost', 0):.4f}")
    else:
        st.info("📡 Connecting to API...")
    
    st.divider()
    
    st.header("ℹ️ About")
    st.markdown("""
    This chatbot scrapes news from:
    - 📡 RSS Feeds (Data Center Dynamics, etc.)
    - 🔍 Google News
    - 💬 Reddit (r/datacenter, r/sysadmin)
    - 🐦 Twitter/X
    - 🌐 Industry websites
    
    Articles are indexed with vector embeddings for semantic search.
    """)
    
    st.divider()
    
    st.header("💡 Sample Questions")
    sample_questions = [
        "What are the latest data center construction projects?",
        "Tell me about hyperscale data center trends",
        "What's happening with data center sustainability?",
        "Latest news about Equinix or Digital Realty?",
        "What are the current data center cooling innovations?",
    ]
    
    for q in sample_questions:
        if st.button(q, key=f"sample_{q[:20]}", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": q})
            with st.spinner("Thinking..."):
                response = chat(q)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response.get("answer", "No response"),
                    "sources": response.get("sources", [])
                })
            st.rerun()

# Main chat interface
st.header("💬 Chat")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Show sources for assistant messages
        if message["role"] == "assistant" and message.get("sources"):
            with st.expander("📚 Sources", expanded=False):
                for source in message["sources"]:
                    st.markdown(f"**[{source.get('title', 'Untitled')}]({source.get('url', '#')})**")
                    st.caption(f"Source: {source.get('source', 'Unknown')}")

# Chat input
if prompt := st.chat_input("Ask about data center news..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Searching knowledge base..."):
            response = chat(prompt)
            answer = response.get("answer", "Sorry, I couldn't find an answer.")
            sources = response.get("sources", [])
            
            st.markdown(answer)
            
            if sources:
                with st.expander("📚 Sources", expanded=True):
                    for source in sources:
                        st.markdown(f"**[{source.get('title', 'Untitled')}]({source.get('url', '#')})**")
                        st.caption(f"Source: {source.get('source', 'Unknown')}")
    
    # Save to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources
    })

# Footer
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()
with col2:
    if st.button("🔄 Refresh Stats"):
        st.session_state.last_stats_fetch = 0
        st.rerun()
with col3:
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
