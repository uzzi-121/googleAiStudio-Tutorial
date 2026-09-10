import os
import re
import warnings
import logging
import streamlit as st
import yt_dlp
from google import genai
from google.genai import types

# SDK 및 파이썬 경고 숨김
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

# 페이지 기본 설정
st.set_page_config(
    page_title="유튜브 오디오 STT 트랜스크립터",
    page_icon="🎙️",
    layout="wide"
)

# 커스텀 스타일
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #666;
        margin-bottom: 1.5rem;
    }
    .video-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1.5rem;
        border: 1px solid #e9ecef;
    }
    .timestamp-box {
        font-family: monospace;
        background-color: #f1f3f5;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
        color: #1a73e8;
    }
</style>
""", unsafe_allow_html=True)


def parse_offset_seconds(offset_val) -> float:
    """'0.300s' 또는 숫자 형태를 float(초)로 변환"""
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
    """초를 [HH:MM:SS] 또는 SRT용 [HH:MM:SS,mmm] 형식으로 포맷팅"""
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
    """단어 목록을 문장 종결 부호(., ?, !) 기준으로 묶어 문장별 타임스탬프 생성"""
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


def generate_srt(sentences) -> str:
    """문장 리스트를 표준 .srt 자막 문자열로 생성"""
    srt_blocks = []
    for idx, item in enumerate(sentences, 1):
        start_fmt = format_seconds(item["start"], for_srt=True)
        end_fmt = format_seconds(item["end"], for_srt=True)
        srt_blocks.append(f"{idx}\n{start_fmt} --> {end_fmt}\n{item['text']}\n")
    return "\n".join(srt_blocks)


def download_youtube_audio(url: str, output_dir: str = "downloads"):
    """yt-dlp를 이용하여 유튜브에서 오디오 스트림만 다운로드"""
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
        return {
            "title": info.get("title", "제목 없음"),
            "uploader": info.get("uploader", "알 수 없음"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration", 0),
            "file_path": file_path,
            "ext": info.get("ext", "m4a")
        }


def transcribe_audio(file_path: str, ext: str, api_key: str):
    """Gemini 3.5 Transcribe 모델을 호출하여 텍스트 및 타임스탬프 추출"""
    client = genai.Client(api_key=api_key)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

    # 20MB 미만은 바이트 직접 전송, 이상은 Files API 업로드 활용
    if file_size_mb < 20:
        with open(file_path, "rb") as f:
            audio_bytes = f.read()

        mime_map = {
            "m4a": "audio/mp4",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "webm": "audio/webm",
            "aac": "audio/aac",
            "ogg": "audio/ogg"
        }
        mime_type = mime_map.get(ext.lower(), "audio/mp4")
        audio_content = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    else:
        audio_content = client.files.upload(file=file_path)

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

    return {
        "full_text": full_text.strip(),
        "sentences": sentences,
        "speaker": transcription_data.speaker_label if transcription_data else "화자"
    }


# ================= UI 레이아웃 =================
st.markdown('<div class="main-header">🎙️ 유튜브 오디오 트랜스크립터</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">유튜브 영상 URL만 넣으면 오디오를 추출하고, Gemini 3.5 Transcribe로 정확한 자막과 타임스탬프를 추출합니다.</div>', unsafe_allow_html=True)

# 사이드바 설정 (API 키)
with st.sidebar:
    st.header("⚙️ 환경 설정")
    env_api_key = os.environ.get("GEMINI_API_KEY", "")
    api_key = st.text_input(
        "Gemini API Key",
        value=env_api_key,
        type="password",
        help="Google AI Studio에서 발급받은 GEMINI_API_KEY를 입력하세요."
    )
    st.markdown("---")
    st.markdown("💡 **활용 모델**: `gemini-3.5-transcribe`")
    st.markdown("✨ **주요 기능**:")
    st.markdown("- 오디오 전용 고속 다운로드")
    st.markdown("- 문장별 타임스탬프 자동 계산")
    st.markdown("- .txt 및 자막(.srt) 다운로드 지원")

# 메인 입력 폼
youtube_url = st.text_input(
    "유튜브 영상 URL을 입력하세요",
    placeholder="https://www.youtube.com/watch?v=... 또는 https://youtu.be/..."
)

start_btn = st.button("🚀 오디오 추출 및 트랜스크립트 생성", type="primary", width="stretch")

if start_btn:
    if not api_key.strip():
        st.error("⚠️ Gemini API Key가 필요합니다. 좌측 사이드바에 API 키를 입력해 주세요.")
    elif not youtube_url.strip():
        st.warning("⚠️ 유튜브 영상 URL을 입력해 주세요.")
    else:
        try:
            # 1단계: 오디오 다운로드
            with st.status("🎬 유튜브 영상을 분석하고 오디오를 다운로드하는 중...", expanded=True) as status:
                st.write("유튜브 비디오 메타데이터 및 오디오 스트림 추출 중...")
                video_info = download_youtube_audio(youtube_url.strip())
                st.write(f"✅ 오디오 다운로드 완료: **{video_info['title']}**")
                
                # 2단계: STT 변환
                status.update(label="🤖 Gemini 3.5 Transcribe로 음성 분석 및 텍스트 추출 중...", state="running")
                st.write("Gemini 모델에 오디오 전달 및 타임스탬프 분석 중...")
                stt_result = transcribe_audio(video_info["file_path"], video_info["ext"], api_key)
                status.update(label="🎉 모든 분석이 완료되었습니다!", state="complete", expanded=False)

            st.success("트랜스크립트 추출에 성공했습니다!")

            # 영상 정보 카드
            col1, col2 = st.columns([1, 2])
            with col1:
                if video_info.get("thumbnail"):
                    st.image(video_info["thumbnail"], width="stretch")
            with col2:
                st.subheader(video_info["title"])
                st.caption(f"채널: {video_info['uploader']} | 길이: {format_seconds(video_info['duration'])}")
                
                # 오디오 플레이어
                if os.path.exists(video_info["file_path"]):
                    st.markdown("**🎧 추출된 오디오 바로 듣기:**")
                    st.audio(video_info["file_path"])

            st.divider()

            # 결과 탭 구성
            tab1, tab2, tab3 = st.tabs(["📄 전체 텍스트 (Full Transcript)", "⏱️ 문장별 타임스탬프 (Sentences)", "📥 자막 다운로드 (.srt / .txt)"])

            with tab1:
                st.markdown("#### 전체 스크립트 전문")
                full_text = stt_result["full_text"]
                st.text_area("텍스트 내용 (복사 가능)", value=full_text, height=300)
                st.download_button(
                    label="📄 텍스트 파일(.txt)로 다운로드",
                    data=full_text,
                    file_name=f"{video_info['title']}_transcript.txt",
                    mime="text/plain"
                )

            with tab2:
                st.markdown("#### ⏱️ 문장 단위 타임스탬프 목록")
                sentences = stt_result["sentences"]
                if sentences:
                    for s in sentences:
                        start_str = format_seconds(s["start"])
                        end_str = format_seconds(s["end"])
                        st.markdown(f'<span class="timestamp-box">[{start_str} ~ {end_str}]</span> {s["text"]}', unsafe_allow_html=True)
                else:
                    st.info("단어/문장별 타임스탬프 정보가 없습니다.")

            with tab3:
                st.markdown("#### 📥 자막 및 스크립트 파일 다운로드")
                srt_data = generate_srt(stt_result["sentences"])
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.download_button(
                        label="🎬 Premiere / DaVinci 자막용 (.srt) 다운로드",
                        data=srt_data,
                        file_name=f"{video_info['title']}.srt",
                        mime="text/plain",
                        width="stretch"
                    )
                with col_d2:
                    st.download_button(
                        label="📄 텍스트 파일 (.txt) 다운로드",
                        data=full_text,
                        file_name=f"{video_info['title']}.txt",
                        mime="text/plain",
                        width="stretch"
                    )

                with st.expander("SRT 자막 미리보기"):
                    st.code(srt_data, language="text")

        except Exception as e:
            st.error(f"❌ 오류가 발생했습니다: {str(e)}")
