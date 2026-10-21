import ast
import os

import numpy as np
import pytest

import pipeline
from rsabias.core import classifier

MODEL_NPZ = os.path.join(pipeline.MODEL, 'classification_table_complex.npz')
MODEL_PKL = os.path.join(pipeline.MODEL, 'classification_table_complex.pkl')


def load_legacy_pickle():
    """The pickle only loads with the dependency versions that wrote it."""
    try:
        return classifier.load_object_pickle(MODEL_PKL)
    except Exception as e:
        pytest.skip('legacy pickle not loadable in this environment: {}'.format(e))


def test_resolve_prefers_npz():
    assert classifier.resolve_table_path(MODEL_PKL) == MODEL_NPZ


def test_model_groups_match_groups_file():
    table = classifier.load_classification_table(MODEL_NPZ)
    groups = classifier.ProbaTable.get_list_of_unique_groups(pipeline.GROUPS)
    assert list(table.coords['group'].values) == list(groups)
    assert table.shape == (32, 32, 2, 4, 2, len(groups))


def test_npz_identical_to_legacy_pickle():
    legacy = load_legacy_pickle()
    converted = classifier.load_classification_table(MODEL_NPZ)
    for d in legacy.dims:
        assert np.array_equal(legacy.coords[d].values, converted.coords[d].values), d
    expected = np.array([ast.literal_eval(c) for c in legacy.values.ravel()], dtype=np.float64)
    actual = converted.transpose(*(list(legacy.dims) + ['group'])).values.reshape(expected.shape)
    assert np.array_equal(actual, expected)


def test_save_load_round_trip(tmp_path):
    table = classifier.load_classification_table(MODEL_NPZ)
    path = str(tmp_path / 'table.npz')
    classifier.save_classification_table(table, list(table.coords['group'].values), path)
    pipeline.assert_tables_close(path, MODEL_NPZ, rel=0)


def test_mismatching_groups_rejected(tmp_path):
    groups_path = tmp_path / 'groups.json'
    groups_path.write_text('{"1": [], "2": []}')
    table = classifier.ProbaTable(pipeline.TRANS, str(groups_path), 'complex')
    table.init_common_structures()
    with pytest.raises(classifier.ProbaTableException):
        table.load_classification_tables(MODEL_PKL, 'complex')
