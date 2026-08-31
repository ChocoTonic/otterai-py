# otterai-py

Unofficial Python API for [otter.ai](http://otter.ai)

**Note:** This project is a fork of [gmchad/otterai-api](https://github.com/gmchad/otterai-api), as the original repository appears to be abandoned. Improvements and updates will be maintained here.

## Contents

-   [Installation](#installation)
-   [Setup](#setup)
-   [APIs](#apis)
    -   [User](#user)
    -   [Speeches](#speeches)
    -   [Speakers](#speakers)
    -   [Folders](#folders)
    -   [Calendar](#calendar)
    -   [Live recording](#live-recording)
    -   [Groups](#groups)
    -   [Notifications](#notifications)
-   [Exceptions](#exceptions)
-   [Contribution](#contribution)

## Installation

Install via PyPI:

```bash
pip install otterai-py
```

Alternatively, install the development version:

```bash
pip install .[dev]
```

or in a virtual environment:

```bash
python3 -m venv env
source env/bin/activate
pip install .[dev]
```

## Setup

```python
from otterai import OtterAI
otter = OtterAI()
otter.login('USERNAME', 'PASSWORD')
```

## APIs

### User

Get user-specific data:

```python
otter.get_user()
```

### Speeches

Get all speeches.

**Optional parameters**: `folder`, `page_size`, `source`

```python
otter.get_speeches()
```

Get a speech by ID:

```python
otter.get_speech(OTID)
```

Query a speech:

```python
otter.query_speech(QUERY, OTID)
```

Upload a speech.

**Optional parameters**: `content_type` (default: `audio/mp4`)

```python
otter.upload_speech(FILE_NAME)
```

Download a speech.

**Optional parameters**: `filename` (default: `id`), `format` (default: all available formats (`txt,pdf,mp3,docx,srt`) as a zip file)

```python
otter.download_speech(OTID, FILE_NAME)
```

Move a speech to the trash:

```python
otter.move_to_trash_bin(OTID)
```

Set speech title:

```python
otter.set_speech_title(OTID, TITLE)
```

### Live recording

Live recording uses Otter's undocumented web API and may change without notice.
The recorder captures 16 kHz, mono, signed 16-bit PCM and streams it to the
short-lived WebSocket URL returned by `speech_start`.

```python
from otterai import LiveSpeechRecorder

recorder = LiveSpeechRecorder(
    otter,
    device=7,
    folder_id=2133370,
    title="Manual recording",
).start()

# Later:
recorder.stop()
```

Use an Otter calendar meeting by passing its numeric `calendar_meeting_id` and
its `meeting_otid` from `get_current_calendar_meetings()`.

The lower-level API methods are also available:

```python
started = otter.speech_start(folder_id=FOLDER_ID, event_id=EVENT_ID)
otter.stop_speech(OTID, START_TIME, SAMPLE_COUNT)
```

Do not log or persist the `token` or `ws_url` returned by `speech_start`.

### Speakers

Get all speakers:

```python
otter.get_speakers()
```

Create a speaker:

```python
otter.create_speaker(SPEAKER_NAME)
```

### Folders

Get all folders:

```python
otter.get_folders()
```

List one page of conversations that are not assigned to a folder:

```python
otter.list_unsorted_speeches(page_size=45)
```

Assign or move conversations to a folder:

```python
otter.move_speeches_to_folder(FOLDER_ID, [OTID])
```

Remove conversations from a folder and return them to Unsorted:

```python
otter.remove_speeches_from_folder(FOLDER_ID, [OTID])
```

### Calendar

List meetings synced through Otter's Google or Microsoft calendar integration:

```python
otter.get_current_calendar_meetings()
```

### Command line and Stream Deck

Set credentials in the environment, or in the repository's ignored `.env`
file, rather than placing a password in a Stream Deck command:

```powershell
$env:OTTERAI_USERNAME = "you@example.com"
$env:OTTERAI_PASSWORD = "..."
```

```dotenv
OTTERAI_USERNAME="you@example.com"
OTTERAI_PASSWORD="..."
```

List microphones and synced calendar meetings:

```powershell
otterai devices
otterai calendar
```

Record in the foreground until Ctrl+C:

```powershell
otterai record --device 7 --folder-id 2133370 --title "Manual recording"
```

Use separate Start and Stop commands for Stream Deck buttons:

```powershell
otterai start --device 7 --folder-id 2133370 --title "Manual recording"
otterai status
otterai stop
```

To associate a recording with a synced event, add `--calendar-meeting-id` and
`--meeting-otid` using values returned by `otterai calendar`.

Background state and logs are stored in `%LOCALAPPDATA%\otterai-py` on Windows.

### Groups

Get all groups:

```python
otter.list_groups()
```

### Notifications

Get notification settings:

```python
otter.get_notification_settings()
```

## Exceptions

```python
from otterai import OtterAIException

try:
    ...
except OtterAIException as e:
    ...
```

## Contribution

To contribute to this project, follow these steps:

1. Create a `.env` file in the root directory with the following content:

    ```plaintext
    OTTERAI_USERNAME=""
    OTTERAI_PASSWORD=""
    TEST_OTTERAI_SPEECH_OTID=""
    ```

    - Replace `OTTERAI_USERNAME` and `OTTERAI_PASSWORD` with your Otter.ai credentials.
    - Replace `TEST_OTTERAI_SPEECH_OTID` with the ID of a speech you create on Otter.ai. This is required for the tests to pass.

2. Set up your development environment and install dependencies:

    ```bash
    make init-dev
    ```

3. To format the codebase, run:

    ```bash
    make format
    ```

4. To run the tests and generate coverage reports, use:

    ```bash
    make test
    ```

5. Ensure all tests pass and update/add tests as needed if you modify or add functionality.

6. Submit a pull request with a clear description of your changes.
