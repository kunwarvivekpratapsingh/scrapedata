import streamlit as st
import requests
import subprocess

# Apply custom CSS for styling
st.markdown(
    """
    <style>
        .stTextArea { width: 100%; font-size: 16px; }
        .stButton>button { width: 100%; font-size: 18px; background-color: #4CAF50; color: white; }
        .stMarkdown pre { background: #f4f4f4; padding: 15px; border-radius: 5px; }
    </style>
    """,
    unsafe_allow_html=True
)

def analyze_merchant_url(url):
    """Call external script to analyze merchant URL."""
    try:
        result = subprocess.run(["python", "analyze_url.py", url], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else "Error analyzing URL"
    except Exception as e:
        return f"Error: {str(e)}"

# Streamlit UI
st.set_page_config(page_title="Merchant URL Analyzer", page_icon="🔍", layout="centered")

st.title("🔍 Merchant URL Analyzer")
st.write("Enter a merchant URL below and click Analyze to get insights.")

# Input text area
url_input = st.text_input("Enter Merchant URL:")

# Analyze button
if st.button("Analyze URL", use_container_width=True):
    if url_input.strip():
        st.subheader("🔍 Analysis Result")
        with st.spinner("Analyzing URL..."):
            analysis_result = analyze_merchant_url(url_input)
        st.code(analysis_result, language="markdown")
    else:
        st.warning("Please enter a valid URL before analyzing!")
