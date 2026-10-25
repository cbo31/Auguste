from auguste.agent.loop import DECLINED, Agent
from auguste.agent.policy import Policy
from auguste.agent.providers.base import Completion
from conftest import FakeProvider, tool_turn


async def collect(agent, text="hi"):
    return [e async for e in agent.run(text)]


def approve(answer, asked):
    async def confirm(call, tier):
        asked.append(call.name)
        return answer

    return confirm


async def test_safe_tool_runs_without_asking(tools):
    asked = []
    provider = FakeProvider(tool_turn(("get_scene_info", {})), Completion(text="ok"))
    events = await collect(Agent(provider, tools, approve(True, asked)))
    assert tools.called == [("get_scene_info", {})]
    assert asked == []
    assert events[-1].data["reason"] == "finished"
    assert provider.calls[1][-1] == {"role": "tool", "tool_call_id": "c0", "content": "ran get_scene_info"}


async def test_declined_dangerous_tool_is_never_called(tools):
    asked = []
    provider = FakeProvider(tool_turn(("execute_python", {"code": "hou.exit()"})), Completion(text="ok"))
    events = await collect(Agent(provider, tools, approve(False, asked)))
    assert asked == ["execute_python"]
    assert tools.called == []
    assert [e.type for e in events] == ["tool_call", "confirm", "tool_skipped", "text", "done"]
    assert provider.calls[1][-1]["content"] == DECLINED


async def test_approved_dangerous_tool_runs(tools):
    provider = FakeProvider(tool_turn(("delete_node", {"node_path": "/obj/a"})), Completion(text="ok"))
    await collect(Agent(provider, tools, approve(True, [])))
    assert tools.called == [("delete_node", {"node_path": "/obj/a"})]


async def test_ask_mutating(tools):
    asked = []
    provider = FakeProvider(tool_turn(("create_node", {"node_type": "geo"})), Completion(text="ok"))
    await collect(Agent(provider, tools, approve(False, asked), Policy(ask_mutating=True)))
    assert asked == ["create_node"] and tools.called == []


async def test_max_turns(tools):
    provider = FakeProvider(*[tool_turn(("get_scene_info", {})) for _ in range(10)])
    events = await collect(Agent(provider, tools, approve(True, []), max_turns=3))
    assert events[-1].data["reason"] == "max_turns"
    assert len(provider.calls) == 3


async def test_max_tokens(tools):
    provider = FakeProvider(*[tool_turn(("get_scene_info", {}), tokens=600) for _ in range(10)])
    events = await collect(Agent(provider, tools, approve(True, []), max_tokens=1000))
    assert events[-1].data["reason"] == "max_tokens"
    assert len(provider.calls) == 2


async def test_stop_during_confirmation_skips_remaining_calls(tools):
    agent = None

    async def confirm(call, tier):
        agent.stop()
        return True

    provider = FakeProvider(tool_turn(("execute_python", {}), ("get_scene_info", {})))
    agent = Agent(provider, tools, confirm)
    events = await collect(agent)
    assert tools.called == []
    assert [e.data.get("reason") for e in events if e.type == "tool_skipped"] == ["stopped", "stopped"]
    assert events[-1].data["reason"] == "stopped"
    # every tool call still has a tool reply in the history
    assert [m["tool_call_id"] for m in agent.messages if m["role"] == "tool"] == ["c0", "c1"]


async def test_provider_error_ends_run(tools):
    class Broken:
        model = "x"

        async def complete(self, messages, tools):
            raise RuntimeError("no key")

    events = await collect(Agent(Broken(), tools, approve(True, [])))
    assert [e.type for e in events] == ["error", "done"]


async def test_history_carries_over(tools):
    provider = FakeProvider(Completion(text="one"), Completion(text="two"))
    agent = Agent(provider, tools, approve(True, []))
    await collect(agent, "first")
    await collect(agent, "second")
    assert [m["content"] for m in provider.calls[1] if m["role"] == "user"] == ["first", "second"]
