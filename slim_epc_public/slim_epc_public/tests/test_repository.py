import pytest

from epc.db import EPCRepository
from epc.models import UEState, BearerConfig, ThroughputStats


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test_epc.db"
    return EPCRepository(str(db_path))


# --- UE repository tests ---

def test_repository_new_ue_does_not_exist(repo):
    assert repo.ue_exists(1) is False


def test_repository_attach_ue(repo):
    repo.attach_ue(1)

    assert repo.ue_exists(1) is True


def test_repository_attach_ue_adds_default_bearer_9(repo):
    repo.attach_ue(1)

    ue = repo.get_ue(1)

    assert 9 in ue.bearers
    assert ue.bearers[9].bearer_id == 9


def test_repository_cannot_attach_same_ue_twice(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="UE already attached"):
        repo.attach_ue(1)


def test_repository_detach_ue(repo):
    repo.attach_ue(1)

    repo.detach_ue(1)

    assert repo.ue_exists(1) is False


def test_repository_cannot_detach_missing_ue(repo):
    with pytest.raises(ValueError, match="UE not found"):
        repo.detach_ue(99)


def test_repository_get_ue_returns_state(repo):
    repo.attach_ue(5)

    ue = repo.get_ue(5)

    assert ue.ue_id == 5


def test_repository_get_missing_ue_raises_error(repo):
    with pytest.raises(ValueError, match="UE not found"):
        repo.get_ue(123)


def test_repository_list_ues_empty(repo):
    assert list(repo.list_ues()) == []


def test_repository_list_ues_sorted(repo):
    repo.attach_ue(3)
    repo.attach_ue(1)
    repo.attach_ue(2)

    assert list(repo.list_ues()) == [1, 2, 3]


def test_repository_reset_all_removes_all_ues(repo):
    repo.attach_ue(1)
    repo.attach_ue(2)
    repo.attach_ue(3)

    repo.reset_all()

    assert list(repo.list_ues()) == []


# --- save_ue tests ---

def test_repository_save_ue_creates_state(repo):
    state = UEState(ue_id=10)

    repo.save_ue(state)

    assert repo.ue_exists(10) is True
    assert repo.get_ue(10).ue_id == 10


def test_repository_save_ue_replaces_existing_state(repo):
    repo.attach_ue(10)

    state = repo.get_ue(10)
    state.bearers[5] = BearerConfig(bearer_id=5)

    repo.save_ue(state)

    saved = repo.get_ue(10)

    assert 5 in saved.bearers


# --- Bearer repository tests ---

def test_repository_add_bearer(repo):
    repo.attach_ue(1)

    repo.add_bearer(1, 5)

    ue = repo.get_ue(1)

    assert 5 in ue.bearers
    assert ue.bearers[5].bearer_id == 5


def test_repository_cannot_add_existing_bearer(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="Bearer already exists"):
        repo.add_bearer(1, 9)


def test_repository_cannot_add_bearer_to_missing_ue(repo):
    with pytest.raises(ValueError, match="UE not found"):
        repo.add_bearer(99, 5)


def test_repository_update_bearer_adds_or_replaces_bearer(repo):
    repo.attach_ue(1)

    bearer = BearerConfig(bearer_id=4)
    repo.update_bearer(1, bearer)

    ue = repo.get_ue(1)

    assert 4 in ue.bearers
    assert ue.bearers[4].bearer_id == 4


def test_repository_delete_bearer(repo):
    repo.attach_ue(1)
    repo.add_bearer(1, 5)

    repo.delete_bearer(1, 5)

    ue = repo.get_ue(1)

    assert 5 not in ue.bearers


def test_repository_cannot_delete_default_bearer(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="Cannot remove default bearer"):
        repo.delete_bearer(1, 9)


def test_repository_cannot_delete_missing_bearer(repo):
    repo.attach_ue(1)

    with pytest.raises(ValueError, match="Bearer not found"):
        repo.delete_bearer(1, 5)


def test_repository_cannot_delete_bearer_from_missing_ue(repo):
    with pytest.raises(ValueError, match="UE not found"):
        repo.delete_bearer(99, 5)


# --- Stats tests ---

def test_repository_update_stats(repo):
    repo.attach_ue(1)

    stats = ThroughputStats(
        ue_id=1,
        bearer_id=9,
        bytes_tx=100,
        bytes_rx=200,
    )

    repo.update_stats(1, stats)

    ue = repo.get_ue(1)

    assert 9 in ue.stats
    assert ue.stats[9].bytes_tx == 100
    assert ue.stats[9].bytes_rx == 200

def test_repository_update_stats_for_missing_ue(repo):
    stats = ThroughputStats(
        ue_id=99,
        bearer_id=9,
        bytes_tx=100,
        bytes_rx=200,
    )

    with pytest.raises(ValueError, match="UE not found"):
        repo.update_stats(99, stats)

def test_repository_delete_bearer_removes_stats_too(repo):
    repo.attach_ue(1)
    repo.add_bearer(1, 5)

    stats = ThroughputStats(
        ue_id=1,
        bearer_id=5,
        bytes_tx=100,
        bytes_rx=200,
    )

    repo.update_stats(1, stats)

    repo.delete_bearer(1, 5)

    ue = repo.get_ue(1)

    assert 5 not in ue.bearers
    assert 5 not in ue.stats