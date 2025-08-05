import requests
from urllib.parse import urlparse, parse_qs
import streamlit as st
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1402211944743567440/7jRAZdnPJq8MzmHsmIERrShv253fG4toTBskp9BafOv4k9EAu0BHsbNMlxI3kB6PrLpc"

# === Constants ===
BASE_URL = "https://dmhs.teams.com.tw"
DASHBOARD_URL_TEMPLATE = f"{BASE_URL}/VideoProgress!dashboard?user={{user_id}}&showCompleted=true"
PROGRESS_URL = f"{BASE_URL}/VideoProgress!insertProgress"

DEFAULT_SESSION = "AF1B47245D695296E9CF45A2B7A36162"
DEFAULT_USER_ID = "D10028_STUDENT_003052"
def send_discord_webhook(video_url, user_id):
    content = f"🎬 **Video progress hacked**\n🔗 {video_url}\n👤 User: {user_id}"
    data = {"content": content}

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if resp.status_code != 204:
            st.warning(f"⚠️ Discord webhook failed: {resp.status_code}")
    except Exception as e:
        st.warning(f"⚠️ Exception while sending webhook: {e}")


if "users_helped" not in st.session_state:
    st.session_state.users_helped = 0
if "videos_progressed" not in st.session_state:
    st.session_state.videos_progressed = 0
if "links" not in st.session_state:
    st.session_state.links = []
if "manual_links" not in st.session_state:
    st.session_state.manual_links = ""

# === Helpers ===
def build_video_url(course, user, unit, task):
    return f"{BASE_URL}/student/cinemaVideo.html?course={course}&user={user}&id={unit}&task={task}"

def get_common_headers(video_url, session_id, user_id):
    return {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': video_url,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Cookie': f"JSESSIONID={session_id}; userId={user_id};"
    }

def fetch_completed_videos(user_id):
    url = DASHBOARD_URL_TEMPLATE.format(user_id=user_id)
    headers = {"X-Requested-With": "XMLHttpRequest"}
    cookies = {"userId": user_id}

    try:
        r = requests.get(url, headers=headers, cookies=cookies)
        if r.status_code != 200:
            return [], f"❌ Failed to fetch video data. Status code: {r.status_code}"

        data = r.json().get("result", [])
        if not data:
            return [], "🎉 No completed videos found."

        links = []
        for item in data:
            task = item.get("task", {})
            unit = item.get("unit", {})

            # ✅ Skip if there's no actual video field
            if not unit.get("video"):
                continue

            course_id = task.get("course", "UNKNOWN_COURSE")
            unit_id = unit.get("_id", "UNKNOWN_UNIT")
            task_id = task.get("_id", "UNKNOWN_TASK")
            if course_id and unit_id and task_id:
                links.append(build_video_url(course_id, user_id, unit_id, task_id))

        return links, f"✅ Found {len(links)} real video(s)."
    except Exception as e:
        return [], f"❌ Exception occurred: {e}"

def submit_video_progress(video_url, session_id, debug=False):
    parsed = urlparse(video_url)
    qs = parse_qs(parsed.query)
    course = qs.get('course', [None])[0]
    user = qs.get('user', [None])[0]
    unit = qs.get('id', [None])[0]
    task = qs.get('task', [None])[0]

    if not all([course, user, unit, task]):
        return f"[ERROR] URL missing params: {video_url}"

    headers = get_common_headers(video_url, session_id, user)
    data = {
        'task': task,
        'unit': unit,
        'course': course,
        'user': user,
        'type': 'teams',
        'startScale': '0',
        'endScale': '100',
    }

    try:
        resp = requests.post(PROGRESS_URL, headers=headers, data=data)
        if resp.status_code == 200:
            st.session_state.videos_progressed += 1
            send_discord_webhook(video_url, user)  # ✅ Only here, if status is 200
            return f"✅ Submitted: {video_url}"
        else:
            return f"❌ Failed ({resp.status_code}): {video_url}"
    except Exception as e:
        return f"⚠️ Exception on {video_url}: {e}"




# === Streamlit UI ===
def main():
    st.set_page_config(page_title="Video Progress Submitter", layout="wide")
    st.title("🎞️ Video Progress Submitter")

    col1, col2 = st.columns(2)
    session_id = col1.text_input("🔐 JSESSIONID", value=DEFAULT_SESSION)
    user_id = col2.text_input("🧑‍🎓 User ID", value=DEFAULT_USER_ID)

    debug = st.toggle("🪛 Enable Debug Logs")

    mode = st.radio("📤 Mode", ["Paste Video Links Manually", "Fetch Completed Videos First"], horizontal=True)

    if mode == "Paste Video Links Manually":
        st.session_state.links = []
        st.session_state.manual_links = st.text_area("📥 Paste video links (one per line)", value=st.session_state.manual_links, height=200)
        if st.session_state.manual_links.strip():
            st.session_state.links = [line.strip() for line in st.session_state.manual_links.strip().splitlines()]
            st.success(f"✅ Loaded {len(st.session_state.links)} manual link(s).")
    else:
        st.session_state.manual_links = ""
        if st.button("🔍 Fetch Completed Video Links"):
            with st.spinner("Fetching..."):
                links, msg = fetch_completed_videos(user_id)
                st.info(msg)
                if links:
                    st.session_state.links = links
                    st.success(f"🎯 {len(links)} video(s) ready to be submitted.")
                    for i, link in enumerate(links, 1):
                        st.markdown(f"{i}. [`{link}`]({link})")

    if st.session_state.links:
        if st.button("🚀 Watch All / Submit All"):
            if not session_id or not user_id:
                st.error("❗ Session ID and User ID are required.")
            else:
                with st.spinner("Submitting all..."):
                    results = []
                    for i, link in enumerate(st.session_state.links, 1):
                        msg = submit_video_progress(link, session_id, debug)
                        results.append(f"{i}. {msg}")
                    st.session_state.users_helped += 1
                    st.markdown("### 📋 Submission Results")
                    for r in results:
                        st.write(r)

        st.download_button("💾 Download Fetched Links", data="\n".join(st.session_state.links), file_name="fetched_links.txt")

    st.markdown("---")
    col3, col4 = st.columns(2)
    col3.metric("📈 Videos Progressed", st.session_state.videos_progressed)
    col4.metric("🧑‍🤝‍🧑 Users Helped", st.session_state.users_helped)

if __name__ == "__main__":
    main()
