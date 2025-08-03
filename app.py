import streamlit as st
import os
import pandas as pd

st.set_page_config(page_title="AMAS Purchase Order System", layout="centered")

def show_sidebar():
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, width=76)
    else:
        st.sidebar.markdown(
            "<span style='color:#b91c1c;font-weight:800;'>[logo.png not found]</span>",
            unsafe_allow_html=True
        )
    st.sidebar.markdown(
        "<div style='font-size:1.07rem;font-weight:700;letter-spacing:0.2px;color:#174e89; margin-bottom:6px; margin-top:0;'>"
        "AMAS Purchase Orders"
        "</div>",
        unsafe_allow_html=True
    )

show_sidebar()

st.markdown(
    """
    <style>
    @media (max-width: 600px) {
        .main .block-container {
            padding-top: 1.1rem;
            padding-bottom: 1rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        h1 {
            font-size: 1.35rem !important;
            margin-bottom: 0.2em !important;
        }
        .stAlert {
            font-size: 1rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- Welcome/Main Content ---
st.markdown("""
# 👋 Welcome to AMAS Purchase Order System

Use the sidebar to access pages such as **Manual PO** and more.
""")

st.info("Go to the sidebar ➡️ and select **Manual PO** to start scanning and creating purchase orders.")

# ---- Caching example (for future heavy data loads) ----
@st.cache_data
def load_orders():
    # Replace with your real file/database/API
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "purchase_orders.csv")
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    else:
        return pd.DataFrame()  # Empty DataFrame

orders_df = load_orders()

if not orders_df.empty:
    st.write("Here are the latest orders:")
    st.dataframe(orders_df)
else:
    st.info("No purchase orders yet! (This table will show once you have orders.)")
