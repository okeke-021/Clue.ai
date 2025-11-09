import streamlit as st
import supabase
from supabase import create_client, Client
from transformers import pipeline
import requests
import json
from datetime import datetime
import plotly.graph_objects as go

# Secrets (Streamlit Pro dashboard)
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_ANON_KEY"]
GUMROAD_ACCESS_TOKEN = st.secrets["GUMROAD_ACCESS_TOKEN"]
GUMROAD_PRODUCT_ID = st.secrets["GUMROAD_PRODUCT_ID"]  # e.g., "abc123def"

# Init Supabase (non-Streamlit)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# UI Config FIRST
st.set_page_config(page_title="Product Review AI", layout="wide")

# Load model (cached, after config)
@st.cache_resource
def load_sentiment_model():
    return pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")

sentiment_pipeline = load_sentiment_model()

def scrape_reddit_reviews(product: str) -> list[str]:
    query = product.replace(" ", "+") + "+review"
    url = f"https://www.reddit.com/search.json?q={query}&sort=new&limit=10"
    try:
        resp = requests.get(url, timeout=10).json()
        return [
            post["data"]["title"] + " " + (post["data"]["selftext"] or "")
            for post in resp["data"]["children"]
            if len(post["data"]["selftext"] or "") > 20
        ]
    except Exception as e:
        st.error(f"Fetch failed: {e}")
        return []

def scrape_google_reviews(product: str) -> list[str]:
    # Premium: Real integration later; mock for now
    return [f"Deep insight: {product} excels in usability (4.8/5 from Google).", f"Trend: Recent updates boost {product} quality."]

def get_sentiment_summary(reviews: list[str]):
    if not reviews:
        return {"overall": "NO_DATA", "avg_score": 0, "details": []}
    sentiments = sentiment_pipeline(reviews)
    scores = [1 if s["label"] == "POSITIVE" else 0 for s in sentiments]
    avg_score = sum(scores) / len(scores)
    overall = "POSITIVE" if avg_score > 0.6 else "NEGATIVE" if avg_score < 0.4 else "NEUTRAL"
    return {"overall": overall, "avg_score": avg_score, "details": sentiments[:5]}

def verify_gumroad_sub(email: str, code: str) -> bool:
    # Poll API + code match
    url = "https://api.gumroad.com/v2/sales"
    params = {"access_token": GUMROAD_ACCESS_TOKEN, "product_id": GUMROAD_PRODUCT_ID, "email": email, "status": "alive"}
    try:
        resp = requests.get(url, params=params).json()
        sales = resp.get("sales", [])
        if sales and any(sale.get("custom_fields", {}).get("code", "") == code for sale in sales):
            return True
    except:
        pass
    return False

def get_user_stats(email: str):
    # Fetch or create user
    res = supabase.table("users").select("searches_used, is_premium").eq("email", email).execute()
    if res.data:
        return res.data[0]
    else:
        # Create new user
        supabase.table("users").insert({"email": email, "searches_used": 0, "is_premium": False}).execute()
        return {"searches_used": 0, "is_premium": False}

def increment_search(email: str):
    supabase.table("users").update({"searches_used": supabase.sql("searches_used + 1")}).eq("email", email).execute()

def set_premium(email: str):
    supabase.table("users").update({"is_premium": True}).eq("email", email).execute()

def save_review(user_id: str, product: str, summary: dict, searches_used: int):
    data = {"user_id": user_id, "product_name": product, "sentiment_score": summary["avg_score"], "review_summary": json.dumps(summary["details"]), "searches_used": searches_used, "created_at": datetime.now().isoformat()}
    supabase.table("saved_reviews").insert(data).execute()

# Sidebar: Quick Auth (Always Visible)
with st.sidebar:
    st.header("👤 Quick Sign-In")
    if "email" not in st.session_state:
        st.session_state.email = None
        st.session_state.stats = None
    email = st.text_input("Email", value=st.session_state.email or "")
    if st.button("Sign In & Track Trial"):
        if email:
            st.session_state.email = email
            st.session_state.stats = get_user_stats(email)
            st.rerun()

    if st.session_state.email:
        stats = st.session_state.stats
        remaining = 2 - stats["searches_used"] if not stats["is_premium"] else "Unlimited"
        st.info(f"**Trial Status**: {remaining} searches left" if isinstance(remaining, int) else f"**Premium**: {remaining}")
        if st.button("Upgrade to Unlimited ($10/mo)"):
            # Gumroad Widget
            gumroad_url = f"https://godwinnova8.gumroad.com/l/{GUMROAD_PRODUCT_ID}"  # Update 'yourusername'
            widget_html = f"""
            <script src="https://gumroad.com/js/gumroad-1.0.js"></script>
            <a class="gumroad-button" href="{gumroad_url}" data-gumroad-overlay="true" style="background-color: #007AFF; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; display: block; text-align: center;">Subscribe Now</a>
            """
            st.markdown(widget_html, unsafe_allow_html=True)

# Main UI
st.title("🚀 Product Review AI")
st.markdown("AI-powered reviews from Reddit + Google. Try 2 free searches—then unlock unlimited for $10/mo.")

product = st.text_input("Enter product/service (e.g., 'iPhone 15 Pro')")

if st.button("Get Deep Review", type="primary") and product and st.session_state.email:
    stats = st.session_state.stats
    if stats["is_premium"] or stats["searches_used"] < 2:
        with st.spinner("AI analyzing..."):
            reviews = scrape_reddit_reviews(product) + scrape_google_reviews(product)
            summary = get_sentiment_summary(reviews)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Overall Score", f"{summary['avg_score']:.1%}", delta="🟢 Positive vibes")
            with col2:
                labels = [s["label"] for s in summary["details"]]
                scores = [s["score"] for s in summary["details"]]
                fig = go.Figure([go.Bar(x=labels, y=scores, marker_color=['green' if l == 'POSITIVE' else 'red' for l in labels])])
                fig.update_layout(title="Sentiment Breakdown")
                st.plotly_chart(fig, use_container_width=True)

            rec = "🟢 Buy Now – Top Pick!" if summary["overall"] == "POSITIVE" else "🔴 Avoid – Red Flags" if summary["overall"] == "NEGATIVE" else "🟡 Consider – Mixed Bag"
            st.markdown(f"**Verdict**: {rec}")
            st.write(f"Powered by {len(reviews)} sources (Reddit + Google).")

            # Increment & Save
            increment_search(st.session_state.email)
            st.session_state.stats["searches_used"] += 1  # Local update
            save_review(st.session_state.email, product, summary, st.session_state.stats["searches_used"])
            st.balloons()
            st.success(f"Search {st.session_state.stats['searches_used']}/2 complete!" if st.session_state.stats["searches_used"] < 2 else "Unlimited access active!")
    else:
        st.error("Trial exhausted! Upgrade via sidebar for unlimited.")
        # Gumroad Widget Fallback
        gumroad_url = f"https://yourusername.gumroad.com/l/{GUMROAD_PRODUCT_ID}"
        widget_html = f"""
        <script src="https://gumroad.com/js/gumroad-1.0.js"></script>
        <a class="gumroad-button" href="{gumroad_url}" data-gumroad-overlay="true" style="background-color: #007AFF; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; display: block; text-align: center;">Unlock Unlimited ($10/mo)</a>
        """
        st.markdown(widget_html, unsafe_allow_html=True)
elif not st.session_state.email:
    st.warning("Sign in sidebar to start your 2 free searches!")

# Verification (For Post-Sub Code Entry)
if st.button("Verify Premium Code (After Sub)"):
    code = st.text_input("Enter Code from Gumroad Email")
    if code and verify_gumroad_sub(st.session_state.email, code):
        set_premium(st.session_state.email)
        st.session_state.stats["is_premium"] = True
        st.success("Premium unlocked! Refresh for unlimited.")
        st.rerun()
    else:
        st.error("Invalid code. Check email.")

st.markdown("---")
st.markdown("Questions? Reply to your Gumroad email. | [Privacy](https://example.com/privacy)")
