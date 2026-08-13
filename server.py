#!/usr/bin/env python3
"""
Zernio Desk — 주제 하나로 Facebook / LinkedIn 게시물을 만들고 발행하는 로컬 콘솔.

브라우저에서 Zernio API를 직접 부를 수 없습니다(CORS, 그리고 키가 노출됨).
그래서 이 서버가 중간에 서서 키를 들고 대신 호출합니다. 키는 .env 파일에만 있고
브라우저로 내려가지 않습니다.

실행:
    .env.example을 .env로 복사한 뒤 키 입력
    python server.py                         # http://127.0.0.1:8787

의존성 없음. 파이썬 3.9+.
"""

import base64
import hmac
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

HERE = Path(__file__).resolve().parent


def load_dotenv(path):
    """의존성 없이 간단한 KEY=VALUE 형식의 .env를 읽는다."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_dotenv(HERE / ".env")

PORT = int(os.environ.get("PORT", "8787"))

ZERNIO_BASE = os.environ.get("ZERNIO_BASE", "https://zernio.com/api/v1")
ZERNIO_KEY = os.environ.get("ZERNIO_API_KEY", "")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
SITE_USERNAME = os.environ.get("SITE_USERNAME", "")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")

TIMEOUT = 90
app = Flask(__name__)


# --------------------------------------------------------------- HTTP helpers
def _req(url, method="GET", headers=None, data=None, timeout=TIMEOUT):
    r = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"연결 실패: {e.reason}") from e


def zernio(path, method="GET", payload=None):
    if not ZERNIO_KEY:
        raise RuntimeError("ZERNIO_API_KEY 환경변수가 비어 있습니다.")
    headers = {"Authorization": f"Bearer {ZERNIO_KEY}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    status, _, body = _req(f"{ZERNIO_BASE}{path}", method, headers, data)
    try:
        parsed = json.loads(body.decode() or "{}")
    except json.JSONDecodeError:
        parsed = {"raw": body.decode(errors="replace")[:2000]}
    if status >= 400:
        msg = parsed.get("message") or parsed.get("error") or parsed.get("raw") or "알 수 없는 오류"
        raise RuntimeError(f"Zernio {status}: {msg}")
    return parsed


# --------------------------------------------------------------- media upload
def upload_image(filename, b64):
    """presign → PUT → publicUrl"""
    ctype = mimetypes.guess_type(filename)[0] or "image/png"
    pre = zernio("/media/presign", "POST", {"filename": filename, "contentType": ctype})
    up_url = pre.get("uploadUrl") or pre.get("url")
    public = pre.get("publicUrl") or pre.get("fileUrl") or pre.get("mediaUrl")
    if not up_url or not public:
        raise RuntimeError(f"presign 응답에 uploadUrl/publicUrl이 없습니다: {json.dumps(pre)[:400]}")

    raw = base64.b64decode(b64.split(",", 1)[-1])
    status, _, body = _req(up_url, "PUT", {"Content-Type": ctype}, raw)
    if status >= 400:
        raise RuntimeError(f"이미지 업로드 실패 {status}: {body.decode(errors='replace')[:300]}")
    return public


# --------------------------------------------------------------- copy drafting
DRAFT_SYSTEM = """당신은 AX(AI 전환) 전문 컨설턴트의 소셜 미디어 초안을 쓴다.

절대 규칙:
- 사용자가 제공한 '근거 자료'에 없는 수치, 날짜, 기업명, 인용을 만들어내지 않는다.
- 근거가 부족하면 그 항목을 비우거나 일반적 서술로 대체한다. 추측을 사실처럼 쓰지 않는다.
- 과장된 수식어("혁명적", "게임체인저", "충격")를 쓰지 않는다.
- 결론은 도입 기업 관점의 실행 함의로 맺는다.

출력은 아래 스키마의 JSON 하나만. 마크다운 코드펜스나 설명 문장을 붙이지 않는다.

{
  "title": ["한 줄 12자 내외", "두 번째 줄"],
  "subtitle": "부제 한 문장, 40자 내외",
  "kicker": "AI BRIEF / 2026.08.11 형태의 짧은 영문 슬러그",
  "chips": ["키워드1", "키워드2", "키워드3"],
  "figures": [
    {"tag": "분류", "value": "핵심 수치", "desc": "한 줄 설명"},
    {"tag": "", "value": "", "desc": ""},
    {"tag": "", "value": "", "desc": ""}
  ],
  "insights": [
    {"head": "소제목", "body": "두 줄 이내 설명"},
    {"head": "", "body": ""},
    {"head": "", "body": ""}
  ],
  "punchline": "마지막 한 문장. 질문이 어떻게 바뀌는지.",
  "linkedin": "링크드인 본문. 구조화된 인사이트형. 1500~2500자. 이모지 번호 사용 가능. 해시태그 5개 이내로 마무리.",
  "facebook": "페이스북 본문. 짧은 요약형. 400~800자. 불릿 3개 + 한 줄 결론."
}"""

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "array", "items": {"type": "string"}},
        "subtitle": {"type": "string"},
        "kicker": {"type": "string"},
        "chips": {"type": "array", "items": {"type": "string"}},
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                    "value": {"type": "string"},
                    "desc": {"type": "string"},
                },
                "required": ["tag", "value", "desc"],
            },
        },
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "head": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["head", "body"],
            },
        },
        "punchline": {"type": "string"},
        "linkedin": {"type": "string"},
        "facebook": {"type": "string"},
    },
    "required": [
        "title", "subtitle", "kicker", "chips", "figures", "insights",
        "punchline", "linkedin", "facebook",
    ],
}


def draft_copy(topic, sources, tone, date):
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY가 없습니다. 카피를 직접 작성하거나 키를 설정하세요.")
    user = f"""주제: {topic}
날짜: {date}
톤: {tone}

근거 자료 (이 안의 사실만 사용):
{sources.strip() or "(제공된 근거 없음 — 수치와 고유명사는 쓰지 말고 일반적 관점으로만 작성)"}"""

    payload = {
        "systemInstruction": {"parts": [{"text": DRAFT_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": DRAFT_SCHEMA,
            "temperature": 0.4,
        },
    }
    status, _, body = _req(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        "POST",
        {
            "x-goog-api-key": GEMINI_KEY,
            "Content-Type": "application/json",
        },
        json.dumps(payload).encode(),
    )
    try:
        data = json.loads(body.decode())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini 응답이 JSON이 아닙니다: {body.decode(errors='replace')[:300]}") from e
    if status >= 400:
        raise RuntimeError(f"Gemini {status}: {data.get('error', {}).get('message', '오류')}")

    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason") or "응답 후보가 없습니다"
        raise RuntimeError(f"Gemini 초안 생성 실패: {reason}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        finish_reason = candidates[0].get("finishReason", "알 수 없음")
        raise RuntimeError(
            f"Gemini가 불완전한 JSON을 반환했습니다(종료 사유: {finish_reason}). "
            "다시 시도해 주세요."
        ) from e


# --------------------------------------------------------------- publish
def publish(body):
    images = body.get("images", [])
    targets = body.get("targets", [])
    mode = body.get("mode", "draft")
    slug = body.get("slug", "post")

    if not targets:
        raise RuntimeError("발행할 계정이 선택되지 않았습니다.")

    media_urls = []
    for i, img in enumerate(images, 1):
        media_urls.append(upload_image(f"{slug}-{i}.png", img))

    results = []
    for t in targets:
        entry = {"platform": t["platform"], "accountId": t["accountId"]}
        if t.get("pageId"):
            entry["platformSpecificData"] = {"pageId": t["pageId"]}

        post = {
            "content": t["content"],
            "mediaItems": [{"url": u, "type": "image"} for u in media_urls],
            "platforms": [entry],
        }
        if mode == "now":
            post["publishNow"] = True
        elif mode == "schedule":
            post["scheduledFor"] = body["scheduledFor"]
            post["timezone"] = body.get("timezone", "Asia/Seoul")

        res = zernio("/posts", "POST", post)
        p = res.get("post", res)
        results.append({
            "platform": t["platform"],
            "id": p.get("_id") or p.get("id"),
            "status": p.get("status", mode),
            "url": p.get("permalink") or p.get("url"),
        })

    return {"results": results, "mediaUrls": media_urls}


# --------------------------------------------------------------- web app
def _auth_required():
    return bool(SITE_USERNAME or SITE_PASSWORD or os.environ.get("VERCEL"))


@app.before_request
def require_site_auth():
    if not _auth_required():
        return None
    if not SITE_USERNAME or not SITE_PASSWORD:
        return jsonify({"error": "SITE_USERNAME과 SITE_PASSWORD를 모두 설정하세요."}), 503
    auth = request.authorization
    if (
        auth
        and hmac.compare_digest(auth.username or "", SITE_USERNAME)
        and hmac.compare_digest(auth.password or "", SITE_PASSWORD)
    ):
        return None
    return Response(
        "로그인이 필요합니다.", 401,
        {"WWW-Authenticate": 'Basic realm="PostingByZernio"'},
    )


@app.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
@app.get("/index.html")
def index():
    path = HERE / "index.html"
    if not path.exists():
        return jsonify({"error": "index.html이 server.py와 같은 폴더에 없습니다."}), 500
    return send_file(path, mimetype="text/html")


@app.get("/api/health")
def health():
    return jsonify({
        "zernio": bool(ZERNIO_KEY),
        "gemini": bool(GEMINI_KEY),
        "model": GEMINI_MODEL,
        "base": ZERNIO_BASE,
    })


@app.get("/api/accounts")
def accounts():
    try:
        data = zernio("/accounts")
        items = data.get("accounts", data if isinstance(data, list) else [])
        slim = [{
            "id": item.get("_id") or item.get("id"),
            "platform": (item.get("platform") or "").lower(),
            "name": item.get("name") or item.get("username") or item.get("displayName") or "",
            "pageId": item.get("pageId") or (item.get("platformSpecificData") or {}).get("pageId"),
        } for item in items]
        return jsonify({"accounts": slim, "raw": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/copy")
def copy_api():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "요청 본문이 JSON이 아닙니다."}), 400
    try:
        return jsonify(draft_copy(
            body.get("topic", ""), body.get("sources", ""),
            body.get("tone", "분석적"), body.get("date", ""),
        ))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/publish")
def publish_api():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "요청 본문이 JSON이 아닙니다."}), 400
    try:
        return jsonify(publish(body))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


def main():
    if not ZERNIO_KEY:
        print("⚠  ZERNIO_API_KEY가 없습니다. 계정 조회와 발행은 실패하지만 화면과 이미지 생성은 동작합니다.\n")
    print(f"Zernio Desk  →  http://127.0.0.1:{PORT}")
    print("   Ctrl+C 로 종료. 127.0.0.1 에만 바인딩되어 외부에서 접근할 수 없습니다.\n")
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
