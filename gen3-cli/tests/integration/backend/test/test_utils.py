import os
import json
import tempfile
import pytest
from cot.backend.test.templates.json_validator_obj_block import JSONValidator
from cot.backend.test.templates.json_structure_obj_block import JSONStructure
from cot.backend.test.templates.cfn_structure_obj_block import CFNStructure
from cot.backend.test.templates.cfn_lint_test_func_block import cfn_lint_test
from cot.backend.test.templates.cfn_nag_test_func_block import cfn_nag_test
from .conftest import DATA_DIR

CF_TEMPLATES_PATH = os.path.join(DATA_DIR, 'cf')
CFNStructure = CFNStructure(JSONValidator)
JSONStructure = JSONStructure(JSONValidator)


def test_cfn_nag_test():
    cfn_nag_test(os.path.join(CF_TEMPLATES_PATH, 'secure.json'))
    with pytest.raises(AssertionError):
        cfn_nag_test(os.path.join(CF_TEMPLATES_PATH, 'insecure.json'))


def test_cfn_lint_test():
    cfn_lint_test(os.path.join(CF_TEMPLATES_PATH, 'valid-syntax.json'))
    with pytest.raises(AssertionError):
        cfn_lint_test(os.path.join(CF_TEMPLATES_PATH, 'invalid-syntax.json'))


def test_json_structure_object():
    body = {
        'path': {
            'exists': []
        },
        'not': {
            'empty': {
                'list': [1, 2],
                'scalar': 1,
                'obj': {
                    '1': 'value',
                    '2': 'value',
                    '3': 'value'
                }
            }
        },
        'empty': {
            'list': [],
            'scalar': None,
            'obj': {}
        }
    }

    template = JSONStructure(body)

    template.match('path.exists', [])
    template.len('not.empty.list', 2)
    template.len('not.empty.obj', 3)

    template.exists('path.exists')

    template.not_empty('not.empty.list')
    template.not_empty('not.empty.scalar')
    template.not_empty('not.empty.obj')
    assert not template.errors

    template = JSONStructure(body)
    template.match('path.exists', [1])
    template.match('not.empty.scalar', 10)
    template.match('not.empty.obj', {'1': 'value'})
    assert len(template.errors) == 3

    template = JSONStructure(body)
    template.len('not.empty.list', 3)
    template.len('not.empty.obj', 2)
    assert len(template.errors) == 2

    template = JSONStructure(body)
    template.exists('not.path.exists')
    assert len(template.errors) == 1

    template = JSONStructure(body)
    template.not_empty('empty.list')
    template.not_empty('empty.scalar')
    template.not_empty('empty.obj')
    assert len(template.errors) == 3


def test_cfn_structure_object():
    body = {
        "Resources": {
            "TestResource": {
                "Type": "TestType"
            }
        },
        "Output": {
            "TestOutput": {
                "Property": "Value"
            }
        }
    }

    template = CFNStructure(body)
    template.resource("TestResource", "TestType")
    template.output("TestOutput")
    assert not template.errors
    template = CFNStructure(body)
    template.resource("MissingResource", "TestType")
    assert len(template.errors) == 1
    template = CFNStructure(body)
    template.resource("TestResource", "WrongType")
    assert len(template.errors) == 1
    template = CFNStructure(body)
    template.output("MissingOutput")
    assert len(template.errors) == 1


def test_json_validator_object():
    with tempfile.TemporaryDirectory() as temp_dir:
        # testing from_file classmethod
        template_filename = os.path.join(temp_dir, 'template.json')

        with pytest.raises(AssertionError) as einfo:
            JSONValidator.from_file(template_filename)
        assert str(einfo.value) == f"{template_filename} not found"

        os.mknod(template_filename)
        with pytest.raises(AssertionError) as einfo:
            JSONValidator.from_file(template_filename)
        assert str(einfo.value) == f"{template_filename} is not a valid JSON"

        with open(template_filename, 'wt') as f:
            json.dump({'key': 'value'}, f)

        # testing assert_structure method that uses collection of validators
        validator = JSONValidator.from_file(template_filename)

        def validator_func():
            raise AssertionError("Text")

        validator._validators.append(validator_func)
        with pytest.raises(AssertionError) as einfo:
            validator.assert_structure()
        assert json.loads(str(einfo.value)) == [
            {
                "rule": "validator_func",
                "msg": "Text"
            }
        ]

        validator = JSONValidator.from_file(template_filename)
        validator.assert_structure()
