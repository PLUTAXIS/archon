import json

from archon.contracts.stamp import stamp


def test_stamp_has_required_keys():
    s = stamp()
    assert set(s) == {"archon_version", "git_sha", "dirty"}
    assert isinstance(s["dirty"], bool)
    assert len(s["git_sha"]) in (7, 40, len("unknown"))


def test_stamp_is_json_serializable():
    json.dumps(stamp())   # must not raise


def test_version_is_real():
    s = stamp()
    assert s["archon_version"] == "0.1.0"
