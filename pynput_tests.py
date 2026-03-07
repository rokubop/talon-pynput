import time
from talon import Module, actions
from .pynput_talon import (
    _fire_press,
    _fire_release,
    _hold_state,
    _key_registry,
    _combo_registry,
    _sequence_registry,
)

mod = Module()


def _reset():
    _key_registry.clear()
    _combo_registry.clear()
    _sequence_registry.clear()
    _hold_state.clear()


def _test_single_key():
    results = []
    actions.user.pynput_register("a", lambda: results.append("down"), lambda: results.append("up"))
    _fire_press("a")
    _fire_release("a")
    actions.user.pynput_unregister("a")
    assert results == ["down", "up"], f"Expected ['down', 'up'], got {results}"
    assert "a" not in _key_registry, "Key not cleaned up"


def _test_single_key_no_repeat():
    count = []
    actions.user.pynput_register("a", lambda: count.append(1))
    _fire_press("a")
    _fire_press("a")
    _fire_press("a")
    actions.user.pynput_unregister("a")
    assert len(count) == 1, f"Expected 1 press, got {len(count)}"


def _test_combo():
    results = []
    actions.user.pynput_register("ctrl-shift", lambda: results.append("down"), lambda: results.append("up"))
    _fire_press("ctrl")
    assert results == [], "Combo fired too early"
    _fire_press("shift")
    assert results == ["down"], f"Expected ['down'], got {results}"
    _fire_release("shift")
    assert results == ["down", "up"], f"Expected ['down', 'up'], got {results}"
    _fire_release("ctrl")
    actions.user.pynput_unregister("ctrl-shift")


def _test_combo_plus_syntax():
    results = []
    actions.user.pynput_register("ctrl+shift", lambda: results.append("ok"))
    _fire_press("ctrl")
    _fire_press("shift")
    _fire_release("shift")
    _fire_release("ctrl")
    actions.user.pynput_unregister("ctrl+shift")
    assert results == ["ok"], f"Expected ['ok'], got {results}"


def _test_sequence():
    results = []
    actions.user.pynput_register("j j", lambda: results.append("seq"))
    _fire_press("j")
    _fire_release("j")
    assert results == [], "Sequence fired after first key"
    _fire_press("j")
    assert results == ["seq"], f"Expected ['seq'], got {results}"
    _fire_release("j")
    actions.user.pynput_unregister("j j")


def _test_sequence_three_steps():
    results = []
    actions.user.pynput_register("a b c", lambda: results.append("abc"))
    _fire_press("a")
    _fire_release("a")
    _fire_press("b")
    _fire_release("b")
    assert results == [], "Sequence fired too early"
    _fire_press("c")
    assert results == ["abc"], f"Expected ['abc'], got {results}"
    _fire_release("c")
    actions.user.pynput_unregister("a b c")


def _test_sequence_timeout():
    results = []
    actions.user.pynput_register("j j", lambda: results.append("seq"))
    _fire_press("j")
    _fire_release("j")
    time.sleep(0.35)
    _fire_press("j")
    _fire_release("j")
    assert results == [], f"Sequence should not fire after timeout, got {results}"
    # After timeout reset, that second j counted as step 0, so one more completes it
    _fire_press("j")
    assert results == ["seq"], f"Expected ['seq'] after reset, got {results}"
    _fire_release("j")
    actions.user.pynput_unregister("j j")


def _test_sequence_with_combo_step():
    results = []
    actions.user.pynput_register("ctrl-space c", lambda: results.append("chord"))
    _fire_press("ctrl")
    _fire_press("space")
    _fire_release("space")
    _fire_release("ctrl")
    assert results == [], "Should not fire until final step"
    _fire_press("c")
    assert results == ["chord"], f"Expected ['chord'], got {results}"
    _fire_release("c")
    actions.user.pynput_unregister("ctrl-space c")


def _test_is_held():
    actions.user.pynput_register("x", lambda: None)
    _fire_press("x")
    assert actions.user.pynput_is_held("x") == True, "x should be held"
    _fire_release("x")
    assert actions.user.pynput_is_held("x") == False, "x should not be held"
    actions.user.pynput_unregister("x")


def _test_dict_register():
    results = []
    actions.user.pynput_register({
        "a": (lambda: results.append("a_down"), lambda: results.append("a_up")),
        "b": (lambda: results.append("b_down"),),
    })
    _fire_press("a")
    _fire_release("a")
    _fire_press("b")
    _fire_release("b")
    actions.user.pynput_unregister(["a", "b"])
    assert results == ["a_down", "a_up", "b_down"], f"Expected ['a_down', 'a_up', 'b_down'], got {results}"


def _test_unregister_list():
    actions.user.pynput_register("a", lambda: None)
    actions.user.pynput_register("b", lambda: None)
    actions.user.pynput_register("c", lambda: None)
    actions.user.pynput_unregister(["a", "b", "c"])
    assert len(_key_registry) == 0, f"Expected empty registry, got {_key_registry}"


def _test_mouse_button():
    results = []
    actions.user.pynput_register("mouse_left", lambda: results.append("down"), lambda: results.append("up"))
    _fire_press("mouse_left")
    _fire_release("mouse_left")
    actions.user.pynput_unregister("mouse_left")
    assert results == ["down", "up"], f"Expected ['down', 'up'], got {results}"


def _test_mixed_combo():
    results = []
    actions.user.pynput_register("ctrl-mouse_left", lambda: results.append("combo"))
    _fire_press("ctrl")
    assert results == [], "Should not fire without mouse"
    _fire_press("mouse_left")
    assert results == ["combo"], f"Expected ['combo'], got {results}"
    _fire_release("mouse_left")
    _fire_release("ctrl")
    actions.user.pynput_unregister("ctrl-mouse_left")


def _test_stack_override():
    """Register same key twice — second should override first."""
    results = []
    actions.user.pynput_register("a", lambda: results.append("first"))
    actions.user.pynput_register("a", lambda: results.append("second"))
    _fire_press("a")
    _fire_release("a")
    assert results == ["second"], f"Expected ['second'], got {results}"
    actions.user.pynput_unregister("a")


def _test_unregister_last_restores():
    """unregister_last pops top, restoring previous registration."""
    results = []
    actions.user.pynput_register("a", lambda: results.append("first"))
    actions.user.pynput_register("a", lambda: results.append("second"))
    actions.user.pynput_unregister_last("a")
    _fire_press("a")
    _fire_release("a")
    assert results == ["first"], f"Expected ['first'], got {results}"
    actions.user.pynput_unregister("a")


def _test_unregister_last_empty():
    """unregister_last on single registration removes it."""
    actions.user.pynput_register("a", lambda: None)
    actions.user.pynput_unregister_last("a")
    assert "a" not in _key_registry, "Key should be removed"


def _test_unregister_clears_stack():
    """unregister removes entire stack."""
    actions.user.pynput_register("a", lambda: None)
    actions.user.pynput_register("a", lambda: None)
    actions.user.pynput_register("a", lambda: None)
    actions.user.pynput_unregister("a")
    assert "a" not in _key_registry, "Key should be fully removed"


def _test_stack_combo():
    """Stack works for combos too."""
    results = []
    actions.user.pynput_register("ctrl-shift", lambda: results.append("first"))
    actions.user.pynput_register("ctrl-shift", lambda: results.append("second"))
    _fire_press("ctrl")
    _fire_press("shift")
    _fire_release("shift")
    _fire_release("ctrl")
    assert results == ["second"], f"Expected ['second'], got {results}"
    actions.user.pynput_unregister_last("ctrl-shift")
    _fire_press("ctrl")
    _fire_press("shift")
    _fire_release("shift")
    _fire_release("ctrl")
    assert results == ["second", "first"], f"Expected ['second', 'first'], got {results}"
    actions.user.pynput_unregister("ctrl-shift")


def _test_unregister_last_list():
    """unregister_last works with list of keys."""
    results = []
    actions.user.pynput_register("a", lambda: results.append("a1"))
    actions.user.pynput_register("b", lambda: results.append("b1"))
    actions.user.pynput_register("a", lambda: results.append("a2"))
    actions.user.pynput_register("b", lambda: results.append("b2"))
    actions.user.pynput_unregister_last(["a", "b"])
    _fire_press("a")
    _fire_release("a")
    _fire_press("b")
    _fire_release("b")
    assert results == ["a1", "b1"], f"Expected ['a1', 'b1'], got {results}"
    actions.user.pynput_unregister(["a", "b"])


@mod.action_class
class Actions:
    def pynput_tests():
        """Run pynput tests in Talon REPL"""
        print("\n  Running pynput tests (thread warnings above are expected)...\n")
        tests = [
            ("single key press/release", _test_single_key),
            ("single key no repeat", _test_single_key_no_repeat),
            ("combo (ctrl-shift)", _test_combo),
            ("combo + syntax", _test_combo_plus_syntax),
            ("sequence (j j)", _test_sequence),
            ("sequence three steps", _test_sequence_three_steps),
            ("sequence timeout", _test_sequence_timeout),
            ("sequence with combo step", _test_sequence_with_combo_step),
            ("is_held", _test_is_held),
            ("dict register", _test_dict_register),
            ("unregister list", _test_unregister_list),
            ("mouse button", _test_mouse_button),
            ("mixed combo (ctrl-mouse_left)", _test_mixed_combo),
            ("stack override", _test_stack_override),
            ("unregister_last restores", _test_unregister_last_restores),
            ("unregister_last empty", _test_unregister_last_empty),
            ("unregister clears stack", _test_unregister_clears_stack),
            ("stack combo", _test_stack_combo),
            ("unregister_last list", _test_unregister_last_list),
        ]

        passed = 0
        failed = 0

        for name, test_fn in tests:
            _reset()
            try:
                test_fn()
                print(f"  PASS: {name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL: {name} - {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR: {name} - {type(e).__name__}: {e}")
                failed += 1
            finally:
                _reset()

        print(f"\n  {passed} passed, {failed} failed, {passed + failed} total")
