from unittest.mock import patch, MagicMock
from app_icon import register_notification_identity, APP_ID, APP_NAME, ICON_PATH


def test_notification_identity_uses_current_user_and_existing_icon():
    import winreg
    key = MagicMock()
    with patch("winreg.CreateKeyEx", return_value=key) as create, patch("winreg.SetValueEx") as write:
        register_notification_identity()
    assert create.call_args.args[0] == winreg.HKEY_CURRENT_USER
    assert create.call_args.args[1].endswith(APP_ID)
    values = {call.args[1]: call.args[4] for call in write.call_args_list}
    assert values == {"DisplayName": APP_NAME, "IconUri": str(ICON_PATH)}
    assert ICON_PATH.is_file()
