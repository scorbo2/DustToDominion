"""AGENTS.md drift canary: every conftest fixture must be documented.

AGENTS.md hand-lists the test fixtures available to agents writing tests.
When a fixture is added to ``tests/conftest.py`` but not to AGENTS.md,
agents get surprised by the gap (the ``mixer_ready`` incident during the
spec 13 review - the doc claimed a fixture didn't exist when it did).
This test turns that class of staleness into a red test instead.

The fixture inventory is extracted from conftest.py via AST rather than
by importing it: conftest sets SDL env vars and imports pygame at module
level, and a test module should not depend on import side effects to
answer a documentation question.
"""
from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFTEST_PATH = PROJECT_ROOT / "tests" / "conftest.py"
AGENTS_MD_PATH = PROJECT_ROOT / "AGENTS.md"


def _is_pytest_fixture_decorator(decorator: ast.expr) -> bool:
    """True for ``@pytest.fixture`` with or without call arguments.

    Covers both bare ``@pytest.fixture`` and ``@pytest.fixture(autouse=True)``
    forms; the call wrapper's ``.func`` is the attribute access underneath.
    """
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "fixture"
        and isinstance(target.value, ast.Name)
        and target.value.id == "pytest"
    )


def _conftest_fixture_names() -> set[str]:
    """Every function name decorated with ``@pytest.fixture`` in conftest."""
    tree = ast.parse(CONFTEST_PATH.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_pytest_fixture_decorator(d) for d in node.decorator_list)
    }


class TestAgentsMdDocumentsFixtures:
    def test_allConftestFixtures_shouldEachBeNamedInAgentsMd(self) -> None:
        # GIVEN a non-empty fixture inventory (a silently broken AST scan
        # must not let this test pass vacuously):
        fixture_names = _conftest_fixture_names()
        assert fixture_names, (
            f"no fixtures discovered in {CONFTEST_PATH}; the AST scan is "
            "broken and this canary is blind"
        )

        # GIVEN the current AGENTS.md text:
        agents_text = AGENTS_MD_PATH.read_text(encoding="utf-8")

        # WHEN we look for fixtures that AGENTS.md never mentions,
        # THEN there should be none:
        undocumented = sorted(name for name in fixture_names if name not in agents_text)
        assert not undocumented, (
            f"fixtures defined in tests/conftest.py but not named in "
            f"AGENTS.md: {undocumented}. Add them to the Testing gotchas "
            "section (autouse vs opt-in) so agents know they exist."
        )
