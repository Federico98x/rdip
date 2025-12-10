# RDIP v1.3.0 - Streamlit Frontend
"""
Streamlit-based user interface for Reddit Deep Intelligence Platform.
Features polling-based job tracking, tabbed results display, and download options.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", st.secrets.get("API_URL", "http://localhost:8000"))
POLL_INTERVAL = 1.0
MAX_POLLS = 300

st.set_page_config(
    page_title="RDIP - Reddit Deep Intelligence",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stButton > button { width: 100%; }
        .main .block-container { padding-top: 2rem; }
        div[data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "job_id" not in st.session_state:
    st.session_state.job_id = None
    st.session_state.poll_count = 0
    st.session_state.last_result = None


def check_backend_health() -> tuple[bool, str]:
    """Check if the backend API is available."""
    try:
        response = httpx.get(f"{API_URL}/v1/health", timeout=5.0)
        if response.status_code == 200:
            return True, "OK"
        return False, f"Status: {response.status_code}"
    except httpx.RequestError as e:
        return False, str(e)


def submit_analysis(url: str, force_refresh: bool, deep_scan: bool) -> Optional[Dict[str, Any]]:
    """Submit a URL for analysis."""
    try:
        response = httpx.post(
            f"{API_URL}/v1/analyze",
            json={
                "url": url,
                "force_refresh": force_refresh,
                "deep_scan": deep_scan,
            },
            timeout=15.0,
        )
        if response.status_code == 200:
            return response.json()
        st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
        return None
    except httpx.RequestError as e:
        st.error(f"Connection error: {e}")
        return None


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a job."""
    try:
        response = httpx.get(f"{API_URL}/v1/status/{job_id}", timeout=5.0)
        if response.status_code == 200:
            return response.json()
        return None
    except httpx.RequestError:
        return None


def render_sidebar():
    """Render the sidebar with configuration options."""
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        is_healthy, health_msg = check_backend_health()
        if is_healthy:
            st.success("✅ Backend conectado")
        else:
            st.error(f"❌ Backend no disponible: {health_msg}")
        
        st.divider()
        
        force_refresh = st.checkbox(
            "🔄 Forzar reanálisis",
            help="Ignorar cache y volver a analizar",
        )
        
        deep_scan = st.checkbox(
            "🔍 Escaneo profundo",
            help="Extraer más comentarios (más lento)",
        )
        
        st.divider()
        
        st.markdown("### 📊 Información")
        st.markdown(
            """
            **RDIP v1.3.0**
            
            - 🤖 LLMs: Groq + Gemini
            - 📝 Resumen post/comentarios
            - 😊 Sentimiento separado
            - 🔗 Links útiles
            - 📥 Descargas
            """
        )
        
        return force_refresh, deep_scan


def render_input_section(force_refresh: bool, deep_scan: bool):
    """Render the URL input section."""
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("📝 URL del hilo de Reddit")
        url_input = st.text_input(
            "URL:",
            placeholder="https://www.reddit.com/r/python/comments/...",
            key="reddit_url",
            label_visibility="collapsed",
        )
        
        if st.button("🔍 Analizar hilo", type="primary", use_container_width=True):
            if not url_input:
                st.error("Por favor introduce una URL de Reddit.")
            else:
                with st.spinner("Enviando solicitud..."):
                    data = submit_analysis(url_input, force_refresh, deep_scan)
                
                if data:
                    st.session_state.job_id = data["job_id"]
                    st.session_state.poll_count = 0
                    
                    if data["status"] == "completed":
                        st.success("✅ Resultado desde cache")
                        st.session_state.last_result = data["result"]
                        st.session_state.job_id = None
                    else:
                        st.info(f"📋 Job enviado: {data['job_id'][:8]}...")
                        st.rerun()
    
    with col_right:
        st.subheader("ℹ️ Cómo funciona")
        st.info(
            """
            1. Pega un enlace de Reddit
            2. Pulsa "Analizar hilo"
            3. Espera el procesamiento
            
            Recibirás:
            - Resumen del post
            - Resumen de comentarios
            - Análisis de sentimiento
            - Links útiles
            - Texto completo
            """
        )


def render_polling_section():
    """Render the job polling section."""
    if st.session_state.job_id and st.session_state.job_id != "cache":
        st.subheader("⏳ Estado del análisis")
        
        if st.session_state.poll_count > MAX_POLLS:
            st.error("⏱️ Timeout: el análisis ha tardado demasiado.")
            st.session_state.job_id = None
            return
        
        st.session_state.poll_count += 1
        
        status_data = get_job_status(st.session_state.job_id)
        
        if not status_data:
            st.error("Error obteniendo estado del job.")
            st.session_state.job_id = None
            return
        
        progress = status_data.get("progress", 0)
        st.progress(progress / 100, text=f"Progreso: {progress}%")
        
        status = status_data["status"]
        
        if status == "completed":
            st.success("✅ Análisis completado")
            st.session_state.last_result = status_data["result"]
            st.session_state.job_id = None
            st.session_state.poll_count = 0
            st.rerun()
        
        elif status == "failed":
            st.error(f"❌ Error: {status_data.get('error', 'Unknown')}")
            st.session_state.job_id = None
            st.session_state.poll_count = 0
        
        else:
            status_emoji = "🔄" if status == "processing" else "⏳"
            st.info(f"{status_emoji} Estado: {status} ({st.session_state.poll_count}s)")
            time.sleep(POLL_INTERVAL)
            st.rerun()


def render_results():
    """Render the analysis results."""
    if not st.session_state.last_result:
        return
    
    result = st.session_state.last_result
    
    st.divider()
    st.header("📊 Resultados del Análisis")
    
    tabs = st.tabs([
        "📋 Resumen",
        "😊 Sentimiento",
        "🔗 Links",
        "📜 Texto completo",
        "📊 JSON",
    ])
    
    with tabs[0]:
        render_summary_tab(result)
    
    with tabs[1]:
        render_sentiment_tab(result)
    
    with tabs[2]:
        render_links_tab(result)
    
    with tabs[3]:
        render_raw_text_tab(result)
    
    with tabs[4]:
        render_json_tab(result)


def render_summary_tab(result: Dict[str, Any]):
    """Render the summary tab."""
    meta = result.get("meta", {})
    
    st.subheader(meta.get("title", "Sin título"))
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("⬆️ Upvotes", meta.get("upvotes", 0))
    col2.metric("💬 Comentarios", meta.get("total_comments", 0))
    col3.metric("📁 Subreddit", meta.get("subreddit", "N/A"))
    col4.metric("👤 Autor", meta.get("author", "N/A")[:15])
    
    st.markdown("### 📝 Resumen del post")
    st.write(result.get("summary_post", "No disponible"))
    
    st.markdown("### 💬 Resumen de los comentarios")
    st.write(result.get("summary_comments", "No disponible"))
    
    st.markdown("### 🤝 Consenso")
    st.info(result.get("consensus", "No disponible"))
    
    controversies = result.get("key_controversies", [])
    if controversies:
        st.markdown("### ⚡ Controversias clave")
        for i, controversy in enumerate(controversies, 1):
            st.write(f"{i}. {controversy}")


def render_sentiment_tab(result: Dict[str, Any]):
    """Render the sentiment analysis tab."""
    st.markdown("### 📝 Sentimiento del Post")
    
    sp = result.get("sentiment_post", {})
    col_a, col_b = st.columns(2)
    
    with col_a:
        label = sp.get("label", "Neutro")
        emoji = get_sentiment_emoji(label)
        st.metric("Sentimiento", f"{emoji} {label}")
    
    with col_b:
        score = sp.get("score", 0.5)
        st.metric("Puntuación", f"{score:.2f}")
    
    st.caption(sp.get("details", ""))
    
    st.divider()
    
    st.markdown("### 💬 Sentimiento de los Comentarios")
    
    sc = result.get("sentiment_comments", {})
    col_c, col_d = st.columns(2)
    
    with col_c:
        label = sc.get("label", "Neutro")
        emoji = get_sentiment_emoji(label)
        st.metric("Sentimiento", f"{emoji} {label}")
    
    with col_d:
        score = sc.get("score", 0.5)
        st.metric("Puntuación", f"{score:.2f}")
    
    st.caption(sc.get("details", ""))


def get_sentiment_emoji(label: str) -> str:
    """Get emoji for sentiment label."""
    mapping = {
        "Positivo": "😊",
        "Negativo": "😞",
        "Neutro": "😐",
        "Mixto": "😕",
        "Controversial": "🔥",
    }
    return mapping.get(label, "❓")


def render_links_tab(result: Dict[str, Any]):
    """Render the useful links tab."""
    st.markdown("### 🔗 Links útiles detectados")
    
    links = result.get("useful_links", [])
    
    if not links:
        st.info("No se encontraron links útiles en el hilo.")
        return
    
    for link in links:
        url = link.get("url", "")
        link_type = link.get("type", "Link")
        context = link.get("context", "")
        
        type_emoji = {
            "Doc": "📄",
            "News": "📰",
            "Tool": "🛠️",
            "Reference": "📚",
            "Other": "🔗",
        }.get(link_type, "🔗")
        
        st.markdown(f"{type_emoji} **[{link_type}]** [{url}]({url})")
        if context:
            st.caption(context)
        st.write("")


def render_raw_text_tab(result: Dict[str, Any]):
    """Render the raw text tab with download options."""
    st.markdown("### 📝 Texto completo del post")
    
    raw_post = result.get("raw_post_text", "")
    st.text_area(
        "Post",
        value=raw_post or "(Sin texto)",
        height=200,
        key="raw_post_area",
    )
    
    st.markdown("### 💬 Comentarios serializados")
    
    raw_comments = result.get("raw_comments_text", "")
    st.text_area(
        "Comentarios",
        value=raw_comments or "(Sin comentarios)",
        height=300,
        key="raw_comments_area",
    )
    
    st.divider()
    
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        st.download_button(
            "⬇️ Descargar post (.txt)",
            data=raw_post or "(Sin contenido)",
            file_name="reddit_post.txt",
            mime="text/plain",
        )
    
    with col_dl2:
        st.download_button(
            "⬇️ Descargar comentarios (.txt)",
            data=raw_comments or "(Sin comentarios)",
            file_name="reddit_comments.txt",
            mime="text/plain",
        )


def render_json_tab(result: Dict[str, Any]):
    """Render the JSON output tab."""
    st.markdown("### 📊 Resultado completo en JSON")
    
    st.json(result)
    
    json_str = json.dumps(result, indent=2, ensure_ascii=False)
    
    st.download_button(
        "⬇️ Descargar JSON completo",
        data=json_str,
        file_name="reddit_analysis.json",
        mime="application/json",
    )


def main():
    """Main application entry point."""
    st.title("🔴 Reddit Deep Intelligence Platform")
    st.caption("v1.3.0 – Análisis de hilos de Reddit con IA")
    
    force_refresh, deep_scan = render_sidebar()
    
    render_input_section(force_refresh, deep_scan)
    
    st.divider()
    
    render_polling_section()
    
    render_results()
    
    st.divider()
    st.caption("RDIP v1.3.0 – Groq + Gemini + AsyncPRAW – Free tier friendly")


if __name__ == "__main__":
    main()
