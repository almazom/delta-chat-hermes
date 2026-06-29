"""Tests for non-interactive setup.py CLI."""

import setup


def test_argparser_non_interactive():
    parser = setup._build_argparser()
    args = parser.parse_args([
        "--non-interactive",
        "--relay", "nine.testrun.org",
        "--name", "Bot",
        "--profile", "work",
    ])
    assert args.non_interactive is True
    assert args.relay == "nine.testrun.org"
    assert args.name == "Bot"
    assert args.profile == "work"


def test_argparser_defaults():
    parser = setup._build_argparser()
    args = parser.parse_args([])
    assert args.non_interactive is False
    assert args.relay is None
    assert args.name is None
    assert args.profile is None
    assert args.email is None
    assert args.password is None
