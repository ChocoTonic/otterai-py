import os
from pprint import pprint

from dotenv import load_dotenv

from otterai.otterai import OtterAI, OtterAIException


def main():
    load_dotenv()

    try:
        otter = OtterAI()

        username = os.getenv("OTTERAI_USERNAME")
        print(f"Username: {username}")
        password = os.getenv("OTTERAI_PASSWORD")
        print(f"Password: ...{password[-4:]}")

        login_response = otter.login(username, password)
        print(f"Login successful: {login_response['status'] == 200}")

        user_info = otter.get_user()
        # print("User info:")
        # pprint(user_info)

        speeches = otter.get_speeches()
        # print("Speeches:")
        # pprint(speeches)
    except OtterAIException as e:
        print(f"An error occurred: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
