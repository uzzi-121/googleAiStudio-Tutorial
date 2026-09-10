# Gemini 3.1 Flash TTS 파이썬 코드 라인별(Line-by-Line) 해설

이 문서는 `gemini-31-tts-example.py` 파일의 전체 소스코드를 한 줄씩(Line-by-Line) 분석하여 각 줄이 어떤 역할을 하는지 초보자도 쉽게 이해할 수 있도록 정리한 가이드입니다.

---

## 1. 패키지 설치 및 모듈 임포트 (Lines 1 ~ 10)

```python
1: # To run this code you need to install the following dependencies:
2: # pip install google-genai
3: 
4: #변경사항이 발생했습니다.
5: import mimetypes
6: import os
7: import re
8: import struct
9: from google import genai
10: from google.genai import types
```

- **Line 1~2**: 코드 실행에 필요한 Google GenAI 공식 SDK 패키지(`pip install google-genai`) 설치 안내 주석입니다.
- **Line 5 (`import mimetypes`)**: 오디오 파일의 MIME 타입(예: `audio/wav`, `audio/mp3`)을 확인하여 적절한 파일 확장자(`.wav`)를 알아내기 위한 표준 라이브러리입니다.
- **Line 6 (`import os`)**: 시스템 환경 변수(API 키 등)를 읽어오기 위한 파이썬 기본 모듈입니다.
- **Line 7 (`import re`)**: 정규 표현식을 다루는 모듈입니다. (MIME 타입 파싱에 사용)
- **Line 8 (`import struct`)**: 파이썬의 숫자나 문자열 데이터를 C 언어 스타일의 바이너리 바이트(리틀 엔디안 정수 등)로 패킹해 주는 모듈입니다. 순수 PCM 원시 오디오 데이터 앞에 **44바이트 표준 WAV 헤더**를 직접 조립할 때 필수적으로 사용됩니다.
- **Line 9 (`from google import genai`)**: Google의 차세대 통합 Gemini SDK의 메인 클라이언트(`genai.Client`)를 불러옵니다.
- **Line 10 (`from google.genai import types`)**: API 호출 시 전달할 파라미터 구조체(Content, Part, GenerateContentConfig 등)의 데이터 규격 클래스를 불러옵니다.

---

## 2. 바이너리 파일 저장 유틸리티 함수 (Lines 13 ~ 17)

```python
13: def save_binary_file(file_name, data):
14:     f = open(file_name, "wb")
15:     f.write(data)
16:     f.close()
17:     print(f"File saved to to: {file_name}")
```

- **Line 13**: 파일명(`file_name`)과 바이트 데이터(`data`)를 전달받아 디스크에 저장하는 함수를 정의합니다.
- **Line 14**: `"wb"` (Write Binary, 바이너리 쓰기 모드)로 파일을 엽니다. 음성 데이터는 텍스트가 아닌 순수 2진수(바이트)이므로 바이너리 모드로 열어야 손상되지 않습니다.
- **Line 15**: 바이트 데이터를 파일에 씁니다.
- **Line 16**: 파일 핸들을 닫아 시스템 메모리 및 리소스를 반환합니다.
- **Line 17**: 저장이 완료된 파일 경로를 콘솔에 출력합니다.

---

## 3. 음성 생성 메인 함수 - 클라이언트 및 프롬프트 설정 (Lines 20 ~ 45)

```python
20: def generate():
21:     client = genai.Client(
22:         api_key=os.environ.get("GEMINI_API_KEY"),
23:     )
```

- **Line 20**: 음성 합성 작업을 수행하는 `generate()` 메인 함수를 선언합니다.
- **Line 21~23**: 시스템 환경 변수에 저장된 `GEMINI_API_KEY`를 읽어와 Gemini API 클라이언트를 초기화합니다.

```python
24: 
25:     model = "gemini-3.1-flash-tts-preview"
26:     contents = [
27:         types.Content(
28:             role="user",
29:             parts=[
30:                 types.Part.from_text(text="""Read the following transcript based on the audio profile.
31: 
32: # Audio Profile
33: warm
34: 
35: ## Scene:
36: A tense, fast-paced breaking news studio. The atmosphere is dramatic, sensational, and urgent.
37: 
38: ## Sample Context:
39: The anchor is delivering an unbelievable, shocking piece of tech news with exaggerated seriousness and slight disbelief.
40: 
41: ## Transcript:
42: [urgent] 속보입니다! 구글이 방금 차세대 AI 모델, '제미나이 4.0 프로'를 전격 공개했습니다. [pause] [gasp] 그런데, 가격표를 본 전 세계 개발자들이 경악을 금치 못하고 있습니다! [shocked] 월 구독료가 무려 천만 원에 달한다는 충격적인 소식인데요! [dramatic] "AI가 밥 먹여주냐", "이러다 집 팔아서 프롬프트 날리겠다"는 개발자들의 비명이 쏟아지고 있습니다. [skeptical] 과연 진짜 이 가격이 맞을까요? [chuckle] 믿기 힘든 소식, 잠시 후 팩트체크로 이어집니다!"""),
43:             ],
44:         ),
45:     ]
```

- **Line 25**: 음성 합성에 특화된 전용 모델인 `gemini-3.1-flash-tts-preview`를 지정합니다.
- **Line 26~29**: 사용자의 요청 콘텐츠(`types.Content`, `role="user"`)를 생성합니다.
- **Line 30~43**: Gemini TTS 전용 프롬프트 구조를 전달합니다:
  - **`# Audio Profile`**: 전반적인 목소리 분위기(예: `warm`)를 지정합니다.
  - **`## Scene`**: 발화가 일어나는 무대 배경과 분위기(긴박한 속보 스튜디오)를 묘사하여 긴장감 있는 톤을 연출합니다.
  - **`## Sample Context`**: 화자가 어떤 감정과 태도(황당함, 과장된 진지함)로 말해야 하는지 맥락을 설명합니다.
  - **`## Transcript`**: 실제로 발화할 대사입니다. `[urgent]`, `[pause]`, `[gasp]`, `[shocked]`, `[dramatic]`, `[skeptical]`, `[chuckle]` 같은 감정/호흡 태그를 포함하여 사람처럼 생생하게 말하도록 유도합니다.

---

## 4. TTS 생성 파라미터 및 보이스 설정 (Lines 46 ~ 58)

```python
46:     generate_content_config = types.GenerateContentConfig(
47:         temperature=1,
48:         response_modalities=[
49:             "audio",
50:         ],
51:         speech_config=types.SpeechConfig(
52:             voice_config=types.VoiceConfig(
53:                 prebuilt_voice_config=types.PrebuiltVoiceConfig(
54:                     voice_name="Charon"
55:                 )
56:             )
57:         ),
58:     )
```

- **Line 46~47**: 모델 설정 객체를 생성하고, 감정 표현의 생동감을 위해 `temperature=1`을 지정합니다.
- **Line 48~50**: 응답 형태(`response_modalities`)를 `["audio"]`로 지정하여 텍스트가 아닌 실제 오디오 바이너리 스트림을 요청합니다.
- **Line 51~57**: Gemini의 사전 정의된 프리빌트 보이스(`PrebuiltVoiceConfig`) 중 `"Charon"` 목소리를 선택합니다. (Puck, Charon, Aoede, Fenrir, Zephyr 등 교체 가능)

---

## 5. 스트리밍 오디오 수집 및 단일 WAV 저장 (Lines 60 ~ 84)

```python
60:     audio_chunks = []
61:     mime_type = "audio/L16;rate=24000"
62: 
63:     print("오디오 생성 중...")
64:     for chunk in client.models.generate_content_stream(
65:         model=model,
66:         contents=contents,
67:         config=generate_content_config,
68:     ):
69:         if chunk.parts is None:
70:             continue
71:         if chunk.parts[0].inline_data and chunk.parts[0].inline_data.data:
72:             inline_data = chunk.parts[0].inline_data
73:             mime_type = inline_data.mime_type
74:             audio_chunks.append(inline_data.data)
75:         else:
76:             if text := chunk.text:
77:                 print(text)
```

- **Line 60**: 스트리밍으로 전달되는 오디오 바이트 조각(청크)들을 순서대로 담아둘 리스트 버퍼 `audio_chunks`를 초기화합니다.
- **Line 61**: 기본 MIME 타입(16비트 리니어 PCM, 24kHz 샘플레이트)을 지정합니다.
- **Line 64~68**: `client.models.generate_content_stream`을 호출해 실시간으로 스트리밍 응답 청크를 수신합니다.
- **Line 69~70**: 청크 안에 부품 데이터(`parts`)가 비어 있으면 건너뜁니다.
- **Line 71~74**: 음성 데이터(`inline_data`)가 포함되어 있으면, MIME 타입을 업데이트하고 바이트 데이터를 `audio_chunks`에 차곡차곡 추가합니다. *(조각마다 파일을 생성하지 않고 메모리에 모아둡니다)*
- **Line 75~77**: 음성이 아닌 텍스트 안내가 온 경우 화면에 출력합니다.

```python
79:     if audio_chunks:
80:         full_audio_data = b"".join(audio_chunks)
81:         wav_data = convert_to_wav(full_audio_data, mime_type)
82:         output_file_name = "gemini_4_news.wav"
83:         save_binary_file(output_file_name, wav_data)
84:         print(f"완성된 오디오가 '{output_file_name}'로 저장되었습니다.")
```

- **Line 79**: 수신된 오디오 청크가 있는지 확인합니다.
- **Line 80**: 분할 수신된 모든 바이너리 오디오 조각들을 `b"".join(...)`으로 하나의 연속된 바이트로 합칩니다.
- **Line 81**: 아래의 `convert_to_wav()` 함수를 호출하여 원시 PCM 데이터 앞에 **44바이트 표준 WAV 헤더**를 붙입니다.
- **Line 82~84**: 완성된 음성을 단 1개의 파일인 `gemini_4_news.wav`로 저장하고 안내 메시지를 출력합니다.

---

## 6. WAV 헤더 패킹 함수 (Lines 86 ~ 124)

```python
86: def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
...
105:     header = struct.pack(
106:         "<4sI4s4sIHHIIHH4sI",
107:         b"RIFF",          # ChunkID
108:         chunk_size,       # ChunkSize (total file size - 8 bytes)
109:         b"WAVE",          # Format
110:         b"fmt ",          # Subchunk1ID
111:         16,               # Subchunk1Size (16 for PCM)
112:         1,                # AudioFormat (1 for PCM)
113:         num_channels,     # NumChannels (1 = 모노)
114:         sample_rate,      # SampleRate (예: 24000Hz)
115:         byte_rate,        # ByteRate (초당 처리 바이트 수)
116:         block_align,      # BlockAlign (샘플당 바이트 수)
117:         bits_per_sample,  # BitsPerSample (16 bits)
118:         b"data",          # Subchunk2ID
119:         data_size         # Subchunk2Size (순수 오디오 데이터 크기)
120:     )
121:     return header + audio_data
```

- **Line 86~104**: MIME 타입에서 비트 수(16비트)와 샘플레이트(24kHz)를 구하고 헤더 크기 및 블록 정렬을 계산합니다.
- **Line 105~120**: `struct.pack`을 통해 마이크로소프트/IBM 표준 RIFF WAVE 헤더 포맷을 정확히 44바이트 규격으로 패킹합니다:
  - `<`: 리틀 엔디안(Little-endian) 정렬
  - `RIFF`, `WAVE`: 파일 형식 식별 문자열
  - `fmt `: 오디오 형식 서브청크
  - `data`: 실제 PCM 오디오 데이터 서브청크
- **Line 121**: 완성된 44바이트 헤더 뒤에 원시 오디오 데이터 바이트를 붙여 완벽한 `.wav` 파일을 리턴합니다.

---

## 7. MIME 타입 분석 함수 및 실행 진입점 (Lines 126 ~ 162)

```python
126: def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
...
135:     bits_per_sample = 16
136:     rate = 24000
...
155:     return {"bits_per_sample": bits_per_sample, "rate": rate}
156: 
158: 
161: if __name__ == "__main__":
162:     generate()
```

- **Line 126~155**: `"audio/L16;rate=24000"` 같은 문자열을 파싱하여 샘플레이트(24000)와 비트 수(16)를 정수로 반환합니다.
- **Line 161~162**: 파이썬 인터프리터가 이 스크립트를 직접 실행할 때 메인 루틴인 `generate()`를 호출합니다.
