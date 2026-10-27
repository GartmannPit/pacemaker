"""Lasttest ausschliesslich mit kuenstlichen Daten und gemockten Diensten."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.services.openai.live import events

from pacemaker_agent.metrics import live_diag, live_events, run_manifest, turn_ledger
from pacemaker_agent.metrics.aggregate import load_runs
from pacemaker_agent.metrics.conversation import load_runs as conversation_runs
from pacemaker_agent.metrics.load_aggregate import aggregate, block_health, cpu_values
from pacemaker_agent.metrics.transcript_export import export
from pacemaker_agent.tests import synthetic_caller


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def vmstat(path: Path, busy: int = 20) -> None:
    path.write_text(
        "procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----\n"
        "r b swpd free buff cache si so bi bo in cs us sy id wa st\n"
        "0 0 0 0 0 0 0 0 0 0 0 0 99 0 1 0 0\n"
        f"0 0 0 0 0 0 0 0 0 0 0 0 {busy} 0 {100 - busy} 0 0\n"
    )


def block(root: Path, name: str, count: int, latency: float, busy: int = 20) -> Path:
    path = root / name
    write_json(
        path / "block.json",
        {
            "mode": "reihe",
            "stage": "E" if count == 1 else f"L{count}",
            "callers": count,
            "turns": 3,
        },
    )
    vmstat(path / "vmstat.log", busy)
    write_jsonl(
        path / "callers.jsonl", [{"caller": c, "exit_code": 0} for c in range(1, count + 1)]
    )
    for c in range(1, count + 1):
        rid = run_manifest.new_run_id("live")
        write_json(
            path / "manifests" / f"{rid}.json",
            {
                "run_id": rid,
                "started": datetime.fromtimestamp(0, UTC).isoformat(),
                "finished": datetime.fromtimestamp(60, UTC).isoformat(),
                "session_complete": True,
                "config": {
                    "stack": "live",
                    "live_region": "referenz",
                    "fixtures_sha": "mock",
                    "load_concurrency": count,
                    "load_caller": c,
                },
            },
        )
        write_jsonl(
            path / "turns" / f"{rid}.jsonl",
            [
                {
                    "utterance_id": i,
                    "status": status,
                    "window_start": (i - 1) * 10,
                    "speech_end_clip": (i - 1) * 10 + 1,
                    "first_audio_after_clip_ms": 999999 if i == 1 else latency,
                }
                for i, status in enumerate(("beantwortet", "zerfallen", "abgebrochen"), 1)
            ],
        )
        write_jsonl(
            path / "live_diag" / f"{rid}.jsonl",
            [{"t": i * 10 + 1 + latency / 2000, "art": "audio", "still": False} for i in range(3)],
        )
    return path


def test_run_id_parallel_and_frozen_clock(monkeypatch) -> None:
    class FixedClock:
        @staticmethod
        def now(_tz):
            return datetime(2026, 10, 27, tzinfo=UTC)

    monkeypatch.setattr(run_manifest, "datetime", FixedClock)
    with ThreadPoolExecutor(max_workers=16) as pool:
        ids = list(pool.map(lambda _: run_manifest.new_run_id("live"), range(1000)))
    assert len(set(ids)) == 1000
    assert all(rid.endswith("-live") and "/" not in rid for rid in ids)


@pytest.mark.parametrize("concurrency,caller", [(None, "1"), ("0", "1"), ("5", "6"), ("x", "1")])
def test_invalid_load_config(monkeypatch, concurrency, caller) -> None:
    monkeypatch.delenv("PACEMAKER_LOAD_CONCURRENCY", raising=False)
    if concurrency is not None:
        monkeypatch.setenv("PACEMAKER_LOAD_CONCURRENCY", concurrency)
    monkeypatch.setenv("PACEMAKER_LOAD_CALLER", caller)
    with pytest.raises(ValueError):
        run_manifest.load_config()


def test_manifest_and_run_id_readers(tmp_path, monkeypatch) -> None:
    from pacemaker_agent.config import load_tuning_config

    monkeypatch.setattr(run_manifest, "MANIFEST_DIR", tmp_path / "manifests")
    monkeypatch.setattr(run_manifest, "_fixtures_hash", lambda: "mock")
    monkeypatch.setattr(run_manifest, "_git_revision", lambda: {"revision": "mock"})
    monkeypatch.setenv("PACEMAKER_LOAD_CONCURRENCY", "5")
    monkeypatch.setenv("PACEMAKER_LOAD_CALLER", "2")
    rid = run_manifest.new_run_id("live")
    run_manifest.write_manifest(
        rid, stack="live", llm_model="mock", tuning=load_tuning_config(), system_prompt="mock"
    )
    assert run_manifest.load_manifest(rid)["config"]["load_caller"] == 2
    assert run_manifest.load_manifest(rid)["config"]["load_concurrency"] == 5
    write_jsonl(tmp_path / f"{rid}.jsonl", [{"e2e_ms": 1, "stack": "live"}])
    write_json(tmp_path / "events" / f"{rid}.json", {"clips": []})
    write_jsonl(
        tmp_path / "transcripts" / f"{rid}.jsonl",
        [
            {
                "role": "assistant",
                "text": "Mock",
                "ts": "2026-10-27T12:00:00+00:00",
                "stack": "live",
                "llm_model": "mock",
            }
        ],
    )
    assert load_runs(tmp_path)[0].run_id == rid
    assert conversation_runs(tmp_path)[0]["run_id"] == rid
    assert all(p.exists() for p in export(tmp_path / "transcripts" / f"{rid}.jsonl"))


@pytest.mark.parametrize(
    "ratio,verdict",
    [
        (1.0, "bestanden"),
        (1.1, "unklar"),
        (1.2, "unklar"),
        (1.3, "unklar"),
        (1.4, "nicht bestanden"),
    ],
)
def test_load_quantiles_statuses_cold_start_and_ratio(tmp_path, ratio, verdict) -> None:
    block(tmp_path, "1-E", 1, 1000)
    block(tmp_path, "2-L5", 5, 1000 * ratio)
    block(tmp_path, "3-E", 1, 1000)
    block(tmp_path, "4-L10", 10, 1000 * ratio)
    block(tmp_path, "5-E", 1, 1000)
    report = aggregate(tmp_path)
    assert report["stages"]["E"]["agent"] == {"n": 6, "p50_ms": 1000, "p90_ms": 1000}
    stage = report["stages"]["L5"]
    assert stage["excluded"]["cold_start"] == 5
    assert stage["agent"]["n"] == 10
    assert stage["ratio_to_E"]["p90_ms"] == pytest.approx(ratio)
    assert stage["server"]["p90_ms"] == pytest.approx(500 * ratio)
    assert stage["verdict"] == verdict
    assert stage["live_peak_tpm"] is None


def test_vm_limited_uses_block_means_and_skips_boot_row(tmp_path) -> None:
    block(tmp_path, "1-E", 1, 1000)
    path = block(tmp_path, "2-L5", 5, 2000, busy=86)
    assert cpu_values(path / "vmstat.log") == [86]
    stage = aggregate(tmp_path)["stages"]["L5"]
    assert stage["verdict"] == "VM-begrenzt"
    assert stage["cpu_mean_percent"] == stage["cpu_max_percent"] == 86


def test_service_errors_and_missing_records(tmp_path) -> None:
    block(tmp_path, "1-E", 1, 1000)
    path = block(tmp_path, "2-L5", 5, 1000)
    manifests = sorted((path / "manifests").glob("*.json"))
    for p in manifests[:3]:
        manifest = json.loads(p.read_text())
        manifest["service_errors"] = [{"http_status": 429}]
        write_json(p, manifest)
    assert block_health(path)["service_error_sessions"] == 3
    assert aggregate(tmp_path)["stages"]["L5"]["verdict"] == "nicht bestanden"
    manifests[0].unlink()
    assert not block_health(path)["complete"]


def test_hangup_before_last_clip_counts_as_complete(tmp_path) -> None:
    # Läufe 2026-10-15: GPT-Live-Persona legte in allen vollständigen Sitzungen vor Clip 10 auf.
    path = block(tmp_path, "1-E", 1, 1000)
    manifest_path = next((path / "manifests").glob("*.json"))
    turns_path = path / "turns" / f"{manifest_path.stem}.jsonl"
    turns_path.write_text("".join(turns_path.read_text().splitlines(keepends=True)[:2]))
    assert not block_health(path)["complete"]
    manifest = json.loads(manifest_path.read_text())
    manifest["hung_up"] = True
    write_json(manifest_path, manifest)
    assert block_health(path)["complete"]


def test_persona_hung_up_reads_only_exact_event(tmp_path, monkeypatch) -> None:
    from pacemaker_agent.tests import synthetic_caller

    monkeypatch.setattr(synthetic_caller, "RUNS_DIR", tmp_path)
    write_jsonl(
        tmp_path / "transcripts" / "a.jsonl", [{"role": "event", "text": "auflegen_unterbrochen"}]
    )
    write_jsonl(tmp_path / "transcripts" / "b.jsonl", [{"role": "event", "text": "auflegen"}])
    assert not synthetic_caller.persona_hung_up("a")
    assert synthetic_caller.persona_hung_up("b")
    assert not synthetic_caller.persona_hung_up("fehlt")


def test_status_exclusions_and_function_test_not_pooled(tmp_path) -> None:
    block(tmp_path, "1-E", 1, 1000)
    path = block(tmp_path, "2-L5", 5, 1000)
    turn_path = next((path / "turns").glob("*.jsonl"))
    turns = [json.loads(line) for line in turn_path.read_text().splitlines()]
    turns[1].update(status="keine_antwort", first_audio_after_clip_ms=None)
    write_jsonl(turn_path, turns)
    write_json(tmp_path / "0-F" / "block.json", {"mode": "funktionstest"})
    stage = aggregate(tmp_path)["stages"]["L5"]
    assert stage["excluded"]["status"] == {"keine_antwort": 1}
    assert stage["verdict"] == "unklar"


class FakeLive:
    _session_started_on_connection = False
    push_error = AsyncMock()
    _close_session = AsyncMock()
    _disconnect = AsyncMock()
    _handle_evt_audio_delta = AsyncMock()
    _handle_evt_transcript_delta = AsyncMock()

    async def _handle_server_event(self, evt):
        if evt.type == "error":
            await self.push_error("NICHT SPEICHERN", force_treat_as_permanent=True)

    async def _receive_task_handler(self):
        return


@pytest.fixture
def observed(tmp_path, monkeypatch):
    monkeypatch.setattr(live_events, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(run_manifest, "MANIFEST_DIR", tmp_path / "manifests")
    write_json(tmp_path / "manifests" / "mock.json", {"run_id": "mock"})
    return live_events.instrument(FakeLive, "mock")(), tmp_path


def test_live_usage_seconds_backend_tokens_rate_limit_and_no_secret_text(observed) -> None:
    service, path = observed

    async def exercise():
        for payload in [
            {"type": "session.usage.updated", "usage": {"seconds": 10}},
            {"type": "session.usage.updated", "usage": {"seconds": 20}},
            {
                "type": "response.event",
                "event": {
                    "type": "response.completed",
                    "response": {
                        "id": "r",
                        "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
                    },
                },
            },
            {"type": "rate_limits.updated", "rate_limits": [{"name": "tokens", "remaining": 17}]},
            {
                "type": "error",
                "error": {"code": "rate_limit_exceeded", "message": "NICHT SPEICHERN"},
            },
        ]:
            await service._handle_server_event(events.parse_server_event(json.dumps(payload)))

    asyncio.run(exercise())
    text = (path / "live_usage" / "mock.jsonl").read_text()
    rows = [json.loads(line) for line in text.splitlines()]
    assert all(r["run_id"] == "mock" and r["t"] and r["ts"] for r in rows)
    assert rows[0]["usage"] == {"seconds": 10}
    assert rows[2]["source"] == "backend"
    assert rows[3]["rate_limits"][0]["remaining"] == 17
    assert "NICHT SPEICHERN" not in text
    error = json.loads((path / "manifests" / "mock.json").read_text())["service_errors"][0]
    assert error["kind"] == "sitzungsablehnung" and error["code"] == "rate_limit_exceeded"


def test_http_status_and_disconnect(observed) -> None:
    service, path = observed
    exc = RuntimeError("NICHT SPEICHERN")
    exc.response = SimpleNamespace(status_code=503)
    asyncio.run(service.push_error("NICHT SPEICHERN", exception=exc))
    asyncio.run(service._receive_task_handler())
    errors = json.loads((path / "manifests" / "mock.json").read_text())["service_errors"]
    assert errors[0]["http_status"] == 503
    assert errors[1]["kind"] == "verbindungsabbruch"


def test_expected_close_is_not_service_error(observed) -> None:
    service, path = observed

    async def exercise():
        await service._close_session()
        await service._handle_server_event(
            events.parse_server_event('{"type":"session.closed","usage":{"seconds":12}}')
        )
        await service._receive_task_handler()

    asyncio.run(exercise())
    assert "service_errors" not in json.loads((path / "manifests" / "mock.json").read_text())


def test_unexpected_session_closed_is_service_error(observed) -> None:
    service, path = observed
    asyncio.run(
        service._handle_server_event(
            events.parse_server_event('{"type":"session.closed","reason":"expired"}')
        )
    )
    assert (
        json.loads((path / "manifests" / "mock.json").read_text())["service_errors"][0]["kind"]
        == "unerwartetes_sitzungsende"
    )


def test_no_automatic_retries_under_load(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PACEMAKER_LOAD_CONCURRENCY", "5")
    monkeypatch.setenv("PACEMAKER_LOAD_CALLER", "1")
    monkeypatch.setattr(synthetic_caller, "_select_clips", lambda *args: [tmp_path / "mock.wav"])
    monkeypatch.setattr(synthetic_caller, "_clips_sha", lambda *args: "mock")
    session = AsyncMock(return_value={"service_error": True, "ended_by_pipeline_after_clip": 0})
    monkeypatch.setattr(synthetic_caller, "_session", session)
    monkeypatch.setattr(synthetic_caller.asyncio, "sleep", AsyncMock())
    ids = asyncio.run(synthetic_caller._run("live", 10, tmp_path, None, False))
    assert len(ids) == session.await_count == 1


def test_pipeline_ends_before_ready_persists_empty_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(synthetic_caller, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(turn_ledger, "TURNS_DIR", tmp_path / "turns")
    monkeypatch.setattr(run_manifest, "MANIFEST_DIR", tmp_path / "manifests")
    write_json(
        tmp_path / "manifests" / "mock.json",
        {"run_id": "mock", "service_errors": [{"http_status": 401}]},
    )
    monkeypatch.setattr(synthetic_caller, "build_pipeline_task", lambda *a, **kw: object())
    monkeypatch.setattr(
        synthetic_caller, "PipelineRunner", lambda: SimpleNamespace(run=AsyncMock())
    )
    monkeypatch.setattr(
        synthetic_caller,
        "SyntheticTransport",
        lambda: SimpleNamespace(input=lambda: SimpleNamespace(ready=asyncio.Event())),
    )
    result = asyncio.run(synthetic_caller._session("live", [Path("mock.wav")], "mock", {}))
    assert result["service_error"] and result["offered"] == 0
    assert (tmp_path / "turns" / "mock.jsonl").exists()
    assert json.loads((tmp_path / "manifests" / "mock.json").read_text())["finished"]


def test_diag_uses_run_id_and_separates_silence(tmp_path, monkeypatch) -> None:
    import base64

    monkeypatch.setattr(live_diag, "RUNS_DIR", tmp_path)
    service = live_diag.instrument(FakeLive, "mock")()
    asyncio.run(
        service._handle_evt_audio_delta(
            SimpleNamespace(delta=base64.b64encode(bytes(480)).decode())
        )
    )
    row = json.loads((tmp_path / "live_diag" / "mock.jsonl").read_text())
    assert row["still"] and row["art"] == "audio"


@pytest.mark.parametrize(
    "mode,failures,expected",
    [
        ("funktionstest", 0, ["1-F"] * 2),
        ("interrupt", -1, []),
        (
            "reihe",
            0,
            ["1-E"] + ["2-L5"] * 5 + ["3-E"] + ["4-L10"] * 10 + ["5-E"] + ["6-L20"] * 20 + ["7-E"],
        ),
        ("reihe", 3, ["1-E"] + ["2-L5"] * 5 + ["3-E", "5-E", "7-E"]),
    ],
)
def test_shell_order_and_l5_abort_with_fully_mocked_commands(
    tmp_path, mode, failures, expected
) -> None:
    import os
    import shutil
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    (tmp_path / "infra").mkdir()
    shutil.copyfile(repo / "infra" / "lasttest.sh", tmp_path / "infra" / "lasttest.sh")
    (tmp_path / "infra" / "rtt-check.sh").write_text("echo '{\"mock\":true}'\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "agent" / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / "agent" / ".venv" / "bin" / "python").symlink_to(sys.executable)

    def command(name: str, source: str) -> None:
        target = bin_dir / name
        target.write_text(f"#!{sys.executable}\n" + source)
        target.chmod(0o755)

    command("uname", "print('Linux')\n")
    command("sleep", "pass\n")
    command("setsid", "import os,sys\nos.setsid()\nos.execvp(sys.argv[1],sys.argv[1:])\n")
    command(
        "timeout",
        "import os,sys\n"
        "assert sys.argv[1:4] == ['--signal=TERM','--kill-after=5s','300']\n"
        "os.execvp(sys.argv[4], sys.argv[4:])\n",
    )
    # Nur kuenstliches vmstat-Protokoll; kein System-Messkommando ausfuehren.
    command(
        "vmstat",
        "import time\nprint('r b us sy id wa st',flush=True)\n"
        "print('0 0 0 0 100 0 0',flush=True)\n"
        "print('0 0 20 0 80 0 0',flush=True)\ntime.sleep(30)\n",
    )
    command(
        "uv",
        """import json,os,sys
from pathlib import Path
if 'pacemaker_agent.tests.synthetic_caller' not in sys.argv:
    module='pacemaker_agent.metrics.load_aggregate'
    args=sys.argv[sys.argv.index(module)+1:]
    os.execv(sys.executable, [sys.executable, '-m', module, *args])
if int(os.environ['MOCK_FAILURES']) == -1:
    import signal
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open(os.environ['MOCK_PIDS'], 'a') as stream:
        stream.write(str(os.getpid())+'\\n')
    while True:
        signal.pause()
root=Path(os.environ['PACEMAKER_RUNS_DIR'])
c=int(os.environ['PACEMAKER_LOAD_CALLER'])
n=int(os.environ['PACEMAKER_LOAD_CONCURRENCY'])
assert os.environ['OPENAI_LIVE_REGION']=='referenz'
assert '--no-service-retries' in sys.argv
assert '--offline' in sys.argv and '--no-sync' in sys.argv
with open(os.environ['MOCK_TRACE'],'a') as stream:
    stream.write(root.name+'\\n')
(root/'manifests').mkdir(exist_ok=True)
(root/'turns').mkdir(exist_ok=True)
errors=[{'http_status':429}] if n==5 and c<=int(os.environ['MOCK_FAILURES']) else []
m={'run_id':str(c),'config':{'load_concurrency':n,'load_caller':c},
   'service_errors':errors,'session_complete':not errors,
   'started':'2026-10-27T00:00:00+00:00','finished':'2026-10-27T00:01:00+00:00'}
(root/'manifests'/f'{c}.json').write_text(json.dumps(m))
turns=int(sys.argv[sys.argv.index('--turns')+1])
rows=[{'utterance_id':i,'status':'beantwortet','first_audio_after_clip_ms':1}
      for i in range(1,turns+1)]
(root/'turns'/f'{c}.jsonl').write_text(''.join(json.dumps(r)+'\\n' for r in rows))
""",
    )
    trace = tmp_path / "trace"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "UV": str(bin_dir / "uv"),
        "MOCK_TRACE": str(trace),
        "MOCK_PIDS": str(tmp_path / "pids"),
        "MOCK_FAILURES": str(failures),
        "PYTHONPATH": str(repo / "agent" / "src"),
        "PYTHON_DOTENV_DISABLED": "1",
    }
    if mode == "interrupt":
        import time

        proc = subprocess.Popen(
            ["bash", "infra/lasttest.sh", "funktionstest"],
            cwd=tmp_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        pidfile = tmp_path / "pids"
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if pidfile.exists() and len(pidfile.read_text().splitlines()) == 2:
                    break
                time.sleep(0.01)
        finally:
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 143, stdout + stderr
        pids = [int(line) for line in pidfile.read_text().splitlines()]
        assert len(pids) == 2
        for pid in pids:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
        return
    result = subprocess.run(
        ["bash", "infra/lasttest.sh", mode],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(trace.read_text().splitlines()) == sorted(expected)
    assert "300 s" in result.stdout
    if failures:
        assert list(tmp_path.glob("experiments/runs/lasttest/*/skipped.jsonl"))


@pytest.mark.parametrize("status", [401, 429, 503])
def test_installed_pipecat_connection_rejection_is_recorded(tmp_path, monkeypatch, status) -> None:
    from pipecat.services.openai.live import llm

    monkeypatch.setattr(live_events, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(run_manifest, "MANIFEST_DIR", tmp_path / "manifests")
    write_json(tmp_path / "manifests" / "mock.json", {"run_id": "mock"})
    exception = RuntimeError("Nicht persistieren")
    exception.response = SimpleNamespace(status_code=status)
    connect = AsyncMock(side_effect=exception)
    monkeypatch.setattr(llm, "websocket_connect", connect)
    monkeypatch.setattr(llm.OpenAILiveLLMService, "push_error", AsyncMock())
    service = live_events.instrument(llm.OpenAILiveLLMService, "mock")(api_key="mock")
    asyncio.run(service._connect())
    connect.assert_awaited_once()
    manifest = json.loads((tmp_path / "manifests" / "mock.json").read_text())
    assert manifest["service_errors"][0]["http_status"] == status
    assert manifest["service_errors"][0]["kind"] == "sitzungsablehnung"


def test_usage_is_cumulative_and_backend_peak_is_separate() -> None:
    from pacemaker_agent.metrics.load_aggregate import _peak, _usage

    usage = _usage(
        [
            {"source": "live", "usage": {"seconds": 5}},
            {"source": "live", "usage": {"seconds": 9}},
            *[
                {
                    "source": "backend",
                    "type": "response.completed",
                    "response_id": rid,
                    "t": ts,
                    "usage": {"total_tokens": tokens},
                }
                for rid, ts, tokens in [("a", 1, 7), ("a", 1, 7), ("b", 59, 3), ("c", 70, 2)]
            ],
        ]
    )
    assert usage["live_seconds"] == 9
    assert usage["live_tokens"] is None
    assert usage["backend_tokens"] == 12
    assert _peak(usage["backend_token_events"]) == 10
