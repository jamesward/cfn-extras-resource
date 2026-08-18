import cfn_extras.sdk_call as sdk_call


def test_flatten_nested_dict_and_list():
    out = {}
    sdk_call.flatten({'A': {'B': 'x'}, 'C': [{'D': 'y'}]}, '', out)
    assert out == {'A.B': 'x', 'C.0.D': 'y'}


def test_flatten_stringifies_non_strings():
    out = {}
    sdk_call.flatten({'N': 5, 'B': True}, '', out)
    assert out == {'N': '5', 'B': 'True'}


def test_dig_walks_dicts_and_indexes_lists():
    obj = {'A': {'B': [{'C': 'deep'}]}}
    assert sdk_call.dig(obj, 'A.B.0.C') == 'deep'


def test_call_flattens_data_and_digs_physical_id(monkeypatch):
    class FakeClient:
        def get_repository_link(self, **kwargs):
            assert kwargs == {'RepositoryLinkId': 'link-1'}
            return {
                'ResponseMetadata': {'RequestId': 'x'},
                'RepositoryLinkInfo': {
                    'ConnectionArn': 'arn:conn',
                    'RepositoryLinkId': 'link-1',
                },
            }

    monkeypatch.setattr(sdk_call.boto3, 'client', lambda service: FakeClient())

    data, physical_id = sdk_call.call({
        'Service': 'codeconnections',
        'Action': 'get_repository_link',
        'Parameters': {'RepositoryLinkId': 'link-1'},
        'PhysicalResourceIdPath': 'RepositoryLinkInfo.ConnectionArn',
    })

    assert physical_id == 'arn:conn'
    assert data['RepositoryLinkInfo.ConnectionArn'] == 'arn:conn'
    assert data['RepositoryLinkInfo.RepositoryLinkId'] == 'link-1'
    # ResponseMetadata is stripped before flattening.
    assert not any(k.startswith('ResponseMetadata') for k in data)


def test_call_without_id_path_returns_none_physical_id(monkeypatch):
    class FakeClient:
        def do_thing(self, **kwargs):
            return {'ResponseMetadata': {}, 'Foo': 'bar'}

    monkeypatch.setattr(sdk_call.boto3, 'client', lambda service: FakeClient())

    data, physical_id = sdk_call.call({'Service': 's3', 'Action': 'do_thing'})

    assert physical_id is None
    assert data == {'Foo': 'bar'}
