#!/usr/bin/env python
# review_app.py – user reviews only items they bought
import streamlit as st
from PIL import Image
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text

# ───────────────── 1) PostgreSQL engine (shared) ───────────────────────────
@st.cache_resource
def get_engine():
    return create_engine(
        "postgresql+psycopg2://st.secrets("DB_USERNAME"):st.secrets("DB_PW")@st.secrets("DB_HOST"):st.secrets("DB_PORT")/st.secrets("DB_NAME)",
        pool_pre_ping=True,
    )

engine = get_engine()

# ───────────────── 2) Cache product images & names ─────────────────────────
@st.cache_data
def load_products_df() -> pd.DataFrame:
    """Return products (product_id, product_name, image_url)."""
    query = "SELECT product_id, product_name, image_url FROM cyshop.products"
    return pd.read_sql(query, engine).set_index("product_id")

products_df = load_products_df()

# ───────────────── 3) Helper: orders for one user ──────────────────────────
@st.cache_data
def fetch_user_products(user: str) -> pd.DataFrame:
    """
    Return DataFrame of the given user’s distinct product_id’s,
    joined with product_name + image_url.
    """
    sql = """
        SELECT DISTINCT o.product_id
        FROM cyshop.orders o
        WHERE o.name = :user
    """
    user_purchases = pd.read_sql(text(sql), engine, params={"user": user})
    return user_purchases.merge(products_df, on="product_id", how="left")

# ───────────────── 4) UI ───────────────────────────────────────────────────
st.title("🛒  Review Your Purchases")

if "user_name" not in st.session_state:
    st.session_state.user_name = ""

st.session_state.user_name = st.text_input(
    "Your name (exactly as used when ordering):",
    value=st.session_state.user_name,
    max_chars=50,
)

# ===== If no name yet – stop early
if not st.session_state.user_name:
    st.info("Please enter your name to see your purchased items.")
    st.stop()

# ───────── NEW: fetch items the visitor actually bought ─────────
user_items = fetch_user_products(st.session_state.user_name)

if user_items.empty:
    st.warning("No purchases found for this name. Buy something first! 🙂")
    st.stop()

# let them pick one of their own items
item_row = st.selectbox(
    "Pick a product to review:",
    options=user_items.itertuples(index=False),
    format_func=lambda r: f"{r.product_name}",
)

# display product image
image = Image.open(item_row.image_url)
st.image(image, width=450, caption=item_row.product_name)

# write review
review_txt = st.text_area("Write your review here", height=120)

# ───────────────── 5) Insert review on submit ──────────────────────────────
def insert_review(row: dict):
    sql = text(
        """
        INSERT INTO cyshop.product_reviews
              (product_id, user_name, review, ts_utc)
        VALUES (:product_id, :user_name, :review, :ts_utc)
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, row)

if st.button("Submit review"):
    if review_txt.strip():
        review_row = {
            "product_id": int(item_row.product_id),
            "user_name": st.session_state.user_name,
            "review": review_txt.strip(),
            "ts_utc": datetime.utcnow(),
        }
        try:
            insert_review(review_row)
            st.success("Thank you! Your review is saved.")
        except Exception as e:
            st.error(f"Database error: {e}")
    else:
        st.error("Please write something before submitting.")

# ───────────────── 6) Show user’s existing reviews (optional) ──────────────
st.divider()
st.subheader("📣  Reviews from other customers")

sql_prev = """
    SELECT user_name, review, ts_utc
    FROM cyshop.product_reviews
    WHERE product_id = :pid
    ORDER BY ts_utc DESC
"""
prev_df = pd.read_sql(text(sql_prev), engine, params={"pid": item_row.product_id})
if prev_df.empty:
    st.write("No reviews yet – be the first!")
else:
    st.dataframe(prev_df, use_container_width=True)
