import json
import secrets
import time
import xml.etree.ElementTree as ET
import uuid

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

from .exceptions import OtterAIException


class OtterAI:
    API_BASE_URL = "https://otter.ai/forward/api/v1/"
    S3_BASE_URL = "https://s3.us-west-2.amazonaws.com/"

    def __init__(self):
        self._session = requests.Session()
        self._userid = None
        self._cookies = None

    def _is_userid_invalid(self):
        if not self._userid:
            return True
        return False

    def _handle_response(self, response, data=None):
        if data:
            return {"status": response.status_code, "data": data}
        try:
            return {"status": response.status_code, "data": response.json()}
        except ValueError:
            return {"status": response.status_code, "data": {}}

    def _csrf_headers(self, referer="https://otter.ai/"):
        if not self._cookies or "csrftoken" not in self._cookies:
            raise OtterAIException("csrftoken is unavailable; log in first")
        return {
            "origin": "https://otter.ai",
            "referer": referer,
            "x-csrftoken": self._cookies["csrftoken"],
        }

    def login(self, username, password):
        auth_url = OtterAI.API_BASE_URL + "login"

        payload = {"username": username}

        self._session.auth = (username, password)

        response = self._session.get(auth_url, params=payload)

        if response.status_code != requests.codes.ok:
            return self._handle_response(response)

        self._userid = response.json()["userid"]
        self._cookies = response.cookies.get_dict()

        return self._handle_response(response)

    def get_user(self):
        user_url = OtterAI.API_BASE_URL + "user"

        response = self._session.get(user_url)

        return self._handle_response(response)

    def get_speakers(self):
        speakers_url = OtterAI.API_BASE_URL + "speakers"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}

        response = self._session.get(speakers_url, params=payload)

        return self._handle_response(response)

    def get_speeches(
        self,
        folder=0,
        page_size=45,
        source="owned",
        last_load_ts=None,
        modified_after=None,
    ):
        speeches_url = OtterAI.API_BASE_URL + "speeches"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {
            "userid": self._userid,
            "folder": folder,
            "page_size": page_size,
            "source": source,
        }
        if last_load_ts is not None:
            payload["last_load_ts"] = last_load_ts
        if modified_after is not None:
            payload["modified_after"] = modified_after

        response = self._session.get(speeches_url, params=payload)

        return self._handle_response(response)

    def list_unsorted_speeches(
        self, page_size=45, last_load_ts=None, modified_after=None
    ):
        """Return one page of owned speeches that are not assigned to a folder."""
        return self.get_speeches(
            page_size=page_size,
            source="nofolder",
            last_load_ts=last_load_ts,
            modified_after=modified_after,
        )

    def get_speech(self, speech_id):
        speech_url = OtterAI.API_BASE_URL + "speech"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid, "otid": speech_id}

        response = self._session.get(speech_url, params=payload)

        return self._handle_response(response)

    def query_speech(self, query, speech_id, size=500):
        query_speech_url = OtterAI.API_BASE_URL + "advanced_search"

        payload = {"query": query, "size": size, "otid": speech_id}

        response = self._session.get(query_speech_url, params=payload)

        return self._handle_response(response)

    def upload_speech(self, file_name, content_type="audio/mp4"):
        speech_upload_params_url = OtterAI.API_BASE_URL + "speech_upload_params"
        speech_upload_prod_url = OtterAI.S3_BASE_URL + "speech-upload-prod"
        finish_speech_upload = OtterAI.API_BASE_URL + "finish_speech_upload"

        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}
        response = self._session.get(speech_upload_params_url, params=payload)

        if response.status_code != requests.codes.ok:
            return self._handle_response(response)

        response_json = response.json()
        params_data = response_json["data"]

        prep_req = requests.Request("OPTIONS", speech_upload_prod_url).prepare()
        prep_req.headers["Accept"] = "*/*"
        prep_req.headers["Connection"] = "keep-alive"
        prep_req.headers["Origin"] = "https://otter.ai"
        prep_req.headers["Referer"] = "https://otter.ai/"
        prep_req.headers["Access-Control-Request-Method"] = "POST"

        response = self._session.send(prep_req)

        if response.status_code != requests.codes.ok:
            return self._handle_response(response)

        # TODO: test for large files (this should stream)
        fields = {}
        params_data["success_action_status"] = str(params_data["success_action_status"])
        del params_data["form_action"]
        fields.update(params_data)
        fields["file"] = (file_name, open(file_name, mode="rb"), content_type)
        multipart_data = MultipartEncoder(fields=fields)

        response = requests.post(
            speech_upload_prod_url,
            data=multipart_data,
            headers={"Content-Type": multipart_data.content_type},
        )

        if response.status_code != 201:
            return self._handle_response(response)

        xmltree = ET.ElementTree(ET.fromstring(response.text))
        xmlroot = xmltree.getroot()
        # TODO: clean this up
        location = xmlroot[0].text
        bucket = xmlroot[1].text
        key = xmlroot[2].text

        payload = {
            "bucket": bucket,
            "key": key,
            "language": "en",
            "country": "us",
            "userid": self._userid,
        }
        response = self._session.get(finish_speech_upload, params=payload)

        return self._handle_response(response)

    def download_speech(self, speech_id, name=None, fileformat="txt,pdf,mp3,docx,srt"):
        download_speech_url = OtterAI.API_BASE_URL + "bulk_export"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}

        data = {"formats": fileformat, "speech_otid_list": [speech_id]}
        headers = {
            "x-csrftoken": self._cookies["csrftoken"],
            "referer": "https://otter.ai/",
        }
        response = self._session.post(
            download_speech_url, params=payload, headers=headers, data=data
        )

        filename = (
            (name if not name == None else speech_id)
            + "."
            + ("zip" if "," in fileformat else fileformat)
        )
        if response.ok:
            with open(filename, "wb") as f:
                f.write(response.content)
        else:
            raise OtterAIException(
                f"Got response status {response.status_code} when attempting to download {speech_id}"
            )
        return self._handle_response(response, data={"filename": filename})

    def move_to_trash_bin(self, speech_id):
        move_to_trash_bin_url = OtterAI.API_BASE_URL + "move_to_trash_bin"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}

        data = {"otid": speech_id}
        headers = {"x-csrftoken": self._cookies["csrftoken"]}
        response = self._session.post(
            move_to_trash_bin_url, params=payload, headers=headers, data=data
        )

        return self._handle_response(response)

    def create_speaker(self, speaker_name):
        create_speaker_url = OtterAI.API_BASE_URL + "create_speaker"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}

        data = {"speaker_name": speaker_name}
        headers = {"x-csrftoken": self._cookies["csrftoken"]}
        response = self._session.post(
            create_speaker_url, params=payload, headers=headers, data=data
        )

        return self._handle_response(response)

    def get_notification_settings(self):
        notification_settings_url = OtterAI.API_BASE_URL + "get_notification_settings"
        response = self._session.get(notification_settings_url)

        return self._handle_response(response)

    def list_groups(self):
        list_groups_url = OtterAI.API_BASE_URL + "list_groups"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}

        response = self._session.get(list_groups_url, params=payload)

        return self._handle_response(response)

    def get_folders(self):
        folders_url = OtterAI.API_BASE_URL + "folders"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {"userid": self._userid}

        response = self._session.get(folders_url, params=payload)

        return self._handle_response(response)

    def get_current_calendar_meetings(self):
        """Return meetings synced from the user's connected calendar."""
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        response = self._session.get(
            OtterAI.API_BASE_URL + "get_current_calendar_meetings",
            params={"appid": "otter-web"},
        )
        return self._handle_response(response)

    def list_folder_speeches(
        self, folder_id, page_size=12, last_load_speech_id=None, speech_metadata=True
    ):
        """
        Fetch speeches in a folder with optional pagination and metadata.
        """
        list_folder_speeches_url = OtterAI.API_BASE_URL + "list_folder_speeches"
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        payload = {
            "userid": self._userid,
            "folder_id": folder_id,
            "page_size": page_size,
            "speech_metadata": str(speech_metadata).lower(),
        }
        if last_load_speech_id:
            payload["last_load_speech_id"] = last_load_speech_id

        response = self._session.get(list_folder_speeches_url, params=payload)
        return self._handle_response(response)

    def add_speeches_to_folder(self, folder_id, speech_ids):
        """Assign one or more speeches to a folder.

        Otter permits one folder per speech, so assigning a speech that is already
        filed moves it to the destination folder.
        """
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")
        speech_ids = self._validate_speech_ids(speech_ids)
        response = self._session.post(
            OtterAI.API_BASE_URL + "add_folder_speeches",
            params={"userid": self._userid, "folder_id": int(folder_id)},
            headers=self._csrf_headers(f"https://otter.ai/folder/{folder_id}"),
            files={"speech_otid_list": (None, ",".join(speech_ids))},
        )
        return self._handle_response(response)

    def move_speeches_to_folder(self, folder_id, speech_ids):
        """Move one or more speeches to a folder."""
        return self.add_speeches_to_folder(folder_id, speech_ids)

    def remove_speeches_from_folder(self, folder_id, speech_ids):
        """Remove one or more speeches from a folder, returning them to Unsorted."""
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")
        speech_ids = self._validate_speech_ids(speech_ids)
        response = self._session.post(
            OtterAI.API_BASE_URL + "remove_folder_speeches",
            params={"userid": self._userid, "folder_id": int(folder_id)},
            headers=self._csrf_headers(f"https://otter.ai/folder/{folder_id}"),
            files={"otid_list": (None, ",".join(speech_ids))},
        )
        return self._handle_response(response)

    @staticmethod
    def _validate_speech_ids(speech_ids):
        if isinstance(speech_ids, str):
            speech_ids = [speech_ids]
        speech_ids = [str(speech_id).strip() for speech_id in speech_ids]
        if not speech_ids or any(not speech_id for speech_id in speech_ids):
            raise ValueError("speech_ids must contain at least one non-empty ID")
        return speech_ids

    def speech_start(
        self,
        title=None,
        folder_id=None,
        event_id=None,
        calendar_meeting_id=None,
        group_id=None,
        language="en",
        country=None,
        meeting_otid=None,
        start_time=None,
        otid=None,
        ignore_event=None,
    ):
        """Create a live speech and return its WebSocket credentials.

        This is an undocumented Otter web endpoint. The returned ``ws_url`` is
        short-lived and must never be persisted or logged.
        """
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        start_time = int(time.time()) if start_time is None else int(start_time)
        otid = secrets.token_urlsafe(20) if otid is None else otid
        if ignore_event is None:
            ignore_event = event_id is None and calendar_meeting_id is None

        payload = {
            "appid": "otter-web",
            "cv": "3.133.0",
            "uuid": str(uuid.uuid4()),
            "network": "WIFI",
            "language": language,
            "userid": self._userid,
            "start_time": start_time,
            "ignore_event": str(bool(ignore_event)).lower(),
            "otid": otid,
        }
        optional = {
            "title": title,
            "folder_id": folder_id,
            "event_id": event_id,
            "calendar_meeting_id": calendar_meeting_id,
            "group_id": group_id,
            "country": country,
            "meeting_otid": meeting_otid,
        }
        payload.update(
            {key: value for key, value in optional.items() if value is not None}
        )

        referer = (
            f"https://otter.ai/folder/{folder_id}"
            if folder_id is not None
            else "https://otter.ai/home"
        )
        response = self._session.post(
            OtterAI.API_BASE_URL + "speech_start",
            params=payload,
            headers=self._csrf_headers(referer),
        )
        return self._handle_response(response)

    def stop_speech(self, otid, start_time, samples, end_time=None):
        """Finish a live speech after all PCM samples have been acknowledged."""
        if self._is_userid_invalid():
            raise OtterAIException("userid is invalid")

        end_time = int(time.time()) if end_time is None else int(end_time)
        payload = {
            "appid": "otter-web",
            "userid": self._userid,
            "otid": otid,
            "start_time": int(start_time),
            "end_time": end_time,
            "samples": int(samples),
        }
        response = self._session.post(
            OtterAI.API_BASE_URL + "speech_finish",
            params=payload,
            headers=self._csrf_headers("https://otter.ai/recording"),
        )
        return self._handle_response(response)
