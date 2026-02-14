import unittest

from classificator.transitions import (
    LevelTransition,
    parse_transitions,
    require_valid_pair_transition,
    require_valid_transition,
    validate_transition_set,
)


class TransitionsTest(unittest.TestCase):
    def test_parse_transitions_single_and_pair(self):
        parsed = parse_transitions("2:1,3-4:3")
        self.assertEqual(
            parsed,
            [
                LevelTransition(from_level=2, to_level=1, from_level_upper=None),
                LevelTransition(from_level=3, to_level=3, from_level_upper=4),
            ],
        )

    def test_validate_transition_overlap_fails(self):
        transitions = [
            LevelTransition(from_level=2, to_level=1),
            LevelTransition(from_level=2, to_level=2),
        ]
        with self.assertRaises(ValueError):
            validate_transition_set(transitions)

    def test_valid_transition_guards(self):
        require_valid_transition(3, 2)
        require_valid_transition(2, 2)
        require_valid_pair_transition(2, 3, 2)


if __name__ == "__main__":
    unittest.main()
