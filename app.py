import streamlit as st
import os

st.set_page_config(page_title="AMAS Purchase Order System", layout="wide")

# --- Sidebar: Logo and App Name ---
with st.sidebar:
    # Logo
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=94)
    else:
        st.markdown("<span style='color:#b91c1c;font-weight:800;'>[logo.png not found]</span>", unsafe_allow_html=True)
    # App Name
    st.markdown(
        "<div style='font-size:1.3rem;font-weight:700;letter-spacing:0.4px;color:#174e89; margin-bottom:10px;'>"
        "AMAS Purchase Orders"
        "</div>",
        unsafe_allow_html=True
    )

# --- Welcome/Main Content ---
st.markdown("""
# 👋 Welcome to AMAS Purchase Order System

Use the sidebar to access pages such as **Manual PO** and more.
""")

st.info("Go to the sidebar ➡️ and select **Manual PO** to start scanning and creating purchase orders.")

