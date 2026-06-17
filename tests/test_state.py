"""Tests for StateManager, focused on the auth-failure debounce counter."""

from __future__ import annotations

import diskcache
import pytest

from utils.state import StateManager


@pytest.fixture
def state(tmp_path) -> StateManager:
    return StateManager(diskcache.Cache(str(tmp_path / "cache")))


def test_auth_failures_start_at_zero(state: StateManager) -> None:
    assert state.get_auth_failures("u") == 0


def test_bump_returns_running_count(state: StateManager) -> None:
    assert state.bump_auth_failures("u") == 1
    assert state.bump_auth_failures("u") == 2
    assert state.bump_auth_failures("u") == 3
    assert state.get_auth_failures("u") == 3


def test_reset_clears_counter(state: StateManager) -> None:
    state.bump_auth_failures("u")
    state.bump_auth_failures("u")
    state.reset_auth_failures("u")
    assert state.get_auth_failures("u") == 0


def test_counters_are_per_user(state: StateManager) -> None:
    state.bump_auth_failures("a")
    state.bump_auth_failures("a")
    state.bump_auth_failures("b")
    assert state.get_auth_failures("a") == 2
    assert state.get_auth_failures("b") == 1


def test_transient_then_recover_never_reaches_threshold(state: StateManager) -> None:
    """A single 401 followed by a success must not accumulate toward the alarm."""
    threshold = 3
    for _ in range(5):
        # one failed run, immediately recovered
        assert state.bump_auth_failures("u") < threshold
        state.reset_auth_failures("u")


def test_sustained_failures_reach_threshold(state: StateManager) -> None:
    threshold = 3
    counts = [state.bump_auth_failures("u") for _ in range(threshold)]
    assert counts == [1, 2, 3]
    assert counts[-1] >= threshold
