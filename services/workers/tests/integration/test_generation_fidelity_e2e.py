"""End-to-end: a generation sends what its prompt structure renders, and
records what it sent.

Drives the REAL generation loop (``generate_llm_responses``) against the
test Postgres with the REAL DeepInfra client pointed at a local mock
OpenAI-compatible server (``mock_chat_server``). Pinned:

* render equivalence: with ``append_schema_instruction`` off and
  ``structured_output: off``, a prompt structure plus a task send exactly
  the designed messages, byte for byte (German legal text with umlauts,
  section signs, dashes, braces of a JSON format block, trailing
  whitespace), with no appended block and no ``response_format``;
* the request record equals the body the server received, and
  ``request_sha256`` hashes it;
* with the defaults, the record shows every block the platform adds (the
  appended label-config instruction, the client's structured-output block);
* format retry: an answer without an answer field is asked again once in the
  same conversation (answer as assistant turn, retry message as user turn);
  the first answer is kept, ``retried`` set, tokens summed; no retry when
  the first answer parses (also for answer controls such as ``Loesung``),
  never more than one re-ask, and a provider refusal of the first answer
  still counts;
* answer keys built from task data and the refusal heuristic.

All fixture content is invented.
"""

import json

import pytest
from ai_services.request_capture import sha256_of
from generation_fidelity import schema_instruction
from mock_chat_server import mock_chat_server
from models import Generation, ResponseGeneration

import tasks

pytestmark = [pytest.mark.integration, pytest.mark.database]

LABEL_CONFIG = """<View>
  <Text name="akte" value="$akte"/>
  <Number name="anteil_mieter" toName="akte"/>
  <TextArea name="begruendung" toName="akte"/>
</View>"""

# A system prompt with its own answer-format block, as a fixed prompt design
# brings it; the place is bound from the task.
SYSTEM_TEMPLATE = (
    "Du prüfst als Schlichtungsstelle für Mietsachen in {{ort}} einen Streitfall. "
    "Antworte nur mit diesem JSON-Objekt:\n\n"
    "```json\n"
    '{"anteil_mieter": <0-100>, "begruendung": "<ein Satz>"}\n```'
)

TASKS = [
    {
        "ort": "Musterstadt",
        "akte": (
            "Schlichtungsakte S-118/26\n\nMieterin: Jana Kröger\nVermieter: Timo Weiß\n\n"
            "Die Mieterin verlangt 480 € Nebenkosten zurück (§ 556 BGB). Sie trägt vor, "
            "die Abrechnung sei „zu spät“ gekommen.  \n"
        ),
    },
    {
        "ort": "Neuheim an der Lahn",
        "akte": (
            "Akte S-9/26\tMieter: Đorđe Novaković\nVermieterin: Aylin Şahin\n\n"
            "Streitig ist die Kaution {Höhe unklar}; Betrag: 1.050 €.\n\n\n"
        ),
    },
]


def _expected_messages(task):
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE.replace("{{ort}}", task["ort"])},
        {"role": "user", "content": task["akte"]},
    ]


def _structure(**options):
    return {
        "name": "Fixed design",
        "system_prompt": {"template": SYSTEM_TEMPLATE, "fields": {"ort": "$ort"}},
        "instruction_prompt": "$akte",
        **options,
    }


OFF = {"append_schema_instruction": False, "structured_output": "off"}
RETRY_MESSAGE = (
    "Ihre Antwort enthielt keinen gültigen JSON-Block. Bitte antworten Sie erneut."
)


@pytest.fixture
def deepinfra_against(monkeypatch):
    """Route generation to the real DeepInfra client on a mock server."""
    from ai_services.deepinfra_service import DeepInfraService

    def _route(server):
        service = DeepInfraService(api_key="test-key")
        service.base_url = server.base_url
        service._provider_name = "DeepInfra"
        monkeypatch.setattr(
            tasks.user_aware_ai_service,
            "get_ai_service_for_user",
            lambda *a, **k: service,
        )
        return service

    return _route


def _generate(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    structure,
    task_data,
    label_config=LABEL_CONFIG,
):
    import uuid

    user = make_user()
    model = make_llm_model(provider="DeepInfra")
    project = make_project(
        created_by=user.id,
        label_config=label_config,
        generation_config={"prompt_structures": {"s0": structure}},
    )
    task = make_task(project.id, task_data, created_by=user.id)
    db_conn.commit()
    rg = ResponseGeneration(
        id=str(uuid.uuid4()),
        project_id=project.id,
        task_id=task.id,
        model_id=model.id,
        status="pending",
        runs_requested=1,
        structure_key="s0",
        created_by=user.id,
    )
    db_conn.add(rg)
    db_conn.commit()
    result = tasks.generate_llm_responses(
        generation_id=rg.id,
        structure_key="s0",
        config_data={"project_id": project.id, "rate_limit_delay": 0},
        model_id=model.id,
        user_id=user.id,
        run_index=0,
    )
    db_conn.expire_all()
    children = db_conn.query(Generation).filter(Generation.generation_id == rg.id).all()
    return result, children


def _metadata(gen):
    meta = gen.response_metadata
    return json.loads(meta) if isinstance(meta, str) else (meta or {})


@pytest.mark.parametrize("task_data", TASKS, ids=["civil", "unicode_and_braces"])
def test_options_off_send_the_rendered_messages_byte_for_byte(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
    task_data,
):
    with mock_chat_server() as server:
        server.reply('{"anteil_mieter": 30, "begruendung": "Verspätete Abrechnung."}')
        deepinfra_against(server)
        result, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            _structure(**OFF),
            task_data,
        )
    assert result["status"] == "success"
    [raw] = server.bodies
    wire = json.loads(raw)
    expected = _expected_messages(task_data)
    assert wire["messages"] == expected
    assert "response_format" not in wire
    assert "IMPORTANT: Respond ONLY" not in raw.decode("utf-8")
    assert "## Output Format" not in raw.decode("utf-8")

    record = gen.request_record
    assert record["messages"] == expected
    assert record["capture"] == "http_body"
    assert record["requests"][0]["body"] == wire
    assert record["response_format"] is None
    assert gen.request_sha256 == sha256_of(wire)
    assert gen.retried is False and gen.first_response_content is None
    assert gen.parse_status == "success"
    assert _metadata(gen)["answer_format"]["schema_instruction_appended"] is False


def test_defaults_record_every_block_the_platform_adds(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
):
    task_data = TASKS[0]
    with mock_chat_server() as server:
        server.reply('{"anteil_mieter": 30, "begruendung": "Verspätete Abrechnung."}')
        deepinfra_against(server)
        _, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            _structure(),
            task_data,
        )
    [wire] = server.json_bodies()
    system, user = wire["messages"][0]["content"], wire["messages"][1]["content"]
    assert user == task_data["akte"] + schema_instruction(
        ["anteil_mieter", "begruendung"]
    )
    assert system.startswith(_expected_messages(task_data)[0]["content"])
    assert "## Output Format" in system
    # Nothing the platform added is missing from the record.
    assert gen.request_record["messages"] == wire["messages"]
    assert _metadata(gen)["answer_format"]["structured_output_requested"] is True


def test_format_retry_asks_again_in_the_same_conversation(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
):
    task_data = TASKS[0]
    first = "Ich halte den Anspruch für überwiegend begründet."
    final = '{"anteil_mieter": 20, "begruendung": "Frist nicht eingehalten."}'
    structure = _structure(**OFF, format_retry={"message": RETRY_MESSAGE})
    with mock_chat_server() as server:
        server.reply(first, prompt_tokens=100, completion_tokens=12)
        server.reply(final, prompt_tokens=130, completion_tokens=20)
        deepinfra_against(server)
        _, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            structure,
            task_data,
        )
    first_body, retry_body = server.json_bodies()
    designed = _expected_messages(task_data)
    assert first_body["messages"] == designed
    assert retry_body["messages"] == designed + [
        {"role": "assistant", "content": first},
        {"role": "user", "content": RETRY_MESSAGE},
    ]
    assert gen.retried is True
    assert gen.first_response_content == first
    assert gen.response_content == final
    assert gen.parse_status == "success"
    assert {i["from_name"] for i in gen.parsed_annotation} >= {"anteil_mieter"}
    assert (gen.input_tokens, gen.output_tokens) == (230, 32)
    assert [r["body"] for r in gen.request_record["requests"]] == [
        first_body,
        retry_body,
    ]
    # The hash names the designed request, not the retry.
    assert gen.request_sha256 == sha256_of(first_body)
    assert _metadata(gen)["format_retry"] == {"attempts": 1, "error": None}
    # The retry sends the same parameters, so the answer keeps its system.
    assert _metadata(gen)["system"]["model_id"] == gen.model_id


def test_format_retry_asks_only_once_and_skips_a_parsed_answer(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
):
    # Stored by an earlier version with "max": still a single re-ask.
    structure = _structure(**OFF, format_retry={"max": 3, "message": RETRY_MESSAGE})
    with mock_chat_server() as server:
        server.reply("Erste Antwort ohne JSON.")
        server.reply("Zweite Antwort ohne JSON.")
        server.reply("Dritte Antwort, nie angefragt.")
        deepinfra_against(server)
        _, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            structure,
            TASKS[0],
        )
        assert len(server.bodies) == 2
        assert gen.retried is True
        assert gen.first_response_content == "Erste Antwort ohne JSON."
        assert gen.response_content == "Zweite Antwort ohne JSON."
        assert _metadata(gen)["format_retry"] == {"attempts": 1, "error": None}
        assert _metadata(gen)["answer_format"]["format_retry"] == {
            "message": RETRY_MESSAGE
        }

        server.replies.clear()
        server.bodies.clear()
        server.reply('{"anteil_mieter": 50, "begruendung": "Unklar."}')
        _, [parsed] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            structure,
            TASKS[1],
        )
        assert len(server.bodies) == 1
        assert parsed.retried is False and parsed.first_response_content is None


LOESUNG_ONLY_CONFIG = """<View>
  <Text name="akte" value="$akte"/>
  <Loesung name="loesung" toName="akte"/>
</View>"""


def test_format_retry_skips_a_parsed_answer_of_a_loesung_only_config(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
):
    answer = '{"loesung": "Der Anspruch aus § 556 BGB besteht nicht."}'
    structure = _structure(**OFF, format_retry={"message": RETRY_MESSAGE})
    with mock_chat_server() as server:
        server.reply(answer)
        server.reply("Nie angefragt.")
        deepinfra_against(server)
        _, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            structure,
            TASKS[0],
            label_config=LOESUNG_ONLY_CONFIG,
        )
    assert len(server.bodies) == 1
    assert gen.retried is False and gen.first_response_content is None
    assert gen.response_content == answer
    assert [i["from_name"] for i in gen.parsed_annotation] == ["loesung"]


def test_provider_refusal_of_the_first_answer_survives_a_format_retry(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
):
    structure = _structure(
        **OFF,
        format_retry={"message": RETRY_MESSAGE},
        refusal_heuristic={"pattern": r"^nie passend$"},
    )
    with mock_chat_server() as server:
        server.reply("Dazu äußere ich mich nicht.", finish_reason="content_filter")
        server.reply('{"anteil_mieter": 10, "begruendung": "Geringer Anteil."}')
        deepinfra_against(server)
        _, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            structure,
            TASKS[0],
        )
    assert len(server.bodies) == 2
    assert gen.retried is True
    assert gen.refusal is True
    assert _metadata(gen)["refusal_sources"] == {"provider": True, "heuristic": False}


def test_answer_keys_from_task_data_and_refusal_heuristic(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    deepinfra_against,
):
    task_data = dict(TASKS[0], mieter_key="kroeger")
    structure = _structure(
        **OFF,
        answer_schema={"fields": {"anteil_mieter": {"key": "anteil_{{mieter_key}}"}}},
    )
    with mock_chat_server() as server:
        server.reply('{"anteil_kroeger": 40, "begruendung": "Teilweise berechtigt."}')
        deepinfra_against(server)
        _, [gen] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            structure,
            task_data,
        )
    by_field = {i["from_name"]: i["value"] for i in gen.parsed_annotation}
    assert by_field["anteil_mieter"] == {"number": 40}
    assert gen.parse_metadata["mapped_keys"] == {"anteil_kroeger": "anteil_mieter"}

    refusing = _structure(
        **OFF,
        refusal_heuristic={"pattern": r"ich kann (dazu )?(keine|nicht)", "window": 200},
    )
    with mock_chat_server() as server:
        server.reply("Ich kann dazu keine rechtliche Einschätzung abgeben.")
        deepinfra_against(server)
        _, [refused] = _generate(
            db_conn,
            make_user,
            make_llm_model,
            make_project,
            make_task,
            refusing,
            TASKS[1],
        )
    assert refused.refusal is True
    assert _metadata(refused)["refusal_sources"] == {
        "provider": False,
        "heuristic": True,
    }


class _SilentService:
    """A provider service that answers without reporting a request (an
    overlay service that does not call ``record_request``)."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def is_available(self):
        return True

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "content": self.answers.pop(0),
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            "metadata": {},
        }


@pytest.mark.parametrize(
    "answers, retried",
    [
        (['{"anteil_mieter": 30, "begruendung": "Verspätet."}'], False),
        (["Ohne JSON.", '{"anteil_mieter": 30, "begruendung": "Verspätet."}'], True),
    ],
    ids=["single_call", "format_retry"],
)
def test_a_client_that_reports_no_request_is_recorded_as_a_worker_call(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    monkeypatch,
    answers,
    retried,
):
    service = _SilentService(answers)
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: service
    )
    structure = _structure(**OFF, format_retry={"message": RETRY_MESSAGE})
    _, [gen] = _generate(
        db_conn,
        make_user,
        make_llm_model,
        make_project,
        make_task,
        structure,
        TASKS[0],
    )
    assert gen.retried is retried
    record = gen.request_record
    assert record["capture"] == "worker_call"
    assert len(record["requests"]) == len(answers)
    assert all(
        r["capture"] == "worker_call" and r["sends"] == 0 for r in record["requests"]
    )
    assert record["messages"] == _expected_messages(TASKS[0])
    # Nothing was observed on the wire: the system profile is the run config.
    profile = _metadata(gen)["system"]["parameter_profile"]
    assert profile["temperature"] == float(service.calls[0]["temperature"])
    assert profile["max_tokens"] == service.calls[0]["max_tokens"]
    if retried:
        assert record["requests"][1]["body"]["messages"][-2:] == [
            {"role": "assistant", "content": "Ohne JSON."},
            {"role": "user", "content": RETRY_MESSAGE},
        ]


class _CoercingService(_SilentService):
    """A client that changes the configured knobs before it sends (as the
    OpenAI service does for GPT-5) and records what it sent."""

    def generate(self, **kwargs):
        from ai_services.request_capture import record_request

        record_request(
            "OpenAI",
            "chat.completions",
            {
                "model": "gpt-5",
                "messages": [
                    {"role": "system", "content": kwargs["system_prompt"]},
                    {"role": "user", "content": kwargs["prompt"]},
                ],
                "temperature": 1.0,
                "max_completion_tokens": 321,
            },
        )
        return super().generate(**kwargs)


def test_the_system_profile_is_what_the_client_sent(
    db_conn,
    make_user,
    make_llm_model,
    make_project,
    make_task,
    monkeypatch,
):
    service = _CoercingService(['{"anteil_mieter": 30, "begruendung": "Verspätet."}'])
    monkeypatch.setattr(
        tasks.user_aware_ai_service, "get_ai_service_for_user", lambda *a, **k: service
    )
    _, [gen] = _generate(
        db_conn,
        make_user,
        make_llm_model,
        make_project,
        make_task,
        _structure(**OFF),
        TASKS[0],
    )
    assert service.calls[0]["max_tokens"] != 321
    assert gen.request_record["capture"] == "http_body"
    assert _metadata(gen)["system"]["parameter_profile"] == {
        "temperature": 1.0,
        "max_tokens": 321,
    }
