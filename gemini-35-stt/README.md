# Gemini 3.5 Transcribe STT 파이썬 코드 라인별(Line-by-Line) 해설

이 문서는 `gemini-35-stt-example.py` 파일의 전체 소스코드를 한 줄씩(Line-by-Line) 분석하여 각 줄이 어떤 역할을 하는지 초보자도 쉽게 이해할 수 있도록 정리한 가이드입니다.

---

## 1. 패키지 임포트 및 경고 필터링 (Lines 1 ~ 15)

```python
1: # To run this code you need to install the following dependencies:
2: # pip install google-genai
3: 
4: import logging
5: import os
6: import warnings
7: 
8: # 1. 불필요한 SDK 경고(Warning) 메시지 숨김
9: warnings.filterwarnings("ignore")
10: logging.basicConfig(level=logging.ERROR)
11: logging.getLogger("google").setLevel(logging.ERROR)
12: 
13: from google import genai
14: from google.genai import types
```

- **Line 1~2**: 필요한 공식 패키지(`pip install google-genai`) 설치 안내입니다.
- **Line 4~6**: `logging`, `os`, `warnings` 표준 라이브러리를 불러옵니다.
- **Line 9 (`warnings.filterwarnings("ignore")`)**: 콘솔에 뜨는 파이썬 런타임 Warning 메시지를 화면에 출력하지 않도록 숨깁니다.
- **Line 10~11**: GenAI SDK 내부에서 발생하는 AFC(자동 함수 호출) 권고 메시지나 구조체 경고 로그를 차단하여, 오직 에러(`ERROR`) 이상의 치명적인 문제만 콘솔에 찍히도록 제한합니다.
- **Line 13~14**: Google GenAI SDK 클라이언트와 파라미터 타입 클래스들을 불러옵니다.

---

## 2. 문장별 타임스탬프 그룹화 함수 (Lines 17 ~ 45)

```python
17: def group_words_into_sentences(words):
18:     """단어 목록을 문장 종결 부호(., ?, !) 기준으로 묶어 문장별 타임스탬프를 생성합니다."""
19:     if not words:
20:         return []
21: 
22:     sentences = []
23:     current_words = []
24:     start_time = None
```

- **Line 17~20**: STT 모델이 반환한 단어별 타임스탬프 리스트(`words`)를 입력받아 문장 단위로 묶어주는 헬퍼 함수를 선언합니다. 단어가 없으면 빈 리스트를 반환합니다.
- **Line 22~24**: 완성된 문장 리스트(`sentences`), 현재 만들고 있는 문장의 단어 버퍼(`current_words`), 문장의 시작 시간(`start_time`)을 초기화합니다.

```python
26:     for w in words:
27:         if start_time is None:
28:             start_time = w.start_offset
29:         current_words.append(w.word)
30: 
31:         # 마침표, 물음표, 느낌표 등으로 문장이 끝나면 하나의 문장으로 완성
32:         if any(w.word.rstrip().endswith(punct) for punct in [".", "?", "!"]):
33:             end_time = w.end_offset
34:             sentence_text = " ".join(current_words)
35:             sentences.append((start_time, end_time, sentence_text))
36:             current_words = []
37:             start_time = None
```

- **Line 26**: 단어 목록을 하나씩 순회합니다.
- **Line 27~28**: 새 문장이 시작될 때, 첫 단어의 시작 시간(`w.start_offset`, 예: `0.300s`)을 문장 시작 시간으로 기록합니다.
- **Line 29**: 단어를 현재 문장 단어 버퍼에 추가합니다.
- **Line 32**: 단어의 끝부분이 마침표(`.`), 물음표(`?`), 느낌표(`!`) 등 문장 종결 기호로 끝나는지 확인합니다.
- **Line 33~35**: 문장이 끝났다면 마지막 단어의 끝 시간(`w.end_offset`)을 문장 종료 시간으로 정하고, 단어들을 공백으로 묶어 하나의 완성된 문장 튜플 `(시작시간, 종료시간, 문장텍스트)` 형태로 리스트에 보관합니다.
- **Line 36~37**: 다음 문장을 받기 위해 버퍼를 비우고 시작 시간을 리셋합니다.

```python
39:     # 문장 부호 없이 남은 단어들이 있는 경우 처리
40:     if current_words:
41:         end_time = words[-1].end_offset
42:         sentence_text = " ".join(current_words)
43:         sentences.append((start_time, end_time, sentence_text))
44: 
45:     return sentences
```

- **Line 40~43**: 오디오 마지막에 마침표 없이 끝난 남은 단어들이 있다면, 마지막 단어의 끝 시간을 기준으로 마지막 문장으로 묶어줍니다.
- **Line 45**: 완성된 문장별 타임스탬프 리스트를 반환합니다.

---

## 3. 음성 파일 로드 및 모델 호출 (Lines 48 ~ 84)

```python
48: def generate():
49:     client = genai.Client(
50:         api_key=os.environ.get("GEMINI_API_KEY"),
51:     )
```

- **Line 48~51**: Gemini API 클라이언트를 환경 변수 API 키를 이용해 초기화합니다.

```python
53:     audio_path = os.path.join(os.path.dirname(__file__), "gemini_4_news.wav")
54:     with open(audio_path, "rb") as f:
55:         audio_bytes = f.read()
```

- **Line 53**: 현재 스크립트 파일이 위치한 폴더에서 분석할 음성 파일인 `gemini_4_news.wav`의 절대 경로를 만듭니다. (어느 위치에서 실행해도 경로 에러가 발생하지 않음)
- **Line 54~55**: 오디오 파일을 바이너리 읽기 모드(`"rb"`)로 열어 메모리에 바이트 데이터로 로드합니다.

```python
57:     model = "gemini-3.5-transcribe"
58:     contents = [
59:         types.Content(
60:             role="user",
61:             parts=[
62:                 types.Part.from_bytes(
63:                     data=audio_bytes,
64:                     mime_type="audio/wav",
65:                 ),
66:                 types.Part.from_text(text="이 오디오를 받아써줘."),
67:             ],
68:         ),
69:     ]
```

- **Line 57**: 구글의 음성 전사(STT) 특화 모델인 `gemini-3.5-transcribe`를 지정합니다.
- **Line 62~65**: 읽어온 오디오 바이트 데이터를 `types.Part.from_bytes`를 통해 `audio/wav` 포맷으로 모델에 전달합니다.
- **Line 66**: 음성을 텍스트로 받아쓰라는 지시사항 프롬프트를 함께 전달합니다.

```python
71:     # 타임스탬프 및 화자 분리 설정
72:     generate_content_config = types.GenerateContentConfig(
73:         audio_transcription_config=types.AudioTranscriptionConfig(
74:             word_timestamp=True,
75:             diarization=True,
76:         ),
77:     )
78: 
79:     print("음성 인식(STT) 분석 중...")
80:     response = client.models.generate_content(
81:         model=model,
82:         contents=contents,
83:         config=generate_content_config,
84:     )
```

- **Line 72~77**: 음성 인식 고급 기능을 활성화합니다:
  - `word_timestamp=True`: 단어별 시작/끝 타임스탬프 추출 활성화
  - `diarization=True`: 화자 분리(누가 말했는지 구분) 활성화
- **Line 80~84**: 모델을 호출하여 오디오 음성 분석을 수행하고 전체 응답 객체(`response`)를 수신합니다.

---

## 4. 응답 파싱 및 결과 추출 (Lines 86 ~ 98)

```python
86:     full_text = ""
87:     transcription_data = None
88: 
89:     if response.candidates and response.candidates[0].content:
90:         for part in response.candidates[0].content.parts:
91:             if part.text:
92:                 full_text += part.text
93:             if getattr(part, "audio_transcription", None):
94:                 transcription_data = part.audio_transcription
95: 
96:     # 텍스트 보완
97:     if not full_text.strip() and transcription_data and transcription_data.text:
98:         full_text = transcription_data.text
```

- **Line 86~87**: 전체 텍스트를 저장할 `full_text`와 타임스탬프 객체를 담을 `transcription_data` 변수를 준비합니다.
- **Line 89~94**: 응답 파트(`parts`)를 순회하면서:
  - 일반 텍스트(`part.text`)가 있으면 `full_text`에 누적합니다.
  - 구조화된 전사 데이터 객체(`part.audio_transcription`)가 있으면 `transcription_data`에 저장합니다.
- **Line 97~98**: 일반 텍스트가 비어 있더라도 `transcription_data.text`에 담긴 내용이 있다면 이를 전체 텍스트로 보완합니다.

---

## 5. 결과 서식 출력 (Lines 100 ~ 121)

```python
100:     # [A] 단순 전체 텍스트 깔끔하게 출력 (경고 없음)
101:     print("\n" + "=" * 55)
102:     print(" [A. 전체 텍스트 변환 결과]")
103:     print("=" * 55)
104:     print(full_text.strip() if full_text else "변환된 텍스트가 없습니다.")
```

- **Line 101, 103**: `"=" * 55`를 사용하여 55칸짜리 반듯한 구분선을 그려 터미널 레이아웃을 정돈합니다.
- **Line 104**: 앞뒤 불필요한 공백을 제거한 깔끔한 전체 받아쓰기 결과를 출력합니다.

```python
106:     # [B] 화자 및 문장별 타임스탬프 상세 정보 출력
107:     if transcription_data and transcription_data.words:
108:         speaker = transcription_data.speaker_label or "화자 1"
109:         sentences = group_words_into_sentences(transcription_data.words)
110:         print("\n" + "=" * 55)
111:         print(f" [B. 문장별 타임스탬프 상세 정보 ({speaker})]")
112:         print("=" * 55)
113:         for start, end, text in sentences:
114:             print(f"  [{start:>7} ~ {end:>7}]  {text}")
115:     print()
```

- **Line 107~108**: 단어별 타임스탬프 데이터가 존재하면, 화자 라벨(예: `spk:0`)을 가져옵니다.
- **Line 109**: 앞서 작성한 `group_words_into_sentences()` 함수를 호출하여 단어 데이터를 문장 단위로 묶어줍니다.
- **Line 114**: `{start:>7}`과 `{end:>7}` f-string 서식 지정자를 사용하여 시간 문자열을 **7칸 기준 오른쪽 정렬**로 맞춰 물결표(`~`)가 세로로 반듯하게 일렬 정렬되도록 출력합니다.

```python
118: if __name__ == "__main__":
119:     generate()
```

- **Line 118~119**: 파이썬 인터프리터에서 직접 파일 실행 시 `generate()`를 실행합니다.
