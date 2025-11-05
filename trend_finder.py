import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import base64 # Used for creating download links for JSON

# --- YouTube API Constants ---
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"
# We need to fetch 'contentDetails' for duration (to guess Shorts/Long-form)
VIDEO_PARTS = "statistics,snippet,contentDetails"

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("🧪 Local Viral Trend Finder Test Bed")
st.markdown("Configure your search parameters to find high-performing videos on small channels.")

# --- Sidebar Configuration (Dynamic Inputs) ---
with st.sidebar:
    st.header("⚙️ Search Configuration")
    
    # 1. API Key Input (Security reminder)
    API_KEY = st.text_input("Enter Your YouTube API Key:", type="password")
    if not API_KEY:
        st.warning("Please enter your API key to run the search.")

    # 2. Search Days
    days = st.slider("Days to Search (Trend Focus)", min_value=1, max_value=30, value=7, step=1)
    
    # 3. Max Subscribers
    max_subs = st.slider("Max Channel Subscribers (Niche Size)", min_value=1000, max_value=10000, value=3000, step=500)
    
    # 4. Minimum Virality Score
    min_virality = st.slider("Min Virality Score (Views / Subscribers)", min_value=1.0, max_value=20.0, value=5.0, step=0.5)

    st.markdown("---")
    st.info("The Virality Score is **Views / (Subscribers + 1)**. A score of 5 means the video has 5x more views than the channel has subscribers.")


# --- Main Keyword Input ---
default_keywords = [
    "Affair Relationship Stories", "Reddit Update", "Reddit Relationship Advice", 
    "Reddit Cheating", "AITA Update", "Open Marriage", "Stories Cheat", 
    "AskReddit Surviving Infidelity", "True Cheating Story", "R/Surviving Infidelity"
]

keyword_input = st.text_area(
    "Seed Keywords (Comma or Newline Separated):", 
    value="\n".join(default_keywords),
    height=200
)
# Clean up and parse keywords
keywords = [k.strip() for k in keyword_input.split('\n') if k.strip()]
if not keywords:
    st.error("Please enter at least one keyword.")

# --- Functions for Logic ---

def get_seconds(duration_str):
    """Converts YouTube API duration string (e.g., PT1M30S) to seconds."""
    import re
    match = re.match('PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match: return 0
    h, m, s = [int(x) if x else 0 for x in match.groups()]
    return h * 3600 + m * 60 + s

def get_video_type(duration_seconds):
    """Classifies video as Short or Long based on duration."""
    # YouTube Shorts are typically 60 seconds or less
    return "Shorts (<= 60s)" if duration_seconds > 0 and duration_seconds <= 60 else "Long Form (> 60s)"

# --- Fetch Data Button and Core Logic ---

if st.button("🚀 Start Trend Analysis", disabled=not API_KEY or not keywords):
    st.write("---")
    
    if API_KEY == "":
        st.warning("Please enter a valid API Key to proceed.")
        st.stop()

    try:
        # Calculate date range
        start_date = (datetime.utcnow() - timedelta(days=int(days))).isoformat("T") + "Z"
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # --- 1. Fetch Video IDs and Snippets ---
        st.subheader("1. Searching Videos...")
        
        # Collect all IDs across all keywords first to batch fetch stats
        all_video_ids = []
        all_channel_ids = []
        video_snippets_map = {} # Store snippets for later use

        for i, keyword in enumerate(keywords):
            status_text.text(f"🔍 Searching for keyword: {keyword} ({i+1}/{len(keywords)})")
            progress_bar.progress((i + 1) / len(keywords))

            search_params = {
                "part": "snippet",
                "q": keyword,
                "type": "video",
                "order": "viewCount",
                "publishedAfter": start_date,
                "maxResults": 50, # Max results per page
                "videoDimension": "any", # Ensures Shorts and Long-form are included
                "key": API_KEY,
            }

            response = requests.get(YOUTUBE_SEARCH_URL, params=search_params)
            data = response.json()

            if "items" in data and data["items"]:
                for video in data["items"]:
                    v_id = video["id"].get("videoId")
                    c_id = video["snippet"].get("channelId")
                    
                    if v_id and c_id and v_id not in all_video_ids:
                        all_video_ids.append(v_id)
                        all_channel_ids.append(c_id)
                        video_snippets_map[v_id] = video["snippet"]
            
        progress_bar.empty()
        status_text.empty()
        st.success(f"Found {len(all_video_ids)} unique video IDs to analyze.")

        # --- 2. Batch Fetch Video and Channel Statistics ---
        st.subheader("2. Fetching Statistics...")

        # Remove duplicates from channel IDs before fetching
        unique_channel_ids = list(set(all_channel_ids))
        
        # Batch fetching for statistics is faster and reduces API calls
        
        # Fetch Video Statistics (in batches of 50 to respect API limit)
        video_stats_map = {}
        for i in range(0, len(all_video_ids), 50):
            batch_ids = all_video_ids[i:i+50]
            stats_params = {"part": VIDEO_PARTS, "id": ",".join(batch_ids), "key": API_KEY}
            stats_response = requests.get(YOUTUBE_VIDEO_URL, params=stats_params)
            stats_data = stats_response.json()
            if "items" in stats_data:
                for item in stats_data["items"]:
                    video_stats_map[item['id']] = item
            st.info(f"Fetched video stats for {i+len(batch_ids)}/{len(all_video_ids)} videos.")


        # Fetch Channel Statistics (in batches of 50)
        channel_stats_map = {}
        for i in range(0, len(unique_channel_ids), 50):
            batch_ids = unique_channel_ids[i:i+50]
            channel_params = {"part": "statistics,snippet", "id": ",".join(batch_ids), "key": API_KEY}
            channel_response = requests.get(YOUTUBE_CHANNEL_URL, params=channel_params)
            channel_data = channel_response.json()
            if "items" in channel_data:
                for item in channel_data["items"]:
                    channel_stats_map[item['id']] = item
            st.info(f"Fetched channel stats for {i+len(batch_ids)}/{len(unique_channel_ids)} channels.")

        # --- 3. Process, Filter, and Calculate Virality ---
        st.subheader("3. Filtering Results...")
        
        final_results = []
        for v_id in all_video_ids:
            snippet = video_snippets_map.get(v_id)
            stat = video_stats_map.get(v_id)
            
            if not snippet or not stat: continue

            c_id = snippet.get("channelId")
            channel_stat = channel_stats_map.get(c_id)
            
            if not channel_stat: continue

            # Get Stats
            views = int(stat["statistics"].get("viewCount", 0))
            # Handle hidden subscriber count
            subs = int(channel_stat["statistics"].get("subscriberCount", 0))
            duration_str = stat["contentDetails"].get("duration", "PT0S")
            duration_seconds = get_seconds(duration_str)
            video_type = get_video_type(duration_seconds)
            
            # Filter 1: Small Channel Check
            if subs <= max_subs:
                # Calculate Virality Score: Views / (Subscribers + 1)
                virality_score = views / (subs + 1)
                
                # Filter 2: Virality Score Check
                if virality_score >= min_virality:
                    
                    # Calculate Days Published
                    published_at_str = snippet["publishedAt"]
                    published_date = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%S%z")
                    days_published = (datetime.utcnow().replace(tzinfo=None) - published_date.replace(tzinfo=None)).days

                    final_results.append({
                        "Video_ID": v_id,
                        "Title": snippet.get("title", "N/A"),
                        "Channel_Title": snippet.get("channelTitle", "N/A"),
                        "Video_Type": video_type,
                        "Views": views,
                        "Subscribers": subs,
                        "Virality_Score": round(virality_score, 2),
                        "Days_Published": days_published,
                        "Link": f"https://www.youtube.com/watch?v={v_id}",
                        "Description_Snippet": snippet.get("description", "")[:100] + "...",
                    })

        # --- 4. Display and Download Results ---
        st.write("---")
        
        if final_results:
            df = pd.DataFrame(final_results)
            
            # Sort by Virality Score (highest first)
            df_sorted = df.sort_values(by="Virality_Score", ascending=False).reset_index(drop=True)
            
            st.success(f"✅ Found **{len(df_sorted)}** potential viral videos meeting all criteria!")
            
            st.subheader("📈 Viral Trend Data Table")
            
            # Allow post-search filtering by video type (Shorts/Long-form)
            video_types = df_sorted['Video_Type'].unique()
            selected_types = st.multiselect("Filter by Video Type:", video_types, default=video_types)
            df_filtered = df_sorted[df_sorted['Video_Type'].isin(selected_types)]
            
            st.dataframe(
                df_filtered,
                column_config={
                    "Virality_Score": st.column_config.NumberColumn("🔥 SCORE", format="%.2f"),
                    "Link": st.column_config.LinkColumn("Watch Video", display_text="🔗 Link"),
                    "Views": st.column_config.NumberColumn("Views", format="%.0f"),
                    "Subscribers": st.column_config.NumberColumn("Subs", format="%.0f"),
                    "Days_Published": st.column_config.NumberColumn("Days Old", format="%d"),
                    "Description_Snippet": st.column_config.Column("Description", width="small")
                },
                hide_index=True,
                # NEW CODE (Fixes Warning)
                width='stretch'
            )

            # --- Download Buttons ---
            
            # 1. CSV Download
            csv_data = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Filtered Data (CSV)",
                data=csv_data,
                file_name='viral_trends_data.csv',
                mime='text/csv',
                key='csv_download'
            )

            # 2. JSON Download
            json_string = df_filtered.to_json(orient='records', indent=4)
            b64 = base64.b64encode(json_string.encode()).decode()
            href = f'<a href="data:file/json;base64,{b64}" download="viral_trends_data.json">📥 Download Filtered Data (JSON)</a>'
            st.markdown(href, unsafe_allow_html=True)
            

        else:
            st.warning("No videos found that meet the strict criteria (small channel, high virality, and published recently). Try adjusting your parameters.")

    except requests.exceptions.HTTPError as e:
        st.error(f"❌ YouTube API Error: Ensure your API Key is correct and not rate-limited. Error details: {e}")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")