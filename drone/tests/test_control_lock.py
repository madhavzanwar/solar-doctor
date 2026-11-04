# drone/tests/test_control_lock.py
from drone.relay.control_lock import ControlLock


def test_first_operator_acquires():
    lock = ControlLock()
    assert lock.acquire("d1", "op-a") is True
    assert lock.holder("d1") == "op-a"


def test_second_operator_is_denied_while_held():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.acquire("d1", "op-b") is False
    assert lock.holder("d1") == "op-a"


def test_reacquire_by_same_operator_is_idempotent():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.acquire("d1", "op-a") is True


def test_release_frees_lock_only_for_holder():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.release("d1", "op-b") is False  # not the holder
    assert lock.release("d1", "op-a") is True
    assert lock.holder("d1") is None
    assert lock.acquire("d1", "op-b") is True   # now free


def test_holds_predicate():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.holds("d1", "op-a") is True
    assert lock.holds("d1", "op-b") is False
    assert lock.holds("d2", "op-a") is False
