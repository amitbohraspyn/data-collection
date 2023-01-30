import json
import threading
import time
from io import BytesIO
import base64
import tempfile
import av
import cv2
import os
import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account
from streamlit_webrtc import webrtc_streamer

# lock = threading.Lock()
if("is_recording" not in st.session_state):
    st.session_state["is_recording"] = False

def get_video_resolution(file):
    with tempfile.NamedTemporaryFile(suffix=".mp4") as temp:
        temp.write(file)
        temp.seek(0)
        cap = cv2.VideoCapture(temp.name)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        return (width, height, fps)


def uploadToGCP(file, class_label, mode):
    bucket_name = "spyn_datasets"
    class_label = str(class_label)
    folder_name = class_label
    file_name = f"{int(time.time())}_{class_label}_video_{mode}.mp4"
    creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"])
    # path_to_credentials = "app/mlServiceAccountKey.json"
    # creds = service_account.Credentials.from_service_account_file(
    #     path_to_credentials)
    # creds = None
    # if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
    #     creds = os.environ['GOOGLE_APPLICATION_CREDENTIALS']

    client = storage.Client.from_service_account_json(creds)
    client = storage.Client(credentials=creds)
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(f"activity_recognition/{folder_name}/{file_name}")
    blob.upload_from_string(file, content_type="video/mp4")
    blob.make_public()
    public_url = blob.public_url
    print(
        public_url)
    
    
    # Check if a JSON file exists in the desired folder
    metadata_file = bucket.blob("activity_recognition/metadata.json")
    if metadata_file.exists():
        metadata = json.loads(metadata_file.download_as_string().decode("utf-8"))
    else:
        metadata = []
    resolution = get_video_resolution(file)
    file_size = len(file)
    size_kb = file_size / 1024
    size_mb = size_kb / 1024
    size_gb = size_mb / 1024
    if size_gb >= 1:
        size = f"{round(size_gb, 2)} GB"
    elif size_mb >= 1:
        size = f"{round(size_mb, 2)} MB"
    else:
        size = f"{round(size_kb, 2)} KB"
    metadata.append({
        "class_label": class_label,
        "public_url": public_url,
        "video_name": file_name,
        "mode": mode.upper(),
        "timestamp": int(time.time()),
        "file_size": size,
        "actual_file_size": file_size,
        "resolution": f'{resolution[0]}x{resolution[1]}',
        "fps": resolution[2]
    })
    metadata_file.upload_from_string(json.dumps(metadata).encode("utf-8"), content_type="application/json")
    metadata_file.make_public()
    st.success("Video uploaded successfully!")



    


class_options = {
    "0. Thumb Up": 0,
    "1. Thumb Down": 1,
    "2. Hand Wave": 2,
    "3. Ok Sign": 3,
    "4. Victory Sign": 4,
    "5. Hand Heart": 5
}

st.set_page_config(page_title="Activity Recognition Dataset Collection",
                   page_icon=":guardsman:", layout="centered")
st.write(
    '<style>div.row-widget.stRadio > div{flex-direction:row;}</style>', unsafe_allow_html=True)
st.markdown(
    "<h1 style='text-align: center; color: grey;'>Activity Recognition Dataset Creator</h1>", unsafe_allow_html=True)
class_label = st.radio("Select the class", list(class_options.keys()))
class_label = class_options[class_label]
choice = st.radio("Select one option:", ("Upload a file", "Record webcam"))
if choice == "Upload a file":
    file = st.file_uploader("Upload your video file", type=["mp4", "mov"])
    if file is None:
        st.error("Please upload a video file")
    else:
        if file:
            file_bytes = file.getvalue()
            if file_bytes:
                encoded_video = base64.b64encode(file_bytes).decode("utf-8")

                width = 480
                height = 360

                st.write("""
                <video width="{}" height="{}" controls>
                    <source src="data:video/mp4;base64,{}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                """.format(width, height, encoded_video), unsafe_allow_html=True)
                # st.video(file_bytes, format="video/mp4")
            else:
                st.error("Error in reading the bytes of the video. Please retry")
            st.button("Upload it to GCP", on_click=lambda: uploadToGCP(
                file_bytes, class_label, 'u'))
else:
    lock = threading.Lock()
    width = 480
    height = 360
    current_time = int(time.time())
    file_name = f"{current_time}_{class_label}_video_r.mp4"
    img_container = {"img": None}

    # Callback function that is called every time a new video frame is received
    def video_frame_callback(frame):
        img = frame.to_ndarray(format="bgr24")
        with lock:
            img_container["img"] = img
        return frame

    # Create the WebRTC streamer
    ctx = webrtc_streamer(
        key="example", video_frame_callback=video_frame_callback, rtc_configuration={
        "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}, ]
    }, media_stream_constraints={"video": True, "audio": False},
    async_processing=False,)
    print('ctx state previous', ctx.state.playing)
    fig_place = st.empty()
    i = 0
    totalCount = 120
    counter = 0
    while ctx.state.playing:
        if("is_recording" not in st.session_state.keys()):
            st.session_state["is_recording"] = False
            print('is_recording', st.session_state)
        if ctx.state.playing:
            counter+=1
            if not st.session_state.is_recording:
                # Create the output file and add the video stream
                st.session_state.video_file = BytesIO()
                st.session_state.writer = av.open(st.session_state.video_file, "w", format="mp4")
                st.session_state.video_stream = st.session_state.writer.add_stream("h264", str(25))
                st.session_state.video_stream.pix_fmt = 'yuv420p'   # Select yuv420p pixel format for wider compatibility.
                st.session_state.video_stream.options = {'crf': '17'}  
                st.session_state.video_stream.width = width
                st.session_state.video_stream.height = height
                st.session_state.is_recording = True
                print("Recording started")
        if("is_recording" not in st.session_state.keys()):
            st.session_state["is_recording"] = False
            print('is_recording', st.session_state)
        if st.session_state.is_recording:
            with lock:
                img = img_container["img"]
            if img is None:
                continue
            if(counter % 60 == 0):
                i += 1
            with fig_place.container():
                st.write(("#" * min(0, i-(4*i))))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = av.VideoFrame.from_ndarray(img, format='rgb24')
            if(counter % 120 == 0):
                packet = st.session_state.video_stream.encode(img)
                if packet:
                    st.session_state.writer.mux(packet)
    else:
        if("is_recording" not in st.session_state.keys()):
            st.session_state["is_recording"] = False
        if st.session_state.is_recording:
            packet = st.session_state.video_stream.encode(None)
            st.session_state.writer.mux(packet)
            st.session_state.writer.close()
            st.session_state.is_recording = False
            st.session_state.video_file.seek(0)
            print("Recording stopped and saved to {}".format(file_name))
            if st.session_state.video_file is None:
                st.error("Camera not recorded")
            else:
                if st.session_state.video_file:
                    file_bytes = st.session_state.video_file
                    if file_bytes:
                        encoded_video = base64.b64encode(file_bytes.getvalue()).decode("utf-8")
                        width = 480
                        height = 360

                        st.write("""
                        <video width="{}" height="{}" controls>
                            <source src="data:video/mp4;base64,{}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                        """.format(width, height, encoded_video), unsafe_allow_html=True)
                        # st.video(file_bytes, format="video/mp4")
                    else:
                        st.error(
                            "Error in reading the bytes of the video. Please retry")
                    st.button("Upload it to GCP", on_click=lambda: uploadToGCP(
                        file_bytes.read(), class_label, "r"))
                        
