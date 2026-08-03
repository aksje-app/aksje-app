from drift_center import STEPS


def test_steps_are_complete_and_ordered():
    assert [row[0] for row in STEPS] == list(range(1, 9))
    assert STEPS[0][1] == "Markedsskanning"
    assert STEPS[-1][1] == "Produksjonshandel"


def test_unique_persistent_keys():
    keys = [row[2] for row in STEPS]
    assert len(keys) == len(set(keys)) == 8
