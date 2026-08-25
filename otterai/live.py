"""Live microphone recording for Otter's undocumented web protocol."""

import json
import re
import threading
import time

from .exceptions import OtterAIException


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
BLOCK_SAMPLES = 1_600


def _safe_error(error):
    message = str(error)
    message = re.sub(r"(?i)(token=)[^&\s]+", r"\1[REDACTED]", message)
    message = re.sub(r"eyJ[A-Za-z0-9_.-]+", "[REDACTED]", message)
    return f"{type(error).__name__}: {message}"


def _sounddevice():
    try:
        import sounddevice
    except ImportError as exc:
        raise OtterAIException(
            "live recording requires the 'sounddevice' package"
        ) from exc
    return sounddevice


def _websocket():
    try:
        import websocket
    except ImportError as exc:
        raise OtterAIException(
            "live recording requires the 'websocket-client' package"
        ) from exc
    return websocket


def list_audio_devices():
    """Return input devices in a JSON-serializable form."""
    devices = _sounddevice().query_devices()
    return [
        {
            "id": index,
            "name": device["name"],
            "hostapi": device["hostapi"],
            "max_input_channels": device["max_input_channels"],
            "default_samplerate": device["default_samplerate"],
        }
        for index, device in enumerate(devices)
        if device["max_input_channels"] > 0
    ]


class LiveSpeechRecorder:
    """Stream 16 kHz, mono, signed 16-bit PCM from a microphone to Otter."""

    def __init__(
        self,
        otter,
        device=None,
        title=None,
        folder_id=None,
        event_id=None,
        calendar_meeting_id=None,
        meeting_otid=None,
        language="en",
        block_samples=BLOCK_SAMPLES,
        ack_timeout=20,
    ):
        self.otter = otter
        self.device = device
        self.title = title
        self.folder_id = folder_id
        self.event_id = event_id
        self.calendar_meeting_id = calendar_meeting_id
        self.meeting_otid = meeting_otid
        self.language = language
        self.block_samples = block_samples
        self.ack_timeout = ack_timeout

        self.start_time = None
        self.end_time = None
        self.samples = 0
        self.acknowledged_samples = 0
        self.speech_id = None
        self.otid = None
        self.response = None
        self.audio_overflows = 0

        self._socket = None
        self._stream = None
        self._audio_thread = None
        self._receiver_thread = None
        self._stop_requested = threading.Event()
        self._ack_event = threading.Event()
        self._lock = threading.Lock()
        self._error = None

    @property
    def is_recording(self):
        return self._stream is not None and not self._stop_requested.is_set()

    def start(self):
        """Create the speech, connect its socket, and start microphone capture."""
        if self.is_recording:
            raise OtterAIException("recording is already active")

        self.start_time = int(time.time())
        result = self.otter.speech_start(
            title=self.title,
            folder_id=self.folder_id,
            event_id=self.event_id,
            calendar_meeting_id=self.calendar_meeting_id,
            meeting_otid=self.meeting_otid,
            language=self.language,
            start_time=self.start_time,
        )
        data = result.get("data", {})
        if result.get("status") != 200 or data.get("status") != "OK":
            raise OtterAIException(
                f"speech_start failed with HTTP status {result.get('status')}"
            )

        self.speech_id = data["speech_id"]
        self.otid = data["otid"]
        ws_url = data["ws_url"]

        try:
            websocket = _websocket()
            self._socket = websocket.create_connection(
                ws_url,
                origin="https://otter.ai",
                timeout=5,
                enable_multithread=True,
            )
            self._socket.send(
                json.dumps(
                    {"action": "start", "speech_id": self.speech_id, "offset": 0},
                    separators=(",", ":"),
                )
            )

            self._stop_requested.clear()
            self._ack_event.clear()
            self._receiver_thread = threading.Thread(
                target=self._receive_messages,
                name="otter-live-receiver",
                daemon=True,
            )
            self._receiver_thread.start()

            sounddevice = _sounddevice()
            self._stream = sounddevice.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=self.block_samples,
                device=self.device,
                channels=CHANNELS,
                dtype="int16",
            )
            self._stream.start()
            self._audio_thread = threading.Thread(
                target=self._stream_audio,
                name="otter-live-audio",
                daemon=True,
            )
            self._audio_thread.start()
        except Exception as exc:
            self._stop_requested.set()
            if self._socket is not None:
                self._socket.close()
            self.otter.stop_speech(
                otid=self.otid,
                start_time=self.start_time,
                samples=self.samples,
            )
            self._socket = None
            raise OtterAIException(
                f"unable to start live recording: {_safe_error(exc)}"
            ) from exc
        return self

    def _stream_audio(self):
        try:
            while not self._stop_requested.is_set():
                audio, overflowed = self._stream.read(self.block_samples)
                if overflowed:
                    self.audio_overflows += 1
                payload = bytes(audio)
                if not payload:
                    continue
                self._socket.send_binary(payload)
                with self._lock:
                    self.samples += len(payload) // SAMPLE_WIDTH
        except Exception as exc:
            if not self._stop_requested.is_set():
                self._error = exc
                self._stop_requested.set()

    def _receive_messages(self):
        websocket = _websocket()
        try:
            while self._socket and self._socket.connected:
                try:
                    message = self._socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not message:
                    continue
                if isinstance(message, bytes):
                    continue
                try:
                    event = json.loads(message)
                except (TypeError, ValueError):
                    continue
                if event.get("type") != "ack":
                    continue
                result = event.get("result", {})
                acknowledged = result.get("processed_offset")
                if acknowledged is not None:
                    self.acknowledged_samples = int(acknowledged) + 1
                    with self._lock:
                        if self.acknowledged_samples >= self.samples:
                            self._ack_event.set()
        except Exception as exc:
            if not self._stop_requested.is_set():
                self._error = exc

    def stop(self):
        """Stop capture, flush the WebSocket, and finish the Otter speech."""
        if self.start_time is None or self._socket is None:
            raise OtterAIException("recording is not active")

        self._stop_requested.set()
        if self._stream is not None:
            try:
                self._stream.abort()
            finally:
                self._stream.close()
        if self._audio_thread is not None:
            self._audio_thread.join(timeout=2)

        self._socket.send(
            json.dumps(
                {"action": "stop", "speech_id": self.speech_id},
                separators=(",", ":"),
            )
        )
        self._ack_event.wait(self.ack_timeout)
        self.end_time = int(time.time())
        self._socket.close()

        self.response = self.otter.stop_speech(
            otid=self.otid,
            start_time=self.start_time,
            end_time=self.end_time,
            samples=self.samples,
        )
        self._stream = None
        self._socket = None

        if self._error is not None:
            raise OtterAIException(f"live recording failed: {_safe_error(self._error)}")
        return self.response

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        if self._socket is not None:
            self.stop()
