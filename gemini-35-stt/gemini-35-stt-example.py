# To run this code you need to install the following dependencies:
# pip install google-genai

import logging
import os
import warnings

# 1. 불필요한 SDK 경고(Warning) 메시지 숨김
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

from google import genai
from google.genai import types


def group_words_into_sentences(words):
    """단어 목록을 문장 종결 부호(., ?, !) 기준으로 묶어 문장별 타임스탬프를 생성합니다."""
    if not words:
        return []

    sentences = []
    current_words = []
    start_time = None

    for w in words:
        if start_time is None:
            start_time = w.start_offset
        current_words.append(w.word)

        # 마침표, 물음표, 느낌표 등으로 문장이 끝나면 하나의 문장으로 완성
        if any(w.word.rstrip().endswith(punct) for punct in [".", "?", "!"]):
            end_time = w.end_offset
            sentence_text = " ".join(current_words)
            sentences.append((start_time, end_time, sentence_text))
            current_words = []
            start_time = None

    # 문장 부호 없이 남은 단어들이 있는 경우 처리
    if current_words:
        end_time = words[-1].end_offset
        sentence_text = " ".join(current_words)
        sentences.append((start_time, end_time, sentence_text))

    return sentences


def generate():
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    audio_path = os.path.join(os.path.dirname(__file__), "gemini_4_news.wav")
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    model = "gemini-3.5-transcribe"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/wav",
                ),
                types.Part.from_text(text="이 오디오를 받아써줘."),
            ],
        ),
    ]

    # 타임스탬프 및 화자 분리 설정
    generate_content_config = types.GenerateContentConfig(
        audio_transcription_config=types.AudioTranscriptionConfig(
            word_timestamp=True,
            diarization=True,
        ),
    )

    print("음성 인식(STT) 분석 중...")
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )

    full_text = ""
    transcription_data = None

    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                full_text += part.text
            if getattr(part, "audio_transcription", None):
                transcription_data = part.audio_transcription

    # 텍스트 보완
    if not full_text.strip() and transcription_data and transcription_data.text:
        full_text = transcription_data.text

    # [A] 단순 전체 텍스트 깔끔하게 출력 (경고 없음)
    print("\n" + "=" * 55)
    print(" [A. 전체 텍스트 변환 결과]")
    print("=" * 55)
    print(full_text.strip() if full_text else "변환된 텍스트가 없습니다.")

    # [B] 화자 및 문장별 타임스탬프 상세 정보 출력
    if transcription_data and transcription_data.words:
        speaker = transcription_data.speaker_label or "화자 1"
        sentences = group_words_into_sentences(transcription_data.words)
        print("\n" + "=" * 55)
        print(f" [B. 문장별 타임스탬프 상세 정보 ({speaker})]")
        print("=" * 55)
        for start, end, text in sentences:
            print(f"  [{start:>7} ~ {end:>7}]  {text}")
    print()


if __name__ == "__main__":
    generate()


