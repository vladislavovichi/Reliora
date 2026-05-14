import ops.scripts.port_available as port_available_script
import pytest
from ops.cli import app
from ops.scripts.port_available import main as port_available_main
from typer.testing import CliRunner


def test_help_output_lists_ops_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Reliora operational developer tooling" in result.output
    assert "port-available" in result.output
    assert "ai-smoke-check" in result.output
    assert "check-architecture" in result.output


def test_port_available_command_succeeds_for_free_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(port_available_script.socket, "socket", _socket_factory(111))

    result = CliRunner().invoke(app, ["port-available", "8088"])

    assert result.exit_code == 0
    assert result.output == ""


def test_port_available_command_rejects_invalid_port() -> None:
    result = CliRunner().invoke(app, ["port-available", "70000"])

    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert "70000" in result.output


def test_port_available_wrapper_matches_cli_for_busy_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(port_available_script.socket, "socket", _socket_factory(0))

    result = CliRunner().invoke(app, ["port-available", "8088"])
    wrapper_exit_code = port_available_main(["8088"])

    assert result.exit_code == 1
    assert result.output == ""
    assert wrapper_exit_code == 1


def test_port_available_wrapper_rejects_invalid_arguments() -> None:
    with pytest.raises(SystemExit) as exc_info:
        port_available_main(["70000"])

    assert exc_info.value.code == 2


def test_check_architecture_succeeds_without_source_roots() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["check-architecture"])

    assert result.exit_code == 0
    assert result.output == ""


class _FakeSocket:
    def __init__(self, connect_result: int) -> None:
        self._connect_result = connect_result

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect_ex(self, address: tuple[str, int]) -> int:
        self.address = address
        return self._connect_result

    def close(self) -> None:
        self.closed = True


def _socket_factory(connect_result: int) -> type[_FakeSocket]:
    class Socket(_FakeSocket):
        def __init__(self) -> None:
            super().__init__(connect_result)

    return Socket
