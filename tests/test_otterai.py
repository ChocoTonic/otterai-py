import os
from unittest.mock import Mock

import pytest
from dotenv import load_dotenv

from otterai.otterai import OtterAI, OtterAIException
from tests.helpers import dump_json_response

load_dotenv()


@pytest.fixture
def logged_in_otter():
    username = os.getenv("OTTERAI_USERNAME")
    password = os.getenv("OTTERAI_PASSWORD")
    if not username or not password:
        pytest.skip("OTTERAI_USERNAME and OTTERAI_PASSWORD are not configured")
    otter = OtterAI()
    otter.login(username, password)
    return otter


def test_dump_json_dummy_input_dict_expected_file():
    dummy_response = {"foo": "bar", "baz": [1, 2, 3]}
    dump_json_response(dummy_response, "dummy.json")


def test_init_no_userid_expected_invalid():
    otter = OtterAI()
    assert otter._userid is None
    assert otter._is_userid_invalid() is True


def test_is_userid_invalid_no_userid_expected_true():
    otter = OtterAI()
    assert otter._is_userid_invalid() is True


def test_is_userid_invalid_valid_userid_expected_false():
    otter = OtterAI()
    otter._userid = "validid"
    assert otter._is_userid_invalid() is False


def test_login_valid_credentials_expected_userid(logged_in_otter):
    assert logged_in_otter._userid is not None


def test_get_user_valid_session_expected_email(logged_in_otter):
    username = os.getenv("OTTERAI_USERNAME")
    response = logged_in_otter.get_user()
    assert response["data"]["user"]["email"] == username


def test_get_speakers_valid_session_expected_200(logged_in_otter):
    response = logged_in_otter.get_speakers()
    assert response["status"] == 200


def test_get_speeches_valid_session_expected_200(logged_in_otter):
    response = logged_in_otter.get_speeches()
    assert response["status"] == 200


def test_list_unsorted_speeches_uses_nofolder_source():
    otter = OtterAI()
    otter.get_speeches = Mock(return_value={"status": 200, "data": {}})

    response = otter.list_unsorted_speeches(page_size=20, last_load_ts=123)

    assert response["status"] == 200
    otter.get_speeches.assert_called_once_with(
        page_size=20,
        source="nofolder",
        last_load_ts=123,
        modified_after=None,
    )


def test_move_speeches_to_folder_posts_library_endpoint():
    otter = OtterAI()
    otter._userid = 42
    otter._cookies = {"csrftoken": "csrf"}
    response = Mock(status_code=200)
    response.json.return_value = {"status": "OK"}
    otter._session.post = Mock(return_value=response)

    result = otter.move_speeches_to_folder(123, ["one", "two"])

    assert result["status"] == 200
    otter._session.post.assert_called_once_with(
        OtterAI.API_BASE_URL + "add_folder_speeches",
        params={"userid": 42, "folder_id": 123},
        headers={
            "origin": "https://otter.ai",
            "referer": "https://otter.ai/folder/123",
            "x-csrftoken": "csrf",
        },
        files={"speech_otid_list": (None, "one,two")},
    )


def test_remove_speeches_from_folder_posts_library_endpoint():
    otter = OtterAI()
    otter._userid = 42
    otter._cookies = {"csrftoken": "csrf"}
    response = Mock(status_code=200)
    response.json.return_value = {"status": "OK"}
    otter._session.post = Mock(return_value=response)

    result = otter.remove_speeches_from_folder(123, "one")

    assert result["status"] == 200
    otter._session.post.assert_called_once_with(
        OtterAI.API_BASE_URL + "remove_folder_speeches",
        params={"userid": 42, "folder_id": 123},
        headers={
            "origin": "https://otter.ai",
            "referer": "https://otter.ai/folder/123",
            "x-csrftoken": "csrf",
        },
        files={"otid_list": (None, "one")},
    )


def test_move_speeches_to_folder_rejects_empty_ids():
    otter = OtterAI()
    otter._userid = 42

    with pytest.raises(ValueError, match="speech_ids"):
        otter.move_speeches_to_folder(123, [])


def test_get_notification_settings_valid_session_expected_200_data(logged_in_otter):
    response = logged_in_otter.get_notification_settings()
    assert response["status"] == 200
    assert "data" in response


def test_get_folders_valid_session_expected_200_data(logged_in_otter):
    response = logged_in_otter.get_folders()
    assert response["status"] == 200
    assert "data" in response


def test_get_speakers_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.get_speakers()


def test_get_speeches_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.get_speeches()


def test_get_speech_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.get_speech("dummyid")


def test_upload_speech_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.upload_speech("dummy.mp4")


def test_download_speech_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.download_speech("dummyid")


def test_move_to_trash_bin_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.move_to_trash_bin("dummyid")


def test_create_speaker_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.create_speaker("dummy_speaker")


def test_list_groups_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.list_groups()


def test_get_folders_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.get_folders()


def test_stop_speech_no_userid_expected_exception():
    otter = OtterAI()
    with pytest.raises(OtterAIException, match="userid is invalid"):
        otter.stop_speech("dummy-otid", 1, 16000, end_time=2)
