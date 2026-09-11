import os
import sys
import re
import json
import logging
import warnings
import webbrowser
import threading
from typing import List, Optional, Dict, Any

# Windows 콘솔 인코딩 호환성 보장
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import yt_dlp
from google import genai
from google.genai import types

# 1. 경고 및 불필요 로그 필터링
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("youtube-ai-search")

app = FastAPI(title="YouTube AI Search API", version="1.0.0")

# CORS 활성화
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)


# ================= Pydantic Request Models =================
class AnalyzeRequest(BaseModel):
    url: str
    api_key: Optional[str] = None

class ChatRequest(BaseModel):
    question: str
    full_text: str
    sentences: List[Dict[str, Any]] = []
    chat_history: List[Dict[str, str]] = []
    api_key: Optional[str] = None


# ================= 헬퍼 함수 =================
def get_api_key(provided_key: Optional[str]) -> str:
    key = (provided_key or "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Gemini API Key가 설정되지 않았습니다. 환경 변수(GEMINI_API_KEY)를 설정해 주세요.")
    return key


def parse_offset_seconds(offset_val) -> float:
    if offset_val is None:
        return 0.0
    if isinstance(offset_val, (int, float)):
        return float(offset_val)
    s = str(offset_val).strip()
    if s.endswith("s"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def format_seconds(seconds: float, for_srt: bool = False) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    whole_secs = int(secs)
    millis = int(round((secs - whole_secs) * 1000))
    if millis >= 1000:
        whole_secs += 1
        millis = 0

    if for_srt:
        return f"{hours:02d}:{minutes:02d}:{whole_secs:02d},{millis:03d}"
    else:
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{whole_secs:02d}"
        return f"{minutes:02d}:{whole_secs:02d}"


def group_words_into_sentences(words):
    if not words:
        return []

    sentences = []
    current_words = []
    start_time = None

    for w in words:
        if start_time is None:
            start_time = parse_offset_seconds(w.start_offset)
        current_words.append(w.word)

        if any(w.word.rstrip().endswith(punct) for punct in [".", "?", "!"]):
            end_time = parse_offset_seconds(w.end_offset)
            sentence_text = " ".join(current_words)
            sentences.append({
                "start": start_time,
                "end": end_time,
                "text": sentence_text
            })
            current_words = []
            start_time = None

    if current_words:
        end_time = parse_offset_seconds(words[-1].end_offset)
        sentence_text = " ".join(current_words)
        sentences.append({
            "start": start_time,
            "end": end_time,
            "text": sentence_text
        })

    return sentences


def extract_youtube_id(url: str) -> str:
    if not url:
        return ""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def download_youtube_audio(url: str, output_dir: str = DOWNLOADS_DIR):
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "m4a/bestaudio/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        video_id = info.get("id") or extract_youtube_id(url)
        return {
            "id": video_id,
            "title": info.get("title", "제목 없음"),
            "uploader": info.get("uploader", "알 수 없음"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration", 0),
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "ext": info.get("ext", "m4a")
        }


def transcribe_and_summarize(file_path: str, ext: str, api_key: str):
    client = genai.Client(api_key=api_key)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

    # 1. 오디오 준비
    if file_size_mb < 20:
        with open(file_path, "rb") as f:
            audio_bytes = f.read()

        mime_map = {
            "m4a": "audio/mp4",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "webm": "audio/webm",
        }
        mime_type = mime_map.get(ext.lower(), "audio/mp4")
        audio_content = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    else:
        audio_content = client.files.upload(file=file_path)

    # 2. Gemini STT 호출
    contents = [
        types.Content(
            role="user",
            parts=[
                audio_content,
                types.Part.from_text(text="이 오디오를 한국어 음성을 포함하여 정확하게 받아써줘."),
            ]
        )
    ]

    config = types.GenerateContentConfig(
        audio_transcription_config=types.AudioTranscriptionConfig(
            word_timestamp=True,
            diarization=True
        )
    )

    response = client.models.generate_content(
        model="gemini-3.5-transcribe",
        contents=contents,
        config=config,
    )

    full_text = ""
    transcription_data = None

    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                full_text += part.text
            if getattr(part, "audio_transcription", None):
                transcription_data = part.audio_transcription

    if not full_text.strip() and transcription_data and transcription_data.text:
        full_text = transcription_data.text

    words = transcription_data.words if transcription_data else []
    sentences = group_words_into_sentences(words)

    # 3. Gemini 요약 및 키워드, 시청자 예상 질문지 추출 (전사 스크립트 기반)
    summary_text = "요약을 생성하지 못했습니다."
    keywords = []
    suggested_questions = []

    if full_text.strip():
        try:
            summary_prompt = f"""너는 유튜브 영상의 전사 스크립트를 정밀하게 분석하여 핵심 요약, 주요 키워드, 그리고 시청자 맞춤형 예상 질문지를 생성하는 전문 AI 분석가야.
아래에 제공된 [스크립트 전문]을 꼼꼼히 읽고, 영상의 실제 대화 및 전달 내용을 충실하게 반영하여 다음 세 가지를 작성해줘:

1. 영상 핵심 요약 (summary): 영상에서 전달하는 핵심 주제, 주요 내용, 결론 등을 3~5개의 완성도 높은 불릿 포인트 문장으로 구체적이고 일목요연하게 작성해줘.
2. 주요 키워드 (keywords): 영상의 핵심 주제, 고유 명사, 핵심 개념을 대표하는 가장 중요한 키워드 5~8개를 추출해줘 (일반적인 단어인 '유튜브', '영상' 등은 제외).
3. 시청자 예상 질문지 (suggested_questions): 유튜브의 '이 동영상에 대해 물어보세요' 공식 AI 추천 질문 스타일로 작성해줘.
   - 첫 번째 질문은 반드시 "동영상을 요약해 줘", 두 번째 질문은 반드시 "관련 콘텐츠를 추천해 줘"로 작성.
   - 3번째부터 5번째 질문은 영상의 실제 대화 및 핵심 내용을 바탕으로 시청자가 가장 궁금해할 만한 호기심 자극 질문(20자 내외의 간결하고 직관적인 의문문) 3개를 작성 (예: 'AI 기업들이 숨기는 실체는?', '왜 AI는 인간이 필요한가?', '인클로저 운동과 AI 관계?').

반드시 아래 JSON 포맷으로만 응답해줘:
{{
  "summary": [
    "핵심 요약 내용 1...",
    "핵심 요약 내용 2...",
    "핵심 요약 내용 3..."
  ],
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
  "suggested_questions": [
    "동영상을 요약해 줘",
    "관련 콘텐츠를 추천해 줘",
    "AI 기업들이 숨기는 실체는?",
    "왜 AI는 인간이 필요한가?",
    "인클로저 운동과 AI 관계?"
  ]
}}

[스크립트 전문]
{full_text[:30000]}
"""
            sum_resp = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=summary_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                )
            )
            raw_text = sum_resp.text or ""
            data = json.loads(raw_text)

            summary_items = data.get("summary", [])
            if isinstance(summary_items, list) and summary_items:
                summary_text = "\n".join([f"- {s}" if not str(s).strip().startswith(("-", "*", "•")) else str(s).strip() for s in summary_items])
            elif isinstance(summary_items, str) and summary_items.strip():
                summary_text = summary_items.strip()

            raw_kws = data.get("keywords", [])
            if isinstance(raw_kws, list):
                keywords = [str(k).strip().lstrip("#") for k in raw_kws if str(k).strip()]
            elif isinstance(raw_kws, str):
                keywords = [k.strip().lstrip("#") for k in raw_kws.split(",") if k.strip()]

            raw_sq = data.get("suggested_questions", [])
            if isinstance(raw_sq, list):
                suggested_questions = [str(q).strip() for q in raw_sq if str(q).strip()]
            elif isinstance(raw_sq, str):
                suggested_questions = [q.strip() for q in raw_sq.split("\n") if q.strip()]
        except Exception as e:
            logger.error(f"요약 및 키워드 추출 중 오류 발생: {e}")
            summary_text = "스크립트 내용 기반 요약을 생성하는 중 오류가 발생했습니다."
            keywords = []
            suggested_questions = []

    return {
        "full_text": full_text.strip(),
        "sentences": sentences,
        "speaker": transcription_data.speaker_label if transcription_data else "화자",
        "summary": summary_text,
        "keywords": keywords,
        "suggested_questions": suggested_questions,
    }


def ask_gemini_about_video(question: str, full_text: str, sentences: list, chat_history: list, api_key: str) -> str:
    client = genai.Client(api_key=api_key)
    formatted_ts = "\n".join([f"[{format_seconds(s['start'])}] {s['text']}" for s in sentences[:80]])

    system_instruction = f"""너는 유튜브 영상 내용을 완벽하게 파악하고 있는 친절하고 스마트한 AI 어시스턴트야.
아래에 제공된 영상의 [전체 스크립트]와 [주요 타임스탬프]를 바탕으로 사용자의 질문에 정확하고 구체적으로 답변해줘.

답변할 때는 다음 지침을 지켜줘:
1. 영상 내용에 근거하여 명확하게 답변할 것.
2. 사용자가 '동영상을 요약해 줘'라고 요청하면 영상의 도입, 전개, 핵심 결론을 일목요연한 불릿포인트로 요약해줘.
3. 사용자가 '관련 콘텐츠를 추천해 줘'라고 요청하면 영상 내용과 연관된 흥미로운 후속 탐구 주제나 관련 추천 분야를 3~4가지 제시해줘.
4. 관련된 내용이 나오는 타임스탬프가 있다면 반드시 `[MM:SS]` 형식으로 함께 언급해줘 (예: "영상 01:25 부근에서 언급되었듯이...").
5. 한국어로 자연스럽고 정중하게 답할 것.

[영상 타임스탬프 및 대사]
{formatted_ts}

[전체 전문 내용 일부]
{full_text[:15000]}
"""

    prompt = f"질문: {question}"
    try:
        resp = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=f"{system_instruction}\n\n{prompt}",
        )
        return resp.text or "답변을 생성하지 못했습니다."
    except Exception as e:
        return f"답변 생성 중 오류가 발생했습니다: {str(e)}"


# ================= API Routes =================
@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="유튜브 영상 URL을 입력해 주세요.")
    
    api_key = get_api_key(req.api_key)
    url = req.url.strip()

    logger.info(f"Analyzing YouTube URL: {url}")
    try:
        # 1. 오디오 다운로드
        v_info = download_youtube_audio(url)
        # 2. STT 및 요약/키워드/질문 생성
        stt_res = transcribe_and_summarize(v_info["file_path"], v_info["ext"], api_key)

        return {
            "video_info": {
                "id": v_info["id"],
                "url": url,
                "title": v_info["title"],
                "uploader": v_info["uploader"],
                "thumbnail": v_info["thumbnail"],
                "duration": v_info["duration"],
                "duration_formatted": format_seconds(v_info["duration"]),
                "filename": v_info["filename"],
                "audio_url": f"/api/audio/{v_info['filename']}"
            },
            "stt_result": stt_res
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분석 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="질문 내용을 입력해 주세요.")
    
    api_key = get_api_key(req.api_key)
    try:
        answer = ask_gemini_about_video(
            question=req.question.strip(),
            full_text=req.full_text,
            sentences=req.sentences,
            chat_history=req.chat_history,
            api_key=api_key
        )
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"답변 생성 실패: {str(e)}")


@app.get("/api/audio/{filename}")
def api_audio(filename: str):
    file_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="오디오 파일을 찾을 수 없습니다.")
    
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime_map = {
        "m4a": "audio/mp4",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "webm": "audio/webm",
    }
    media_type = mime_map.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type, filename=filename)


# 정적 파일 서빙
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"status": "running", "message": "index.html not yet created."})


def open_browser_tab():
    import time
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[YouTube AI Search] Server starting at: http://127.0.0.1:{port}")
    threading.Thread(target=open_browser_tab, daemon=True).start()
    uvicorn.run("server:app", host="127.0.0.1", port=port, reload=True)
