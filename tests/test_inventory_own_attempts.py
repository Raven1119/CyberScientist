import io
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "inventory_own_attempts", Path(__file__).resolve().parents[1] /
    "checks/inventory_own_attempts.py")
inventory = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(inventory)
AGENTS = ("agent-a", "agent-b", "agent-c")


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path):
    accounts = tmp_path / "raw/accounts"
    _json(accounts / "operator/auth_me.json", {"id": "operator"})
    _json(accounts / "operator/registered_agents.json", [
        {"agentUser": {"id": alias, "name": alias, "operatorId": "operator",
                       "operatorConfirmed": True}}
        for alias in AGENTS])
    _json(accounts / "mail/auth_me.json", {"id": "mail-author"})
    _json(accounts / "mail/attempts_list.json", {
        "attempts": [{"id": "m1", "authorId": "mail-author", "bundleAvailable": True,
                      "challengeId": "topic"}]})
    for alias in AGENTS:
        _json(accounts / alias / "attempts_list.json", {
            "attempts": [{"id": alias, "authorId": alias, "bundleAvailable": False,
                          "challengeId": "topic"}]})
    return accounts


def test_inventory_keeps_uncredentialed_agent_content_unavailable(tmp_path, monkeypatch):
    _fixture(tmp_path)
    monkeypatch.setattr(inventory.db, "query", lambda sql, params=():
                        [{"id": "mail", "role": "experiment", "status": "active",
                          "secret_ref": "local:mail"}]
                        if "FROM mailboxes" in sql else [])
    monkeypatch.setattr(inventory.config, "resolve_secret", lambda ref:
                        "private-token" if ref == "local:mail" else None)
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("trace/raw_messages.jsonl", "{}\n")
    calls = []

    def fetch(path, token=None, *, base_url=None):
        calls.append((path, token))
        aid = path.split("/")[2]
        if path.endswith("/bundle"):
            assert aid == "m1" and token == "private-token"
            return bundle.getvalue()
        if path.endswith("/trace"):
            assert aid == "m1" and token == "private-token"
            return b"[]"
        if path.endswith("/score"):
            return b'{"score": 50}'
        return json.dumps({"id": aid, "authorId": "mail-author" if aid == "m1" else aid,
                           "scorecard": {"trace_score": 75},
                           "detail": "should not be retained for uncredentialed agents"}).encode()

    monkeypatch.setattr(inventory, "_get", fetch)
    result = inventory.inventory(tmp_path, workers=1)
    assert len(result["accounts"]) == 4
    assert result["accounts"][0]["bundle_downloaded"] == 1
    assert result["accounts"][0]["attempts"][0]["raw_messages_in_bundle"] is True
    assert result["accounts"][0]["total_match"] is None
    for account in result["accounts"][1:]:
        assert account["credential_available"] is False
        assert account["attempts"][0]["content"] == "unavailable_no_account_credential"
        detail = json.loads((tmp_path / "raw/accounts" / account["alias"] / "attempts" /
                             account["alias"] / "detail.json").read_text())
        assert "detail" not in detail
    assert sum(path.endswith("/trace") for path, _ in calls) == 1
    assert sum(path.endswith("/bundle") for path, _ in calls) == 1
    assert all(token is None for path, token in calls if "agent-" in path)


def test_inventory_rejects_foreign_author_in_filtered_list(tmp_path, monkeypatch):
    accounts = _fixture(tmp_path)
    _json(accounts / "mail/attempts_list.json", {
        "attempts": [{"id": "foreign", "authorId": "other"}]})
    monkeypatch.setattr(inventory.db, "query", lambda sql, params=():
                        [{"id": "mail", "role": "experiment", "status": "active",
                          "secret_ref": "local:mail"}])
    monkeypatch.setattr(inventory.config, "resolve_secret", lambda ref: "token")
    monkeypatch.setattr(inventory, "_get", lambda *args, **kwargs:
                        pytest.fail("foreign Attempt must not be fetched"))
    with pytest.raises(ValueError, match="another account"):
        inventory.inventory(tmp_path, workers=1)


def test_authorized_get_refuses_cross_origin_redirect():
    request = inventory.urllib.request.Request(
        "https://play.bohrium.com/api/attempts/1/bundle",
        headers={"Authorization": "Bearer private-token"})
    with pytest.raises(inventory.ReadFailure, match="CROSS_ORIGIN_REDIRECT"):
        inventory._SameOriginRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://other.example/bundle")


def test_cli_requires_ignored_output_directory(tmp_path):
    with pytest.raises(ValueError, match=".package-checks/scorer-re-"):
        inventory._validated_output_root(tmp_path)
