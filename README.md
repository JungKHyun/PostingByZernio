# Zernio Desk

주제 하나를 넣으면 → 근거 기반 초안 + 정사각 이미지 3장 → Facebook / LinkedIn 발행까지 한 화면에서.

```
zernio-desk/
  server.py     로컬 서버. API 키를 들고 Zernio·Gemini를 대신 호출한다. 의존성 없음.
  index.html    화면. 이미지는 브라우저 Canvas에서 1080×1080으로 그린다.
```

## 실행

`.env.example`을 `.env`로 복사합니다.

```powershell
Copy-Item .env.example .env
```

생성된 `.env`를 열어 실제 키를 입력합니다.

```dotenv
ZERNIO_API_KEY=실제_Zernio_키
GEMINI_API_KEY=실제_Gemini_키
GEMINI_MODEL=gemini-2.5-flash
INITIAL_ADMIN_PASSWORD=초기_관리자_비밀번호
SESSION_SECRET=충분히_긴_임의_문자열
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
PORT=8787
```

그다음 서버를 실행합니다.

```powershell
python .\server.py
```

macOS/Linux에서는 첫 단계만 다음과 같이 실행하면 됩니다.

```bash
cp .env.example .env
python3 server.py
```

ChatGPT Desktop 플러그인에 저장한 키는 이 로컬 Python 프로세스로 전달되지 않으므로 `.env`에도 입력해야 합니다. `.env`는 Git 제외 대상으로 설정되어 있으며, 키를 `server.py`나 `index.html`에 직접 넣으면 안 됩니다. 운영체제 환경변수와 `.env`에 같은 항목이 있으면 운영체제 환경변수를 우선합니다.

브라우저에서 `http://127.0.0.1:8787`. 파이썬 3.9 이상이면 됩니다.

관리자 아이디는 `admin` 한 명으로 고정됩니다. `INITIAL_ADMIN_PASSWORD`로 처음 로그인하면 즉시 8자 이상의 새 비밀번호를 설정해야 합니다. 로컬에서 변경한 비밀번호는 Git에서 제외되는 `data/admin-password.json`에 해시로 저장됩니다.

**휴대폰에서 쓰려면** — 같은 와이파이에서 `server.py` 마지막의 `"127.0.0.1"`을 `"0.0.0.0"`으로 바꾸고 `http://<맥/PC의 로컬 IP>:8787` 로 접속하세요. 다만 그 순간 같은 네트워크의 다른 기기도 접근할 수 있으니, 신뢰하는 네트워크에서만 하세요.

## 왜 서버가 필요한가

브라우저에서 Zernio API를 직접 부를 수 없습니다. 두 가지 이유입니다.

1. **CORS** — Zernio API는 임의의 웹페이지 출처를 허용하지 않습니다.
2. **키 노출** — 프런트엔드 JS에 키를 넣으면 페이지를 여는 누구나 볼 수 있습니다.

그래서 키는 서버가 읽는 `.env`에만 존재하고, 브라우저로는 절대 내려가지 않습니다. 서버는 `127.0.0.1`에만 바인딩됩니다.

## GitHub와 Vercel에 배포

이 프로젝트는 GitHub Pages가 아니라 GitHub 저장소를 Vercel에 연결해 배포합니다. Vercel은 `server.py`의 Flask `app`을 Python Function으로 실행합니다.

1. GitHub에 이 저장소를 푸시합니다.
2. Vercel에서 **Add New → Project**를 누르고 GitHub의 `PostingByZernio` 저장소를 가져옵니다.
3. Framework Preset은 자동 감지를 사용하고 별도의 Build Command나 Output Directory는 입력하지 않습니다.
4. Vercel Marketplace에서 **Upstash Redis**를 프로젝트에 연결합니다. Vercel 서버리스의 로컬 파일은 영구 저장되지 않기 때문에 변경된 관리자 비밀번호를 Redis에 저장합니다.
5. Vercel 프로젝트의 **Settings → Environment Variables**에 다음 값을 등록합니다. Upstash 연결 시 Redis 관련 두 값은 자동으로 추가될 수 있습니다.

```text
ZERNIO_API_KEY=실제_Zernio_키
GEMINI_API_KEY=실제_Gemini_키
GEMINI_MODEL=gemini-2.5-flash
INITIAL_ADMIN_PASSWORD=초기_관리자_비밀번호
SESSION_SECRET=8자_이상의_임의_문자열
UPSTASH_REDIS_REST_URL=Upstash_REST_URL
UPSTASH_REDIS_REST_TOKEN=Upstash_REST_TOKEN
```

6. Production, Preview, Development 환경에 필요한 값을 적용한 뒤 배포합니다.

배포 후 관리자 아이디 `admin`과 초기 비밀번호로 로그인하면 비밀번호 변경 화면으로만 이동합니다. 변경을 완료해야 게시 화면에 들어갈 수 있습니다. 새 비밀번호는 PBKDF2-SHA256 해시로만 저장되며 세션은 12시간 유지됩니다. `SESSION_SECRET`은 최소 8자이지만 세션 보안을 위해 32자 이상의 무작위 값을 권장합니다.

Vercel에서는 초기 비밀번호, 세션 서명키와 Upstash 연결값 중 하나라도 빠지면 요청을 차단합니다. `.env`는 `.gitignore`에 포함되어 GitHub와 Vercel 배포 파일에 올라가지 않습니다.

## 흐름

```
주제 + 근거 자료
      ↓  POST /api/copy      → Gemini (서버가 호출)
초안 JSON  { title, figures, insights, linkedin, facebook }
      ↓  Canvas 렌더링        → 브라우저에서 1080×1080 PNG 3장
본문 수정 · 이미지 문구 수정
      ↓  POST /api/publish   → 서버가 순서대로:
         1. /media/presign   presigned URL 발급
         2. PUT uploadUrl    이미지 업로드
         3. /posts           publicUrl 을 mediaItems 에 넣어 게시
결과 (초안 / 예약 / 즉시)
```

## 근거 자료란?

`근거 자료`는 Gemini가 게시글에서 사실로 사용해도 되는 정보를 직접 제공하는 입력란입니다. 기사 요약, 발표 날짜, 핵심 수치, 회사명과 출처 URL 등을 넣을 수 있습니다.

예를 들어 주제가 `2026년 8월 13일자 인공지능 뉴스 TOP 3`이라면 다음처럼 입력합니다.

```text
1. 구글이 Gemini 신규 기능을 발표했다.
핵심 내용: 발표 내용 요약
발표일: 2026-08-13
출처: https://example.com/article-1

2. OpenAI가 새로운 API 기능을 공개했다.
핵심 내용: 공개된 기능과 적용 범위
출처: https://example.com/article-2

3. 국내 기업의 AI 도입 조사 결과가 발표됐다.
핵심 수치: 조사에서 확인된 수치
출처: https://example.com/article-3
```

현재 앱은 입력된 URL의 본문을 자동으로 방문하거나 최신 뉴스를 검색하지 않습니다. URL만 붙이는 대신 게시글에 반영할 핵심 내용도 함께 입력해야 합니다.

- 근거 자료에 입력한 내용은 LinkedIn·Facebook 본문과 이미지 문구를 만드는 데 사용됩니다.
- 입력하지 않은 수치, 날짜, 회사명과 인용문은 생성하지 않도록 프롬프트가 설정되어 있습니다.
- 근거 자료를 비워두면 구체적인 수치와 고유명사가 없는 일반적인 관점의 글이 생성됩니다.
- 생성 결과는 발행 전에 반드시 사실관계와 출처를 확인하세요.

## 초안 생성 규칙

`server.py`의 `DRAFT_SYSTEM`에 이렇게 걸어 뒀습니다.

- 근거 자료에 없는 수치·날짜·기업명·인용을 만들어내지 않는다
- 근거가 부족하면 비우거나 일반적 서술로 대체한다
- 과장 수식어를 쓰지 않는다
- 별표 강조 같은 마크다운 강조 문법과 이모지·이모티콘을 제거한다
- 도입 기업 관점의 실행 함의로 맺는다

근거 자료를 비우면 수치와 고유명사 없이 일반론만 나옵니다. 의도된 동작입니다.

## 알아둘 것

- **Facebook은 페이지에만 게시됩니다.** 개인 타임라인은 API로 불가능합니다. 페이지 관리자 또는 편집자 권한이 필요합니다.
- **글자수 한도** — LinkedIn 3,000자, Facebook 63,206자. 화면 하단 카운터가 초과하면 빨갛게 변하고 발행이 막힙니다.
- **첫 실행은 `초안 저장`으로.** Zernio 대시보드에서 렌더링을 확인한 뒤 예약이나 즉시 발행으로 넘어가세요. `즉시`를 고르면 슬러그 바가 빨갛게 바뀌고 확인창이 한 번 더 뜹니다.
- **엔드포인트 응답 형태**는 Zernio 문서 기준으로 맞췄지만 스펙이 바뀔 수 있습니다. `/api/accounts`는 원본 JSON도 함께 돌려주니, 계정이 안 보이면 그 값을 확인하세요.
- 이미지 문구 편집란은 `분류 | 값 | 설명` 처럼 파이프로 나눕니다. 한 줄이 한 항목입니다.
