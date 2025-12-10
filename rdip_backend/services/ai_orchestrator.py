# RDIP v1.3.0 - AI Orchestrator Service
"""
LLM orchestration with Groq (primary) and Gemini (fallback).
Includes robust JSON parsing with multiple fallback strategies.
Now with structured output and subreddit-specific prompts.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict

import google.generativeai as genai
from groq import Groq

from rdip_backend.core.config import get_settings
from rdip_backend.core.logging import get_logger
from rdip_backend.models import ThreadContext, SubredditType

logger = get_logger(__name__)

SUBREDDIT_CATEGORIES = {
    "tech": ["programming", "technology", "webdev", "python", "javascript", "rust", 
             "golang", "java", "cpp", "machinelearning", "datascience", "devops",
             "linux", "apple", "android", "software", "coding", "learnprogramming"],
    "gaming": ["gaming", "games", "pcgaming", "ps5", "xbox", "nintendo", "steam",
               "valorant", "leagueoflegends", "minecraft", "fortnite", "overwatch"],
    "finance": ["wallstreetbets", "stocks", "investing", "cryptocurrency", "bitcoin",
                "ethereum", "personalfinance", "financialindependence", "economics"],
    "science": ["science", "askscience", "space", "physics", "biology", "chemistry",
                "astronomy", "medicine", "neuroscience", "environment"],
    "politics": ["politics", "worldnews", "news", "uspolitics", "geopolitics",
                 "conservative", "liberal", "democrat", "republican"],
}

SUBREDDIT_PROMPTS = {
    "tech": """Eres un analista experto en tecnología y desarrollo de software.
Enfócate en:
- Tendencias tecnológicas y herramientas mencionadas
- Debates sobre arquitectura, frameworks o lenguajes
- Problemas técnicos y soluciones propuestas
- Recursos de aprendizaje compartidos (documentación, tutoriales)
- Opiniones sobre empresas tech o productos""",
    
    "gaming": """Eres un analista de la industria del gaming y comunidades de jugadores.
Enfócate en:
- Opiniones sobre juegos, mecánicas o actualizaciones
- Debates sobre hardware gaming (PC, consolas)
- Reacciones a noticias de la industria
- Recomendaciones y críticas de la comunidad
- Discusiones sobre esports o streaming""",
    
    "finance": """Eres un analista financiero especializado en mercados y comunidades de inversión.
Enfócate en:
- Análisis de acciones, criptomonedas o activos mencionados
- Sentimiento del mercado expresado
- Estrategias de inversión discutidas
- Riesgos y oportunidades identificados
- Tono del FOMO o FUD en la discusión""",
    
    "science": """Eres un comunicador científico analizando discusiones académicas.
Enfócate en:
- Rigor científico de las afirmaciones
- Referencias a estudios o papers
- Debates sobre metodología
- Divulgación y explicaciones claras
- Escepticismo o consenso científico""",
    
    "politics": """Eres un analista político imparcial.
Enfócate en:
- Posiciones políticas expresadas (izquierda/derecha/centro)
- Nivel de polarización en la discusión
- Argumentos principales de cada posición
- Desinformación o claims sin fuentes
- Civility del debate""",
    
    "general": """Eres un analista de contenido de comunidades online.
Enfócate en:
- Temas principales discutidos
- Tono general de la conversación
- Puntos de acuerdo y desacuerdo
- Links y recursos compartidos
- Dinámicas de la comunidad"""
}

STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_post": {"type": "string", "description": "Resumen ejecutivo del post (2-4 frases)"},
        "summary_comments": {"type": "string", "description": "Resumen de la discusión (4-8 frases)"},
        "sentiment_post": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": ["Positivo", "Negativo", "Neutro", "Mixto", "Controversial"]},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "details": {"type": "string"}
            },
            "required": ["label", "score", "details"]
        },
        "sentiment_comments": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": ["Positivo", "Negativo", "Neutro", "Mixto", "Controversial"]},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "details": {"type": "string"}
            },
            "required": ["label", "score", "details"]
        },
        "consensus": {"type": "string"},
        "key_controversies": {"type": "array", "items": {"type": "string"}},
        "useful_links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "type": {"type": "string"},
                    "context": {"type": "string"}
                }
            }
        }
    },
    "required": ["summary_post", "summary_comments", "sentiment_post", "sentiment_comments", "consensus", "key_controversies", "useful_links"]
}


def detect_subreddit_type(subreddit: str) -> SubredditType:
    """Detect the category of a subreddit for specialized prompts."""
    subreddit_lower = subreddit.lower()
    
    for category, subreddits in SUBREDDIT_CATEGORIES.items():
        if subreddit_lower in subreddits:
            return SubredditType(category)
    
    for category, subreddits in SUBREDDIT_CATEGORIES.items():
        for sub in subreddits:
            if sub in subreddit_lower or subreddit_lower in sub:
                return SubredditType(category)
    
    return SubredditType.GENERAL


def get_system_prompt(subreddit: str) -> str:
    """Get a specialized system prompt based on subreddit type."""
    sub_type = detect_subreddit_type(subreddit)
    specialized_context = SUBREDDIT_PROMPTS.get(sub_type.value, SUBREDDIT_PROMPTS["general"])
    
    return f"""{specialized_context}

Recibirás:
- El título y texto del post (submission)
- Un resumen serializado de los comentarios (con indentación tipo >)

DEBES devolver SIEMPRE un JSON VÁLIDO con esta estructura EXACTA:

{{
  "summary_post": "Resumen ejecutivo del post (2-4 frases)",
  "summary_comments": "Resumen de la discusión en comentarios (4-8 frases)",
  "sentiment_post": {{
    "label": "Positivo/Negativo/Neutro/Mixto/Controversial",
    "score": 0.75,
    "details": "Explica brevemente el tono dominante del post"
  }},
  "sentiment_comments": {{
    "label": "Positivo/Negativo/Neutro/Mixto/Controversial",
    "score": 0.60,
    "details": "Explica brevemente el tono dominante de los comentarios"
  }},
  "consensus": "Describe si hay acuerdo, desacuerdo o posiciones divididas",
  "key_controversies": [
    "Tema o punto concreto donde hay desacuerdo",
    "Otro tema polémico"
  ],
  "useful_links": [
    {{
      "url": "https://...",
      "type": "Doc/News/Tool/Reference/GitHub/Video/Article",
      "context": "Quién lo menciona o en qué contexto"
    }}
  ]
}}

REGLAS IMPORTANTES:
- Si NO hay consenso claro, dilo explícitamente.
- No inventes hechos que no aparezcan en el texto.
- Si no hay links útiles, devuelve "useful_links": [].
- El JSON debe ser la única salida (sin texto fuera de las llaves).
- El score debe estar entre 0.0 y 1.0 (ej: 0.75 = 75% positivo).
"""


class AIOrchestrator:
    """
    Orchestrates LLM calls with automatic fallback from Groq to Gemini.
    
    Uses synchronous LLM clients wrapped in asyncio.to_thread() to avoid
    blocking the event loop.
    
    Example:
        orchestrator = AIOrchestrator(rate_limiter)
        result = await orchestrator.analyze(context)
    """
    
    def __init__(self, rate_limiter: "RateLimitManager") -> None:
        self._rate_limiter = rate_limiter
        self._settings = get_settings()
        
        self._groq_client: Groq | None = None
        if self._settings.is_groq_configured:
            self._groq_client = Groq(api_key=self._settings.groq_api_key)
            logger.info("Groq client initialized")
        
        self._gemini_configured = False
        if self._settings.is_gemini_configured:
            genai.configure(api_key=self._settings.google_api_key)
            self._gemini_configured = True
            logger.info("Gemini client initialized")
    
    async def analyze(self, context: ThreadContext) -> Dict[str, Any]:
        """
        Analyze a Reddit thread using available LLMs with subreddit-specific prompts.
        """
        subreddit = context.metadata.get("subreddit", "")
        sub_type = detect_subreddit_type(subreddit)
        logger.info(f"Detected subreddit type: {sub_type.value} for r/{subreddit}")
        
        can_use_groq = (
            self._groq_client is not None
            and context.token_count_llama < self._settings.groq_max_tokens
            and await self._rate_limiter.can_use_groq()
        )
        
        if can_use_groq:
            await self._rate_limiter.record_groq_usage()
            try:
                logger.info("Attempting analysis with Groq (structured output)...")
                return await self._invoke_groq(context, subreddit)
            except Exception as e:
                logger.warning(f"Groq failed: {e}. Attempting Gemini fallback...")
        
        if self._gemini_configured and await self._rate_limiter.can_use_gemini():
            await self._rate_limiter.record_gemini_usage()
            try:
                logger.info("Attempting analysis with Gemini...")
                return await self._invoke_gemini(context, subreddit)
            except Exception as e:
                logger.error(f"Gemini failed: {e}")
                raise RuntimeError(f"All LLMs failed. Last error: {e}") from e
        
        raise RuntimeError("No LLM available (rate limits exceeded or not configured)")
    
    def _build_user_prompt(self, context: ThreadContext) -> str:
        urls = context.metadata.get("urls_detected", [])
        urls_str = "\n".join(f"- {u}" for u in urls) if urls else "Ninguna URL detectada."
        
        return (
            f"TÍTULO DEL POST:\n{context.title}\n\n"
            f"TEXTO DEL POST:\n{context.selftext or '(Sin texto, solo título)'}\n\n"
            f"COMENTARIOS SERIALIZADOS:\n{context.serialized_comments or '(Sin comentarios)'}\n\n"
            f"LISTA DE URLs DETECTADAS EN EL HILO:\n{urls_str}\n\n"
            "Analiza todo el contenido siguiendo estrictamente las instrucciones del sistema."
        )
    
    async def _invoke_groq(self, context: ThreadContext, subreddit: str = "") -> Dict[str, Any]:
        if not self._groq_client:
            raise RuntimeError("Groq client not initialized")
        
        system_prompt = get_system_prompt(subreddit)
        prompt = self._build_user_prompt(context)
        
        def _call_groq() -> str:
            response = self._groq_client.chat.completions.create(
                model=self._settings.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        
        raw_response = await asyncio.to_thread(_call_groq)
        logger.debug(f"Groq raw response length: {len(raw_response)}")
        
        return self._parse_json_response(raw_response)
    
    async def _invoke_gemini(self, context: ThreadContext, subreddit: str = "") -> Dict[str, Any]:
        system_prompt = get_system_prompt(subreddit)
        prompt = system_prompt + "\n\n" + self._build_user_prompt(context)
        
        def _call_gemini() -> str:
            model = genai.GenerativeModel(
                self._settings.gemini_model,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                )
            )
            response = model.generate_content(prompt)
            return response.text or ""
        
        raw_response = await asyncio.to_thread(_call_gemini)
        logger.debug(f"Gemini raw response length: {len(raw_response)}")
        
        return self._parse_json_response(raw_response)
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("Direct JSON parse failed, trying extraction...")
        
        code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                logger.debug("Code block JSON parse failed...")
        
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                logger.debug("Brace extraction failed...")
        
        cleaned = re.sub(r"[\x00-\x1F\x7F]", "", text)
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("Cleaned text parse failed...")
        
        nested_match = re.search(r"\{.*\}", text, re.DOTALL)
        if nested_match:
            candidate = nested_match.group()
            candidate = self._fix_json_issues(candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        
        logger.error("All JSON parsing strategies failed, returning fallback structure")
        return self._create_fallback_response(text)
    
    @staticmethod
    def _fix_json_issues(text: str) -> str:
        text = re.sub(r",\s*([}\]])", r"\1", text)
        return text
    
    @staticmethod
    def _create_fallback_response(raw_text: str) -> Dict[str, Any]:
        summary_post = raw_text[:400] if raw_text else "Error al procesar respuesta del LLM"
        summary_comments = raw_text[400:1000] if len(raw_text) > 400 else ""
        
        return {
            "summary_post": summary_post,
            "summary_comments": summary_comments,
            "sentiment_post": {
                "label": "Neutro",
                "score": 0.5,
                "details": "Error de parseo: no se pudo extraer JSON válido",
            },
            "sentiment_comments": {
                "label": "Neutro",
                "score": 0.5,
                "details": "Error de parseo: no se pudo extraer JSON válido",
            },
            "consensus": "No disponible debido a error de procesamiento",
            "key_controversies": [],
            "useful_links": [],
        }