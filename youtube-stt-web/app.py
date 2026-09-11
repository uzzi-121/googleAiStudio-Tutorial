import os
import re
import json
import warnings
import logging
import streamlit as st
import streamlit.components.v1 as components
import yt_dlp
from google import genai
from google.genai import types

# 1. 경고 및 불필요 로그 숨김
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

# 2. 페이지 기본 설정
st.set_page_config(
    page_title="YouTube AI Search",
    page_icon="▶️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 3. 유튜브 스타일 모던 CSS
st.markdown("""
<style>
    .block-container {
        padding-top: 4.5rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    .stDeployButton {
        display: none;
    }
    .video-title {
        font-size: 1.35rem;
        font-weight: 700;
        line-height: 1.4;
        margin-top: 0.8rem;
        margin-bottom: 0.4rem;
        color: #0f0f0f;
    }
    .video-channel-row {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 0.8rem;
    }
    .channel-avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background-color: #e50914;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 1.1rem;
    }
    .channel-name {
        font-weight: 600;
        font-size: 1.0rem;
        color: #0f0f0f;
    }
    .channel-sub {
        font-size: 0.8rem;
        color: #606060;
    }
    .metric-box {
        background: #f8f9fa;
        border: 1px solid #eee;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
    }
    .metric-value {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1a73e8;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #666;
    }
    .kw-tag {
        display: inline-block;
        background: #e8f0fe;
        color: #1a73e8;
        padding: 3px 10px;
        border-radius: 15px;
        font-size: 0.85rem;
        font-weight: 500;
        margin: 3px;
    }
    /* 유튜브 '이 동영상에 대해 물어보세요' 스타일 카드 */
    .yt-ask-card {
        background: #181818;
        border: 1px solid #2e2e2e;
        border-radius: 16px;
        padding: 20px 22px 14px 22px;
        margin-bottom: 12px;
        color: #ffffff;
    }
    .yt-ask-header {
        font-size: 1.15rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
        color: #ffffff;
    }
    .yt-ask-sparkle {
        font-size: 1.25rem;
        color: #ffffff;
    }
    .yt-ask-intro {
        font-size: 0.92rem;
        color: #d0d0d0;
        line-height: 1.6;
        margin-bottom: 8px;
    }

    /* 추천 질문 알약(Pill) 버튼 - 끝까지 안 잘리고 줄바꿈 지원 */
    div[class*="st-key-sq_btn_"] {
        margin-bottom: 8px !important;
    }
    div[class*="st-key-sq_btn_"] button {
        background-color: #242424 !important;
        color: #f1f1f1 !important;
        border: 1px solid #3d3d3d !important;
        border-radius: 24px !important;
        padding: 9px 18px !important;
        height: auto !important;
        min-height: 40px !important;
        white-space: normal !important;
        word-break: keep-all !important;
        line-height: 1.45 !important;
        font-size: 13.5px !important;
        font-weight: 500 !important;
        text-align: right !important;
        justify-content: flex-end !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important;
        transition: all 0.2s ease !important;
    }
    div[class*="st-key-sq_btn_"] button:hover {
        background-color: #383838 !important;
        border-color: #777777 !important;
        color: #ffffff !important;
        transform: translateY(-1px);
        box-shadow: 0 3px 10px rgba(0,0,0,0.35) !important;
    }
    div[class*="st-key-sq_btn_"] button p {
        white-space: normal !important;
        word-break: keep-all !important;
        text-align: right !important;
        margin: 0 !important;
        padding: 0 !important;
        font-size: 13.5px !important;
        color: #f1f1f1 !important;
        font-weight: 500 !important;
    }
</style>
""", unsafe_allow_html=True)


# ================= 세션 상태(Session State) 관리 =================
if "video_info" not in st.session_state:
    st.session_state.video_info = None
if "stt_result" not in st.session_state:
    st.session_state.stt_result = None
if "video_start_time" not in st.session_state:
    st.session_state.video_start_time = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "youtube_url" not in st.session_state:
    st.session_state.youtube_url = ""


# ================= 헬퍼 함수 =================
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


def generate_srt(sentences) -> str:
    srt_blocks = []
    for idx, item in enumerate(sentences, 1):
        start_fmt = format_seconds(item["start"], for_srt=True)
        end_fmt = format_seconds(item["end"], for_srt=True)
        srt_blocks.append(f"{idx}\n{start_fmt} --> {end_fmt}\n{item['text']}\n")
    return "\n".join(srt_blocks)


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


def render_youtube_player(video_id: str):
    player_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            html, body {{
                width: 100%;
                height: 100%;
                overflow: hidden;
                background: #000;
                border-radius: 12px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                user-select: none;
            }}
            #main-container {{
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                background: #000;
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid #222;
            }}
            #player-wrap {{
                position: relative;
                flex: 1;
                width: 100%;
                background: #000;
            }}
            #yt-player {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                border: none;
            }}
            /* 유튜브 스타일 하단 컨트롤 바 */
            #ctrl-bar {{
                height: 48px;
                background: #0f0f0f;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 14px;
                border-top: 1px solid #222;
                color: #eee;
                font-size: 13px;
            }}
            .ctrl-group {{
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .ctrl-btn {{
                background: transparent;
                border: none;
                color: #f1f1f1;
                font-size: 15px;
                cursor: pointer;
                padding: 6px 10px;
                border-radius: 6px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 5px;
                transition: all 0.15s ease;
            }}
            .ctrl-btn:hover {{
                background: rgba(255, 255, 255, 0.15);
                color: #fff;
            }}
            /* CC 자막 버튼 */
            .cc-toggle-btn {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid #444;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12.5px;
                font-weight: 600;
                color: #bbb;
                cursor: pointer;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            .cc-toggle-btn:hover {{
                background: rgba(255, 255, 255, 0.2);
                color: #fff;
                border-color: #888;
            }}
            .cc-toggle-btn.active {{
                background: #e50914;
                color: #ffffff;
                border-color: #e50914;
                box-shadow: 0 0 8px rgba(229, 9, 20, 0.5);
            }}
            /* 볼륨 슬라이더 */
            .vol-wrap {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .vol-slider {{
                -webkit-appearance: none;
                appearance: none;
                width: 85px;
                height: 5px;
                border-radius: 3px;
                background: #444;
                outline: none;
                cursor: pointer;
                transition: background 0.2s;
            }}
            .vol-slider::-webkit-slider-thumb {{
                -webkit-appearance: none;
                appearance: none;
                width: 13px;
                height: 13px;
                border-radius: 50%;
                background: #fff;
                cursor: pointer;
                transition: transform 0.1s, background 0.1s;
            }}
            .vol-slider::-webkit-slider-thumb:hover {{
                transform: scale(1.2);
                background: #e50914;
            }}
            .vol-slider:hover {{
                background: #666;
            }}
            #vol-label {{
                font-size: 12px;
                color: #aaa;
                min-width: 34px;
            }}
            #time-label {{
                font-size: 12.5px;
                color: #aaa;
                margin-left: 6px;
                font-variant-numeric: tabular-nums;
            }}
        </style>
    </head>
    <body>
        <div id="main-container">
            <div id="player-wrap">
                <div id="yt-player"></div>
            </div>
            <div id="ctrl-bar">
                <div class="ctrl-group">
                    <button id="play-pause-btn" class="ctrl-btn" title="재생 / 일시정지">▶</button>
                    <div class="vol-wrap">
                        <button id="mute-btn" class="ctrl-btn" title="음소거 토글">🔊</button>
                        <input type="range" id="vol-slider" class="vol-slider" min="0" max="100" value="100" title="음향 조절" />
                        <span id="vol-label">100%</span>
                    </div>
                    <span id="time-label">00:00 / --:--</span>
                </div>
                <div class="ctrl-group">
                    <button id="cc-btn" class="cc-toggle-btn" title="자막 켜기/끄기">
                        <span>💬 자막 OFF</span>
                    </button>
                </div>
            </div>
        </div>
        <script>
            var tag = document.createElement('script');
            tag.src = "https://www.youtube.com/iframe_api";
            var firstScriptTag = document.getElementsByTagName('script')[0];
            firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

            var player;
            var isReady = false;
            var pendingSeek = null;
            var ccActive = false;
            var lastVolume = 100;

            function formatTime(seconds) {{
                if (!seconds || isNaN(seconds) || seconds < 0) return "00:00";
                seconds = Math.floor(seconds);
                var m = Math.floor(seconds / 60);
                var s = seconds % 60;
                return (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
            }}

            function onYouTubeIframeAPIReady() {{
                player = new YT.Player('yt-player', {{
                    videoId: '{video_id}',
                    playerVars: {{
                        'autoplay': 0,
                        'playsinline': 1,
                        'rel': 0,
                        'modestbranding': 1,
                        'enablejsapi': 1,
                        'cc_load_policy': 0, // 기본 자막 끄기
                        'controls': 1 // 유튜브 기본 컨트롤도 유지
                    }},
                    events: {{
                        'onReady': onPlayerReady,
                        'onStateChange': onPlayerStateChange
                    }}
                }});
            }}

            function onPlayerReady(event) {{
                isReady = true;

                // 기본 자막 끄기 보장
                try {{
                    player.unloadModule("captions");
                }} catch(e) {{}}

                if (pendingSeek !== null) {{
                    seekToTime(pendingSeek);
                    pendingSeek = null;
                }}

                try {{
                    window.parent.seekYouTubePlayer = seekToTime;
                }} catch(e) {{}}

                // 초기 볼륨 설정
                updateVolumeUI(100);

                // 시간 업데이트 인터벌 시작
                setInterval(updateTimeDisplay, 500);
            }}

            function onPlayerStateChange(event) {{
                var playBtn = document.getElementById('play-pause-btn');
                if (event.data === YT.PlayerState.PLAYING) {{
                    playBtn.innerText = '⏸';
                }} else {{
                    playBtn.innerText = '▶';
                }}
            }}

            function togglePlayPause() {{
                if (!player || typeof player.getPlayerState !== 'function') return;
                var state = player.getPlayerState();
                if (state === YT.PlayerState.PLAYING) {{
                    player.pauseVideo();
                }} else {{
                    player.playVideo();
                }}
            }}

            function updateTimeDisplay() {{
                if (!player || typeof player.getCurrentTime !== 'function') return;
                var current = player.getCurrentTime() || 0;
                var total = player.getDuration() || 0;
                document.getElementById('time-label').innerText = formatTime(current) + " / " + formatTime(total);
            }}

            function updateVolumeUI(val) {{
                document.getElementById('vol-slider').value = val;
                document.getElementById('vol-label').innerText = val + "%";
                var muteBtn = document.getElementById('mute-btn');
                if (val == 0) {{
                    muteBtn.innerText = '🔇';
                }} else if (val < 50) {{
                    muteBtn.innerText = '🔉';
                }} else {{
                    muteBtn.innerText = '🔊';
                }}
            }}

            function onVolumeChange(val) {{
                val = parseInt(val, 10);
                lastVolume = val;
                if (player && typeof player.setVolume === 'function') {{
                    player.setVolume(val);
                    if (val > 0 && player.isMuted()) {{
                        player.unMute();
                    }}
                }}
                updateVolumeUI(val);
            }}

            function toggleMute() {{
                if (!player) return;
                if (player.isMuted()) {{
                    player.unMute();
                    var restoreVal = lastVolume > 0 ? lastVolume : 50;
                    player.setVolume(restoreVal);
                    updateVolumeUI(restoreVal);
                }} else {{
                    player.mute();
                    updateVolumeUI(0);
                }}
            }}

            function toggleCaptions() {{
                if (!player) return;
                ccActive = !ccActive;
                var ccBtn = document.getElementById('cc-btn');
                if (ccActive) {{
                    try {{
                        player.loadModule("captions");
                        player.setOption("captions", "track", {{"languageCode": "ko"}});
                    }} catch(e) {{}}
                    ccBtn.classList.add('active');
                    ccBtn.innerHTML = '<span>💬 자막 ON</span>';
                }} else {{
                    try {{
                        player.unloadModule("captions");
                        player.setOption("captions", "track", {{}});
                    }} catch(e) {{}}
                    ccBtn.classList.remove('active');
                    ccBtn.innerHTML = '<span>💬 자막 OFF</span>';
                }}
            }}

            function seekToTime(sec) {{
                if (player && typeof player.seekTo === 'function') {{
                    player.seekTo(sec, true);
                    player.playVideo();
                }} else {{
                    pendingSeek = sec;
                }}
            }}

            // Event Listeners
            document.getElementById('play-pause-btn').onclick = togglePlayPause;
            document.getElementById('mute-btn').onclick = toggleMute;
            document.getElementById('vol-slider').oninput = function(e) {{
                onVolumeChange(e.target.value);
            }};
            document.getElementById('cc-btn').onclick = toggleCaptions;

            // 1. BroadcastChannel
            try {{
                const bc = new BroadcastChannel('youtube_player_channel');
                bc.onmessage = function(ev) {{
                    if (ev.data && ev.data.type === 'SEEK' && typeof ev.data.time === 'number') {{
                        seekToTime(ev.data.time);
                    }}
                }};
            }} catch(e) {{}}

            // 2. Window message
            window.addEventListener('message', function(ev) {{
                if (ev.data && ev.data.type === 'SEEK_YOUTUBE' && typeof ev.data.time === 'number') {{
                    seekToTime(ev.data.time);
                }}
            }});
            try {{
                window.parent.addEventListener('message', function(ev) {{
                    if (ev.data && ev.data.type === 'SEEK_YOUTUBE' && typeof ev.data.time === 'number') {{
                        seekToTime(ev.data.time);
                    }}
                }});
            }} catch(e) {{}}
        </script>
    </body>
    </html>
    """
    components.html(player_html, height=500)


def render_interactive_timestamps(sentences: list):
    sentences_json = json.dumps(sentences, ensure_ascii=False)
    ts_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            html, body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
                background: transparent;
                color: #1f1f1f;
                height: 100%;
                overflow: hidden;
            }}
            #container {{
                display: flex;
                flex-direction: column;
                height: 100%;
                padding-right: 4px;
            }}
            #search-bar {{
                position: sticky;
                top: 0;
                z-index: 10;
                background: #ffffff;
                padding-bottom: 8px;
            }}
            .search-input {{
                width: 100%;
                padding: 9px 12px;
                border: 1px solid #dcdcdc;
                border-radius: 8px;
                font-size: 13.5px;
                outline: none;
                transition: border-color 0.2s, box-shadow 0.2s;
            }}
            .search-input:focus {{
                border-color: #1a73e8;
                box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.2);
            }}
            .search-meta {{
                font-size: 11.5px;
                color: #666;
                margin-top: 5px;
                margin-bottom: 6px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            #list-container {{
                flex: 1;
                overflow-y: auto;
                border: 1px solid #eeeeee;
                border-radius: 8px;
                background: #fafafa;
                padding: 6px;
            }}
            #list-container::-webkit-scrollbar {{
                width: 6px;
            }}
            #list-container::-webkit-scrollbar-thumb {{
                background: #cccccc;
                border-radius: 3px;
            }}
            #list-container::-webkit-scrollbar-thumb:hover {{
                background: #999999;
            }}
            .ts-row {{
                display: flex;
                align-items: flex-start;
                gap: 10px;
                padding: 8px 10px;
                margin-bottom: 4px;
                border-radius: 6px;
                background: #ffffff;
                border-left: 3px solid transparent;
                transition: all 0.15s ease;
                cursor: pointer;
            }}
            .ts-row:hover {{
                background: #f1f5f9;
                border-left-color: #e50914;
            }}
            .ts-row.active {{
                background: #eff6ff;
                border-left-color: #1a73e8;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }}
            .ts-btn {{
                flex-shrink: 0;
                background: #f0f4f9;
                color: #1a73e8;
                border: 1px solid #d3e3fd;
                border-radius: 14px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                white-space: nowrap;
            }}
            .ts-btn:hover {{
                background: #e50914;
                color: #ffffff;
                border-color: #e50914;
                transform: scale(1.03);
            }}
            .ts-text {{
                font-size: 13px;
                line-height: 1.45;
                color: #222222;
                padding-top: 2px;
                flex: 1;
            }}
            .empty-msg {{
                text-align: center;
                color: #888;
                padding: 40px 10px;
                font-size: 13px;
            }}
        </style>
    </head>
    <body>
        <div id="container">
            <div id="search-bar">
                <input type="text" id="search-input" class="search-input" placeholder="🔍 특정 단어나 문장 검색 (실시간 필터링)..." />
                <div class="search-meta">
                    <span id="match-count">총 {len(sentences)}개 문장</span>
                    <span style="color: #1a73e8; font-weight: 500;">▶ 클릭 시 영상이 멈추지 않고 즉시 이동</span>
                </div>
            </div>
            <div id="list-container"></div>
        </div>

        <script>
            const allSentences = {sentences_json};
            const listEl = document.getElementById('list-container');
            const searchInput = document.getElementById('search-input');
            const matchCountEl = document.getElementById('match-count');

            function formatSeconds(sec) {{
                const total = Math.floor(sec);
                const m = Math.floor(total / 60);
                const s = total % 60;
                return (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
            }}

            function seekVideo(sec, rowEl) {{
                document.querySelectorAll('.ts-row').forEach(r => r.classList.remove('active'));
                if (rowEl) {{
                    rowEl.classList.add('active');
                }}

                // 1. BroadcastChannel
                try {{
                    const bc = new BroadcastChannel('youtube_player_channel');
                    bc.postMessage({{ type: 'SEEK', time: sec }});
                }} catch(e) {{}}

                // 2. window.parent direct call
                try {{
                    if (window.parent && typeof window.parent.seekYouTubePlayer === 'function') {{
                        window.parent.seekYouTubePlayer(sec);
                    }}
                }} catch(e) {{}}

                // 3. postMessage
                try {{
                    window.parent.postMessage({{ type: 'SEEK_YOUTUBE', time: sec }}, '*');
                }} catch(e) {{}}
            }}

            function renderList(filterText = '') {{
                listEl.innerHTML = '';
                const query = filterText.trim().toLowerCase();
                let count = 0;

                allSentences.forEach((s, idx) => {{
                    const text = s.text || '';
                    if (query && !text.toLowerCase().includes(query)) {{
                        return;
                    }}
                    count++;

                    const row = document.createElement('div');
                    row.className = 'ts-row';
                    const startSec = Math.floor(s.start || 0);

                    row.innerHTML = `
                        <button class="ts-btn" type="button">▶ ${{formatSeconds(s.start)}}</button>
                        <div class="ts-text">${{text}}</div>
                    `;

                    row.onclick = () => seekVideo(startSec, row);
                    row.querySelector('.ts-btn').onclick = (e) => {{
                        e.stopPropagation();
                        seekVideo(startSec, row);
                    }};

                    listEl.appendChild(row);
                }});

                if (count === 0) {{
                    listEl.innerHTML = '<div class="empty-msg">검색 결과가 없습니다.</div>';
                }}
                matchCountEl.textContent = query ? `검색 결과: ${{count}}개 발견` : `총 ${{count}}개 문장`;
            }}

            searchInput.addEventListener('input', (e) => {{
                renderList(e.target.value);
            }});

            renderList();
        </script>
    </body>
    </html>
    """
    components.html(ts_html, height=520)


def download_youtube_audio(url: str, output_dir: str = "downloads"):
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
            logging.error(f"요약 및 키워드 추출 중 오류 발생: {e}")
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


# ================= 상단 헤더 바 (YouTube AI Search Header) =================
header_col1, header_col2 = st.columns([1, 3], vertical_alignment="center")

with header_col1:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 8px;">
        <span style="color: #FF0000; font-size: 28px; line-height: 1;">▶</span>
        <span style="font-size: 21px; font-weight: 800; letter-spacing: -0.5px; color: #0f0f0f;">YouTube</span>
        <span style="font-size: 11px; font-weight: 700; color: #ffffff; background: #e50914; padding: 2px 6px; border-radius: 4px;">AI Search</span>
    </div>
    """, unsafe_allow_html=True)

with header_col2:
    search_c1, search_c2 = st.columns([6, 1], vertical_alignment="center")
    with search_c1:
        input_url = st.text_input(
            "Search Input",
            value=st.session_state.youtube_url,
            placeholder="유튜브 영상 주소(URL)를 입력하세요... (예: https://www.youtube.com/watch?v=...)",
            label_visibility="collapsed"
        )
    with search_c2:
        start_btn = st.button("🔍 분석", type="primary", width="stretch")

active_api_key = st.session_state.get("api_key", os.environ.get("GEMINI_API_KEY", ""))

st.divider()

# ================= 분석 프로세스 실행 =================
if start_btn:
    if not input_url.strip():
        st.warning("⚠️ 유튜브 URL을 입력해 주세요.")
    elif not active_api_key.strip():
        st.error("⚠️ Gemini API Key가 설정되지 않았습니다. 환경 변수(GEMINI_API_KEY)를 설정해 주세요.")
    else:
        st.session_state.youtube_url = input_url.strip()
        st.session_state.video_start_time = 0
        st.session_state.chat_history = []
        
        with st.status("🎬 유튜브 영상을 분석 중입니다...", expanded=True) as status:
            try:
                st.write("1/3 유튜브 영상 메타데이터 및 오디오 다운로드 중...")
                v_info = download_youtube_audio(st.session_state.youtube_url)
                st.session_state.video_info = v_info
                
                status.update(label="🤖 Gemini 3.5 Transcribe로 정밀 STT 분석 중...", state="running")
                st.write("2/3 오디오 전사 및 문장별 타임스탬프 계산 중...")
                stt_res = transcribe_and_summarize(v_info["file_path"], v_info["ext"], active_api_key)
                st.session_state.stt_result = stt_res
                
                status.update(label="🎉 분석이 성공적으로 완료되었습니다!", state="complete", expanded=False)
                st.rerun()
            except Exception as e:
                status.update(label="❌ 오류가 발생했습니다.", state="error")
                st.error(f"오류 상세: {str(e)}")


# ================= 메인 본문 (좌측 영상 60% : 우측 3대 탭 40%) =================
if st.session_state.video_info and st.session_state.stt_result:
    v_info = st.session_state.video_info
    stt_res = st.session_state.stt_result

    left_col, right_col = st.columns([13, 10], gap="large")

    # ---------------- 좌측 비디오 영역 ----------------
    with left_col:
        # 1. 실제 유튜브 영상 플레이어 (끊김 없는 즉시 이동 지원)
        video_id = extract_youtube_id(st.session_state.youtube_url)
        if video_id:
            render_youtube_player(video_id)
        else:
            st.video(st.session_state.youtube_url, start_time=st.session_state.video_start_time)
        
        # 2. 영상 제목
        st.markdown(f'<div class="video-title">{v_info["title"]}</div>', unsafe_allow_html=True)
        
        # 3. 채널 및 부가 정보
        uploader_initial = v_info["uploader"][:1].upper() if v_info.get("uploader") else "Y"
        st.markdown(f"""
        <div class="video-channel-row">
            <div class="channel-avatar">{uploader_initial}</div>
            <div>
                <div class="channel-name">{v_info["uploader"]}</div>
                <div class="channel-sub">재생시간: {format_seconds(v_info["duration"])}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 4. 설명란 및 전체 트랜스크립트 전문
        with st.expander("📝 영상 설명란 & 전체 트랜스크립트 전문 펼치기", expanded=False):
            st.markdown("#### 전체 전사문 (Full Transcript)")
            st.text_area("스크립트 내용 (복사 가능)", value=stt_res["full_text"], height=250)
            if os.path.exists(v_info["file_path"]):
                st.markdown("**🎧 추출된 고음질 오디오 직접 듣기:**")
                st.audio(v_info["file_path"])

    # ---------------- 우측 3대 탭 영역 ----------------
    with right_col:
        tab_dash, tab_time, tab_chat = st.tabs(["📊 대시보드", "⏱️ 타임스탬프", "💬 AI 질의응답"])

        # ====== 탭 1: 대시보드 ======
        with tab_dash:
            st.subheader("📌 영상 핵심 요약")
            st.markdown(stt_res.get("summary", "요약 정보가 없습니다."))
            
            st.divider()
            
            st.markdown("##### 🏷️ 주요 키워드")
            kws = stt_res.get("keywords", [])
            if kws:
                kw_html = " ".join([f'<span class="kw-tag">#{k}</span>' for k in kws])
                st.markdown(kw_html, unsafe_allow_html=True)
            else:
                st.caption("키워드가 없습니다.")

            st.divider()

            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{format_seconds(v_info['duration'])}</div>
                    <div class="metric-label">총 영상 길이</div>
                </div>
                """, unsafe_allow_html=True)
            with m_col2:
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{len(stt_res['sentences'])}개</div>
                    <div class="metric-label">추출된 문장 수</div>
                </div>
                """, unsafe_allow_html=True)
            with m_col3:
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{stt_res.get('speaker', '화자 1')}</div>
                    <div class="metric-label">인식 화자</div>
                </div>
                """, unsafe_allow_html=True)

            st.divider()

            st.markdown("##### 📥 자막 파일 다운로드")
            srt_content = generate_srt(stt_res["sentences"])
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                st.download_button(
                    "🎬 자막 파일 (.srt)",
                    data=srt_content,
                    file_name=f"{v_info['title']}.srt",
                    mime="text/plain",
                    width="stretch"
                )
            with d_col2:
                st.download_button(
                    "📄 텍스트 파일 (.txt)",
                    data=stt_res["full_text"],
                    file_name=f"{v_info['title']}.txt",
                    mime="text/plain",
                    width="stretch"
                )

        # ====== 탭 2: 타임스탬프 & 영상 위치 연동 ======
        with tab_time:
            st.subheader("⏱️ 문장별 타임스탬프")
            st.caption("시간 버튼(`▶ 00:00`)이나 문장을 클릭하면 영상이 멈추지 않고 해당 위치로 즉시 이동합니다.")
            
            video_id = extract_youtube_id(st.session_state.youtube_url)
            sentences = stt_res.get("sentences", [])
            
            if not sentences:
                st.info("표시할 타임스탬프 문장이 없습니다.")
            elif video_id:
                render_interactive_timestamps(sentences)
            else:
                # 일반 비디오 URL 폴백
                search_query = st.text_input("🔍 특정 단어나 문장 검색", placeholder="예: 아이폰, 가격, 출시일 등", label_visibility="collapsed")
                if search_query.strip():
                    sentences = [s for s in sentences if search_query.lower() in s["text"].lower()]
                    st.caption(f"검색 결과: 총 {len(sentences)}개 문장 발견")

                time_container = st.container(height=520)
                with time_container:
                    for idx, s in enumerate(sentences):
                        start_sec = int(s["start"])
                        btn_label = f"▶ {format_seconds(s['start'])}"
                        btn_col, txt_col = st.columns([1, 3], vertical_alignment="center")
                        with btn_col:
                            if st.button(btn_label, key=f"ts_{idx}_{start_sec}", width="stretch", help="클릭 시 영상 이동"):
                                st.session_state.video_start_time = start_sec
                                st.rerun()
                        with txt_col:
                            st.write(s["text"])

        # ====== 탭 3: AI 질의응답 (영상 챗봇) ======
        with tab_chat:
            # 1. 유튜브 '이 동영상에 대해 물어보세요' 스타일 헤더 & 추천 질문지
            suggested_q = stt_res.get("suggested_questions", [])
            if not suggested_q:
                suggested_q = [
                    "동영상을 요약해 줘",
                    "관련 콘텐츠를 추천해 줘",
                    "이 영상의 가장 핵심적인 내용은?",
                    "영상에서 다룬 중요 포인트는?",
                    "결론 및 시사점은 무엇인가요?"
                ]

            clicked_q = None

            # 유튜브 AI 공식 스타일 카드 렌더링
            st.markdown("""
            <div class="yt-ask-card">
                <div class="yt-ask-header">
                    <span class="yt-ask-sparkle">✦</span>
                    <span>이 동영상에 대해 물어보세요</span>
                </div>
                <div class="yt-ask-intro">
                    안녕하세요. 시청 중인 콘텐츠가 궁금하신가요? 최선을 다해 도와드리겠습니다.<br><br>
                    어떻게 질문해야 할지 모르겠다면 다음 예와 같이 질문해 보세요.
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 우측 정렬 알약(Pill) 질문 버튼 목록 (문장이 끝까지 잘리지 않고 줄바꿈 표시)
            for idx, q_text in enumerate(suggested_q):
                _, q_col = st.columns([1, 4])
                with q_col:
                    if st.button(q_text, key=f"sq_btn_{idx}", width="stretch", help="클릭하여 즉시 질문하기"):
                        clicked_q = q_text

            st.divider()

            # 2. 대화 기록 컨테이너
            chat_container = st.container(height=360)
            with chat_container:
                if not st.session_state.chat_history:
                    st.chat_message("assistant").write("위의 **추천 질문**을 클릭하시거나 아래 입력창에 직접 질문을 입력해 주시면 타임스탬프와 함께 자세히 답변해 드릴게요. 😊")
                else:
                    for msg in st.session_state.chat_history:
                        st.chat_message(msg["role"]).write(msg["content"])

            input_q = st.chat_input("이 동영상에 대해 질문하세요... (예: 핵심 결론이 뭐야?, 가격이 얼마야?)")
            
            active_question = clicked_q or input_q

            if active_question:
                if not active_api_key.strip():
                    st.error("⚠️ Gemini API Key가 필요합니다. 환경 변수(GEMINI_API_KEY)를 확인해 주세요.")
                else:
                    st.session_state.chat_history.append({"role": "user", "content": active_question})
                    
                    with chat_container:
                        st.chat_message("user").write(active_question)
                        with st.chat_message("assistant"):
                            with st.spinner("영상을 분석하여 답변을 생성하는 중..."):
                                ai_answer = ask_gemini_about_video(
                                    question=active_question,
                                    full_text=stt_res["full_text"],
                                    sentences=stt_res["sentences"],
                                    chat_history=st.session_state.chat_history,
                                    api_key=active_api_key
                                )
                                st.write(ai_answer)
                    
                    st.session_state.chat_history.append({"role": "assistant", "content": ai_answer})
                    st.rerun()

else:
    st.markdown("""
    <div style="text-align: center; padding: 4rem 2rem; color: #606060;">
        <div style="font-size: 3.5rem; margin-bottom: 1rem;">📺</div>
        <h2 style="color: #0f0f0f; font-weight: 700;">YouTube AI Search에 오신 것을 환영합니다!</h2>
        <p style="font-size: 1.1rem; max-width: 600px; margin: 0.5rem auto 1.5rem auto;">
            상단 검색창에 분석하고 싶은 <b>유튜브 영상 링크(URL)</b>를 입력하고 <b>[🔍 분석]</b> 버튼을 눌러보세요.<br>
            영상 재생과 함께 <b>대시보드 요약, 타임스탬프 연동, AI 질의응답 챗봇</b>이 즉시 활성화됩니다.
        </p>
    </div>
    """, unsafe_allow_html=True)


# ================= 자동 실행 지원 =================
if __name__ == "__main__":
    import streamlit.runtime
    if not streamlit.runtime.exists():
        import sys
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())
