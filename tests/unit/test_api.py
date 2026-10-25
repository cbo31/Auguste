import json
import threading

from starlette.testclient import TestClient

from auguste.agent.loop import Agent
from auguste.api.server import create_app
from auguste.agent.providers.base import Completion
from conftest import FakeProvider, FakeTools, tool_turn


def make_client(*completions):
    tools = FakeTools()
    app = create_app(lambda confirm: Agent(FakeProvider(*completions), tools, confirm), {"model": "fake"})
    return TestClient(app), tools


def stream(client, sid, text, on_confirm=None):
    events = []
    with client.stream("POST", f"/sessions/{sid}/messages", json={"text": text}) as response:
        for line in response.iter_lines():
            event = json.loads(line)
            events.append(event)
            if event["type"] == "confirm" and on_confirm:
                on_confirm(event)
    return events


def test_http_stream_with_decline():
    client, tools = make_client(tool_turn(("execute_python", {"code": "1"})), Completion(text="fine"))
    assert client.get("/health").json() == {"ok": True, "model": "fake"}
    sid = client.post("/sessions").json()["session_id"]

    def decline(event):
        # answered from another thread, like the Houdini dialog does
        t = threading.Thread(
            target=lambda: client.post(f"/sessions/{sid}/confirm", json={"id": event["id"], "approved": False})
        )
        t.start()
        t.join()

    events = stream(client, sid, "run code", decline)
    assert [e["type"] for e in events] == ["tool_call", "confirm", "tool_skipped", "text", "done"]
    assert tools.called == []


def test_websocket_approve():
    client, tools = make_client(tool_turn(("delete_node", {"node_path": "/obj/a"})), Completion(text="deleted"))
    sid = client.post("/sessions").json()["session_id"]
    with client.websocket_connect(f"/sessions/{sid}/ws") as ws:
        ws.send_json({"type": "message", "text": "delete a"})
        events = []
        while not events or events[-1]["type"] != "done":
            events.append(ws.receive_json())
            if events[-1]["type"] == "confirm":
                ws.send_json({"type": "confirm", "id": events[-1]["id"], "approved": True})
    assert tools.called == [("delete_node", {"node_path": "/obj/a"})]
    assert events[-2] == {"type": "text", "text": "deleted"}


def test_websocket_stop_declines_pending_confirm():
    client, tools = make_client(tool_turn(("execute_python", {})))
    sid = client.post("/sessions").json()["session_id"]
    with client.websocket_connect(f"/sessions/{sid}/ws") as ws:
        ws.send_json({"type": "message", "text": "go"})
        events = []
        while not events or events[-1]["type"] != "done":
            events.append(ws.receive_json())
            if events[-1]["type"] == "confirm":
                ws.send_json({"type": "stop"})
    assert tools.called == []
    assert events[-1]["reason"] == "stopped"


def test_unknown_session():
    client, _ = make_client()
    assert client.post("/sessions/nope/stop").status_code == 404

