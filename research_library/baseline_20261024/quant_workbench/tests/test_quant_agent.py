import hashlib
import json

import pytest
from quant_workbench.agent_interface import dispatch
from quant_workbench.quant_agent import RUN_FILES, verify_log, verify_manifest


def test_complete_manifest_rejects_tampering_and_omission(tmp_path):
    manifest = {}
    for name in RUN_FILES:
        (tmp_path/name).write_bytes(b"registered bytes")
        manifest[name] = hashlib.sha256(b"registered bytes").hexdigest()
    path = tmp_path/"manifest.json"
    path.write_text(json.dumps(manifest))
    assert verify_manifest(tmp_path) == 10
    (tmp_path/"nav.parquet").write_bytes(b"changed performance")
    with pytest.raises(ValueError, match="changed"):
        verify_manifest(tmp_path)
    manifest.pop("nav.parquet")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="complete"):
        verify_manifest(tmp_path)


def test_hash_chain_detects_modified_event_and_broken_link(tmp_path):
    path = tmp_path/"events.jsonl"
    entries = []
    previous = ""
    for n in range(2):
        event = {"action": "verify", "result": n, "previous": previous}
        event["hash"] = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        previous = event["hash"]
        entries.append(event)
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    assert verify_log(path) == 2
    entries[0]["result"] = 999
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    with pytest.raises(ValueError, match="chain changed"):
        verify_log(path)


@pytest.mark.parametrize("name,args", [("shell", {"command": "anything"}), ("get_status", {"path": "../secret"}),
                                       ("run_registered", {}), ("run_registered", {"minutes": float("nan")}),
                                       ("run_registered", {"minutes": 241}), ("run_registered", {"minutes": True})])
def test_agent_boundary_rejects_unregistered_calls(name, args):
    with pytest.raises(ValueError):
        dispatch(name, args)
