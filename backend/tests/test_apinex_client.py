

def test_structural_json_slips_are_repaired_without_touching_text() -> None:
    from app.providers.apinex_client import sanitize_and_parse_json as parse

    assert parse('{"a": [1, 2,], "b": "x, y"}') == {"a": [1, 2], "b": "x, y"}
    assert parse('{"a": [{"id": 1} {"id": 2}] "b": "he said \\"hi\\" ok"}') == {
        "a": [{"id": 1}, {"id": 2}], "b": 'he said "hi" ok'}
    assert parse('{"a": "x" "b": [1 2]}') == {"a": "x", "b": [1, 2]}
    assert parse('Here you go:\n{"a": true}\nDone') == {"a": True}


def test_a_broken_answer_after_gateway_errors_is_asked_once_more() -> None:
    import httpx

    from app.providers.apinex_client import APInexClient

    answers = iter([httpx.Response(502), httpx.Response(502),
                    httpx.Response(200, json={"choices": [{"message": {"content": '{"a": "x'}}]}),
                    httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})])
    sent: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        sent.append(1)
        return next(answers)

    client = APInexClient(model="free/minimax-m3.1-flash", api_key="k",
                          transport=httpx.MockTransport(handler), sleep_fn=lambda _s: None)
    assert client.complete_sync("s", "u") == {"a": 1}
    assert len(sent) == 4  # 502, 502, broken JSON on the last attempt, then a fresh call
