import pytest
from sr_harness.cli import setup_parser


def test_serve_has_independent_service_options():
    args = setup_parser().parse_args(["serve", "--root", "/data/new", "--port", "8010"])
    assert args.root == "/data/new"
    assert args.port == 8010
    assert args.global_tasks == 8
    assert args.per_user_tasks == 2


def test_retired_browser_server_is_not_a_cli_command():
    with pytest.raises(SystemExit):
        setup_parser().parse_args(["run"])
