/**
 * YouTube AI Search - Client Application Logic
 * Vanilla JavaScript implementation
 */

// ================= 상태 관리 (State) =================
const state = {
    videoInfo: null,
    sttResult: null,
    chatHistory: [],
    player: null,
    isPlayerReady: false,
    pendingSeek: null,
    ccActive: false,
    lastVolume: 100,
    timeUpdateTimer: null
};

// ================= DOM 요소 셀렉터 =================
const elements = {
    // Header & Search
    headerLogoBtn: document.getElementById('header-logo-btn'),
    analyzeForm: document.getElementById('analyze-form'),
    ytUrlInput: document.getElementById('yt-url-input'),
    clearSearchBtn: document.getElementById('clear-search-btn'),
    analyzeBtn: document.getElementById('analyze-btn'),
    
    // Views
    welcomeView: document.getElementById('welcome-view'),
    loadingOverlay: document.getElementById('loading-overlay'),
    loadingTitle: document.getElementById('loading-title'),
    step1: document.getElementById('step-1'),
    step2: document.getElementById('step-2'),
    step3: document.getElementById('step-3'),
    resultView: document.getElementById('result-view'),

    // Video Player & Controls
    ytPlayerContainer: document.getElementById('yt-player'),
    playPauseBtn: document.getElementById('play-pause-btn'),
    playIcon: document.getElementById('play-icon'),
    muteBtn: document.getElementById('mute-btn'),
    volSlider: document.getElementById('vol-slider'),
    volLabel: document.getElementById('vol-label'),
    timeLabel: document.getElementById('time-label'),
    ccBtn: document.getElementById('cc-btn'),
    
    // Video Meta
    videoTitle: document.getElementById('video-title'),
    channelAvatar: document.getElementById('channel-avatar'),
    channelName: document.getElementById('channel-name'),
    channelSub: document.getElementById('channel-sub'),
    fullTranscriptArea: document.getElementById('full-transcript-area'),
    copyTranscriptBtn: document.getElementById('copy-transcript-btn'),
    extractedAudio: document.getElementById('extracted-audio'),

    // Tabs
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabPanels: document.querySelectorAll('.tab-panel'),

    // Dashboard
    summaryContent: document.getElementById('summary-content'),
    keywordsContent: document.getElementById('keywords-content'),
    metricDuration: document.getElementById('metric-duration'),
    metricSentences: document.getElementById('metric-sentences'),
    metricSpeaker: document.getElementById('metric-speaker'),
    downloadSrtBtn: document.getElementById('download-srt-btn'),
    downloadTxtBtn: document.getElementById('download-txt-btn'),

    // Timestamps
    tsSearchInput: document.getElementById('ts-search-input'),
    tsMatchCount: document.getElementById('ts-match-count'),
    tsListContainer: document.getElementById('ts-list-container'),

    // Chat
    suggestedQuestionsList: document.getElementById('suggested-questions-list'),
    chatMessagesBox: document.getElementById('chat-messages-box'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    chatSendBtn: document.querySelector('.chat-send-btn')
};


// ================= 헬퍼 함수 =================
function formatSeconds(seconds, forSrt = false) {
    if (isNaN(seconds) || seconds < 0) seconds = 0;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    const wholeSecs = Math.floor(secs);
    const millis = Math.round((secs - wholeSecs) * 1000);

    const pad = (n, width = 2) => String(n).padStart(width, '0');

    if (forSrt) {
        return `${pad(hours)}:${pad(minutes)}:${pad(wholeSecs)},${pad(millis, 3)}`;
    } else {
        if (hours > 0) {
            return `${pad(hours)}:${pad(minutes)}:${pad(wholeSecs)}`;
        }
        return `${pad(minutes)}:${pad(wholeSecs)}`;
    }
}

function parseTimeToSeconds(timeStr) {
    const parts = timeStr.trim().split(':').map(Number);
    if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    } else if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    return 0;
}

function extractYoutubeId(url) {
    if (!url) return '';
    const patterns = [
        /(?:v=|\/)([0-9A-Za-z_-]{11}).*/,
        /(?:embed\/)([0-9A-Za-z_-]{11})/,
        /(?:youtu\.be\/)([0-9A-Za-z_-]{11})/,
        /(?:shorts\/)([0-9A-Za-z_-]{11})/
    ];
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }
    return '';
}

function generateSrt(sentences) {
    if (!sentences || !sentences.length) return '';
    return sentences.map((s, idx) => {
        const startFmt = formatSeconds(s.start || 0, true);
        const endFmt = formatSeconds(s.end || 0, true);
        return `${idx + 1}\n${startFmt} --> ${endFmt}\n${s.text || ''}\n`;
    }).join('\n');
}

function triggerDownload(content, filename, mimeType = 'text/plain;charset=utf-8') {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 100);
}


// ================= YouTube IFrame API 연동 =================
window.onYouTubeIframeAPIReady = function() {
    console.log("YouTube IFrame API Ready");
};

function initYouTubePlayer(videoId) {
    if (state.player) {
        try {
            state.player.destroy();
        } catch (e) {
            console.warn("Player destroy error:", e);
        }
        state.player = null;
    }

    state.isPlayerReady = false;
    state.ccActive = false;
    updateCaptionsUI(false);

    // YT.Player 객체 초기화
    state.player = new YT.Player('yt-player', {
        videoId: videoId,
        playerVars: {
            'autoplay': 0,
            'playsinline': 1,
            'rel': 0,
            'modestbranding': 1,
            'enablejsapi': 1,
            'cc_load_policy': 0, // 기본 자막 끄기
            'controls': 1        // 유튜브 표준 컨트롤도 유지
        },
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
}

function onPlayerReady(event) {
    state.isPlayerReady = true;

    // 초기 볼륨 설정
    updateVolumeUI(100);

    // 기본 자막 끄기
    try {
        state.player.unloadModule("captions");
    } catch (e) {}

    // 지연된 seek가 있으면 실행
    if (state.pendingSeek !== null) {
        seekVideo(state.pendingSeek);
        state.pendingSeek = null;
    }

    // 시간 업데이트 타이머 시작
    if (state.timeUpdateTimer) clearInterval(state.timeUpdateTimer);
    state.timeUpdateTimer = setInterval(updateTimeDisplay, 500);
}

function onPlayerStateChange(event) {
    if (event.data === YT.PlayerState.PLAYING) {
        elements.playIcon.textContent = '⏸';
    } else {
        elements.playIcon.textContent = '▶';
    }
}

function togglePlayPause() {
    if (!state.player || !state.isPlayerReady) return;
    const playerState = state.player.getPlayerState();
    if (playerState === YT.PlayerState.PLAYING) {
        state.player.pauseVideo();
    } else {
        state.player.playVideo();
    }
}

function updateTimeDisplay() {
    if (!state.player || !state.isPlayerReady) return;
    try {
        const current = state.player.getCurrentTime() || 0;
        const total = state.player.getDuration() || (state.videoInfo ? state.videoInfo.duration : 0);
        elements.timeLabel.textContent = `${formatSeconds(current)} / ${formatSeconds(total)}`;
    } catch (e) {}
}

function updateVolumeUI(val) {
    elements.volSlider.value = val;
    elements.volLabel.textContent = `${val}%`;
    if (val === 0) {
        elements.muteBtn.textContent = '🔇';
    } else if (val < 50) {
        elements.muteBtn.textContent = '🔉';
    } else {
        elements.muteBtn.textContent = '🔊';
    }
}

function onVolumeChange(val) {
    val = parseInt(val, 10);
    state.lastVolume = val;
    if (state.player && state.isPlayerReady) {
        state.player.setVolume(val);
        if (val > 0 && state.player.isMuted()) {
            state.player.unMute();
        }
    }
    updateVolumeUI(val);
}

function toggleMute() {
    if (!state.player || !state.isPlayerReady) return;
    if (state.player.isMuted()) {
        state.player.unMute();
        const restoreVal = state.lastVolume > 0 ? state.lastVolume : 50;
        state.player.setVolume(restoreVal);
        updateVolumeUI(restoreVal);
    } else {
        state.player.mute();
        updateVolumeUI(0);
    }
}

function updateCaptionsUI(active) {
    if (active) {
        elements.ccBtn.classList.add('active');
        elements.ccBtn.innerHTML = '<span>💬 자막 ON</span>';
    } else {
        elements.ccBtn.classList.remove('active');
        elements.ccBtn.innerHTML = '<span>💬 자막 OFF</span>';
    }
}

function toggleCaptions() {
    if (!state.player || !state.isPlayerReady) return;
    state.ccActive = !state.ccActive;
    if (state.ccActive) {
        try {
            state.player.loadModule("captions");
            state.player.setOption("captions", "track", { "languageCode": "ko" });
        } catch (e) {}
        updateCaptionsUI(true);
    } else {
        try {
            state.player.unloadModule("captions");
            state.player.setOption("captions", "track", {});
        } catch (e) {}
        updateCaptionsUI(false);
    }
}

/**
 * 끊김 없는 타임스탬프 스킵:
 * 영상을 멈추지 않고 실시간으로 즉시 재생 유지
 */
function seekVideo(seconds) {
    if (state.player && state.isPlayerReady) {
        state.player.seekTo(seconds, true);
        state.player.playVideo();
    } else {
        state.pendingSeek = seconds;
    }
}


// ================= 분석 API 통신 =================
async function analyzeVideo(url) {
    if (!url.trim()) return;

    // 로딩 UI 표시 및 단계 시뮬레이션
    elements.loadingOverlay.style.display = 'flex';
    elements.step1.className = 'step-item active';
    elements.step2.className = 'step-item';
    elements.step3.className = 'step-item';
    elements.analyzeBtn.disabled = true;

    const stepTimer1 = setTimeout(() => {
        elements.step1.className = 'step-item done';
        elements.step2.className = 'step-item active';
    }, 3500);

    const stepTimer2 = setTimeout(() => {
        elements.step2.className = 'step-item done';
        elements.step3.className = 'step-item active';
    }, 12000);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url.trim() })
        });

        clearTimeout(stepTimer1);
        clearTimeout(stepTimer2);

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `서버 에러 (${response.status})`);
        }

        const data = await response.json();
        state.videoInfo = data.video_info;
        state.sttResult = data.stt_result;
        state.chatHistory = [];

        // 성공 상태 표시
        elements.step1.className = 'step-item done';
        elements.step2.className = 'step-item done';
        elements.step3.className = 'step-item done';

        setTimeout(() => {
            elements.loadingOverlay.style.display = 'none';
            renderAllResults();
        }, 500);

    } catch (err) {
        clearTimeout(stepTimer1);
        clearTimeout(stepTimer2);
        elements.loadingOverlay.style.display = 'none';
        alert(`분석 중 오류가 발생했습니다: ${err.message}`);
    } finally {
        elements.analyzeBtn.disabled = false;
    }
}


// ================= 화면 렌더링 =================
function renderAllResults() {
    const v = state.videoInfo;
    const s = state.sttResult;

    // 1. 웰컴 화면 숨기고 결과 뷰 표시
    elements.welcomeView.style.display = 'none';
    elements.resultView.style.display = 'grid';

    // 2. 유튜브 플레이어 로드
    initYouTubePlayer(v.id);

    // 3. 비디오 메타 정보 렌더링
    elements.videoTitle.textContent = v.title;
    elements.channelName.textContent = v.uploader;
    elements.channelAvatar.textContent = (v.uploader || 'Y').charAt(0).toUpperCase();
    elements.channelSub.textContent = `재생시간: ${v.duration_formatted || formatSeconds(v.duration)}`;

    // 4. 전체 트랜스크립트 및 오디오
    elements.fullTranscriptArea.value = s.full_text || '';
    if (v.audio_url) {
        elements.extractedAudio.src = v.audio_url;
    }

    // 5. 탭 1: 대시보드 렌더링
    renderDashboard();

    // 6. 탭 2: 타임스탬프 렌더링
    renderTimestamps();

    // 7. 탭 3: AI 질의응답 렌더링
    renderChatInterface();

    // 창 스크롤 상단 이동
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderDashboard() {
    const s = state.sttResult;
    const v = state.videoInfo;

    // 요약 불릿 포인트
    const summaryLines = (s.summary || '').split('\n').filter(line => line.trim());
    if (summaryLines.length > 0) {
        const listHtml = summaryLines.map(line => {
            const cleanText = line.replace(/^[-*•]\s*/, '');
            return `<li>${cleanText}</li>`;
        }).join('');
        elements.summaryContent.innerHTML = `<ul>${listHtml}</ul>`;
    } else {
        elements.summaryContent.innerHTML = '<p>요약 정보가 없습니다.</p>';
    }

    // 키워드 태그
    const keywords = s.keywords || [];
    if (keywords.length > 0) {
        elements.keywordsContent.innerHTML = keywords.map(kw => `<span class="kw-tag">#${kw}</span>`).join('');
    } else {
        elements.keywordsContent.innerHTML = '<span class="text-muted">키워드가 없습니다.</span>';
    }

    // 메트릭스
    elements.metricDuration.textContent = v.duration_formatted || formatSeconds(v.duration);
    elements.metricSentences.textContent = `${(s.sentences || []).length}개`;
    elements.metricSpeaker.textContent = s.speaker || '화자 1';
}

function renderTimestamps(filterQuery = '') {
    const sentences = state.sttResult ? (state.sttResult.sentences || []) : [];
    const query = filterQuery.trim().toLowerCase();
    elements.tsListContainer.innerHTML = '';

    let matchCount = 0;

    sentences.forEach((item, index) => {
        const text = item.text || '';
        if (query && !text.toLowerCase().includes(query)) {
            return;
        }
        matchCount++;

        const row = document.createElement('div');
        row.className = 'ts-row';
        row.dataset.index = index;

        const startSec = Math.floor(item.start || 0);
        const timeBadgeText = `▶ ${formatSeconds(item.start || 0)}`;

        // 검색어 하이라이팅
        let displayText = text;
        if (query) {
            const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
            displayText = text.replace(regex, '<span class="highlight">$1</span>');
        }

        row.innerHTML = `
            <button class="ts-btn" type="button">${timeBadgeText}</button>
            <div class="ts-text">${displayText}</div>
        `;

        // 행 전체 또는 버튼 클릭 시 즉시 영상 이동
        row.onclick = () => {
            document.querySelectorAll('.ts-row.active').forEach(el => el.classList.remove('active'));
            row.classList.add('active');
            seekVideo(startSec);
        };

        elements.tsListContainer.appendChild(row);
    });

    elements.tsMatchCount.textContent = query 
        ? `검색 결과: 총 ${matchCount}개 문장 발견` 
        : `총 ${matchCount}개 문장`;

    if (matchCount === 0) {
        elements.tsListContainer.innerHTML = '<div style="text-align: center; padding: 24px; color: #888;">일치하는 검색 결과가 없습니다.</div>';
    }
}

function renderChatInterface() {
    const s = state.sttResult;
    const questions = s.suggested_questions || [
        "동영상을 요약해 줘",
        "관련 콘텐츠를 추천해 줘",
        "이 영상의 가장 핵심적인 내용은?",
        "영상에서 다룬 중요 포인트는?",
        "결론 및 시사점은 무엇인가요?"
    ];

    // 유튜브 공식 AI 추천 질문 알약(Pill) 목록 생성
    elements.suggestedQuestionsList.innerHTML = '';
    questions.forEach(qText => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'suggested-q-btn';
        btn.textContent = qText;
        btn.title = '클릭하여 질문하기';
        btn.onclick = () => {
            submitChatMessage(qText);
        };
        elements.suggestedQuestionsList.appendChild(btn);
    });

    // 대화창 초기화
    elements.chatMessagesBox.innerHTML = `
        <div class="chat-msg assistant">
            <div class="msg-avatar">🤖</div>
            <div class="msg-bubble">
                위의 <b>추천 질문</b>을 클릭하시거나 아래 입력창에 직접 질문을 입력해 주시면 타임스탬프와 함께 자세히 답변해 드릴게요. 😊
            </div>
        </div>
    `;
}


// ================= AI 채팅 기능 =================
async function submitChatMessage(questionText) {
    if (!questionText || !questionText.trim()) return;
    const question = questionText.trim();
    if (!state.sttResult) return;

    // 1. 사용자 메시지 UI 추가
    appendMessage('user', question);
    elements.chatInput.value = '';
    state.chatHistory.push({ role: 'user', content: question });

    // 2. 어시스턴트 로딩 메시지 UI 추가
    const loadingMsgEl = appendLoadingMessage();

    // 전송 버튼 비활성화
    elements.chatSendBtn.disabled = true;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                full_text: state.sttResult.full_text || '',
                sentences: state.sttResult.sentences || [],
                chat_history: state.chatHistory
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || '답변 생성 실패');
        }

        const data = await response.json();
        const answer = data.answer || '답변을 생성하지 못했습니다.';

        // 로딩 제거 후 실제 답변 렌더링
        loadingMsgEl.remove();
        appendMessage('assistant', answer);
        state.chatHistory.push({ role: 'assistant', content: answer });

    } catch (e) {
        loadingMsgEl.remove();
        appendMessage('assistant', `⚠️ 답변 생성 중 오류가 발생했습니다: ${e.message}`);
    } finally {
        elements.chatSendBtn.disabled = false;
    }
}

function appendMessage(role, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-msg ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = role === 'assistant' ? '🤖' : '👤';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';

    // [MM:SS] 타임스탬프 링크 변환
    const formattedText = text.replace(/\[(\d{1,2}:\d{2})\]/g, (match, timeStr) => {
        const sec = parseTimeToSeconds(timeStr);
        return `<span class="ts-link" data-time="${sec}">${match}</span>`;
    });

    bubble.innerHTML = formattedText.replace(/\n/g, '<br>');

    // 타임스탬프 링크 클릭 이벤트
    bubble.querySelectorAll('.ts-link').forEach(link => {
        link.onclick = (e) => {
            e.stopPropagation();
            const sec = parseInt(link.getAttribute('data-time'), 10);
            seekVideo(sec);
        };
    });

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    elements.chatMessagesBox.appendChild(msgDiv);

    // 스크롤 최하단 이동
    elements.chatMessagesBox.scrollTop = elements.chatMessagesBox.scrollHeight;
    return msgDiv;
}

function appendLoadingMessage() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg assistant';

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = '<em>영상을 분석하여 답변을 생성하는 중... ⏳</em>';

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    elements.chatMessagesBox.appendChild(msgDiv);

    elements.chatMessagesBox.scrollTop = elements.chatMessagesBox.scrollHeight;
    return msgDiv;
}


// ================= 이벤트 리스너 바인딩 =================
function setupEventListeners() {
    // 1. 헤더 로고 클릭 시 초기 화면
    elements.headerLogoBtn.onclick = () => {
        if (confirm('처음 화면으로 돌아가시겠습니까?')) {
            elements.resultView.style.display = 'none';
            elements.welcomeView.style.display = 'flex';
            if (state.player && state.isPlayerReady) {
                state.player.pauseVideo();
            }
        }
    };

    // 2. 검색창 입력 & 클리어
    elements.ytUrlInput.oninput = (e) => {
        elements.clearSearchBtn.style.display = e.target.value ? 'block' : 'none';
    };

    elements.clearSearchBtn.onclick = () => {
        elements.ytUrlInput.value = '';
        elements.clearSearchBtn.style.display = 'none';
        elements.ytUrlInput.focus();
    };

    // 3. 분석 제출
    elements.analyzeForm.onsubmit = (e) => {
        e.preventDefault();
        const url = elements.ytUrlInput.value.trim();
        if (url) {
            analyzeVideo(url);
        }
    };

    // 4. 예시 칩 클릭
    document.querySelectorAll('.example-chip').forEach(chip => {
        chip.onclick = () => {
            const url = chip.getAttribute('data-url');
            elements.ytUrlInput.value = url;
            elements.clearSearchBtn.style.display = 'block';
            analyzeVideo(url);
        };
    });

    // 5. 플레이어 커스텀 컨트롤
    elements.playPauseBtn.onclick = togglePlayPause;
    elements.muteBtn.onclick = toggleMute;
    elements.volSlider.oninput = (e) => onVolumeChange(e.target.value);
    elements.ccBtn.onclick = toggleCaptions;

    // 6. 스크립트 복사
    elements.copyTranscriptBtn.onclick = () => {
        const text = elements.fullTranscriptArea.value;
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            const originalText = elements.copyTranscriptBtn.textContent;
            elements.copyTranscriptBtn.textContent = '✅ 복사 완료!';
            setTimeout(() => {
                elements.copyTranscriptBtn.textContent = originalText;
            }, 1500);
        });
    };

    // 7. 탭 전환
    elements.tabBtns.forEach(btn => {
        btn.onclick = () => {
            const targetTab = btn.getAttribute('data-tab');
            elements.tabBtns.forEach(b => b.classList.remove('active'));
            elements.tabPanels.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const panel = document.getElementById(`tab-${targetTab}`);
            if (panel) panel.classList.add('active');
        };
    });

    // 8. 타임스탬프 검색 필터
    elements.tsSearchInput.oninput = (e) => {
        renderTimestamps(e.target.value);
    };

    // 9. 자막 다운로드
    elements.downloadSrtBtn.onclick = () => {
        if (!state.sttResult || !state.videoInfo) return;
        const srt = generateSrt(state.sttResult.sentences);
        const filename = `${state.videoInfo.title || 'subtitles'}.srt`;
        triggerDownload(srt, filename);
    };

    elements.downloadTxtBtn.onclick = () => {
        if (!state.sttResult || !state.videoInfo) return;
        const txt = state.sttResult.full_text || '';
        const filename = `${state.videoInfo.title || 'transcript'}.txt`;
        triggerDownload(txt, filename);
    };

    // 10. AI 채팅 전송
    elements.chatForm.onsubmit = (e) => {
        e.preventDefault();
        submitChatMessage(elements.chatInput.value);
    };
}

// DOM 준비 완료 시 이벤트 등록
document.addEventListener('DOMContentLoaded', setupEventListeners);
