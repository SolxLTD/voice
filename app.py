# app.py
import streamlit as st
import speech_recognition as sr
import threading
import queue
import time
import os

st.set_page_config(page_title="Improved Speech Recognition", layout="centered")

# -----------------------
# Global state
# -----------------------
recognizer = sr.Recognizer()
audio_queue = queue.Queue()   # holds raw audio for processing
bg_listener = None            # background listener stop function
listening = False             # are we listening?
paused = False                # paused state
transcribed_text = ""         # current transcription

# -----------------------
# Helper: transcribe audio with improved error handling
# -----------------------
def transcribe_audio_data(audio_data, api_choice="Google", language="en-US"):
    """
    Accepts an sr.AudioData instance and returns (success, text_or_error_message).
    api_choice: "Google" or "Sphinx" (pocket sphinx).
    language: BCP-47 like "en-US", "fr-FR".
    """
    try:
        if api_choice == "Google":
            # Online: uses Google Web Speech API
            text = recognizer.recognize_google(audio_data, language=language)
            return True, text

        elif api_choice == "Sphinx":
            # Offline: requires pocketsphinx installed
            # pocketsphinx may not be perfect for all languages; Sphinx primarily supports English
            text = recognizer.recognize_sphinx(audio_data, language=language)
            return True, text

        else:
            # placeholder for other providers (IBM, Microsoft, etc.)
            return False, f"API '{api_choice}' not implemented in this demo."

    except sr.UnknownValueError:
        return False, "Speech was unintelligible — try speaking more clearly or increasing microphone volume."
    except sr.RequestError as e:
        # Typically network or the API key / service problem
        return False, f"Could not contact the recognition service ({api_choice}). Technical detail: {e}"
    except Exception as e:
        return False, f"Unexpected error during transcription: {type(e).__name__}: {e}"

# -----------------------
# Background callback for continuous listening
# -----------------------
def background_callback(recognizer, audio):
    """
    This function is called by listen_in_background for each phrase captured.
    It should be non-blocking or it should quickly push audio into a queue for separate processing.
    """
    try:
        audio_queue.put(audio)
    except Exception as e:
        st.error(f"Failed to queue audio for processing: {e}")

# Worker thread: read from audio_queue and transcribe
def worker_process(api_choice, language):
    global transcribed_text
    while listening:
        if paused:
            time.sleep(0.2)
            continue
        try:
            audio = audio_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        success, result = transcribe_audio_data(audio, api_choice=api_choice, language=language)
        if success:
            # append result to transcribed_text
            if transcribed_text:
                transcribed_text += " " + result
            else:
                transcribed_text = result
            # Optionally you can write to a session state if you want Streamlit to rerun loop
            st.session_state["last_transcription"] = transcribed_text
        else:
            # store error messages to session state so UI can display them
            st.session_state["last_error"] = result

# -----------------------
# UI layout
# -----------------------
st.title("🎤 Improved Speech Recognition App")

# API choice
api_choice = st.selectbox("Choose Speech Recognition API", ["Google", "Sphinx"])

# Language selection
language = st.selectbox("Language (BCP-47 codes)", ["en-US", "en-GB", "fr-FR", "es-ES", "de-DE"])

# Buttons and controls
col1, col2, col3 = st.columns([1,1,1])
with col1:
    start_btn = st.button("▶ Start Listening")
with col2:
    pause_btn = st.button("⏸ Pause" if not paused else "▶ Resume")
with col3:
    stop_btn = st.button("■ Stop Listening")

# area for transcription and errors
if "last_transcription" not in st.session_state:
    st.session_state["last_transcription"] = ""
if "last_error" not in st.session_state:
    st.session_state["last_error"] = ""

st.subheader("Transcribed Text")
transcription_area = st.text_area("", value=st.session_state["last_transcription"], height=200, key="trans_area")

if st.session_state.get("last_error"):
    st.error(st.session_state["last_error"])

# Save transcription
if st.button("💾 Save transcription to file"):
    txt = st.session_state.get("last_transcription", "")
    if not txt.strip():
        st.warning("No transcription to save.")
    else:
        fname = f"transcription_{int(time.time())}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(txt)
        st.success(f"Saved transcription to {fname}")
        st.markdown(f"[Download file]({os.path.abspath(fname)})")  # local path; Streamlit may not allow direct local link

# Start listening handler
if start_btn and not listening:
    try:
        # Begin listening in background
        mic = sr.Microphone()
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.0)  # calibrate to ambient noise

        listening = True
        paused = False
        st.session_state["last_error"] = ""
        st.session_state["last_transcription"] = ""
        # start background listener (non-blocking)
        bg_listener = recognizer.listen_in_background(mic, background_callback)
        # start worker thread to process queued audio
        worker = threading.Thread(target=worker_process, args=(api_choice, language), daemon=True)
        worker.start()
        st.success("Started listening (background). Speak whenever you're ready.")
    except Exception as e:
        st.error(f"Failed to start listening: {type(e).__name__}: {e}")

# Pause/resume toggle
if pause_btn:
    if listening:
        paused = not paused
        if paused:
            st.warning("Recognition paused. Click Resume to continue.")
        else:
            st.success("Recognition resumed.")
    else:
        st.info("Not currently listening. Click Start Listening first.")

# Stop listening handler
if stop_btn and listening:
    try:
        # stop background listener
        if bg_listener:
            bg_listener(wait_for_stop=False)  # stop background listening
        listening = False
        paused = False
        st.success("Stopped listening.")
    except Exception as e:
        st.error(f"Failed to stop listening: {type(e).__name__}: {e}")

# Manual single-shot record + transcribe (alternative to background)
if st.button("🎙️ Record 10 seconds (single-shot)"):
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            st.info("Recording for up to 10 seconds...")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)
        success, result = transcribe_audio_data(audio, api_choice=api_choice, language=language)
        if success:
            st.session_state["last_transcription"] += (" " + result) if st.session_state["last_transcription"] else result
            st.success("Transcription (single-shot) added.")
        else:
            st.session_state["last_error"] = result
            st.error(result)
    except Exception as e:
        st.error(f"Microphone record failed: {type(e).__name__}: {e}")

# show final transcription
st.write("### Current transcription")
st.write(st.session_state.get("last_transcription", ""))
