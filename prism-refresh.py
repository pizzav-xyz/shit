#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime
from importlib import import_module
from typing import Any

microsoft_account = import_module("minecraft_launcher_lib.microsoft_account")


PRISM_CLIENT_ID = "1d644380-5a82-4dbe-bc41-9bf6e6d3d4c9"
DEFAULT_ACCOUNTS = os.path.expanduser("~/.local/share/PrismLauncher/accounts.json")
INTER_ACCOUNT_DELAY_SECONDS = 20
RETRY_DELAY_SECONDS = 20


def log(message: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def load_accounts(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("accounts.json root must be an object")
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts.json missing 'accounts' array")
    return data


def save_accounts_atomic(path: str, data: dict[str, Any]) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp_path, path)


def ensure_token_object(account: dict[str, Any], key: str) -> dict[str, Any]:
    value = account.get(key)
    if not isinstance(value, dict):
        value = {}
        account[key] = value
    return value


def account_label(account: dict[str, Any], index: int) -> str:
    profile = account.get("profile")
    if isinstance(profile, dict):
        name = profile.get("name")
        if isinstance(name, str) and name:
            return name
    return f"account#{index + 1}"


def refresh_account(account: dict[str, Any]) -> None:
    msa = ensure_token_object(account, "msa")
    ygg = ensure_token_object(account, "ygg")

    refresh_token = msa.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise ValueError("missing msa.refresh_token")

    oauth = microsoft_account.refresh_authorization_token(
        client_id=PRISM_CLIENT_ID,
        client_secret=None,
        redirect_uri=None,
        refresh_token=refresh_token,
    )
    if "error" in oauth:
        raise RuntimeError(str(oauth["error"]))

    msa_access_token = oauth["access_token"]
    xbl = microsoft_account.authenticate_with_xbl(msa_access_token)
    xsts = microsoft_account.authenticate_with_xsts(xbl["Token"])
    minecraft = microsoft_account.authenticate_with_minecraft(
        xbl["DisplayClaims"]["xui"][0]["uhs"],
        xsts["Token"],
    )
    if "access_token" not in minecraft:
        detail = (
            minecraft.get("errorMessage")
            or minecraft.get("error")
            or "minecraft authentication failed"
        )
        raise RuntimeError(str(detail))

    profile = microsoft_account.get_profile(minecraft["access_token"])
    if "error" in profile and profile["error"] == "NOT_FOUND":
        raise RuntimeError("account does not own Minecraft")

    now = int(time.time())
    msa["token"] = msa_access_token
    msa["refresh_token"] = oauth["refresh_token"]
    msa["iat"] = now
    msa["exp"] = now + int(oauth["expires_in"])

    ygg["token"] = minecraft["access_token"]
    ygg["iat"] = now
    ygg["exp"] = now + int(minecraft["expires_in"])

    profile_obj = account.get("profile")
    if not isinstance(profile_obj, dict):
        profile_obj = {}
        account["profile"] = profile_obj
    profile_obj["id"] = profile["id"]
    profile_obj["name"] = profile["name"]


def main() -> int:
    accounts_path = os.environ.get("PRISM_ACCOUNTS", DEFAULT_ACCOUNTS)
    data = load_accounts(accounts_path)
    accounts = data["accounts"]

    failures = 0
    msa_indices = [
        index
        for index, account in enumerate(accounts)
        if isinstance(account, dict) and account.get("type") == "MSA"
    ]

    for position, index in enumerate(msa_indices):
        account = accounts[index]
        name = account_label(account, index)
        account_failed = False
        try:
            refresh_account(account)
            log(f"{name}: refresh succeeded")
        except Exception as exc:
            account_failed = True
            failures += 1
            log(f"{name}: refresh failed: {exc}")

        if position + 1 < len(msa_indices):
            delay = (
                RETRY_DELAY_SECONDS if account_failed else INTER_ACCOUNT_DELAY_SECONDS
            )
            time.sleep(delay)

    save_accounts_atomic(accounts_path, data)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
