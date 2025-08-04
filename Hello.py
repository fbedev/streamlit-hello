import requests
from urllib.parse import urlparse, parse_qs
import streamlit as st

def submit_video_progress(video_url, session_id, debug_mode=False):
    parsed = urlparse(video_url)
    qs = parse_qs(parsed.query)

    # Extract parameters from the URL
    course = qs.get('course', [None])[0]
    user = qs.get('user', [None])[0]  # Extract user ID from the link
    unit = qs.get('id', [None])[0]
    task = qs.get('task', [None])[0]

    if not all([course, user, unit, task]):
        return f"[ERROR] URL 缺少参数: {video_url}"

    # URL to submit progress
    url = 'https://dmhs.teams.com.tw/VideoProgress!insertProgress'
    
    # Build the cookie with session ID and user ID extracted from the URL
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': video_url,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
        'Cookie': f"JSESSIONID={session_id}; userId={user};",
    }
    
    data = {
        'task': task,
        'unit': unit,
        'course': course,
        'user': user,  # Use the extracted user ID from the link
        'type': 'teams',
        'startScale': '0',
        'endScale': '100',
    }

    if debug_mode:
        st.write(f"[DEBUG] Parsing URL: {video_url}")
        st.write(f"[DEBUG] Extracted course: {course}, user: {user}, unit: {unit}, task: {task}")
        st.write(f"[DEBUG] Sending request to: {url}")
        st.write(f"[DEBUG] Headers: {headers}")
        st.write(f"[DEBUG] Data: {data}")

    try:
        resp = requests.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            if debug_mode:
                st.write(f"[DEBUG] Response content: {resp.text}")
            return f"[SUCCESS] 提交成功: {video_url}"
        else:
            if debug_mode:
                st.write(f"[DEBUG] Response content: {resp.text}")
            return f"[FAIL] 状态码 {resp.status_code}: {video_url}"
    except Exception as e:
        return f"[ERROR] request problem: {video_url} | {e}"

def main():
    st.title("Video Progress Submitter")
    
    # Input fields for session ID (cookie) and links
    session_id = st.text_area("Enter Session ID (JSESSIONID)", 
                              "AF1B47245D695296E9CF45A2B7A36162")  # Default value for easy testing
    
    # Checkbox for debug mode
    debug_mode = st.checkbox("Enable Debug Mode", value=False)
    
    # Input multiple video links
    st.subheader("Enter Video Links (one per line):")
    video_links_input = st.text_area("Paste each video link here:", height=200)
    
    # Process the links when the button is pressed
    if st.button("Submit Video Progress"):
        if video_links_input.strip():
            video_links = video_links_input.splitlines()
            results = []
            for link in video_links:
                if link:
                    result = submit_video_progress(link.strip(), session_id, debug_mode)
                    results.append(result)
            # Show results in the app
            for result in results:
                st.write(result)
        else:
            st.error("Please enter at least one video link.")

if __name__ == "__main__":
    main()
