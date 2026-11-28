from daemon.target_filters import filter_key_for_repo, passes_target_filter


def _issue(title: str, body: str = "", labels: list[str] | None = None) -> dict:
    return {
        "title": title,
        "body": body,
        "repo_full_name": "example/repo",
        "labels": labels or [],
    }


def test_unlisted_target_is_unfiltered():
    assert passes_target_filter(_issue("Anything at all"), "vllm-project/vllm")


def test_openms_drops_bioinformatics_and_keeps_algorithmic_work():
    assert not passes_target_filter(_issue("Improve peptide annotation for proteomics"), "OpenMS")
    assert passes_target_filter(_issue("Speed up the peak-picking algorithm"), "OpenMS")


def test_deepchem_drops_bioinformatics_but_keeps_chemistry_ml():
    assert not passes_target_filter(_issue("Add a new bioinformatics workflow"), "deepchem")
    assert passes_target_filter(_issue("Support a new molecular graph featurizer"), "deepchem")


def test_ml4sci_requires_a_scientific_ml_signal():
    assert not passes_target_filter(_issue("Fix typo in README"), "ML4SCI")
    assert passes_target_filter(_issue("Benchmark physics simulation dataset loader"), "ML4SCI")


def test_org_entry_governs_member_repo():
    priority = [{"full_name": "OpenMS", "owner": "OpenMS", "is_org": 1}]
    assert filter_key_for_repo("OpenMS/OpenMS", priority) == "OpenMS"
    assert filter_key_for_repo("numpy/numpy", priority) == "numpy/numpy"
