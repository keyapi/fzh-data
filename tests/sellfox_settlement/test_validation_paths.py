import importlib

import pytest


def test_output_rejects_other_repository_and_nested_paths(tmp_path):
    repo = tmp_path / 'other-repo'
    repo.mkdir()
    (repo / '.git').touch()
    helper = importlib.import_module('sellfox_settlement.validation_paths')
    with pytest.raises(ValueError, match='Git'):
        helper.private_output(repo / 'data' / 'out')


def test_output_rejects_original_bills_subdirectory(tmp_path):
    helper = importlib.import_module('sellfox_settlement.validation_paths')
    with pytest.raises(ValueError, match='input'):
        helper.private_output(tmp_path / 'out', input_root=tmp_path)


def test_output_separate_directory_is_allowed(tmp_path):
    helper = importlib.import_module('sellfox_settlement.validation_paths')
    assert helper.private_output(tmp_path / 'out') == (tmp_path / 'out').resolve()
