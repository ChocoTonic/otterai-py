import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from otterai import OtterAI, OtterAIException
from otterai import live


def response(status_code=200, data=None):
    result = Mock()
    result.status_code = status_code
    result.json.return_value = data or {"status": "OK"}
    return result


def authenticated_otter():
    otter = OtterAI()
    otter._userid = "user-id"
    otter._cookies = {"csrftoken": "csrf-value"}
    otter._session = Mock()
    return otter


def test_speech_start_posts_captured_parameters():
    otter = authenticated_otter()
    otter._session.post.return_value = response(
        data={
            "status": "OK",
            "speech_id": "speech-id",
            "otid": "otid",
            "token": "secret",
            "ws_url": "wss://example.invalid/speech?token=secret",
        }
    )

    result = otter.speech_start(
        title="Test",
        folder_id=123,
        event_id=456,
        calendar_meeting_id="meeting",
        start_time=1000,
        otid="client-otid",
    )

    assert result["status"] == 200
    call = otter._session.post.call_args
    assert call.args[0].endswith("/speech_start")
    assert call.kwargs["params"]["folder_id"] == 123
    assert call.kwargs["params"]["event_id"] == 456
    assert call.kwargs["params"]["calendar_meeting_id"] == "meeting"
    assert call.kwargs["params"]["start_time"] == 1000
    assert call.kwargs["params"]["ignore_event"] == "false"
    assert call.kwargs["headers"]["x-csrftoken"] == "csrf-value"
    assert call.kwargs["headers"]["referer"].endswith("/folder/123")


def test_stop_speech_posts_sample_count():
    otter = authenticated_otter()
    otter._session.post.return_value = response()

    otter.stop_speech("otid", start_time=10, end_time=20, samples=84702)

    call = otter._session.post.call_args
    assert call.args[0].endswith("/speech_finish")
    assert call.kwargs["params"] == {
        "appid": "otter-web",
        "userid": "user-id",
        "otid": "otid",
        "start_time": 10,
        "end_time": 20,
        "samples": 84702,
    }


def test_speech_start_requires_csrf_cookie():
    otter = OtterAI()
    otter._userid = "user-id"
    with pytest.raises(OtterAIException, match="csrftoken"):
        otter.speech_start(start_time=1, otid="otid")


class FakeSocket:
    def __init__(self):
        self.connected = True
        self.sent_text = []
        self.sent_binary = []
        self.stop_sent = False

    def send(self, value):
        self.sent_text.append(json.loads(value))
        self.stop_sent = self.sent_text[-1]["action"] == "stop"

    def send_binary(self, value):
        self.sent_binary.append(value)

    def recv(self):
        if self.stop_sent:
            samples = sum(len(value) for value in self.sent_binary) // 2
            self.stop_sent = False
            return json.dumps(
                {
                    "status": "OK",
                    "type": "ack",
                    "result": {"processed_offset": samples - 1},
                }
            )
        time.sleep(0.001)
        raise FakeTimeout()

    def close(self):
        self.connected = False


class FakeTimeout(Exception):
    pass


class FakeInputStream:
    def __init__(self, **kwargs):
        self.blocksize = kwargs["blocksize"]

    def start(self):
        pass

    def read(self, blocksize):
        time.sleep(0.001)
        return bytes(blocksize * 2), False

    def abort(self):
        pass

    def close(self):
        pass


def test_live_recorder_sends_start_pcm_stop_and_finish(monkeypatch):
    socket = FakeSocket()
    websocket_module = SimpleNamespace(
        create_connection=Mock(return_value=socket),
        WebSocketTimeoutException=FakeTimeout,
    )
    sounddevice_module = SimpleNamespace(RawInputStream=FakeInputStream)
    monkeypatch.setattr(live, "_websocket", lambda: websocket_module)
    monkeypatch.setattr(live, "_sounddevice", lambda: sounddevice_module)

    otter = Mock()
    otter.speech_start.return_value = {
        "status": 200,
        "data": {
            "status": "OK",
            "speech_id": "speech-id",
            "otid": "otid",
            "ws_url": "wss://example.invalid/speech?token=secret",
        },
    }
    otter.stop_speech.return_value = {"status": 200, "data": {"status": "OK"}}

    recorder = live.LiveSpeechRecorder(otter, device=7, folder_id=123).start()
    time.sleep(0.01)
    recorder.stop()

    assert socket.sent_text[0] == {
        "action": "start",
        "speech_id": "speech-id",
        "offset": 0,
    }
    assert socket.sent_text[-1] == {"action": "stop", "speech_id": "speech-id"}
    assert socket.sent_binary
    assert recorder.samples == sum(len(value) for value in socket.sent_binary) // 2
    assert otter.stop_speech.call_args.kwargs["samples"] == recorder.samples
