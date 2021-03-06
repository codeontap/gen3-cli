import os
import hashlib
import json
import tempfile

from unittest import mock
from click.testing import CliRunner
from hamlet.command.schema import list_schemas
from hamlet.command.common.context import Generation


def template_backend_run_mock(data):
    def run(
        entrance='schemaset',
        deployment_mode=None,
        output_dir=None,
        generation_input_source=None,
        generation_provider=None,
        generation_framework=None,
        output_filename='schemaset-schemacontract.json'
    ):
        os.makedirs(output_dir, exist_ok=True)
        unitlist_filename = os.path.join(output_dir, output_filename)
        with open(unitlist_filename, 'wt+') as f:
            json.dump(data, f)
    return run


def mock_backend(schemaset=None):
    def decorator(func):
        @mock.patch('hamlet.backend.query.context.Context')
        @mock.patch('hamlet.backend.query.template')
        def wrapper(blueprint_mock, ContextClassMock, *args, **kwargs):
            with tempfile.TemporaryDirectory() as temp_cache_dir:

                ContextObjectMock = ContextClassMock()
                ContextObjectMock.md5_hash.return_value = str(hashlib.md5(str(schemaset).encode()).hexdigest())
                ContextObjectMock.cache_dir = temp_cache_dir

                blueprint_mock.run.side_effect = template_backend_run_mock(schemaset)

                return func(blueprint_mock, ContextClassMock, *args, **kwargs)

        return wrapper
    return decorator


@mock_backend(
    {
        'Stages': [
            {
                'Id': 'StageId1',
                'Steps': [
                    {
                        'Id': 'StepId1',
                        'Parameters': {
                            'SchemaType': 'SchemaType1',
                            'SchemaInstance': 'SchemaInstance1',
                        }
                    },
                    {
                        'Id': 'StepId2',
                        'Parameters': {
                            'SchemaType': 'SchemaType2',
                            'SchemaInstance': 'SchemaInstance2',
                        }
                    }
                ]
            },
            {
                'Id': 'StageId2',
                'Steps': [
                    {
                        'Id': 'StepId3',
                        'Parameters': {
                            'SchemaType': 'SchemaType3',
                            'SchemaInstance': 'SchemaInstance3',
                        }
                    },
                    {
                        'Id': 'StepId4',
                        'Parameters': {
                            'SchemaType': 'SchemaType4',
                            'SchemaInstance': 'SchemaInstance4',
                        }
                    }
                ]
            }
        ]
    }
)
def test_query_list_schemas(blueprint_mock, ContextClassMock):
    obj = Generation()

    cli = CliRunner()
    result = cli.invoke(
        list_schemas,
        [
            '--output-format', 'json'
        ],
        obj=obj
    )
    print(result.output)
    assert result.exit_code == 0
    result = json.loads(result.output)
    assert len(result) == 4
    assert {
        'SchemaType': 'SchemaType1',
        'SchemaInstance': 'SchemaInstance1',
    } in result
    assert {
        'SchemaType': 'SchemaType2',
        'SchemaInstance': 'SchemaInstance2',
    } in result
    assert {
        'SchemaType': 'SchemaType3',
        'SchemaInstance': 'SchemaInstance3',
    } in result
    assert {
        'SchemaType': 'SchemaType4',
        'SchemaInstance': 'SchemaInstance4',
    } in result
