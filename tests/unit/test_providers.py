from types import SimpleNamespace as NS

from auguste.agent.providers.litellm import LiteLLMProvider, parse_response


def test_parse_tool_calls_and_usage():
    call = NS(id="t1", function=NS(name="create_node", arguments='{"node_type": "geo"}'))
    response = NS(choices=[NS(message=NS(content=None, tool_calls=[call]))], usage=NS(total_tokens=42))
    completion = parse_response(response)
    assert completion.text == ""
    assert completion.tokens == 42
    assert (completion.tool_calls[0].name, completion.tool_calls[0].arguments) == ("create_node", {"node_type": "geo"})
    assert completion.as_message()["tool_calls"][0]["function"]["arguments"] == '{"node_type": "geo"}'


async def test_litellm_mock_response():
    provider = LiteLLMProvider("openai/gpt-4o-mini", mock_response="hello")
    completion = await provider.complete([{"role": "user", "content": "hi"}], [])
    assert completion.text == "hello"


def test_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    from auguste.settings import load_dotenv

    env = tmp_path / ".env"
    env.write_text("# dev\nAUGUSTE_T1=from_file\nexport AUGUSTE_T2='quoted'\n")
    monkeypatch.setenv("AUGUSTE_T1", "real")
    monkeypatch.delenv("AUGUSTE_T2", raising=False)
    load_dotenv(env)
    import os

    assert os.environ["AUGUSTE_T1"] == "real"
    assert os.environ["AUGUSTE_T2"] == "quoted"
    monkeypatch.delenv("AUGUSTE_T2")
