"""Dependency-direction regression tests."""

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / 'src' / 'shorty'
INFRASTRUCTURE_PACKAGES = frozenset(
    {'apscheduler', 'fastapi', 'pydantic', 'redis', 'sqlalchemy'},
)


def imported_roots(path: Path) -> set[str]:
    """Return top-level package names imported by one Python module."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.partition('.')[0])
    return roots


def test_domain_and_service_layer_do_not_import_infrastructure() -> None:
    paths = [
        *SOURCE_ROOT.joinpath('domain').glob('*.py'),
        *SOURCE_ROOT.joinpath('service_layer').glob('*.py'),
    ]

    violations = {
        str(path.relative_to(SOURCE_ROOT)): imported_roots(path)
        & INFRASTRUCTURE_PACKAGES
        for path in paths
        if imported_roots(path) & INFRASTRUCTURE_PACKAGES
    }

    assert violations == {}


def test_http_routers_do_not_import_driven_adapters() -> None:
    router_root = SOURCE_ROOT / 'entrypoints' / 'routers'
    violations = {
        path.name
        for path in router_root.glob('*.py')
        if 'shorty.adapters' in path.read_text(encoding='utf-8')
    }

    assert violations == set()
