from unittest.mock import Mock

import pytest

from otterai.otterai import OtterAI, OtterAIException


@pytest.fixture
def otterai_instance():
    return OtterAI()

def test_is_userid_none():
    otter = OtterAI()
    assert otter._is_userid_invalid() is True

def test_is_userid_empty():
    otter = OtterAI()
    otter._userid = ""
    assert otter._is_userid_invalid() is True

def test_is_userid_valid():
    otter = OtterAI()
    otter._userid = "123456"
    assert otter._is_userid_invalid() is False

def test_handle_response_json(otterai_instance):
    # Mock response with JSON data
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"key": "value"}

    result = otterai_instance._handle_response(mock_response)
    assert result["status"] == 200
    assert result["data"] == {"key": "value"}

def test_handle_response_no_json(otterai_instance):
    # Mock response without JSON data
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError  # Simulate no JSON
    mock_response.text = "Some plain text"

    result = otterai_instance._handle_response(mock_response)
    assert result["status"] == 200
    assert result["data"] == {}

def test_handle_response_with_data(otterai_instance):
    # Mock response with additional data passed
    mock_response = Mock()
    mock_response.status_code = 201
    additional_data = {"extra": "info"}

    result = otterai_instance._handle_response(mock_response, data=additional_data)
    assert result["status"] == 201
    assert result["data"] == additional_data