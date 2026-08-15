"""
미디어 리터러시 허브 — 팩트수색대 + Monster Insight (통합판)
API 키는 전부 st.secrets 에서만 읽어옵니다. 이 파일에는 실제 키 값이 없습니다.

필요한 Secrets (전부 선택 사항 — 없으면 데모 데이터로 동작합니다):
  GOOGLE_FACTCHECK_API_KEY
  KOSIS_API_KEY
  POLICY_SERVICE_KEY
  KRDICT_API_KEY
  STDICT_API_KEY
  OPENDICT_API_KEY
  SUPABASE_URL
  SUPABASE_ANON_KEY

※ 초등용 버전: 생성형 AI(Solar) 기능은 모두 제거되었습니다. 대신 사전 검색을
  한국어기초사전 + 표준국어대사전 + 우리말샘 3곳에서 부분일치로 검색하고,
  네이버 국어사전 바로가기를 항상 함께 보여줘서 놓치는 단어를 줄였습니다.

입장 방식: 학교급 선택 → 지역/학년/성별 선택 → 입장 (비밀코드 없음)
(로그인은 앱 전체에서 딱 한 번만 하면 되고, 이후 사이드바에서
 '팩트수색대'와 'Monster Insight' 사이를 자유롭게 오갈 수 있습니다.)

이 파일(main.py)은 화면·게임·설문 기능만 담당합니다.
"""

import os
import random
import re
from base64 import b64encode
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="데이터 스페이스 가디언즈", page_icon="🧭", layout="wide")


# ---------------------------------------------------------------------------
# Secrets (두 앱이 공유)
# ---------------------------------------------------------------------------

def secret(key: str) -> str:
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


GOOGLE_FACTCHECK_API_KEY = secret("GOOGLE_FACTCHECK_API_KEY")
KOSIS_API_KEY = secret("KOSIS_API_KEY")
POLICY_SERVICE_KEY = secret("POLICY_SERVICE_KEY")
KRDICT_API_KEY = secret("KRDICT_API_KEY")
STDICT_API_KEY = secret("STDICT_API_KEY")
OPENDICT_API_KEY = secret("OPENDICT_API_KEY")
SUPABASE_URL = secret("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = secret("SUPABASE_ANON_KEY")


# ---------------------------------------------------------------------------
# Supabase REST 헬퍼 (두 앱이 공유 — student_sessions, game_sessions)
# ---------------------------------------------------------------------------

def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_insert(table: str, record: dict) -> bool:
    if not supabase_enabled():
        return False
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=record,
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def supabase_select(table: str, params: dict | None = None):
    if not supabase_enabled():
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params or {"select": "*"},
            timeout=10,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def supabase_update(table: str, match_params: dict, patch: dict) -> bool:
    if not supabase_enabled():
        return False
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params=match_params,
            json=patch,
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 🔓 입장 화면 (학교급 선택 → 지역/학년/성별) — 비밀코드 없이 바로 입장
# ---------------------------------------------------------------------------

LEVELS = {
    "초등학교": [f"{n}학년" for n in range(1, 7)],
    "중학교": [f"{n}학년" for n in range(1, 4)],
    "고등학교": [f"{n}학년" for n in range(1, 4)],
}

REGIONS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]


def log_student_entry(level: str, region: str, grade: str, gender: str):
    """학생 입장 기록 저장 (실패해도 입장은 막지 않음)."""
    supabase_insert(
        "student_sessions",
        {
            "group_label": level,
            "level": level,
            "region": region,
            "grade": grade,
            "gender": gender,
            "entered_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def entry_gate() -> bool:
    """학교급 → 지역/학년/성별 입력 화면. 정보를 입력하고 버튼을 누르면 바로 통과."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div>
            <div class="cyber-title">🕵️🧠 데이터 스페이스 가디언즈</div>
            <div class="cyber-sub">FACT SEARCH SQUAD · MONSTER INSIGHT</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown("## 🔓 입장하기")
    st.caption("학교급과 정보를 선택하고 입장하세요.")

    level = st.selectbox("학교급", list(LEVELS.keys()), key="gate_level")
    c1, c2, c3 = st.columns(3)
    with c1:
        region = st.selectbox("지역", REGIONS, key="gate_region")
    with c2:
        grade = st.selectbox("학년", LEVELS[level], key="gate_grade")
    with c3:
        gender = st.radio("성별", ["남", "여"], key="gate_gender", horizontal=True)

    if st.button("입장하기", type="primary", key="gate_submit"):
        st.session_state.authenticated = True
        st.session_state.group_label = level
        st.session_state.student_info = {
            "level": level, "region": region, "grade": grade, "gender": gender,
        }
        log_student_entry(level, region, grade, gender)
        st.rerun()

    return False


# ---------------------------------------------------------------------------
# 팩트수색대 전용 스타일
# ---------------------------------------------------------------------------

FACTSQUAD_CSS = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&display=swap');

    .stApp {
        background:
            radial-gradient(circle at 20% 10%, rgba(56,189,248,0.16), transparent 40%),
            radial-gradient(circle at 85% 15%, rgba(94,234,212,0.10), transparent 45%),
            repeating-linear-gradient(0deg, rgba(56,189,248,0.07) 0px, rgba(56,189,248,0.07) 1px, transparent 1px, transparent 46px),
            repeating-linear-gradient(90deg, rgba(56,189,248,0.07) 0px, rgba(56,189,248,0.07) 1px, transparent 1px, transparent 46px),
            linear-gradient(180deg, #04070f 0%, #071527 45%, #0a1b30 100%);
        background-attachment: fixed;
    }

    h1, h2, h3 { color: #eaf6ff; }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"] span,
    label, .stRadio label, .stCheckbox label,
    [data-testid="stWidgetLabel"] p {
        color: #eaf6ff;
    }
    .cyber-title {
        font-family: 'Orbitron', sans-serif;
        font-weight: 900;
        color: #ffffff;
        font-size: 34px;
        letter-spacing: 0.5px;
        margin: 0;
        text-shadow: 0 0 16px rgba(56,189,248,0.55);
    }
    .cyber-sub { color:#9fd6f5; font-size:0.85rem; margin-top:-2px; }
    .cyber-tagline {
        color:#cdeaff; font-size:0.95rem; margin:6px 0 4px;
        border-left:3px solid #38bdf8; padding-left:10px;
    }
    .char-name { text-align:center; font-weight:700; color:#5eead4; margin-top:6px; }
    .char-role { text-align:center; font-size:0.78rem; color:#bcd3e8; line-height:1.4; padding:0 6px; }

    .holo-card {
        position: relative;
        aspect-ratio: 3 / 4;
        border: 1px solid rgba(94,234,212,0.55);
        border-radius: 14px;
        box-shadow: 0 0 22px rgba(56,189,248,0.30);
        overflow: hidden;
    }
    .holo-card img {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
        border: none;
        box-shadow: none;
    }
    .holo-topline {
        position: absolute;
        top: 0; left: 0; right: 0;
        font-family: 'Orbitron', sans-serif;
        font-size: 9px;
        letter-spacing: 1px;
        color: #eafffb;
        display: flex;
        justify-content: space-between;
        padding: 8px 10px;
        background: linear-gradient(180deg, rgba(4,10,20,0.75), transparent);
        z-index: 2;
    }
    .holo-caption {
        position: absolute;
        left: 0; right: 0; bottom: 0;
        padding: 24px 10px 8px;
        background: linear-gradient(180deg, transparent, rgba(4,10,20,0.92) 55%);
        z-index: 2;
    }

    .avatar-circle {
        width: 52px;
        height: 52px;
        border-radius: 50%;
        border: 2px solid #38bdf8;
        background-color: #0b172a;
        overflow: hidden;
        display: inline-block;
    }
    .avatar-circle img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        object-position: center;
        display: block;
    }
    .holo-name {
        font-family: 'Orbitron', sans-serif;
        font-weight: 700;
        color: #ffffff;
        font-size: 15px;
        text-align: center;
        text-shadow: 0 0 8px rgba(56,189,248,0.65);
        margin: 4px 0 0;
    }
    .holo-role {
        font-size: 10.5px;
        color: #9fd6f5;
        text-align: center;
        line-height: 1.35;
        margin-top: 3px;
        padding: 0 4px;
    }
    .holo-bottomline {
        font-family: 'Orbitron', sans-serif;
        font-size: 8px;
        letter-spacing: 1px;
        color: #38bdf8;
        text-align: right;
        margin-top: 5px;
        opacity: 0.8;
    }

    div[class*="st-key-card-"] {
        background: rgba(255, 255, 255, 0.97) !important;
        border: 1px solid rgba(56,189,248,0.35) !important;
        border-radius: 14px !important;
        box-shadow: 0 4px 18px rgba(0,0,0,0.25);
    }
    div[class*="st-key-card-"] h1,
    div[class*="st-key-card-"] h2,
    div[class*="st-key-card-"] h3,
    div[class*="st-key-card-"] h4,
    div[class*="st-key-card-"] p,
    div[class*="st-key-card-"] span,
    div[class*="st-key-card-"] label {
        color: #16233b !important;
    }
    .card-title {
        font-size: 15px;
        font-weight: 700;
        color: #16233b;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin: 0;
    }

    div[class*="st-key-card-dict"] {
        background: #e6f4fd !important;
    }

    .stButton button {
        background-color: #38bdf8 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
    }
    .stButton button:hover { background-color: #2196d4 !important; color: #ffffff !important; }

    .chat-team-row { display: flex; gap: 22px; margin-bottom: 14px; flex-wrap: wrap; }
    .chat-team-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
    .chat-team-item span { font-size: 11.5px; font-weight: 700; color: #16233b; }

    .foreign-card {
        background: rgba(255, 247, 230, 0.96);
        border: 1px solid rgba(245, 158, 11, 0.55);
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.25);
        height: 100%;
    }
    .foreign-card h4 { color:#7c4a03 !important; margin:0 0 6px; font-size:16px; }
    .foreign-card p { color:#8a5a12 !important; font-size:13px; margin:0 0 12px; }
    .foreign-card a.btn {
        display:inline-block; padding:8px 14px; border:1px solid #f59e0b;
        color:#b45309 !important; border-radius:8px; text-decoration:none;
        font-size:13px; font-weight:700; background: rgba(245,158,11,0.08);
    }

    .stTextInput input, .stTextArea textarea {
        background-color: #ffffff !important;
        color: #16233b !important;
        border: 1px solid #d9e2f1 !important;
    }
    .stTextInput input::placeholder { color: #94a3b8 !important; }

    .brand-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 6px;
    }
    .brand-row img { width: 64px; height: 64px; }
    </style>
"""

st.markdown(FACTSQUAD_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 팩트수색대 전용 기능 함수
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_gdelt(q: str):
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {"query": q, "mode": "artlist", "maxrecords": 8, "format": "json", "sort": "hybridrel"}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    try:
        return r.json().get("articles", [])
    except ValueError:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_google_factcheck(q: str):
    if not GOOGLE_FACTCHECK_API_KEY:
        return None
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    params = {"query": q, "key": GOOGLE_FACTCHECK_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    try:
        return r.json().get("claims", [])
    except ValueError:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_kosis(q: str):
    if not KOSIS_API_KEY:
        return None
    url = "https://kosis.kr/openapi/statisticsSearch.do"
    params = {
        "method": "getList",
        "apiKey": KOSIS_API_KEY,
        "searchNm": q,
        "format": "json",
        "resultCount": 8,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        return []
    if isinstance(data, list):
        return data
    return data.get("SearchInfo", data.get("searchInfo", []))


@st.cache_data(ttl=300, show_spinner=False)
def fetch_briefing(keyword: str):
    if not POLICY_SERVICE_KEY:
        return None
    end = datetime.utcnow()
    start = end - timedelta(days=2)
    url = "http://apis.data.go.kr/1371000/policyNewsService/policyNewsList"
    params = {
        "serviceKey": POLICY_SERVICE_KEY,
        "startDate": start.strftime("%Y%m%d"),
        "endDate": end.strftime("%Y%m%d"),
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    xml = r.text

    def field(block: str, tag: str) -> str:
        m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, re.S)
        return m.group(1).strip() if m else ""

    items = []
    for block in xml.split("<NewsItem>")[1:]:
        if field(block, "GroupingCode") != "fact":
            continue
        title = field(block, "Title")
        contents = re.sub("<[^>]+>", " ", field(block, "DataContents"))
        if keyword and keyword.lower() not in title.lower() and keyword.lower() not in contents.lower():
            continue
        items.append({
            "title": title,
            "minister": field(block, "MinisterCode"),
            "date": field(block, "ApproveDate"),
            "url": field(block, "OriginalUrl"),
        })
    return items


def _parse_dict_xml(xml_text: str, source_name: str):
    results = []
    for block in xml_text.split("<item>")[1:]:
        block = block.split("</item>")[0]
        w_match = re.search(r"<word>(.*?)</word>", block, re.S)
        d_match = re.search(r"<definition>(.*?)</definition>", block, re.S)
        if d_match:
            w = w_match.group(1).strip() if w_match else ""
            d = re.sub("<[^>]+>", "", d_match.group(1)).strip()
            results.append({"word": w, "source": source_name, "definition": d})
    return results


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_dict(word: str):
    """한국어기초사전 + 표준국어대사전 + 우리말샘, 3곳을 모두 부분일치(contain)로
    검색해서 결과를 합칩니다. 한 곳에서만 exact 매칭하던 예전 방식보다 쉬운 단어를
    훨씬 더 잘 찾을 수 있습니다."""
    entries = []
    debug = []

    if KRDICT_API_KEY:
        try:
            r = requests.get(
                "https://krdict.korean.go.kr/api/search",
                params={"key": KRDICT_API_KEY, "q": word, "part": "word", "method": "contain"},
                timeout=10,
            )
            debug.append(f"[한국어기초사전] HTTP {r.status_code} · 응답 앞부분: {r.text[:200]}")
            entries += _parse_dict_xml(r.text, "한국어기초사전")
        except Exception as e:
            debug.append(f"[한국어기초사전] 요청 실패: {e}")
    else:
        debug.append("[한국어기초사전] KRDICT_API_KEY가 Secrets에 없습니다.")

    if STDICT_API_KEY:
        try:
            r = requests.get(
                "https://stdict.korean.go.kr/api/search.do",
                params={"key": STDICT_API_KEY, "q": word, "method": "contain"},
                timeout=10,
            )
            debug.append(f"[표준국어대사전] HTTP {r.status_code} · 응답 앞부분: {r.text[:200]}")
            entries += _parse_dict_xml(r.text, "표준국어대사전")
        except Exception as e:
            debug.append(f"[표준국어대사전] 요청 실패: {e}")
    else:
        debug.append("[표준국어대사전] STDICT_API_KEY가 Secrets에 없습니다.")

    if OPENDICT_API_KEY:
        try:
            r = requests.get(
                "https://opendict.korean.go.kr/api/search",
                params={"key": OPENDICT_API_KEY, "q": word, "part": "word", "method": "contain"},
                timeout=10,
            )
            debug.append(f"[우리말샘] HTTP {r.status_code} · 응답 앞부분: {r.text[:200]}")
            entries += _parse_dict_xml(r.text, "우리말샘")
        except Exception as e:
            debug.append(f"[우리말샘] 요청 실패: {e}")
    else:
        debug.append("[우리말샘] OPENDICT_API_KEY가 Secrets에 없습니다. (우리말샘엔 최신 생활 용어가 많이 등록되어 있어요)")

    # 같은 단어+뜻풀이가 여러 사전에 중복으로 나오면 하나만 남긴다
    seen = set()
    unique_entries = []
    for e in entries:
        sig = (e["word"], e["definition"])
        if sig not in seen:
            seen.add(sig)
            unique_entries.append(e)

    return unique_entries, debug


@st.cache_data(show_spinner=False)
def img_b64(path: str):
    """이미지를 base64로 반환. 파일이 없으면 앱이 죽지 않도록 None을 반환한다."""
    try:
        with open(path, "rb") as f:
            return b64encode(f.read()).decode()
    except Exception:
        return None


def title_icon_html(path: str, fallback_emoji: str, size: int = 28) -> str:
    if os.path.exists(path):
        try:
            b64 = img_b64(path)
            ext = os.path.splitext(path)[1].lstrip(".").replace("jpg", "jpeg")
            return (
                f'<img src="data:image/{ext};base64,{b64}" '
                f'style="width:{size}px;height:{size}px;vertical-align:middle;'
                f'border-radius:10px;object-fit:cover;">'
            )
        except Exception:
            pass
    return f'<span style="font-size:{size}px;line-height:1;">{fallback_emoji}</span>'


def sidebar_brand_html(icon_path: str, fallback_emoji: str, title_kr: str, title_en: str, icon_size: int = 56) -> str:
    icon_html = title_icon_html(icon_path, fallback_emoji, size=icon_size)
    return f"""
    <div style="display:flex; align-items:center; justify-content:center;
                gap:14px; margin:6px 0 8px; text-align:center;">
        <div style="flex-shrink:0;">{icon_html}</div>
        <div style="line-height:1.3; text-align:left;">
            <div style="font-size:22px; font-weight:800; color:#16233b;">{title_kr}</div>
            <div style="font-size:11.5px; color:#2b6cb0; letter-spacing:0.5px;">{title_en}</div>
        </div>
    </div>
    """


def holo_card(img_path: str, unit_no: str, name: str, role_line: str, meaning: str):
    b64 = img_b64(img_path)
    img_html = (
        f'<img src="data:image/png;base64,{b64}">'
        if b64 else
        '<div style="display:flex;align-items:center;justify-content:center;'
        'height:100%;font-size:64px;background:#0b172a;">🕵️</div>'
    )
    st.markdown(
        f"""
        <div class="holo-card">
            {img_html}
            <div class="holo-topline"><span>UNIT.{unit_no}</span><span>● ACTIVE</span></div>
            <div class="holo-caption">
                <div class="holo-name">{name}</div>
                <div class="holo-role">{role_line}<br>{meaning}</div>
                <div class="holo-bottomline">SCAN // OK</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def avatar_badge(img_path: str, size: int = 52) -> str:
    b64 = img_b64(img_path)
    if not b64:
        return (
            f'<div class="avatar-circle" style="width:{size}px;height:{size}px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:{int(size * 0.55)}px;">🙂</div>'
        )
    return f'<div class="avatar-circle" style="width:{size}px;height:{size}px;"><img src="data:image/png;base64,{b64}"></div>'


def foreign_card(name: str, desc: str, url: str, link_text: str) -> str:
    return f"""
    <div class="foreign-card">
        <h4>{name}</h4>
        <p>{desc}</p>
        <a class="btn" href="{url}" target="_blank">{link_text} →</a>
    </div>
    """


def naver_dict_link_card(word: str) -> str:
    query = quote(word) if word else ""
    url = f"https://ko.dict.naver.com/#/search?query={query}" if query else "https://ko.dict.naver.com"
    return foreign_card(
        "네이버 국어사전에서 찾아보기",
        "여기서 못 찾은 단어는 네이버 사전에서 더 쉽고 다양한 뜻을 확인할 수 있어요.",
        url,
        "네이버 사전 열기",
    )


def linkout_card(avatar_path: str, title: str, desc: str, url: str, link_text: str) -> str:
    avatar_html = avatar_badge(avatar_path)
    return f"""
    <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; margin-bottom:10px;">
        <p class="card-title" style="white-space:normal;">{title}</p>
        {avatar_html}
    </div>
    <p style="color:#5b6b80; font-size:13px; margin:0 0 10px;">{desc}</p>
    <a href="{url}" target="_blank" style="display:inline-block; padding:8px 14px; border:1px solid #38bdf8;
       color:#16233b; border-radius:8px; text-decoration:none; font-size:13px; font-weight:700;
       background: rgba(56,189,248,0.10);">{link_text} →</a>
    """


def render_fs_hero():
    hero_path = "images/hero-team.png"
    if os.path.exists(hero_path):
        st.markdown(
            f"""
            <img src="data:image/png;base64,{img_b64(hero_path)}"
                 style="width:100%; border-radius:18px; box-shadow:0 6px 28px rgba(0,0,0,0.45); margin-bottom:6px;">
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='cyber-tagline'>AI 시대의 뉴스·정보 교차검증 대시보드</div>",
            unsafe_allow_html=True,
        )
        st.write("")
    else:
        mascot_b64 = img_b64("images/mascot-main.png")
        mascot_html = (
            f'<img src="data:image/png;base64,{mascot_b64}">'
            if mascot_b64 else
            '<span style="font-size:56px;line-height:1;">🕵️</span>'
        )
        st.markdown(
            f"""
            <div class="brand-row">
                {mascot_html}
                <div>
                    <div class="cyber-title">팩트수색대</div>
                    <div class="cyber-sub">FACT SEARCH SQUAD</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            "<div class='cyber-tagline'>AI 시대의 뉴스·정보 교차검증 대시보드</div>",
            unsafe_allow_html=True,
        )

        st.write("")

        hc1, hc2, hc3, hc4 = st.columns(4)
        with hc1:
            holo_card("images/char-briefing-hangyeol.png", "01", "한결 대원", "리더 / 기록", "변함없이 '한결'같은 마음으로 진실을 지킨다")
        with hc2:
            holo_card("images/char-gdelt-jinsil.png", "02", "진실 대원", "정보 수집", "정보 속에 숨겨진 진짜 '진실'을 찾아낸다")
        with hc3:
            holo_card("images/char-kosis-seulgi.png", "03", "슬기 대원", "데이터 분석", "데이터를 '슬기'롭게 분석해 핵심을 짚어낸다")
        with hc4:
            holo_card("images/char-dict-hyeontam.png", "04", "현탐 대원", "현장 조사", "'현장'을 철저히 '탐구'하고 증거를 포착한다")

        st.write("")


def render_fs_search_bar():
    """검증 검색창. 입력값과 마지막으로 실행한 검색어를 세션에 유지해
    사이드바에서 국내/해외 팩트체크 화면을 오가도 결과가 유지되도록 한다."""
    ss = st.session_state
    query_input = st.text_input(
        "검증하고 싶은 키워드나 주장을 입력하세요",
        placeholder="예: 백신 부작용, 물가 상승률",
        label_visibility="collapsed",
        key="fs_query",
    )
    run_clicked = st.button("🔍 교차검증 실행", type="primary", key="fs_run_btn")
    if run_clicked:
        ss.fs_result_query = query_input.strip()

    result_query = ss.get("fs_result_query", "")
    show_results = bool(result_query)
    return result_query, show_results


def render_fs_domestic(query: str, show_results: bool):
    st.subheader("🇰🇷 국내 팩트체크")

    with st.container(border=True, key="card-gdelt"):
        if show_results:
            gdelt_url = f"https://search.naver.com/search.naver?where=news&query={quote(query)}"
            gdelt_desc = f'"{query}" 네이버 뉴스 검색 결과로 바로 이동합니다.'
            gdelt_btn = "검색 결과 보기"
        else:
            gdelt_url = "https://search.naver.com/search.naver?where=news"
            gdelt_desc = "국내 뉴스 기사를 교차검색합니다. 검색어를 입력하고 버튼을 누르면 검색 결과로 바로 연결됩니다."
            gdelt_btn = "네이버 뉴스 바로가기"
        st.markdown(
            linkout_card("images/avatar-jinsil.png", "🌐 네이버 뉴스 검색", gdelt_desc, gdelt_url, gdelt_btn),
            unsafe_allow_html=True,
        )

    with st.container(border=True, key="card-google"):
        ch1, ch2 = st.columns([5, 1])
        ch1.markdown("<p class='card-title'>✅ Google Fact Check</p>", unsafe_allow_html=True)
        ch2.markdown(avatar_badge("images/avatar-hyeontam.png"), unsafe_allow_html=True)
        if show_results:
            error_msg = None
            claims = None
            try:
                claims = fetch_google_factcheck(query)
            except Exception as e:
                error_msg = str(e)
            if error_msg:
                st.caption(f"조회 실패: {error_msg}")
            elif claims is None:
                st.caption("Streamlit Secrets에 GOOGLE_FACTCHECK_API_KEY를 추가하면 조회됩니다.")
            elif claims:
                for c in claims[:8]:
                    review = (c.get("claimReview") or [{}])[0]
                    st.markdown(f"**[{c.get('text','')}]({review.get('url','#')})**")
                    st.caption(f"{c.get('claimant','출처 미상')} · {(review.get('publisher') or {}).get('name','')}")
                    if review.get("textualRating"):
                        st.caption(f"판정: {review['textualRating']}")
            else:
                st.caption("등록된 팩트체크 결과가 없습니다.")
        else:
            st.caption("검색을 실행하면 여기에 결과가 표시됩니다.")


def render_fs_international(query: str, show_results: bool):
    st.subheader("🌍 해외 팩트체크")
    fc1, fc2 = st.columns(2)

    with fc1:
        if show_results:
            pf_url = f"https://www.google.com/search?q=site:politifact.com+{quote(query)}"
            pf_desc = f'"{query}" 관련 PolitiFact 팩트체크 검색 결과로 바로 이동합니다.'
            pf_btn = "검색 결과 보기"
        else:
            pf_url = "https://www.politifact.com"
            pf_desc = "미국 팩트체크 전문 매체. 검색어를 입력하고 실행하면 관련 검색 결과로 연결됩니다."
            pf_btn = "politifact.com 바로가기"
        st.markdown(
            foreign_card("PolitiFact", pf_desc, pf_url, pf_btn),
            unsafe_allow_html=True,
        )

    with fc2:
        if show_results:
            afp_url = f"https://www.google.com/search?q=site:factcheck.afp.com+{quote(query)}"
            afp_desc = f'"{query}" 관련 AFP Fact Check 검색 결과로 바로 이동합니다.'
            afp_btn = "검색 결과 보기"
        else:
            afp_url = "https://factcheck.afp.com"
            afp_desc = "AFP 통신사 국제 팩트체크. 검색어를 입력하고 실행하면 관련 검색 결과로 연결됩니다."
            afp_btn = "factcheck.afp.com 바로가기"
        st.markdown(
            foreign_card("AFP Fact Check", afp_desc, afp_url, afp_btn),
            unsafe_allow_html=True,
        )


def render_fs_stats():
    st.subheader("통계·정책 자료 바로가기")
    col3, col4 = st.columns(2)

    with col3:
        with st.container(border=True, key="card-kosis"):
            st.markdown(
                linkout_card(
                    "images/avatar-seulgi.png",
                    "📊 KOSIS 통합검색",
                    "통계청이 제공하는 국가 통계 원자료. 숫자·통계 관련 주장을 원본 데이터로 직접 대조해보세요.",
                    "https://kosis.kr",
                    "kosis.kr 바로가기",
                ),
                unsafe_allow_html=True,
            )

    with col4:
        with st.container(border=True, key="card-briefing"):
            st.markdown(
                linkout_card(
                    "images/avatar-hangyeol.png",
                    '📰 정책브리핑 "사실은 이렇습니다"',
                    "정부 각 부처가 언론 보도에 직접 반박·해명한 자료 모음. 정책 관련 소문을 정부 공식 입장과 대조해보세요.",
                    "https://www.korea.kr/briefing/factView.do",
                    "korea.kr 바로가기",
                ),
                unsafe_allow_html=True,
            )


def render_fs_dictionary():
    st.subheader("용어 사전")
    with st.container(border=True, key="card-dict"):
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;'>"
            f"{avatar_badge('images/avatar-mascot.png', size=60)}"
            f"<span class='card-title' style='font-size:16px;'>📖 이 낱말, 무슨 뜻?</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown(naver_dict_link_card(""), unsafe_allow_html=True)


def render_factsquad_page():
    """팩트수색대 메인 렌더링.

    사이드바의 '사건 시작' / '국내 팩트체크' / '해외 팩트체크' 버튼에 따라
    st.session_state.fs_page 값이 바뀌며, 선택한 화면만 가운데에 표시되어
    오른쪽 화면을 길게 스크롤하지 않아도 되도록 한다.
    """
    ss = st.session_state
    ss.setdefault("fs_page", "home")
    fs_page = ss.fs_page

    if fs_page == "home":
        render_fs_hero()

    query, show_results = render_fs_search_bar()

    st.divider()

    if fs_page == "domestic":
        _sp_l, sp_m, _sp_r = st.columns([1, 6, 1])
        with sp_m:
            render_fs_domestic(query, show_results)
    elif fs_page == "international":
        _sp_l, sp_m, _sp_r = st.columns([1, 8, 1])
        with sp_m:
            render_fs_international(query, show_results)
    else:
        render_fs_domestic(query, show_results)
        render_fs_international(query, show_results)
        render_fs_stats()
        render_fs_dictionary()


# ---------------------------------------------------------------------------
# Monster Insight 전용 스타일
# ---------------------------------------------------------------------------

MONSTER_CSS = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&display=swap');

    .stApp {
        background:
            radial-gradient(circle at 20% 10%, rgba(56,189,248,0.16), transparent 40%),
            radial-gradient(circle at 85% 15%, rgba(167,139,250,0.12), transparent 45%),
            repeating-linear-gradient(0deg, rgba(56,189,248,0.06) 0px, rgba(56,189,248,0.06) 1px, transparent 1px, transparent 46px),
            repeating-linear-gradient(90deg, rgba(56,189,248,0.06) 0px, rgba(56,189,248,0.06) 1px, transparent 1px, transparent 46px),
            linear-gradient(180deg, #04070f 0%, #0a0f24 45%, #120a2e 100%);
        background-attachment: fixed;
    }
    h1, h2, h3, h4, h5, h6 { color: #eaf6ff; }

    .mi-cyber-title {
        font-family: 'Orbitron', sans-serif; font-weight: 900; color: #ffffff;
        font-size: 34px; letter-spacing: 0.5px; margin: 0;
        text-shadow: 0 0 16px rgba(167,139,250,0.55);
    }
    .mi-cyber-sub { color:#c9b8f5; font-size:0.85rem; margin-top:-2px; }
    .mi-cyber-tagline {
        color:#cdeaff; font-size:0.95rem; margin:6px 0 4px;
        border-left:3px solid #a78bfa; padding-left:10px;
    }

    div[class*="st-key-panel-"] {
        background: rgba(255, 255, 255, 0.97) !important;
        border: 1px solid rgba(167,139,250,0.35) !important;
        border-radius: 16px !important;
        box-shadow: 0 4px 18px rgba(0,0,0,0.28);
    }
    div[class*="st-key-panel-"] h1, div[class*="st-key-panel-"] h2,
    div[class*="st-key-panel-"] h3, div[class*="st-key-panel-"] h4,
    div[class*="st-key-panel-"] p, div[class*="st-key-panel-"] span,
    div[class*="st-key-panel-"] label, div[class*="st-key-panel-"] li,
    div[class*="st-key-panel-"] strong, div[class*="st-key-panel-"] b,
    div[class*="st-key-panel-"] em, div[class*="st-key-panel-"] a,
    div[class*="st-key-panel-"] code {
        color: #16233b !important;
    }

    .monster-card {
        position: relative;
        border-radius: 16px;
        padding: 22px 16px;
        text-align: center;
        border: 2px solid transparent;
        background-clip: padding-box, border-box;
        background-image:
            radial-gradient(circle at 50% 0%, rgba(167,139,250,0.14), rgba(8,10,24,0.92)),
            linear-gradient(135deg, #ec4899, #22d3ee);
        background-origin: border-box;
        box-shadow:
            0 0 10px rgba(236,72,153,0.55),
            0 0 24px rgba(34,211,238,0.35),
            inset 0 0 18px rgba(236,72,153,0.06);
    }
    .monster-card::before {
        content: "";
        position: absolute;
        top: 7px; left: 7px; right: 7px; bottom: 7px;
        border: 1px solid rgba(34,211,238,0.28);
        border-radius: 10px;
        pointer-events: none;
    }
    .monster-emoji { font-size: 58px; line-height: 1; }
    .monster-name {
        font-family: 'Orbitron', sans-serif; font-weight: 700; color: #ffffff;
        font-size: 20px; margin: 8px 0 2px; text-shadow: 0 0 8px rgba(167,139,250,0.65);
    }
    .monster-cat { font-size: 12.5px; color:#9fd6f5; letter-spacing: 1px; }
    .monster-intro { font-size: 14.5px; color:#d7e6ff; margin-top:10px; line-height:1.55; }

    .dex-card {
        border-radius: 14px; padding: 16px 10px; text-align:center;
        border: 1px solid rgba(94,234,212,0.45);
        background: rgba(255,255,255,0.95); color:#16233b;
    }
    .dex-card.locked {
        background: rgba(255,255,255,0.55); color:#7c8aa0;
        border: 1px dashed rgba(148,163,184,0.7);
    }
    .dex-emoji { font-size: 40px; }
    .dex-name { font-weight: 700; margin-top: 6px; }
    .dex-stars { color:#f59e0b; letter-spacing:2px; }

    div[class*="st-key-start-"] button {
        background-color: transparent !important;
        background-image:
            linear-gradient(180deg, rgba(16,10,32,0.92), rgba(20,12,38,0.96)),
            linear-gradient(135deg, #ec4899, #22d3ee) !important;
        background-origin: border-box !important;
        background-clip: padding-box, border-box !important;
        border: 2px solid transparent !important;
        color: #f5f0ff !important;
        box-shadow:
            0 0 10px rgba(236,72,153,0.5),
            0 0 18px rgba(34,211,238,0.35) !important;
    }
    div[class*="st-key-start-"] button:hover {
        box-shadow:
            0 0 16px rgba(236,72,153,0.8),
            0 0 28px rgba(34,211,238,0.55) !important;
    }

    section[data-testid="stSidebar"] .stButton button {
        background-color: #12101f !important;
        background-image: none !important;
        box-shadow: none !important;
        border: 1px solid rgba(167,139,250,0.55) !important;
        color: #ffffff !important;
        text-align: left !important;
        font-size: 16.5px !important;
        font-weight: 700 !important;
        letter-spacing: 0.2px;
        padding-top: 11px !important;
        padding-bottom: 11px !important;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background-color: #1c1836 !important;
        border-color: rgba(167,139,250,0.9) !important;
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stCaptionContainer"] p,
    [data-testid="stCaptionContainer"] span,
    label, .stRadio label, .stCheckbox label {
        color: #eaf6ff;
    }

    [data-testid="stAppViewContainer"] { font-size: 17px; }
    .mi-cyber-sub { font-size: 0.95rem; }
    .mi-cyber-tagline { font-size: 1.05rem; }

    .stTextInput input, .stTextArea textarea {
        background-color: #ffffff !important; color: #16233b !important;
        border: 1px solid #d9e2f1 !important;
    }
    .stTextInput input::placeholder { color: #94a3b8 !important; }

    .xp-badge {
        display:inline-block; padding:5px 14px; border-radius:999px;
        background: rgba(167,139,250,0.18); border:1px solid rgba(167,139,250,0.5);
        color:#ffffff; font-size:14.5px; font-weight:700; margin-right:8px;
    }

    [data-testid="stExpander"] {
        background: rgba(10,12,28,0.92) !important;
        border: 1px solid rgba(167,139,250,0.35) !important;
        border-radius: 12px !important;
    }
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span,
    [data-testid="stExpanderHeader"],
    [data-testid="stExpanderHeader"] p,
    [data-testid="stExpanderHeader"] span {
        color: #eaf6ff !important;
        background: transparent !important;
    }
    [data-testid="stExpander"] svg { fill: #eaf6ff !important; }
    [data-testid="stExpanderDetails"] {
        background: transparent !important;
    }
    [data-testid="stExpanderDetails"] p,
    [data-testid="stExpanderDetails"] span,
    [data-testid="stExpanderDetails"] li,
    [data-testid="stExpanderDetails"] label,
    [data-testid="stExpanderDetails"] strong {
        color: #eaf6ff;
    }
    </style>
"""


# ---------------------------------------------------------------------------
# Monster Insight 전용 데이터
# ---------------------------------------------------------------------------

MONSTERS = {
    "rumor": dict(
        emoji="👻", name="루머 유령", category="news",
        intro="근거 없는 소문을 퍼뜨리며 사람들을 혼란에 빠뜨린다. 출처와 날짜를 확인하면 정체가 드러난다.",
        weakness=["출처 확인", "다른 기사와 비교", "날짜 확인"], xp=20,
    ),
    "deepfake": dict(
        emoji="🤖", name="딥페이크 로봇", category="ai",
        intro="진짜와 구별하기 힘든 가짜 이미지를 만들어낸다. 미세한 오류를 찾아내면 정체가 드러난다.",
        xp=20,
    ),
    "ad": dict(
        emoji="🎭", name="광고 변장술사", category="ad",
        intro="광고를 뉴스처럼 꾸며 독자를 속인다. 문장 속의 숨은 신호를 찾아내자.",
        xp=15,
    ),
    "algorithm": dict(
        emoji="🕸", name="알고리즘 거미", category="algorithm",
        intro="좋아요를 누를수록 점점 더 촘촘한 거미줄(추천 알고리즘)에 가두려 한다.",
        xp=15,
    ),
    "phishing": dict(
        emoji="📦", name="피싱 박스", category="phishing",
        intro="그럴듯한 메시지로 개인정보나 돈을 빼내려 한다. 수상한 신호를 찾아내자.",
        xp=20,
    ),
}

TEAM = list(MONSTERS.keys())
CATEGORY_LABEL = {
    "news": "뉴스·루머 판별력",
    "ai": "AI 판별력",
    "ad": "광고 이해력",
    "algorithm": "알고리즘 이해력",
    "phishing": "피싱 대응력",
}

DEEPFAKE_ROUNDS = [
    {"prompt": "인물의 손가락이 6개이고, 배경 패턴이 부자연스럽게 반복된다.", "answer": "AI 그림",
     "explain": "손가락 개수나 반복되는 배경 패턴 오류는 AI 생성 이미지에서 자주 나타나요."},
    {"prompt": "기자 크레딧, 촬영 장소, 촬영 시각이 명확히 표기된 보도사진이다.", "answer": "실제 사진",
     "explain": "출처와 메타데이터가 분명하면 실제 사진일 가능성이 높아요."},
    {"prompt": "인물 그림자의 방향이 조명과 맞지 않고, 귀걸이 모양이 짝짝이다.", "answer": "AI 그림",
     "explain": "조명과 그림자의 불일치는 대표적인 AI 이미지 오류예요."},
    {"prompt": "여러 언론사가 동일한 원본 사진을 동일 출처(연합뉴스 등)로 보도했다.", "answer": "실제 사진",
     "explain": "여러 매체가 같은 원본을 인용하고 있으면 신뢰도가 높아요."},
    {"prompt": "피부 질감이 지나치게 매끈하고, 배경 속 간판 글자가 깨져 보인다.", "answer": "AI 그림",
     "explain": "글자 왜곡과 과도하게 매끈한 질감은 AI 생성물에서 흔한 특징이에요."},
]

AD_ROUNDS = [
    {"prompt": "\"이 크림 하나로 피부가 10년 젊어졌어요! 지금 주문하면 50% 할인\" — 기사 하단에 '협찬'이라고 작게 표기되어 있다.",
     "answer": "광고", "explain": "'협찬' 표기와 과장된 효과 문구, 할인 유도는 전형적인 네이티브 광고 신호예요."},
    {"prompt": "\"통계청, 올해 2분기 소비자물가 3.2% 상승 발표\" — 담당 부처와 통계 출처가 명시되어 있다.",
     "answer": "뉴스", "explain": "정부 통계 발표를 사실 위주로 전달하는 전형적인 보도 기사예요."},
    {"prompt": "\"이 앱 하나로 한 달 만에 100만원 벌었어요! 링크 클릭하고 지금 바로 시작하세요\"",
     "answer": "광고", "explain": "구체적 수익 보장과 즉시 행동 유도(클릭 유도) 문구는 광고의 전형적 신호예요."},
    {"prompt": "\"서울시, 내년 대중교통 요금 150원 인상 검토\" — 관련 부서 인터뷰와 반대 의견도 함께 실려 있다.",
     "answer": "뉴스", "explain": "찬반 입장을 균형 있게 다루는 것은 일반적인 뉴스 기사의 특징이에요."},
]

DEEPFAKE_TREND = {
    "labels": ["방송통신심의위 심의", "피해자 지원", "경찰 신고"],
    "values": [5, 7, 6],
    "note": "2021년 대비 2024년 10월 기준 증가 배수(배)",
    "source": "한국형사법무정책연구원(KICJ) CCJS 이슈통계 (2024)",
}

PHISHING_TREND = {
    "categories": ["기관사칭형", "대출사기형"],
    "before_label": "이전(2016/2019년)",
    "before_values": [3384, 30448],
    "after_label": "2025년",
    "after_values": [13323, 10037],
    "source": "공공데이터포털 '경찰청_보이스피싱 현황_20251231'",
}

PHISHING_ROUNDS = [
    {"prompt": "\"[긴급] 고객님의 계좌가 정지되었습니다. 아래 링크에서 즉시 본인 인증을 완료하세요: bit.ly/acc-check\"",
     "answer": "피싱", "explain": "긴급성 강조 + 단축 URL + 즉시 인증 요구는 대표적인 피싱 신호예요."},
    {"prompt": "은행 공식 앱에서 발송된 알림으로, 발신 번호가 은행 대표번호와 일치하고 결제 내역만 안내한다.",
     "answer": "정상", "explain": "공식 채널과 발신자가 일치하고 정보 제공에 그치면 정상적인 안내일 가능성이 높아요."},
    {"prompt": "\"택배가 반송 예정입니다. 주소 확인 후 재배송 신청: 111.222.33.44/track\" (숫자로 된 IP 주소 링크)",
     "answer": "피싱", "explain": "정식 도메인이 아닌 IP 주소 링크는 피싱 사이트의 흔한 특징이에요."},
]


def init_state():
    ss = st.session_state
    ss.setdefault("page", "home")
    ss.setdefault("student_name", "")
    ss.setdefault("xp", 0)
    ss.setdefault("current_monster", None)
    ss.setdefault("collection", {})
    ss.setdefault("category_scores", {c: {"attempts": 0, "success": 0} for c in CATEGORY_LABEL})
    ss.setdefault("history", [])


def level_info(xp: int):
    level = xp // 100 + 1
    into_level = xp % 100
    return level, into_level


def record_result(monster_id: str, success: bool, stars: int):
    ss = st.session_state
    m = MONSTERS[monster_id]
    xp_gain = m["xp"] if success else max(m["xp"] // 4, 5)
    ss.xp += xp_gain

    cat = m["category"]
    ss.category_scores[cat]["attempts"] += 1
    if success:
        ss.category_scores[cat]["success"] += 1

    col = ss.collection.setdefault(monster_id, {"stars": 0, "attempts": 0, "success": 0, "captured": False})
    col["attempts"] += 1
    if success:
        col["success"] += 1
        col["captured"] = True
        col["stars"] = max(col["stars"], stars)

    ss.history.append(
        {"time": datetime.now(timezone.utc).isoformat(), "monster": monster_id, "success": success, "xp": xp_gain}
    )

    info = ss.get("student_info", {})
    supabase_insert(
        "game_sessions",
        {
            "student_name": ss.student_name or "익명",
            "monster_id": monster_id,
            "monster_name": m["name"],
            "category": cat,
            "success": success,
            "xp_gained": xp_gain,
            "stars": stars,
            "group_label": ss.get("group_label"),
            "level": info.get("level"),
            "region": info.get("region"),
            "grade": info.get("grade"),
            "gender": info.get("gender"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return xp_gain


MONSTER_IMAGE_DIRS = ["images", "image"]
MONSTER_IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp"]


def _find_monster_image_path(monster_id: str):
    for folder in MONSTER_IMAGE_DIRS:
        for ext in MONSTER_IMAGE_EXTS:
            p = os.path.join(folder, f"{monster_id}{ext}")
            if os.path.exists(p):
                return p
    return None


@st.cache_data(show_spinner=False)
def _img_b64(path: str, mtime: float) -> str:
    with open(path, "rb") as f:
        return b64encode(f.read()).decode()


def monster_visual_html(monster_id: str, size: int = 64) -> str:
    m = MONSTERS[monster_id]
    path = _find_monster_image_path(monster_id)
    if path:
        try:
            b64 = _img_b64(path, os.path.getmtime(path))
            ext = os.path.splitext(path)[1].lstrip(".").replace("jpg", "jpeg")
            return (
                f'<img src="data:image/{ext};base64,{b64}" '
                f'style="width:{size}px;height:{size}px;object-fit:contain;border-radius:10px;" />'
            )
        except Exception:
            pass
    return f'<span style="font-size:{size}px;line-height:1;">{m["emoji"]}</span>'


def stars_html(n: int, total: int = 5) -> str:
    return "★" * n + "☆" * (total - n)


def goto(page: str, monster: str | None = None):
    st.session_state.page = page
    if monster is not None:
        st.session_state.current_monster = monster


def render_which_face_is_real():
    st.markdown("**🕵️ 실전 연습: Which Face Is Real?**")
    st.caption(
        "AI가 만든 얼굴과 실제 사람의 얼굴을 직접 구별해보는 훈련 도구입니다. "
        "워싱턴대학교 Jevin West · Carl Bergstrom 교수의 'Calling Bullshit' 프로젝트에서 제공합니다."
    )
    try:
        components.iframe("https://whichfaceisreal.com/index.php", height=650, scrolling=True)
    except Exception:
        st.info("이 환경에서는 미리보기가 표시되지 않을 수 있어요. 아래 버튼으로 바로 열어보세요.")
    st.link_button("🔗 whichfaceisreal.com 에서 직접 해보기", "https://whichfaceisreal.com/index.php")
    st.caption("출처/저작권: Jevin West & Carl Bergstrom, University of Washington (Calling Bullshit project)")


def render_deepfake_data():
    d = DEEPFAKE_TREND
    fig = go.Figure(
        data=[
            go.Bar(
                x=d["labels"], y=d["values"],
                marker_color=["#a78bfa", "#38bdf8", "#5eead4"],
                text=[f"{v}배" for v in d["values"]], textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title="딥페이크 관련 지표 증가 추세", yaxis_title="증가 배수(배)",
        margin=dict(l=10, r=10, t=40, b=10), height=320,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"{d['note']} · 출처: {d['source']}")


def render_phishing_data():
    d = PHISHING_TREND
    fig = go.Figure()
    fig.add_trace(go.Bar(name=d["before_label"], x=d["categories"], y=d["before_values"], marker_color="#94a3b8"))
    fig.add_trace(go.Bar(name=d["after_label"], x=d["categories"], y=d["after_values"], marker_color="#a78bfa"))
    fig.update_layout(
        barmode="group", title="보이스피싱 유형별 발생 건수 변화", yaxis_title="발생 건수(건)",
        margin=dict(l=10, r=10, t=40, b=10), height=320,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"출처: {d['source']}")


def run_quiz(monster_id: str, rounds: list, choice_labels: list):
    ss = st.session_state
    ridx_key, score_key = f"{monster_id}_ridx", f"{monster_id}_score"
    ss.setdefault(ridx_key, 0)
    ss.setdefault(score_key, 0)

    total = len(rounds)
    ridx = ss[ridx_key]

    if ridx >= total:
        score = ss[score_key]
        ratio = score / total
        stars = max(1, round(ratio * 5))
        success = ratio >= 0.6
        with st.container(border=True, key=f"panel-result-{monster_id}"):
            if success:
                st.markdown(f"### {MONSTERS[monster_id]['emoji']} {MONSTERS[monster_id]['name']} 포획 성공!")
            else:
                st.markdown(f"### {MONSTERS[monster_id]['emoji']} {MONSTERS[monster_id]['name']}이(가) 도망쳤다…")
            st.write(f"정답 {score} / {total}  ·  평가: {stars_html(stars)}")
            if st.button("결과 확정하기", key=f"confirm-{monster_id}"):
                xp = record_result(monster_id, success, stars)
                st.success(f"+{xp} XP 획득!")
                del ss[ridx_key]
                del ss[score_key]
                goto("home")
                st.rerun()
        return

    r = rounds[ridx]
    with st.container(border=True, key=f"panel-quiz-{monster_id}"):
        st.progress(ridx / total, text=f"{ridx + 1} / {total} 라운드")
        st.markdown(f"**{r['prompt']}**")
        choice = st.radio("이것은 무엇일까요?", choice_labels, key=f"{monster_id}_choice_{ridx}", index=None)
        if st.button("제출", key=f"submit-{monster_id}-{ridx}"):
            if choice is None:
                st.warning("먼저 답을 선택해주세요.")
            else:
                correct = choice == r["answer"]
                if correct:
                    ss[score_key] += 1
                    st.success(f"정답! {r['explain']}")
                else:
                    st.error(f"오답이에요. 정답은 '{r['answer']}'. {r['explain']}")
                ss[ridx_key] += 1
                st.rerun()


def play_rumor(monster_id: str):
    m = MONSTERS[monster_id]
    with st.container(border=True, key=f"panel-{monster_id}"):
        st.markdown(f"### {m['emoji']} {m['name']} 수사")
        query = st.text_input("검증할 소문·주장을 입력하세요", placeholder="예: 백신 부작용, 물가 상승률")
        if st.button("🔍 수사 시작", key=f"search-{monster_id}"):
            st.session_state[f"{monster_id}_query"] = query

        query = st.session_state.get(f"{monster_id}_query", "")
        if query:
            claims = None
            error = None
            try:
                claims = fetch_google_factcheck(query)
            except Exception as e:
                error = str(e)

            if error:
                st.caption(f"조회 실패: {error}")
            elif claims is None:
                st.caption("Secrets에 GOOGLE_FACTCHECK_API_KEY가 없어 데모 모드로 진행합니다.")
                claims = [
                    {"text": f"'{query}' 관련 소문은 일부 사실과 다르다", "claimant": "예시 매체",
                     "claimReview": [{"publisher": {"name": "예시 팩트체커"}, "textualRating": "대체로 거짓", "url": "#"}]}
                ]
            if claims:
                for c in claims[:5]:
                    review = (c.get("claimReview") or [{}])[0]
                    st.markdown(f"- **{c.get('text', '')}** · {(review.get('publisher') or {}).get('name', '')} "
                                f"· 판정: {review.get('textualRating', '미상')}")
            else:
                st.caption("등록된 팩트체크 결과가 없습니다. 그래도 아래 체크리스트로 판단해보세요.")

            st.markdown("#### 루머 유령의 약점")
            checks = [st.checkbox(w, key=f"{monster_id}_chk_{i}") for i, w in enumerate(m["weakness"])]
            done = sum(checks)
            if st.button("👻 포획 시도", key=f"capture-{monster_id}"):
                success = done >= 2
                stars = min(5, max(1, done + 2))
                xp = record_result(monster_id, success, stars)
                if success:
                    st.success(f"루머 유령 포획 성공! +{xp} XP · {stars_html(stars)}")
                else:
                    st.warning(f"체크리스트를 더 확인해야 포획할 수 있어요. (+{xp} XP)")
                st.session_state.pop(f"{monster_id}_query", None)
                for i in range(len(m["weakness"])):
                    st.session_state.pop(f"{monster_id}_chk_{i}", None)
                if st.button("← 홈으로", key=f"back-{monster_id}"):
                    goto("home")
                    st.rerun()


def play_algorithm(monster_id: str):
    m = MONSTERS[monster_id]
    ss = st.session_state
    like_key = f"{monster_id}_likes"
    ss.setdefault(like_key, 0)

    feed_pool = [
        "고양이 영상", "고양이 브이로그", "고양이 먹방", "고양이 하이라이트 모음",
        "귀여운 고양이 리액션", "고양이 성대모사 챌린지",
    ]

    with st.container(border=True, key=f"panel-{monster_id}"):
        st.markdown(f"### {m['emoji']} {m['name']}")
        st.write(m["intro"])
        likes = ss[like_key]
        shown = feed_pool[: min(likes + 2, len(feed_pool))]
        st.markdown("**추천 피드**")
        for item in shown:
            st.write(f"▶ {item}")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("👍 좋아요", key=f"like-{monster_id}"):
                ss[like_key] += 1
                st.rerun()
        with c2:
            if st.button("🚪 탈출하기", key=f"escape-{monster_id}"):
                success = True
                stars = min(5, max(1, likes))
                xp = record_result(monster_id, success, stars)
                st.success(
                    f"거미줄 탈출 성공! 좋아요를 누를수록 추천 피드가 점점 비슷한 주제로 좁아지는 것을 확인했어요. "
                    f"이것이 '필터 버블(알고리즘 추천)' 효과예요. +{xp} XP"
                )
                ss[like_key] = 0
                if st.button("← 홈으로", key=f"back-{monster_id}"):
                    goto("home")
                    st.rerun()


def render_dictionary_lookup(monster_id: str):
    st.markdown("**📖 낱말 사전 찾아보기**")
    st.caption("뉴스나 미션에 나온 낯선 단어를 국어사전에서 검색해보세요.")
    word = st.text_input("단어 입력", key=f"dict_word_{monster_id}", placeholder="예: 필리버스터, 유예, 협찬")
    if st.button("사전 검색", key=f"dict_search_{monster_id}"):
        q = word.strip()
        st.session_state[f"dict_query_{monster_id}"] = q
        st.session_state[f"dict_result_{monster_id}"] = fetch_dict(q)[0] if q else []

    query = st.session_state.get(f"dict_query_{monster_id}")
    entries = st.session_state.get(f"dict_result_{monster_id}")
    if entries:
        for e in entries[:5]:
            st.markdown(f"**{e['word']}** · _{e['source']}_")
            st.write(e["definition"])
    elif query is not None:
        if not (STDICT_API_KEY or KRDICT_API_KEY or OPENDICT_API_KEY):
            st.caption("Secrets에 사전 API 키가 없어 데모 모드예요. 등록하면 실제 사전 검색이 가능해요.")
        elif query:
            st.caption(f'"{query}"에 대한 뜻풀이를 찾지 못했어요. 아래 네이버 사전에서 다시 찾아보세요.')

    if query:
        st.write("")
        st.markdown(naver_dict_link_card(query), unsafe_allow_html=True)


def render_monster_intro_card(monster_id: str):
    m = MONSTERS[monster_id]
    st.markdown(
        f"""
        <div class="monster-card">
            <div class="monster-emoji">{monster_visual_html(monster_id, size=72)}</div>
            <div class="monster-name">{m['name']} 등장!!</div>
            <div class="monster-cat">{CATEGORY_LABEL[m['category']]}</div>
            <div class="monster-intro">{m['intro']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def play_monster(monster_id: str):
    st.write("")

    with st.expander("📖 낱말 사전 찾아보기", expanded=False):
        render_dictionary_lookup(monster_id)
    st.write("")

    if monster_id == "rumor":
        play_rumor(monster_id)
    elif monster_id == "deepfake":
        with st.expander("📊 실제 데이터로 보는 딥페이크 위협", expanded=True):
            render_deepfake_data()
        with st.expander("🕵️ 실전 연습: 진짜 얼굴 vs AI 얼굴 구별하기", expanded=True):
            render_which_face_is_real()
        run_quiz(monster_id, DEEPFAKE_ROUNDS, ["AI 그림", "실제 사진"])
    elif monster_id == "ad":
        run_quiz(monster_id, AD_ROUNDS, ["광고", "뉴스"])
    elif monster_id == "phishing":
        with st.expander("📊 실제 데이터로 보는 피싱 범죄 추세", expanded=True):
            render_phishing_data()
        run_quiz(monster_id, PHISHING_ROUNDS, ["피싱", "정상"])
    elif monster_id == "algorithm":
        play_algorithm(monster_id)

    st.write("")
    if st.button("← 사건 목록으로", key=f"leave-{monster_id}"):
        goto("home")
        st.rerun()


def page_home():
    ss = st.session_state
    level, into_level = level_info(ss.xp)
    st.markdown(
        f"<span class='xp-badge'>🏆 Lv.{level}</span>"
        f"<span class='xp-badge'>⚡ {ss.xp} XP</span>"
        f"<span class='xp-badge'>📖 {sum(1 for v in ss.collection.values() if v['captured'])}/{len(MONSTERS)} 몬스터 포획</span>",
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown("#### 사건 파일")
    cols = st.columns(3)
    for i, (mid, m) in enumerate(MONSTERS.items()):
        col = ss.collection.get(mid, {"captured": False, "stars": 0})
        with cols[i % 3]:
            st.markdown(
                f"""
                <div class="monster-card" style="cursor:pointer;">
                    <div class="monster-emoji">{monster_visual_html(mid, size=64)}</div>
                    <div class="monster-name">{m['name']}</div>
                    <div class="monster-cat">{CATEGORY_LABEL[m['category']]}</div>
                    <div class="monster-intro">{'포획 완료 ' + stars_html(col['stars']) if col['captured'] else '아직 미포획'}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("수사 시작", key=f"start-{mid}"):
                goto("playing", mid)
                st.rerun()

    st.write("")
    st.markdown("#### 랜덤 사건 출동")
    st.caption("어떤 몬스터가 나타날지 모릅니다. 준비되셨나요?")
    if st.button("▶ 랜덤 몬스터 출현!", key="random-mission", type="primary"):
        goto("playing", random.choice(TEAM))
        st.rerun()


def page_level():
    ss = st.session_state
    level, into_level = level_info(ss.xp)
    st.markdown("### 🏆 탐정 레벨")
    with st.container(border=True, key="panel-level"):
        st.write(f"**{ss.student_name or '익명 탐정'}** · 현재 레벨 **Lv.{level}**")
        st.progress(into_level / 100, text=f"다음 레벨까지 {100 - into_level} XP")
        st.write(f"누적 XP: **{ss.xp}**")
        total_attempts = sum(v["attempts"] for v in ss.collection.values())
        total_success = sum(v["success"] for v in ss.collection.values())
        rate = (total_success / total_attempts * 100) if total_attempts else 0
        st.write(f"총 시도 {total_attempts}회 · 포획 성공 {total_success}회 · 성공률 {rate:.0f}%")


def page_dex():
    ss = st.session_state
    st.markdown("### 📖 몬스터 도감")
    cols = st.columns(3)
    for i, (mid, m) in enumerate(MONSTERS.items()):
        col_data = ss.collection.get(mid)
        with cols[i % 3]:
            if col_data and col_data["captured"]:
                st.markdown(
                    f"""
                    <div class="dex-card">
                        <div class="dex-emoji">{m['emoji']}</div>
                        <div class="dex-name">{m['name']}</div>
                        <div class="dex-stars">{stars_html(col_data['stars'])}</div>
                        <div style="font-size:11px;color:#5b6b80;margin-top:4px;">
                            시도 {col_data['attempts']} · 성공 {col_data['success']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div class="dex-card locked">
                        <div class="dex-emoji">❓</div>
                        <div class="dex-name">미확인 몬스터</div>
                        <div class="dex-stars">☆☆☆☆☆</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        if (i % 3) == 2:
            st.write("")


def page_report():
    ss = st.session_state
    st.markdown("### 📊 나의 통찰 리포트")
    with st.container(border=True, key="panel-report"):
        st.write(f"**{ss.student_name or '익명 탐정'}** 님의 영역별 역량입니다.")

        labels = list(CATEGORY_LABEL.values())
        scores = []
        any_data = False
        for cat, label in CATEGORY_LABEL.items():
            data = ss.category_scores[cat]
            score = round(data["success"] / data["attempts"] * 100) if data["attempts"] else 0
            if data["attempts"]:
                any_data = True
            scores.append(score)

        if any_data:
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=scores + [scores[0]], theta=labels + [labels[0]],
                                           fill="toself", line_color="#a78bfa", name="역량 점수"))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=False, margin=dict(l=30, r=30, t=30, b=30), height=380,
            )
            st.plotly_chart(fig, use_container_width=True)

        for cat, label in CATEGORY_LABEL.items():
            data = ss.category_scores[cat]
            if data["attempts"] == 0:
                st.write(f"- {label}: 아직 도전 기록이 없어요.")
                continue
            score = round(data["success"] / data["attempts"] * 100)
            st.write(f"**{label}** — {score}점 (시도 {data['attempts']}회 · 성공 {data['success']}회)")
        if not any_data:
            st.info("아직 어떤 몬스터도 조사하지 않았어요. 사건을 시작해보세요!")

        overall_attempts = sum(v["attempts"] for v in ss.category_scores.values())
        overall_success = sum(v["success"] for v in ss.category_scores.values())
        if overall_attempts:
            overall = round(overall_success / overall_attempts * 100)
            st.write("---")
            st.write(f"**종합 통찰 점수: {overall}점**")
            st.progress(overall / 100)


def page_teacher():
    st.markdown("### 🧑‍🏫 교사용 화면")
    if not supabase_enabled():
        st.warning(
            "Supabase가 연결되어 있지 않아 전체 학급 통계를 볼 수 없습니다. "
            "Streamlit Secrets에 SUPABASE_URL과 SUPABASE_ANON_KEY를 등록하면 "
            "`game_sessions` 테이블의 기록을 자동으로 집계합니다."
        )
        st.caption(
            "필요한 테이블 예시(schema_update.sql 참고):\n\n"
            "create table game_sessions (\n"
            "  id bigint generated always as identity primary key,\n"
            "  student_name text, monster_id text, monster_name text,\n"
            "  category text, success boolean, xp_gained int, stars int,\n"
            "  group_label text, level text, region text, grade text, gender text,\n"
            "  created_at timestamptz\n"
            ");"
        )
        return

    rows = supabase_select("game_sessions", {"select": "*"})
    if not rows:
        st.info("아직 저장된 플레이 기록이 없습니다.")
        return

    df = pd.DataFrame(rows)
    df["success"] = df["success"].astype(bool)
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    if "group_label" in df.columns and df["group_label"].notna().any():
        group_options = ["전체"] + sorted(df["group_label"].dropna().unique().tolist())
        selected_group = st.selectbox("학교급 그룹 필터", group_options, key="teacher_group_filter")
        if selected_group != "전체":
            df = df[df["group_label"] == selected_group]

    if df.empty:
        st.info("선택한 그룹에 해당하는 기록이 없습니다.")
        return

    total_success = int(df["success"].sum())

    with st.container(border=True, key="panel-teacher"):
        st.write(f"총 플레이 기록: **{len(df)}건** · 성공 **{total_success}건**")

        monster_stats = (
            df.groupby("monster_name")["success"]
            .agg(시도="count", 성공="sum")
            .reset_index()
        )
        monster_stats["성공률"] = (monster_stats["성공"] / monster_stats["시도"] * 100).round(0)

        if not monster_stats.empty:
            most_caught_row = monster_stats.sort_values("성공", ascending=False).iloc[0]
            hardest_row = monster_stats.sort_values("성공률", ascending=True).iloc[0]
            st.write(f"**가장 많이 잡은 몬스터:** {most_caught_row['monster_name']} ({int(most_caught_row['성공'])}회)")
            st.write(f"**가장 어려운 몬스터:** {hardest_row['monster_name']} (성공률 {hardest_row['성공률']:.0f}%)")

        overall_rate = total_success / len(df) if len(df) else 0
        stars = max(1, round(overall_rate * 5))
        st.write(f"**학급 평균 통찰력:** {stars_html(stars)} (전체 성공률 {overall_rate * 100:.0f}%)")

        st.write("---")
        st.markdown("**몬스터별 시도·성공 건수**")
        if not monster_stats.empty:
            fig_bar = px.bar(
                monster_stats.melt(id_vars="monster_name", value_vars=["시도", "성공"], var_name="구분", value_name="건수"),
                x="monster_name", y="건수", color="구분", barmode="group",
                color_discrete_map={"시도": "#94a3b8", "성공": "#a78bfa"},
            )
            fig_bar.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=340, xaxis_title="", yaxis_title="건수")
            st.plotly_chart(fig_bar, use_container_width=True)

        if "created_at" in df.columns and df["created_at"].notna().any():
            st.markdown("**일별 플레이 건수 추이**")
            daily = (
                df.dropna(subset=["created_at"])
                .set_index("created_at")
                .resample("D")
                .size()
                .reset_index(name="플레이 건수")
            )
            fig_line = px.line(daily, x="created_at", y="플레이 건수", markers=True)
            fig_line.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=300, xaxis_title="날짜")
            st.plotly_chart(fig_line, use_container_width=True)

        st.write("---")
        st.markdown("**학생별 요약**")
        student_stats = (
            df.groupby("student_name")
            .agg(시도=("success", "count"), 성공=("success", "sum"), 누적XP=("xp_gained", "sum"))
            .reset_index()
            .sort_values("누적XP", ascending=False)
        )
        st.dataframe(student_stats, use_container_width=True, hide_index=True)


def render_monster_page():
    st.markdown(MONSTER_CSS, unsafe_allow_html=True)
    init_state()
    ss = st.session_state

    with st.sidebar:
        st.markdown(
            sidebar_brand_html(
                "images/monster-icon.png", "🧠",
                "Monster Insight", "AI MEDIA MONSTER HUNTER",
            ),
            unsafe_allow_html=True,
        )
        st.caption("AI 미디어 몬스터 헌터")
        st.divider()

        if st.button("▶ 사건 시작", use_container_width=True):
            goto("playing", random.choice(TEAM))
            st.rerun()

        st.caption("몬스터 바로가기")
        icon_css_parts = []
        for mid, m in MONSTERS.items():
            path = _find_monster_image_path(mid)
            label = m["name"] if path else f"{m['emoji']} {m['name']}"
            if st.button(label, key=f"nav-{mid}", use_container_width=True):
                goto("playing", mid)
                st.rerun()
            if path:
                try:
                    b64 = _img_b64(path, os.path.getmtime(path))
                    ext = os.path.splitext(path)[1].lstrip(".").replace("jpg", "jpeg")
                    icon_css_parts.append(
                        f"""
                        section[data-testid="stSidebar"] div[class*="st-key-nav-{mid}"] button {{
                            background-image: url(data:image/{ext};base64,{b64}) !important;
                            background-repeat: no-repeat !important;
                            background-position: 14px center !important;
                            background-size: 32px 32px !important;
                            padding-left: 54px !important;
                        }}
                        """
                    )
                except Exception:
                    pass
        if icon_css_parts:
            st.markdown(f"<style>{''.join(icon_css_parts)}</style>", unsafe_allow_html=True)

        st.divider()
        if st.button("🏆 탐정 레벨", use_container_width=True):
            goto("level")
            st.rerun()
        if st.button("📖 몬스터 도감", use_container_width=True):
            goto("dex")
            st.rerun()
        if st.button("📊 나의 통찰 리포트", use_container_width=True):
            goto("report")
            st.rerun()

        st.divider()
        if st.button("🧑‍🏫 교사용 화면", use_container_width=True):
            goto("teacher")
            st.rerun()

    page = ss.page

    if page == "playing":
        mid = ss.current_monster or random.choice(TEAM)
        ss.current_monster = mid
        head_col, card_col = st.columns([1, 1.4])
        with head_col:
            st.markdown(
                """
                <div>
                    <div class="mi-cyber-title">Monster Insight</div>
                    <div class="mi-cyber-sub">AI MEDIA MONSTER HUNTER</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='mi-cyber-tagline'>미디어 몬스터를 잡고 통찰력을 키워라!</div>",
                unsafe_allow_html=True,
            )
        with card_col:
            render_monster_intro_card(mid)
        play_monster(mid)
    else:
        st.markdown(
            """
            <div>
                <div class="mi-cyber-title">Monster Insight</div>
                <div class="mi-cyber-sub">AI MEDIA MONSTER HUNTER</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='mi-cyber-tagline'>미디어 몬스터를 잡고 통찰력을 키워라!</div>", unsafe_allow_html=True)
        st.write("")

        if page == "home":
            page_home()
        elif page == "level":
            page_level()
        elif page == "dex":
            page_dex()
        elif page == "report":
            page_report()
        elif page == "teacher":
            page_teacher()
        else:
            page_home()


# ---------------------------------------------------------------------------
# 통합 메인: 입장 화면(비밀번호 없음) → 사이드바 메뉴 → 팩트수색대 / Monster Insight
# ---------------------------------------------------------------------------

def main():
    if not entry_gate():
        st.stop()

    init_state()

    with st.sidebar:
        st.session_state.student_name = st.text_input(
            "탐정 이름",
            value=st.session_state.get("student_name", ""),
            placeholder="이름을 입력하세요",
            key="student_name_input",
        )
        st.divider()

        st.markdown(
            sidebar_brand_html(
                "images/guardians-icon.png", "🧭",
                "데이터 스페이스<br>가디언즈", "DATA SPACE GUARDIANS",
                icon_size=64,
            ),
            unsafe_allow_html=True,
        )
        info = st.session_state.get("student_info", {})
        st.caption(
            f"{st.session_state.get('group_label', '')} · "
            f"{info.get('region', '')} {info.get('grade', '')} · {info.get('gender', '')}"
        )

        st.session_state.setdefault("fs_page", "home")

        if st.button("▶ 팩트체크-교차검증", key="fs-start", use_container_width=True):
            st.session_state.fs_page = "home"
            st.rerun()

        st.caption("팩트체크 교차검증")
        if st.button("🇰🇷 국내 팩트체크", key="fs-domestic", use_container_width=True):
            st.session_state.fs_page = "domestic"
            st.rerun()
        if st.button("🌍 해외 팩트체크", key="fs-international", use_container_width=True):
            st.session_state.fs_page = "international"
            st.rerun()

        st.divider()

    render_factsquad_page()

    st.divider()
    st.divider()

    render_monster_page()

    st.divider()
    st.caption(
        "수업용 프로토타입 · API 키와 Supabase 접속정보는 Streamlit Secrets에만 보관되며 이 코드에는 들어있지 않습니다."
    )


if __name__ == "__main__":
    main()
