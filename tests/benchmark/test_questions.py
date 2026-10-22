from eaa.benchmark.questions import QUESTIONS


def test_there_are_fifteen_questions() -> None:
    assert len(QUESTIONS) == 15


def test_five_questions_per_category() -> None:
    categories = [q.category for q in QUESTIONS]
    assert categories.count("lookup") == 5
    assert categories.count("aggregation") == 5
    assert categories.count("multi_tool") == 5


def test_all_question_ids_are_unique() -> None:
    ids = [q.id for q in QUESTIONS]
    assert len(ids) == len(set(ids))


def test_every_question_has_a_callable_ground_truth_fn() -> None:
    for q in QUESTIONS:
        assert callable(q.ground_truth_fn)


def test_every_question_has_at_least_one_expected_tool() -> None:
    for q in QUESTIONS:
        assert len(q.expected_tools) >= 1


def test_multi_tool_questions_expect_two_distinct_tools() -> None:
    for q in QUESTIONS:
        if q.category == "multi_tool":
            assert len(set(q.expected_tools)) == 2
