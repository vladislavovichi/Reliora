from typing import Annotated

import typer

from ops.scripts.port_available import check_port_available

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Reliora operational developer tooling.",
    name="reliora-ops",
    no_args_is_help=True,
)


@app.command("port-available")
def port_available(
    port: Annotated[
        int,
        typer.Argument(
            help="TCP port to check on 127.0.0.1.",
            min=1,
            max=65535,
        ),
    ],
) -> None:
    """Exit 0 when a local TCP port is available, 1 when it is busy."""
    raise typer.Exit(check_port_available(port))


@app.command("smoke-check")
def smoke_check() -> None:
    """Run the operational smoke check against the configured stack."""
    from ops.scripts import smoke_check as smoke_check_script

    raise typer.Exit(smoke_check_script.main())


@app.command("ai-smoke-check")
def ai_smoke_check_command() -> None:
    """Verify a real AI completion through ai-service gRPC."""
    from ops.scripts import ai_smoke_check as ai_smoke_check_script

    raise typer.Exit(ai_smoke_check_script.main())


@app.command("check-architecture")
def check_architecture() -> None:
    """Verify Reliora architecture import boundaries."""
    from ops.scripts import check_architecture_boundaries as architecture_script

    raise typer.Exit(architecture_script.main())


@app.command("check-repo-hygiene")
def check_repo_hygiene() -> None:
    """Verify generated artifacts and likely secrets are not tracked."""
    from ops.scripts import check_repo_hygiene as repo_hygiene_script

    raise typer.Exit(repo_hygiene_script.main())


def main() -> None:
    app(prog_name="reliora-ops")


if __name__ == "__main__":
    main()
