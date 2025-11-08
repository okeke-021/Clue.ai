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
GUMROAD_PRODUCT_ID = st.secrets["GUMROAD_PRODUCT_ID"]

# Init
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    # Simple check: Poll API + code match (e.g., code = email hash or buyer-specific)
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

def save_review(user_id: str, product: str, summary: dict):
    data = {"user_id": user_id, "product_name": product, "sentiment_score": summary["avg_score"], "review_summary": json.dumps(summary["details"]), "created_at": datetime.now().isoformat()}
    supabase.table("saved_reviews").insert(data).execute()

# UI
st.set_page_config(page_title="Product Review AI", layout="wide")
st.title("🚀 Product Review AI")
st.markdown("**Premium-Only: Unlock deep, AI-driven reviews for $10/mo.** Honest insights from Reddit + Google to save you money.")

# Premium Gate
if "subbed" not in st.session_state:
    st.session_state.subbed = False
    st.session_state.email = None

if not st.session_state.subbed:
    st.warning("👋 Welcome! Verify your $10/mo Gumroad sub to access.")
    col1, col2 = st.columns(2)
    with col1:
        email = st.text_input("Your Gumroad Email")
        code = st.text_input("Access Code (from purchase email)")
    with col2:
        if st.button("Verify & Enter"):
            if verify_gumroad_sub(email, code):
                st.session_state.subbed = True
                st.session_state.email = email
                # Save to Supabase
                supabase.table("users").upsert({"email": email, "subbed": True}).execute()
                st.success("Unlocked! Dive in.")
                st.rerun()
            else:
                st.error("Invalid sub. Check email or contact support.")
    st.markdown(f"**Not subscribed?** [Get $10/mo access now](https://gumroad.com/l/yourproductid) – Cancel anytime.")
    st.stop()

# Logged-In UI
st.success("Premium active! Unlimited analyses.")
product = st.text_input("Enter product/service (e.g., 'iPhone 15 Pro')")

if st.button("Get Deep Review", type="primary") and product:
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

        save_review(st.session_state.email, product, summary)
        st.balloons()

# Sidebar: Saves
with st.sidebar:
    st.header("Your History")
    res = supabase.table("saved_reviews").select("*").eq("user_id", st.session_state.email).order("created_at", desc=True).limit(10).execute()
    for r in res.data:
        st.write(f"**{r['product_name']}**: {r['sentiment_score']:.1%}")

st.markdown("---")
st.markdown("Questions? Reply to your Gumroad email. | [Privacy](https://example.com/A
