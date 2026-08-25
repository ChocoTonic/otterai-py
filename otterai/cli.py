"""Command-line controls suitable for Stream Deck buttons."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from dotenv import load_dotenv

from .exceptions import OtterAIException
from .live import LiveSpeechRecorder, list_audio_devices
from .otterai import OtterAI


def _state_directory():
    configured = os.getenv("OTTERAI_STATE_DIR")
    if configured:
        return Path(configured)
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / ".local" / "state")
    return Path(base) / "otterai-py"


def _paths():
    directory = _state_directory()
    return {
        "directory": directory,
        "state": directory / "recording.json",
        "stop": directory / "stop.requested",
        "log": directory / "recording.log",
    }


def _write_state(**values):
    paths = _paths()
    paths["directory"].mkdir(parents=True, exist_ok=True)
    temporary = paths["state"].with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    temporary.replace(paths["state"])


def _read_state():
    try:
        return json.loads(_paths()["state"].read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": "idle"}


def _pid_running(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def _device(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _login():
    load_dotenv()
    username = os.getenv("OTTERAI_USERNAME")
    password = os.getenv("OTTERAI_PASSWORD")
    if not username or not password:
        raise OtterAIException(
            "set OTTERAI_USERNAME and OTTERAI_PASSWORD in the environment"
        )
    otter = OtterAI()
    response = otter.login(username, password)
    if response.get("status") != 200:
        raise OtterAIException(
            f"Otter login failed with HTTP status {response.get('status')}"
        )
    return otter


def _recorder(args):
    return LiveSpeechRecorder(
        _login(),
        device=_device(args.device) if args.device is not None else None,
        title=args.title,
        folder_id=args.folder_id,
        event_id=args.event_id,
        calendar_meeting_id=args.calendar_meeting_id,
        meeting_otid=args.meeting_otid,
        language=args.language,
    )


def command_devices(_args):
    for device in list_audio_devices():
        print(
            f"{device['id']:>3}  {device['name']} "
            f"({device['max_input_channels']} in, "
            f"{device['default_samplerate']:.0f} Hz)"
        )
    return 0


def command_calendar(_args):
    response = _login().get_current_calendar_meetings()
    if response.get("status") != 200:
        raise OtterAIException(
            f"calendar lookup failed with HTTP status {response.get('status')}"
        )
    meetings = response.get("data", {}).get("calendar_meetings", [])
    for meeting in meetings:
        start = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(int(meeting["start_ts"]))
        )
        print(
            f"calendar_meeting_id={meeting['id']}  {start}  {meeting['title']} "
            f"meeting_otid={meeting.get('meeting_otid', '')}"
        )
    return 0


def command_record(args):
    recorder = _recorder(args).start()
    print(
        f"Recording started: otid={recorder.otid}. " "Press Ctrl+C to stop and finish."
    )
    deadline = time.monotonic() + args.duration if args.duration else None
    try:
        while deadline is None or time.monotonic() < deadline:
            if recorder._error is not None:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    response = recorder.stop()
    if response.get("status") != 200:
        raise OtterAIException(
            f"speech_finish failed with HTTP status {response.get('status')}"
        )
    print(f"Recording finished: otid={recorder.otid}, samples={recorder.samples}")
    return 0


def _worker(args):
    paths = _paths()
    paths["directory"].mkdir(parents=True, exist_ok=True)
    paths["stop"].unlink(missing_ok=True)
    recorder = None

    def request_stop(_signum=None, _frame=None):
        paths["stop"].touch()

    signal.signal(signal.SIGTERM, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)

    try:
        _write_state(status="starting", pid=os.getpid())
        recorder = _recorder(args).start()
        _write_state(
            status="recording",
            pid=os.getpid(),
            otid=recorder.otid,
            speech_id=recorder.speech_id,
            started_at=recorder.start_time,
            folder_id=args.folder_id,
            device=args.device,
        )
        while not paths["stop"].exists():
            if recorder._error is not None:
                raise recorder._error
            time.sleep(0.2)
        response = recorder.stop()
        if response.get("status") != 200:
            raise OtterAIException(
                f"speech_finish failed with HTTP status {response.get('status')}"
            )
        _write_state(
            status="finished",
            pid=os.getpid(),
            otid=recorder.otid,
            samples=recorder.samples,
            ended_at=recorder.end_time,
        )
        return 0
    except Exception as exc:
        _write_state(status="error", pid=os.getpid(), error=str(exc))
        return 1
    finally:
        paths["stop"].unlink(missing_ok=True)


def command_start(args):
    state = _read_state()
    if state.get("status") in {"starting", "recording"} and _pid_running(
        state.get("pid")
    ):
        raise OtterAIException(
            f"a recording is already {state['status']} (pid {state.get('pid')})"
        )

    paths = _paths()
    paths["directory"].mkdir(parents=True, exist_ok=True)
    paths["stop"].unlink(missing_ok=True)
    command = [sys.executable, "-m", "otterai.cli", "_worker"]
    for name in (
        "device",
        "title",
        "folder_id",
        "event_id",
        "calendar_meeting_id",
        "meeting_otid",
        "language",
    ):
        value = getattr(args, name)
        if value is not None:
            command.extend(["--" + name.replace("_", "-"), str(value)])

    log_handle = paths["log"].open("a", encoding="utf-8")
    popen_options = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "cwd": os.getcwd(),
    }
    if os.name == "nt":
        popen_options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        popen_options["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **popen_options)
    finally:
        log_handle.close()

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = _read_state()
        if state.get("status") == "recording":
            print(f"Recording started: pid={process.pid}, otid={state.get('otid')}")
            return 0
        if state.get("status") == "error":
            raise OtterAIException(state.get("error", "recording failed to start"))
        if process.poll() is not None:
            break
        time.sleep(0.2)
    raise OtterAIException(f"recording did not start; see {paths['log']}")


def command_stop(_args):
    state = _read_state()
    if state.get("status") not in {"starting", "recording"}:
        raise OtterAIException("no recording is active")
    if not _pid_running(state.get("pid")):
        raise OtterAIException("recording process is no longer running")
    paths = _paths()
    paths["stop"].touch()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = _read_state()
        if state.get("status") == "finished":
            print(
                f"Recording finished: otid={state.get('otid')}, "
                f"samples={state.get('samples')}"
            )
            return 0
        if state.get("status") == "error":
            raise OtterAIException(state.get("error", "recording failed to stop"))
        time.sleep(0.2)
    raise OtterAIException("timed out waiting for the recording to stop")


def command_status(_args):
    print(json.dumps(_read_state(), indent=2))
    return 0


def _add_recording_arguments(parser, include_duration=False):
    parser.add_argument("--device", help="input device ID or name")
    parser.add_argument("--folder-id", type=int)
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--calendar-meeting-id")
    parser.add_argument("--meeting-otid")
    parser.add_argument("--title")
    parser.add_argument("--language", default="en")
    if include_duration:
        parser.add_argument("--duration", type=float, help="seconds to record")


def build_parser():
    parser = argparse.ArgumentParser(prog="otterai")
    commands = parser.add_subparsers(dest="command", required=True)

    devices = commands.add_parser("devices", help="list microphone devices")
    devices.set_defaults(handler=command_devices)

    calendar = commands.add_parser("calendar", help="list synced calendar meetings")
    calendar.set_defaults(handler=command_calendar)

    record = commands.add_parser("record", help="record in the foreground")
    _add_recording_arguments(record, include_duration=True)
    record.set_defaults(handler=command_record)

    start = commands.add_parser("start", help="start a background recording")
    _add_recording_arguments(start)
    start.set_defaults(handler=command_start)

    stop = commands.add_parser("stop", help="stop the background recording")
    stop.set_defaults(handler=command_stop)

    status = commands.add_parser("status", help="show background recording state")
    status.set_defaults(handler=command_status)

    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    _add_recording_arguments(worker)
    worker.set_defaults(handler=_worker)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except OtterAIException as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
