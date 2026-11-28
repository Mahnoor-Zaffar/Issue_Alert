"""Per-target keyword filters for priority targets.

Targets are keyed exactly as they appear in ``priority_repos``: an org login
(``OpenMS``) or an ``owner/repo`` pair. When ``include`` is non-empty an issue
must mention at least one of those terms; when ``exclude`` is non-empty an
issue mentioning any of those terms is dropped. Matching is case-insensitive
against the issue title, body, labels and repository name.

Empty rules mean no filtering — that's the default for targets not listed here.
"""

from typing import Any

FilterRule = dict[str, tuple[str, ...]]

# Keep these lists broad on purpose: they exist to remove whole subject areas
# (bioinformatics, generic IT noise), not to hand-pick individual issues.
TARGET_FILTERS: dict[str, FilterRule] = {
    "blender": {
        "include": (
            "blender",
            "bpy",
            "addon",
            "add-on",
            "extension",
            "python",
            "render",
            "shader",
            "geometry",
            "animation",
            "viewport",
            "node",
            "script",
            "plugin",
            "mesh",
            "material",
            "camera",
            "compositor",
            "simulation",
        ),
    },
    "deepchem": {
        "exclude": (
            "bioinformatics",
            "genomics",
            "sequence alignment",
            "patient data",
            "clinical trial",
        ),
    },
    # The org itself is dedicated to ML for science, so no include gate here.
    "ML4SCI": {},
    "numfocus": {
        "include": (
            "scientific",
            "numerical",
            "python",
            "numpy",
            "scipy",
            "pandas",
            "jupyter",
            "matplotlib",
            "numba",
            "math",
            "statistics",
            "optimization",
            "array",
            "dataframe",
            "algorithm",
            "notebook",
            "plot",
            "visualization",
            "computation",
            "symbolic",
            "data",
        ),
        "exclude": (
            "conference",
            "diversity",
            "fundraising",
            "grant proposal",
            "jobs board",
            "website",
        ),
    },
    "OpenMS": {
        "include": (
            "algorithm",
            "machine learning",
            "deep learning",
            "neural",
            "model",
            "classification",
            "clustering",
            "optimization",
            "regression",
            "benchmark",
            "feature",
            "performance",
        ),
        "exclude": (
            "bioinformatics",
            "proteomics",
            "metabolomics",
            "pathway analysis",
        ),
    },
    "OWASP": {
        "include": (
            "security",
            "vulnerability",
            "scanner",
            "authentication",
            "authorization",
            "sast",
            "dast",
            "dependency",
            "web application",
            "api",
            "python",
        ),
    },
    "sugarlabs": {
        "include": (
            "sugar",
            "activity",
            "education",
            "learning",
            "children",
            "python",
            "gtk",
            "game",
        ),
    },
}


def _match_text(issue: dict[str, Any]) -> str:
    labels = issue.get("labels") or []
    if labels and isinstance(labels[0], dict):
        labels = [label.get("name", "") for label in labels]
    parts = (
        issue.get("title"),
        issue.get("body"),
        issue.get("repo_full_name"),
        " ".join(str(label) for label in labels),
    )
    return " ".join(str(part or "") for part in parts).lower()


def passes_target_filter(issue: dict[str, Any], target_key: str | None) -> bool:
    """Return True when ``issue`` is allowed through for ``target_key``."""
    rule = TARGET_FILTERS.get(target_key or "")
    if not rule:
        return True

    text = _match_text(issue)
    if any(term.lower() in text for term in rule.get("exclude", ())):
        return False
    include = rule.get("include", ())
    if include and not any(term.lower() in text for term in include):
        return False
    return True


def filter_key_for_repo(repo_full_name: str, priority_repos: list[dict[str, Any]]) -> str:
    """Resolve the governing target key for a repo (org entries included)."""
    owner = repo_full_name.split("/", 1)[0]
    for entry in priority_repos:
        if entry.get("is_org") and str(entry.get("owner", "")).lower() == owner.lower():
            return str(entry["full_name"])
    return repo_full_name
