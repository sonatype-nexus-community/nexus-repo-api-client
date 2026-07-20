#
# Copyright 2019-Present Sonatype Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import json
import os.path
import sys

import requests
from yaml import dump as yaml_dump

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

if len(sys.argv) != 2:
    print(f'Usage: {sys.argv[0]} <REPO_SERVER_URL>')
    sys.exit(0)

NXRM_SERVER_URL = sys.argv[1]
NXRM_SPEC_PATH = '/service/rest/swagger.json'


def parse_version_from_server_header(header: str) -> str:
    return header.split('/')[1].split(' ')[0]


def ensure_response(path: str, method: str, code: str, description: str) -> None:
    """NXRM has, on occasion, dropped a response entirely from the generated Swagger doc.
    Recreate it (matching the last known-good spec) before patching its content. The skeleton
    includes an empty `application/json` schema so call sites that only patch a nested key
    (e.g. `...['content']['application/json']['schema']['$ref'] = ...`) have something to patch."""
    json_spec['paths'][path][method]['responses'].setdefault(code, {
        'description': description,
        'content': {
            'application/json': {
                'schema': {}
            }
        }
    })


json_spec_response_v2 = requests.get(f'{NXRM_SERVER_URL}{NXRM_SPEC_PATH}')
NXRM_VERSION = parse_version_from_server_header(json_spec_response_v2.headers.get('Server', ''))
json_spec_v2 = json_spec_response_v2.json()

# We need to convert from Swagger 2.0 to OpenAPI 3
json_spec_response = requests.post('https://converter.swagger.io/api/convert', json=json_spec_v2)
json_spec = json_spec_response.json()

# Align OpenAPI Spec Version to 3.1.0
# json_spec['openapi'] = '3.1.0'

# Update OpenAPI Info Block
print('Updating `info`')
json_spec['info'] = {
    'title': 'Sonatype Nexus Repository Manager',
    # 'summary': 'Public REST API for Sonatype Nexus Repository',
    'description': 'This documents the available APIs into [Sonatype Nexus Repository Manager]'
                   '(https://www.sonatype.com/products/sonatype-nexus-repository) as of version ' + NXRM_VERSION + '.',
    'contact': {
        'name': 'Sonatype Community Maintainers',
        'url': 'https://github.com/sonatype-nexus-community'
    },
    'license': {
        'name': 'Apache-2.0',
        'url': 'http://www.apache.org/licenses/LICENSE-2.0.html'
    },
    'version': NXRM_VERSION
}

# Add `securitySchemes` under `components`
if 'components' in json_spec and 'securitySchemes' not in json_spec['components']:
    print('Adding `securitySchemes`...')
    json_spec['components']['securitySchemes'] = {
        'BasicAuth': {
            'type': 'http',
            'scheme': 'basic'
        }
    }
if 'security' not in json_spec:
    json_spec['security'] = [
        {
            'BasicAuth': []
        }
    ]

# Pin/Fix OperationID for GET /v1/repositories
print('Fixing and pinning OperationID for for GET /v1/repositories')
json_spec['paths']['/v1/repositories']['get']['operationId'] = 'getAllRepositories'

# Pin/Fix OperationIDs for all /v1/repositories/[FORMAT]/[TYPE]
print('Fixing and pinning OperationIDs for /v1/repositories/* paths...')
i = 0
for path in json_spec['paths']:
    if str(path).startswith('/v1/repositories/'):
        path_parts = str(path).split('/')
        if len(path_parts) > 4:
            format = path_parts[3]
            type = path_parts[4]
            for method in json_spec['paths'][path]:
                if str(method).lower() == 'get':
                    json_spec['paths'][path]['get'][
                        'operationId'] = f'get{format.capitalize()}{type.capitalize()}Repository'
                    i = i + 1
                if str(method).lower() == 'post':
                    json_spec['paths'][path]['post'][
                        'operationId'] = f'create{format.capitalize()}{type.capitalize()}Repository'
                    i = i + 1
                if str(method).lower() == 'put':
                    json_spec['paths'][path]['put'][
                        'operationId'] = f'update{format.capitalize()}{type.capitalize()}Repository'
                    i = i + 1
print(f'   Fixed {i} Repository Operations')

# Pin/Fix OperationIDs for all /v1/security/privileges/[TYPE]
print('Fixing and pinning OperationIDs for /v1/security/privileges/* paths...')
i = 0
for path in json_spec['paths']:
    if str(path).startswith('/v1/security/privileges/'):
        path_parts = str(path).split('/')
        if len(path_parts) > 4:
            t = path_parts[4]
            for method in json_spec['paths'][path]:
                if str(method).lower() == 'post':
                    json_spec['paths'][path]['post']['operationId'] = f'create{t.capitalize()}Privilege'
                    i = i + 1
                if str(method).lower() == 'put':
                    json_spec['paths'][path]['put']['operationId'] = f'update{t.capitalize()}Privilege'
                    i = i + 1
print(f'   Fixed {i} Privilege Operations')

print('Correcting Response Schema for GET Privileges Operations...')
with open(os.path.join(os.path.dirname(__file__), "snippets", "ApiPrivilegeRequest.json"), 'r') as o:
    json_spec['components']['schemas']['ApiPrivilegeRequest'] = json.load(o)

json_spec['paths']['/v1/security/privileges']['get']['operationId'] = 'getAllPrivileges'
ensure_response('/v1/security/privileges', 'get', '200', 'successful operation')
json_spec['paths']['/v1/security/privileges']['get']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            'type': 'array',
            'items': {
                '$ref': '#/components/schemas/ApiPrivilegeRequest'
            }
        }
    }
}
ensure_response('/v1/security/privileges/{privilegeName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/security/privileges/{privilegeName}']['get']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            '$ref': '#/components/schemas/ApiPrivilegeRequest'
        }
    }
}

print('     Done')

# Resolved in NXRM 3.86
# Fix Schemas relating to Repositories that are missing `format`, `type` and `url`
# repository_schemas_to_fix: list[dict[str, str]] = [
#     {'s': 'AptHostedApiRepository', 't': 'hosted', 'f': 'apt'},
#     {'s': 'AptProxyApiRepository', 't': 'proxy', 'f': 'apt'},
#     {'s': 'CargoGroupApiRepository', 't': 'group', 'f': 'cargo'},
#     {'s': 'CargoProxyApiRepository', 't': 'proxy', 'f': 'cargo'},
#     {'s': 'DockerGroupApiRepository', 't': 'group', 'f': 'docker'},
#     {'s': 'DockerHostedApiRepository', 't': 'hosted', 'f': 'docker'},
#     {'s': 'DockerProxyApiRepository', 't': 'proxy', 'f': 'docker'},
#     {'s': 'MavenHostedApiRepository', 't': 'hosted', 'f': 'maven2'},
#     {'s': 'MavenProxyApiRepository', 't': 'proxy', 'f': 'maven2'},
#     {'s': 'NugetProxyApiRepository', 't': 'proxy', 'f': 'nuget'},
#     {'s': 'SimpleApiGroupRepository', 't': 'group', 'f': None},
#     {'s': 'SimpleApiHostedRepository', 't': 'hosted', 'f': None},
#     {'s': 'NpmProxyApiRepository', 't': 'proxy', 'f': 'npm'},
#     {'s': 'SimpleApiGroupDeployRepository', 't': 'group', 'f': None},
#     {'s': 'SimpleApiProxyRepository', 't': 'proxy', 'f': None},
#     {'s': 'YumHostedApiRepository', 't': 'hosted', 'f': 'yum'}
# ]
# print('Fixing Repository Schemas...')
# for v in repository_schemas_to_fix:
#     json_spec['components']['schemas'][v['s']]['properties']['format'] = {
#         'type': 'string',
#     }
#     if v['f'] is not None:
#         json_spec['components']['schemas'][v['s']]['properties']['format']['default'] = v['f']
#     json_spec['components']['schemas'][v['s']]['properties']['type'] = {
#         'type': 'string',
#         'default': v['t']
#     }
#     json_spec['components']['schemas'][v['s']]['properties']['url'] = {
#         'type': 'string'
#     }
#     print(f'   Fixed `{v['s']}`')

# Fix Schema `StorageAttributes` - missing Write Policy
json_spec['components']['schemas']['StorageAttributes']['properties']['writePolicy'] = {
    'description': 'Controls if deployments of and updates to assets are allowed',
    'enum': ['allow', 'allow_once', 'deny'],
    'example': 'allow_once',
    'type': 'string'
}

# Update schema `HttpClientConnectionAuthenticationAttributes` to also include `preemptive`
json_spec['components']['schemas']['HttpClientConnectionAuthenticationAttributes']['properties']['preemptive'] = {
    'description': 'Whether to use pre-emptive authentication. Use with caution. Defaults to false.',
    'example': 'false',
    'type': 'boolean'
}

# Fix OperationID for some requests
operations_to_fix = [
    {'path': '/v1/blobstores/s3', 'method': 'post', 'operation_id': 'CreateS3BlobStore'},
    {'path': '/v1/blobstores/s3/{name}', 'method': 'get', 'operation_id': 'GetS3BlobStore'},
    {'path': '/v1/blobstores/s3/{name}', 'method': 'put', 'operation_id': 'UpdateS3BlobStore'},
    # `/v1/plan` and `/v1/plan/{planId}` reuse the same operationId for delete/put - disambiguate
    # the bulk (no id) operations, matching their "all"/"execute" semantics from `summary`.
    {'path': '/v1/plan', 'method': 'delete', 'operation_id': 'deleteAllPlans'},
    {'path': '/v1/plan', 'method': 'put', 'operation_id': 'executeAllPlans'},
    {'path': '/v1/plan/{planId}', 'method': 'put', 'operation_id': 'executePlan'},
]
i = 0
print('Overriding operation IDs...')
for o in operations_to_fix:
    print(f'    Setting OperationID to {o['operation_id']} for {o['method']}:{o['path']}')
    json_spec['paths'][o['path']][o['method']]['operationId'] = o['operation_id']
    i = i + 1
print(f'Overwrote {i} Operation IDs')

# Add Response Schema /system/ldap/* PATHS
print('Fixing /security/ldap/* response schemas...')
ensure_response('/v1/security/ldap', 'get', '200', 'LDAP server list returned')
json_spec['paths']['/v1/security/ldap']['get']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            'type': 'array',
            'items': {
                '$ref': '#/components/schemas/ReadLdapServerXo'
            }
        }
    }
}
ensure_response('/v1/security/ldap/{name}', 'get', '200', 'LDAP server returned')
json_spec['paths']['/v1/security/ldap/{name}']['get']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            '$ref': '#/components/schemas/ReadLdapServerXo'
        }
    }
}
print('Fixing Create/Update Schema required objects for /security/ldap/*')
temp_required: list[str] = json_spec['components']['schemas']['CreateLdapServerXo']['required']
# temp_required.remove('groupType') Removed for 3.90.1
json_spec['components']['schemas']['CreateLdapServerXo']['required'] = temp_required
json_spec['components']['schemas']['ReadLdapServerXo']['required'] = temp_required
json_spec['components']['schemas']['UpdateLdapServerXo']['required'] = temp_required
print('Done')

# Not required from NXRM 3.85.0 onwards
# print('Fixing response schema for IQ Connection...')
# json_spec['paths']['/v1/iq']['get']['responses']['200']['content'] = {
#     'application/json': {
#         'schema': {
#             '$ref': '#/components/schemas/IqConnectionXo'
#         }
#     }
# }
# print('     Done')

print('Adding missing 201 empty responses...')
paths_missing_201: dict[str, list[str]] = {
    '/v1/security/privileges/application': ['post'],
    '/v1/security/privileges/repository-admin': ['post'],
    '/v1/security/privileges/repository-content-selector': ['post'],
    '/v1/security/privileges/repository-view': ['post'],
    '/v1/security/privileges/script': ['post'],
    '/v1/security/privileges/wildcard': ['post'],
}
for p, ms in paths_missing_201.items():
    for m in ms:
        json_spec['paths'][p][m]['responses'].update({'201': {'content': {}, 'description': 'Success'}})
print('     Done')

print('Adding missing 204 empty responses...')
paths_missing_204: dict[str, list[str]] = {
    '/v1/security/privileges/application/{privilegeName}': ['put'],
    '/v1/security/privileges/repository-admin/{privilegeName}': ['put'],
    '/v1/security/privileges/repository-content-selector/{privilegeName}': ['put'],
    '/v1/security/privileges/repository-view/{privilegeName}': ['put'],
    '/v1/security/privileges/script/{privilegeName}': ['put'],
    '/v1/security/privileges/wildcard/{privilegeName}': ['put'],
    '/v1/security/roles/{id}': ['delete'],
    '/v1/security/users/{userId}': ['put'],
    '/v1/security/users/{userId}/change-password': ['put']
}
for p, ms in paths_missing_204.items():
    for m in ms:
        json_spec['paths'][p][m]['responses'].update({'204': {'content': {}, 'description': 'Success'}})
print('     Done')

print('Correcting schema InputStream...')
json_spec['components']['schemas']['InputStream'] = {
    'type': 'string',
    'format': 'binary'
}
print('     Done')

print('Correcting response schema for GET /v1/repositories/docker/hosted/{name}...')
json_spec['components']['schemas']['DockerHostedApiRepository']['properties']['storage'] = {
    '$ref': '#/components/schemas/DockerHostedStorageAttributes'
}
print('     Done')

print('Correcting response schema for GET /v1/repositories/pypi/proxy/{name}...')
json_spec['components']['schemas'].update({
    'PyPiProxyApiRepository': {
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'format': {'type': 'string', 'default': 'pypi'},
            'httpClient': {'$ref': '#/components/schemas/HttpClientAttributes'},
            'name': {
                'description': 'A unique identifier for this repository',
                'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$',
                'type': 'string',
            },
            'negativeCache': {'$ref': '#/components/schemas/NegativeCacheAttributes'},
            'online': {
                'description': 'Whether this repository accepts incoming requests',
                'type': 'boolean',
            },
            'proxy': {'$ref': '#/components/schemas/ProxyAttributes'},
            'pypi': {'$ref': '#/components/schemas/PyPiProxyAttributes'},
            'replication': {'$ref': '#/components/schemas/ReplicationAttributes'},
            'routingRuleName': {'type': 'string'},
            'storage': {'$ref': '#/components/schemas/StorageAttributes'},
            'type': {'type': 'string', 'default': 'proxy'},
            'url': {'type': 'string'},
        },
        'required': [
            'format', 'httpClient', 'name', 'negativeCache', 'online', 'proxy', 'pypi', 'storage', 'type', 'url'
        ]
    }
})
ensure_response('/v1/repositories/pypi/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/pypi/proxy/{repositoryName}']['get']['responses']['200']['content'][('application'
                                                                                                          '/json')][
    'schema']['$ref'] = '#/components/schemas/PyPiProxyApiRepository'
print('     Done')

print('Correcting response schema for GET /v1/repositories/{format}/{group}/{name} where writable member...')
paths_to_fix_writable_member = [
    '/v1/repositories/pypi/group/{repositoryName}'
]
for p in paths_to_fix_writable_member:
    ensure_response(p, 'get', '200', 'successful operation')
    json_spec['paths'][p]['get']['responses']['200']['content']['application/json']['schema'] = {
        '$ref': '#/components/schemas/SimpleApiGroupDeployRepository'
    }
# Resolved in NXRM 3.85
# json_spec['components']['schemas']['PypiGroupRepositoryApiRequest']['properties']['group'] = {
#     '$ref': '#/components/schemas/GroupDeployAttributes'
# }
print('     Done')

print('Correcting response schema for GET /v1/repositories/raw/*/{name}...')
json_spec['components']['schemas'].update({
    'RawGroupApiRepository': {
        'properties': {
            'format': {'type': 'string', 'default': 'raw'},
            'group': {'$ref': '#/components/schemas/GroupAttributes'},
            'name': {
                'description': 'A unique identifier for this repository',
                'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$',
                'type': 'string',
            },
            'online': {
                'description': 'Whether this repository accepts incoming requests',
                'type': 'boolean',
            },
            'raw': {'$ref': '#/components/schemas/RawAttributes'},
            'storage': {'$ref': '#/components/schemas/StorageAttributes'},
            'type': {'type': 'string', 'default': 'group'},
            'url': {'type': 'string'},
        },
        'required': [
            'format', 'group', 'name', 'online', 'raw', 'storage', 'type', 'url'
        ]
    }
})
ensure_response('/v1/repositories/raw/group/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/raw/group/{repositoryName}']['get']['responses']['200']['content'][('application'
                                                                                                         '/json')][
    'schema']['$ref'] = '#/components/schemas/RawGroupApiRepository'
json_spec['components']['schemas'].update({
    'RawHostedApiRepository': {
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'component': {'$ref': '#/components/schemas/ComponentAttributes'},
            'format': {'type': 'string', 'default': 'raw'},
            'name': {
                'description': 'A unique identifier for this repository',
                'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$',
                'type': 'string',
            },
            'online': {
                'description': 'Whether this repository accepts incoming requests',
                'type': 'boolean',
            },
            'raw': {'$ref': '#/components/schemas/RawAttributes'},
            'storage': {'$ref': '#/components/schemas/HostedStorageAttributes'},
            'type': {'type': 'string', 'default': 'hosted'},
            'url': {'type': 'string'},
        },
        'required': [
            'format', 'name', 'online', 'raw', 'storage', 'type', 'url'
        ]
    }
})
ensure_response('/v1/repositories/raw/hosted/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/raw/hosted/{repositoryName}']['get']['responses']['200']['content'][('application'
                                                                                                          '/json')][
    'schema']['$ref'] = '#/components/schemas/RawHostedApiRepository'
json_spec['components']['schemas'].update({
    'RawProxyApiRepository': {
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'format': {'type': 'string', 'default': 'pypi'},
            'httpClient': {'$ref': '#/components/schemas/HttpClientAttributes'},
            'name': {
                'description': 'A unique identifier for this repository',
                'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$',
                'type': 'string',
            },
            'negativeCache': {'$ref': '#/components/schemas/NegativeCacheAttributes'},
            'online': {
                'description': 'Whether this repository accepts incoming requests',
                'type': 'boolean',
            },
            'proxy': {'$ref': '#/components/schemas/ProxyAttributes'},
            'raw': {'$ref': '#/components/schemas/RawAttributes'},
            'replication': {'$ref': '#/components/schemas/ReplicationAttributes'},
            'routingRuleName': {'type': 'string'},
            'storage': {'$ref': '#/components/schemas/StorageAttributes'},
            'type': {'type': 'string', 'default': 'raw'},
            'url': {'type': 'string'},
        },
        'required': [
            'format', 'httpClient', 'name', 'negativeCache', 'online', 'proxy', 'raw', 'storage', 'type', 'url'
        ]
    }
})
ensure_response('/v1/repositories/raw/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/raw/proxy/{repositoryName}']['get']['responses']['200']['content'][('application'
                                                                                                         '/json')][
    'schema']['$ref'] = '#/components/schemas/RawProxyApiRepository'
print('     Done')

print('Correcting Schema CargoGroupApiRepository...')
json_spec['components']['schemas']['CargoGroupApiRepository']['properties']['group'] = {
    '$ref': '#/components/schemas/GroupAttributes'
}
print('     Done')

print('Correcting response schema for GET /v1/repositories/conan/group/{repositoryName}...')
ensure_response('/v1/repositories/conan/group/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/conan/group/{repositoryName}']['get']['responses']['200']['content'][('application'
                                                                                                           '/json')][
    'schema']['$ref'] = '#/components/schemas/SimpleApiGroupDeployRepository'
print('     Done')

print('Injecting requestBody schema for PUT /v1/tasks/{taskId}...')
json_spec['paths']['/v1/tasks/{taskId}']['put']['requestBody']['content']['application/json']['schema'] = {
    'properties': {
        'alertEmail': {
            'description': 'e-mail for task notifications.',
            'type': 'string'
        },
        'enabled': {
            'description': 'Indicates if the task would be enabled.',
            'type': 'boolean'
        },
        'frequency': {
            '$ref': '#/components/schemas/FrequencyXO'
        },
        'name': {
            'description': 'The name of the task template.',
            'type': 'string'
        },
        'notificationCondition': {
            'description': 'Condition required to notify a task execution.',
            'enum': ['FAILURE', 'SUCCESS_FAILURE'],
            'type': 'string'
        },
        'properties': {
            'additionalProperties': {
                'type': 'string'
            },
            'description': 'Additional properties for the task',
            'type': 'object'
        },
        'type': {
            'description': 'The type of task to be created.',
            'type': 'string'
        }
    },
    'required': [
        'enabled', 'frequency', 'name', 'notificationCondition'
    ]
}
print('     Done')

print('Injecting Response Schema for POST /v1/tasks...')
json_spec['paths']['/v1/tasks']['post']['responses'] = {
    '201': {
        'content': {
            'application/json': {
                'schema': {
                    'properties': {
                        'id': {
                            'description': 'Task ID',
                            'format': 'uuid',
                            'type': 'string'
                        }
                    },
                    'required': ['id']
                }
            }
        },
        'description': 'Task created successfully'
    }
}
print('     Done')

print('Adding missing `tags` field for schema `ComponentXO`...')
json_spec['components']['schemas']['ComponentXO']['properties']['tags'] = {
    'items': {
        'type': 'string'
    },
    'type': 'array'
}
print('     Done')

print('Correct `attributes` field for schema `TagXO`...')
json_spec['components']['schemas']['TagXO']['properties']['attributes'] = {
    'additionalProperties': {},
    'type': 'object'
}
print('     Done')

print('Correct response schema for `GET /v1/repositories/conan/proxy/{repositoryName}`...')
json_spec['components']['schemas'].update({
    'ConanProxyApiRepository': {
        'allOf': [
            {
                '$ref': '#/components/schemas/ConanProxyRepositoryApiRequest'
            },
            {
                'type': 'object',
                'required': ['format', 'type', 'url'],
                'properties': {
                    'format': {'type': 'string', 'default': 'conan'},
                    'type': {'type': 'string', 'default': 'proxy'},
                    'url': {'type': 'string'},
                    'routingRuleName': {
                        'description': 'The name of the routing rule assigned to this repository',
                        'type': 'string'
                    }
                }
            }
        ]
    }
})
ensure_response('/v1/repositories/conan/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/conan/proxy/{repositoryName}']['get']['responses']['200']['content'][
    'application/json']['schema'] = {
    '$ref': '#/components/schemas/ConanProxyApiRepository'
}
print('     Done')

print('Patching schema `HttpSettingsXo`...')
json_spec['components']['schemas']['HttpSettingsXo']['properties']['nonProxyHosts'].update({'nullable': 'true'})
json_spec['components']['schemas']['HttpSettingsXo']['properties']['userAgent'].update({'nullable': 'true'})
json_spec['components']['schemas']['ProxySettingsXo'].update({'nullable': 'true'})
print('     Done')

print('Inject response schema for POST /v1/iq/verify-connection and set OperationId')
json_spec['paths']['/v1/iq/verify-connection']['post']['operationId'] = 'verifyIqConnection'
ensure_response('/v1/iq/verify-connection', 'post', '200',
                 'Connection verification complete, check response body for result')
json_spec['paths']['/v1/iq/verify-connection']['post']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            '$ref': '#/components/schemas/IqConnectionVerificationXo'
        }
    }
}
print('     Done')

print('Inject response schema for GET /v1/repositories/terraform/proxy/{repositoryName}')
ensure_response('/v1/repositories/terraform/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/terraform/proxy/{repositoryName}']['get']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            '$ref': '#/components/schemas/TerraformProxyApiRepository'
        }
    }
}
print('     Done')

print('Complete type for `terraform.uploadType` for POST /v1/components')
# NXRM has, on occasion, dropped the entire multipart `requestBody` for this operation from the
# generated Swagger doc. Re-create it (as seen in NXRM 3.93) before patching `terraform.uploadType`.
if 'requestBody' not in json_spec['paths']['/v1/components']['post']:
    with open(os.path.join(os.path.dirname(__file__), "snippets", "ComponentsUploadRequestBody.json"), 'r') as o:
        json_spec['paths']['/v1/components']['post']['requestBody'] = json.load(o)
json_spec['paths']['/v1/components']['post']['requestBody']['content']['multipart/form-data']['schema']['properties'][
    'terraform.uploadType'] = {
    'description': 'terraform Upload Type',
    'enum': ['module', 'provider'],
    'type': 'string'
}
print('     Done')

print('Correct response schema for POST /v1/tasks')
json_spec['paths']['/v1/tasks']['post']['responses']['201']['content']['application/json'] = {
    'schema': {
        '$ref': '#/components/schemas/TaskXO'
    }
}
print('     Done')

print('Fix `TerraformHostedRepositoryApiRequest` schema (missing fields)')
json_spec['components']['schemas']['TerraformHostedRepositoryApiRequest']['properties'].update({
    'format': {
        'type': 'string',
        'default': 'terraform'
    },
    'type': {
        'type': 'string',
        'default': 'hosted'
    },
    'url': {
        'type': 'string'
    },
    'component': {
        '$ref': '#/components/schemas/ComponentAttributes'
    }
})
print('     Done')

print('Correct response schema for GET /v1/repositories/terraform/hosted/{repositoryName')
ensure_response('/v1/repositories/terraform/hosted/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/terraform/hosted/{repositoryName}']['get']['responses']['200']['content'][
    'application/json'] = {
    'schema': {
        '$ref': '#/components/schemas/TerraformHostedRepositoryApiRequest'
    }
}
print('     Done')

print('Correct response schema for GET /v1/repositories/swift/proxy/{repositoryName}')
ensure_response('/v1/repositories/swift/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/swift/proxy/{repositoryName}']['get']['responses']['200']['content'][
    'application/json'] = {
    'schema': {
        '$ref': '#/components/schemas/SwiftProxyApiRepository'
    }
}
print('     Done')

# Updates for NXRM 3.92.x
print('Correct invalid schema name "Licensed Solution"...')
if 'Licensed Solution' in json_spec['components']['schemas']:
    json_spec['components']['schemas']['LicensedSolution'] = json_spec['components']['schemas']['Licensed Solution']
    del json_spec['components']['schemas']['Licensed Solution']
    # Only repoint the ref when we actually performed the rename above - otherwise NXRM is already
    # emitting a validly-named schema (e.g. `LicensedSolutionXO`) and the existing $ref is correct;
    # forcibly overwriting it here would point at a component that no longer exists.
    json_spec['components']['schemas']['IqConnectionXo']['properties']['licensedSolutions']['items'][
        '$ref'] = '#/components/schemas/LicensedSolution'
    print('     Done')
else:
    # Resolved upstream - NXRM no longer emits the schema under the invalid, space-containing name.
    print('     Skipped - schema name already correct')

# Patch TerraformProxyApiRepository schema - now missing `terraform` item
json_spec['components']['schemas']['TerraformProxyApiRepository']['properties']['terraform'] = {
    '$ref': '#/components/schemas/TerraformAttributes'
}

print('Correct response schema for GET /v1/repositories/yum/proxy/{repositoryName}...')
json_spec['components']['schemas'].update({
    'YumProxyApiRepository': {
        'allOf': [
            {
                '$ref': '#/components/schemas/YumProxyRepositoryApiRequest'
            },
            {
                'type': 'object',
                'required': ['format', 'type', 'url'],
                'properties': {
                    'format': {'type': 'string', 'default': 'yum'},
                    'type': {'type': 'string', 'default': 'proxy'},
                    'url': {'type': 'string'},
                    'routingRuleName': {
                        'description': 'The name of the routing rule assigned to this repository',
                        'type': 'string'
                    }
                }
            }
        ]
    }
})
ensure_response('/v1/repositories/yum/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/yum/proxy/{repositoryName}']['get']['responses']['200']['content'][
    'application/json']['schema'] = {
    '$ref': '#/components/schemas/YumProxyApiRepository'
}
print('     Done')

print('Correct response schema for GET /v1/repositories/yum/group/{repositoryName}...')
json_spec['components']['schemas'].update({
    'YumGroupApiRepository': {
        'allOf': [
            {
                '$ref': '#/components/schemas/YumGroupRepositoryApiRequest'
            },
            {
                'type': 'object',
                'required': ['format', 'type', 'url'],
                'properties': {
                    'format': {'type': 'string', 'default': 'yum'},
                    'type': {'type': 'string', 'default': 'group'},
                    'url': {'type': 'string'}
                }
            }
        ]
    }
})
ensure_response('/v1/repositories/yum/group/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/yum/group/{repositoryName}']['get']['responses']['200']['content'][
    'application/json']['schema'] = {
    '$ref': '#/components/schemas/YumGroupApiRepository'
}
print('     Done')

print('Correct response schema for GET /v1/repositories/alpine/hosted/{repositoryName}...')
json_spec['components']['schemas'].update({
    'AlpineHostedApiRepository': {
        'allOf': [
            {
                '$ref': '#/components/schemas/AlpineHostedRepositoryApiRequest'
            },
            {
                'type': 'object',
                'required': ['format', 'type', 'url'],
                'properties': {
                    'format': {'type': 'string', 'default': 'alpine'},
                    'type': {'type': 'string', 'default': 'hosted'},
                    'url': {'type': 'string'},
                }
            }
        ]
    }
})
ensure_response('/v1/repositories/alpine/hosted/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/alpine/hosted/{repositoryName}']['get']['responses']['200']['content'][
    'application/json']['schema'] = {
    '$ref': '#/components/schemas/AlpineHostedApiRepository'
}
print('     Done')

print('Correct response schema for GET /v1/repositories/alpine/proxy/{repositoryName}...')
json_spec['components']['schemas'].update({
    'AlpineProxyApiRepository': {
        'allOf': [
            {
                '$ref': '#/components/schemas/AlpineProxyRepositoryApiRequest'
            },
            {
                'type': 'object',
                'required': ['format', 'type', 'url'],
                'properties': {
                    'format': {'type': 'string', 'default': 'alpine'},
                    'type': {'type': 'string', 'default': 'proxy'},
                    'url': {'type': 'string'},
                    'routingRuleName': {
                        'description': 'The name of the routing rule assigned to this repository',
                        'type': 'string'
                    }
                }
            }
        ]
    }
})
ensure_response('/v1/repositories/alpine/proxy/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/alpine/proxy/{repositoryName}']['get']['responses']['200']['content'][
    'application/json']['schema'] = {
    '$ref': '#/components/schemas/AlpineProxyApiRepository'
}
print('     Done')

print('Correct response schema for GET /v1/repositories/alpine/group/{repositoryName}...')
json_spec['components']['schemas'].update({
    'AlpineGroupApiRepository': {
        'allOf': [
            {
                '$ref': '#/components/schemas/AlpineGroupRepositoryApiRequest'
            },
            {
                'type': 'object',
                'required': ['format', 'type', 'url'],
                'properties': {
                    'format': {'type': 'string', 'default': 'alpine'},
                    'type': {'type': 'string', 'default': 'group'},
                    'url': {'type': 'string'},
                }
            }
        ]
    }
})
ensure_response('/v1/repositories/alpine/group/{repositoryName}', 'get', '200', 'successful operation')
json_spec['paths']['/v1/repositories/alpine/group/{repositoryName}']['get']['responses']['200']['content'][
    'application/json']['schema'] = {
    '$ref': '#/components/schemas/AlpineGroupApiRepository'
}
print('     Done')

# NXRM has, on occasion, dropped `description` from the `200` response of repository-format GET
# endpoints across many/all formats (not just the ones patched by name above). OpenAPI Generator
# requires it, so backfill it wherever it's missing rather than special-casing every format.
print('Backfilling missing `200` response descriptions for /v1/repositories/* GET endpoints...')
i = 0
for path in json_spec['paths']:
    if str(path).startswith('/v1/repositories/'):
        get_op = json_spec['paths'][path].get('get')
        if get_op and '200' in get_op.get('responses', {}) and 'description' not in get_op['responses']['200']:
            get_op['responses']['200']['description'] = 'successful operation'
            i = i + 1
print(f'   Fixed {i} missing response descriptions')

# Correcting response content dropped from several `200` responses (description was retained,
# but `content` was not) - restoring the content/examples last seen in 3.93.2.
print('Correcting missing `200` response content...')
json_spec['paths']['/v1/status/check']['get']['responses']['200']['content'] = {
    'application/json': {
        'schema': {
            'type': 'object',
            'additionalProperties': {
                '$ref': '#/components/schemas/Result'
            }
        }
    }
}
json_spec['paths']['/v1/system/eula']['get']['responses']['200']['content'] = {
    'application/json': {
        'example': {
            'accepted': False,
            'disclaimer': 'Use of Sonatype Nexus Repository - Community Edition is governed by the End '
                          'User License Agreement at https://links.sonatype.com/products/nxrm/ce-eula. '
                          'By returning the value from ‘accepted:false’ to ‘accepted:true’, '
                          'you acknowledge that you have read and agree to the End User License Agreement '
                          'at https://links.sonatype.com/products/nxrm/ce-eula.'
        }
    }
}
json_spec['paths']['/v1/security/ssrf-protection']['get']['responses']['200']['content'] = {
    'application/json': {
        'example': {
            'enabled': True,
            'allowedDomains': ['internal.corp.com', 'registry.local'],
            'allowedIPs': ['10.0.0.50', '192.168.1.100']
        }
    }
}
json_spec['paths']['/v1/monthly-metrics']['get']['responses']['200']['content'] = {
    'application/json': {
        'example': [
            {
                'metricDate': '2025-03-01T00:00:00Z',
                'requestCount': 0,
                'componentCount': 0,
                'percentageChangeRequest': 'N/A',
                'percentageChangeComponent': 'N/A'
            }
        ]
    }
}
json_spec['paths']['/v1/usage-history']['get']['responses']['200']['content'] = {
    'application/json': {
        'example': {
            'metric': 'requests',
            'period': 'daily',
            'data': [
                {'date': '2026-01-18', 'value': 1234}
            ]
        }
    }
}
print('     Done')

# Correcting several responses that were relabeled from `200` to `default`. The schema/content
# is otherwise unchanged - move it back under `200` with its original description.
print('Correcting responses relabeled from `200` to `default`...')
paths_relabel_default_to_200 = [
    ('/v1/repositories', 'get'),
    ('/v1/search', 'get'),
    ('/v1/search/assets', 'get'),
    ('/v1/tasks', 'get'),
    ('/v1/tasks/templates', 'get'),
    ('/v1/tasks/templates/{typeId}', 'get'),
    ('/v1/capabilities', 'get'),
    ('/v1/capabilities', 'post'),
    ('/v1/capabilities/types', 'get'),
    ('/v1/blobstores', 'get'),
    ('/v1/blobstores/{name}/quota-status', 'get'),
    ('/v1/security/realms/active', 'get'),
    ('/v1/security/realms/available', 'get'),
    ('/v1/security/ldap/templates', 'get'),
    ('/v1/security/ldap/verify-user-mapping', 'post'),
    ('/v1/security/user-tokens', 'get'),
    ('/v1/security/user-tokens', 'put'),
    ('/v1/script', 'get'),
    ('/v1/system/license', 'get'),
    ('/v1/system/license', 'post'),
    ('/v1/tags', 'get'),
    ('/v1/formats/upload-specs', 'get'),
    ('/v1/formats/{format}/upload-specs', 'get'),
    ('/v1/lifecycle/phase', 'get'),
]
i = 0
for p, m in paths_relabel_default_to_200:
    responses = json_spec['paths'][p][m]['responses']
    default_response = responses.pop('default', None)
    if default_response is not None:
        default_response['description'] = 'successful operation'
        responses['200'] = default_response
        i = i + 1
print(f'   Relabeled {i} responses')

# Correcting several `200` response objects that were dropped entirely (only error responses
# remain) - recreate them, matching the last known-good description/content from 3.93.2.
print('Correcting missing `200` responses...')
paths_missing_200: list[dict] = [
    {'path': '/v1/assets', 'method': 'get', 'schema': {'$ref': '#/components/schemas/PageAssetXO'}},
    {'path': '/v1/assets/{id}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/AssetXO'}},
    {'path': '/v1/components', 'method': 'get', 'schema': {'$ref': '#/components/schemas/PageComponentXO'}},
    {'path': '/v1/components/{id}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/ComponentXO'}},
    {'path': '/v1/email', 'method': 'get', 'schema': {'$ref': '#/components/schemas/ApiEmailConfiguration'}},
    {'path': '/v1/repositories/{repositoryName}', 'method': 'get',
     'schema': {'$ref': '#/components/schemas/RepositoryXO'}},
    {'path': '/v1/routing-rules', 'method': 'get',
     'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/RoutingRuleXO'}}},
    {'path': '/v1/routing-rules/{name}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/RoutingRuleXO'}},
    {'path': '/v1/script/{name}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/ScriptXO'}},
    {'path': '/v1/script/{name}/run', 'method': 'post', 'schema': {'$ref': '#/components/schemas/ScriptResultXO'}},
    {'path': '/v1/security/anonymous', 'method': 'get',
     'schema': {'$ref': '#/components/schemas/AnonymousAccessSettingsXO'}},
    {'path': '/v1/security/anonymous', 'method': 'put',
     'schema': {'$ref': '#/components/schemas/AnonymousAccessSettingsXO'}},
    {'path': '/v1/security/roles', 'method': 'get',
     'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/RoleXOResponse'}}},
    {'path': '/v1/security/roles', 'method': 'post', 'schema': {'$ref': '#/components/schemas/RoleXOResponse'}},
    {'path': '/v1/security/roles/{id}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/RoleXOResponse'}},
    {'path': '/v1/security/ssl', 'method': 'get', 'schema': {'$ref': '#/components/schemas/ApiCertificate'}},
    {'path': '/v1/security/ssl/truststore', 'method': 'get',
     'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/ApiCertificate'}}},
    {'path': '/v1/security/user-sources', 'method': 'get',
     'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/ApiUserSource'}}},
    {'path': '/v1/security/users', 'method': 'get',
     'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/ApiUser'}}},
    {'path': '/v1/security/users', 'method': 'post', 'schema': {'$ref': '#/components/schemas/ApiUser'}},
    {'path': '/v1/system/node', 'method': 'get', 'schema': {'$ref': '#/components/schemas/NodeInformation'}},
    {'path': '/v1/tags/{name}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/TagXO'}},
    {'path': '/v1/tags/{name}', 'method': 'put', 'schema': {'$ref': '#/components/schemas/TagXO'}},
    {'path': '/v1/tasks/{id}', 'method': 'get', 'schema': {'$ref': '#/components/schemas/TaskXO'}},
    {'path': '/beta/status/check/cluster', 'method': 'get',
     'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/SystemCheckResultsApiDTO'}}},
]
for entry in paths_missing_200:
    ensure_response(entry['path'], entry['method'], '200', 'successful operation')
    json_spec['paths'][entry['path']][entry['method']]['responses']['200']['content'] = {
        'application/json': {
            'schema': entry['schema']
        }
    }
print(f'   Restored {len(paths_missing_200)} `200` responses')

# Correcting several repository-format polymorphic GET endpoints whose `200` response schema
# was replaced by the generic `AbstractApiRepository` under a relabeled `default` response. Some
# of these formats reuse a schema that still exists (`SimpleApiGroupRepository`); others reuse a
# schema that was deleted from `components.schemas` entirely - recreate those verbatim from
# 3.93.2 before repointing the ref.
# Note: `/v1/repositories/helm/group/{repositoryName}` is deliberately excluded here - it already
# has its own valid concrete schema (`HelmGroupApiRepository`) under `200`.
print('Correcting repository schemas under `200`...')
json_spec['components']['schemas'].update({
    'AptHostedApiRepository': {
        'type': 'object',
        'required': ['apt', 'aptSigning', 'online', 'storage'],
        'properties': {
            'apt': {'$ref': '#/components/schemas/AptHostedRepositoriesAttributes'},
            'aptSigning': {'$ref': '#/components/schemas/AptSigningRepositoriesAttributes'},
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'component': {'$ref': '#/components/schemas/ComponentAttributes'},
            'format': {'type': 'string', 'description': 'Component format held in this repository',
                       'example': 'apt'},
            'name': {'type': 'string', 'description': 'A unique identifier for this repository',
                     'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$', 'example': 'internal',
                     'readOnly': True},
            'online': {'type': 'boolean', 'description': 'Whether this repository accepts incoming requests',
                       'example': True, 'readOnly': True},
            'storage': {'$ref': '#/components/schemas/HostedStorageAttributes'},
            'type': {'type': 'string',
                     'description': 'Controls if deployments of and updates to artifacts are allowed',
                     'enum': ['hosted', 'proxy', 'group'], 'example': 'hosted'},
            'url': {'type': 'string', 'description': 'URL to the repository',
                    'example': 'http://localhost:8081/repository/apt-example', 'readOnly': True},
        }
    },
    'AptProxyApiRepository': {
        'type': 'object',
        'required': ['apt', 'httpClient', 'negativeCache', 'online', 'proxy', 'storage'],
        'properties': {
            'apt': {'$ref': '#/components/schemas/AptProxyRepositoriesAttributes'},
            'aptSigning': {'$ref': '#/components/schemas/AptSigningRepositoriesAttributes'},
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'format': {'type': 'string', 'description': 'Component format held in this repository',
                       'example': 'apt'},
            'httpClient': {'$ref': '#/components/schemas/HttpClientAttributes'},
            'name': {'type': 'string', 'description': 'A unique identifier for this repository',
                     'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$', 'example': 'internal'},
            'negativeCache': {'$ref': '#/components/schemas/NegativeCacheAttributes'},
            'online': {'type': 'boolean', 'description': 'Whether this repository accepts incoming requests',
                       'example': True},
            'proxy': {'$ref': '#/components/schemas/ProxyAttributes'},
            'replication': {'$ref': '#/components/schemas/ReplicationAttributes'},
            'routingRuleName': {'type': 'string',
                                'description': 'The name of the routing rule assigned to this repository'},
            'storage': {'$ref': '#/components/schemas/StorageAttributes'},
            'type': {'type': 'string',
                     'description': 'Controls if deployments of and updates to artifacts are allowed',
                     'enum': ['hosted', 'proxy', 'group'], 'example': 'proxy'},
            'url': {'type': 'string', 'description': 'URL to the repository',
                    'example': 'http://localhost:8081/repository/apt-example'},
        }
    },
    'MavenHostedApiRepository': {
        'type': 'object',
        'required': ['maven', 'online', 'storage'],
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'component': {'$ref': '#/components/schemas/ComponentAttributes'},
            'format': {'type': 'string', 'description': 'Component format held in this repository',
                       'example': 'maven2'},
            'maven': {'$ref': '#/components/schemas/MavenAttributes'},
            'name': {'type': 'string', 'description': 'A unique identifier for this repository',
                     'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$', 'example': 'internal'},
            'online': {'type': 'boolean', 'description': 'Whether this repository accepts incoming requests',
                       'example': True},
            'storage': {'$ref': '#/components/schemas/HostedStorageAttributes'},
            'type': {'type': 'string',
                     'description': 'Controls if deployments of and updates to artifacts are allowed',
                     'enum': ['hosted', 'proxy', 'group'], 'example': 'hosted'},
            'url': {'type': 'string', 'description': 'URL to the repository',
                    'example': 'http://localhost:8081/repository/maven2-example'},
        }
    },
    'MavenProxyApiRepository': {
        'type': 'object',
        'required': ['httpClient', 'maven', 'negativeCache', 'online', 'proxy', 'storage'],
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'format': {'type': 'string', 'description': 'Component format held in this repository',
                       'example': 'maven2'},
            'httpClient': {'$ref': '#/components/schemas/HttpClientAttributes'},
            'maven': {'$ref': '#/components/schemas/MavenAttributes'},
            'name': {'type': 'string', 'description': 'A unique identifier for this repository',
                     'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$', 'example': 'internal'},
            'negativeCache': {'$ref': '#/components/schemas/NegativeCacheAttributes'},
            'online': {'type': 'boolean', 'description': 'Whether this repository accepts incoming requests',
                       'example': True},
            'proxy': {'$ref': '#/components/schemas/ProxyAttributes'},
            'replication': {'$ref': '#/components/schemas/ReplicationAttributes'},
            'routingRuleName': {'type': 'string',
                                'description': 'The name of the routing rule assigned to this repository'},
            'storage': {'$ref': '#/components/schemas/StorageAttributes'},
            'type': {'type': 'string',
                     'description': 'Controls if deployments of and updates to artifacts are allowed',
                     'enum': ['hosted', 'proxy', 'group'], 'example': 'proxy'},
            'url': {'type': 'string', 'description': 'URL to the repository',
                    'example': 'http://localhost:8081/repository/maven2-example'},
        }
    },
    'SimpleApiHostedRepository': {
        'type': 'object',
        'required': ['online', 'storage'],
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'component': {'$ref': '#/components/schemas/ComponentAttributes'},
            'format': {'type': 'string', 'description': 'Component format held in this repository',
                       'example': 'simpleapihostedrepository'},
            'name': {'type': 'string', 'description': 'A unique identifier for this repository',
                     'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$', 'example': 'internal'},
            'online': {'type': 'boolean', 'description': 'Whether this repository accepts incoming requests',
                       'example': True},
            'storage': {'$ref': '#/components/schemas/HostedStorageAttributes'},
            'type': {'type': 'string',
                     'description': 'Controls if deployments of and updates to artifacts are allowed',
                     'enum': ['hosted', 'proxy', 'group'], 'example': 'hosted'},
            'url': {'type': 'string', 'description': 'URL to the repository',
                    'example': 'http://localhost:8081/repository/simpleapihostedrepository-example'},
        }
    },
    'SimpleApiProxyRepository': {
        'type': 'object',
        'required': ['httpClient', 'negativeCache', 'online', 'proxy', 'storage'],
        'properties': {
            'cleanup': {'$ref': '#/components/schemas/CleanupPolicyAttributes'},
            'format': {'type': 'string', 'description': 'Component format held in this repository',
                       'example': 'simpleapiproxyrepository'},
            'httpClient': {'$ref': '#/components/schemas/HttpClientAttributes'},
            'name': {'type': 'string', 'description': 'A unique identifier for this repository',
                     'pattern': '^[a-zA-Z0-9\\-]{1}[a-zA-Z0-9_\\-\\.]*$', 'example': 'internal'},
            'negativeCache': {'$ref': '#/components/schemas/NegativeCacheAttributes'},
            'online': {'type': 'boolean', 'description': 'Whether this repository accepts incoming requests',
                       'example': True},
            'proxy': {'$ref': '#/components/schemas/ProxyAttributes'},
            'replication': {'$ref': '#/components/schemas/ReplicationAttributes'},
            'routingRuleName': {'type': 'string',
                                'description': 'The name of the routing rule assigned to this repository'},
            'storage': {'$ref': '#/components/schemas/StorageAttributes'},
            'type': {'type': 'string',
                     'description': 'Controls if deployments of and updates to artifacts are allowed',
                     'enum': ['hosted', 'proxy', 'group'], 'example': 'proxy'},
            'url': {'type': 'string', 'description': 'URL to the repository',
                    'example': 'http://localhost:8081/repository/simpleapiproxyrepository-example'},
        }
    },
})
paths_to_fix_repository_schema_ref = [
    ('/v1/repositories/apt/hosted/{repositoryName}', '#/components/schemas/AptHostedApiRepository'),
    ('/v1/repositories/apt/proxy/{repositoryName}', '#/components/schemas/AptProxyApiRepository'),
    ('/v1/repositories/cargo/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/cocoapods/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/composer/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/conan/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/conda/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/conda/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/gitlfs/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/go/group/{repositoryName}', '#/components/schemas/SimpleApiGroupRepository'),
    ('/v1/repositories/go/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/go/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/helm/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/helm/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/huggingface/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/maven/group/{repositoryName}', '#/components/schemas/SimpleApiGroupRepository'),
    ('/v1/repositories/maven/hosted/{repositoryName}', '#/components/schemas/MavenHostedApiRepository'),
    ('/v1/repositories/maven/proxy/{repositoryName}', '#/components/schemas/MavenProxyApiRepository'),
    ('/v1/repositories/npm/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/nuget/group/{repositoryName}', '#/components/schemas/SimpleApiGroupRepository'),
    ('/v1/repositories/nuget/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/p2/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/pub/group/{repositoryName}', '#/components/schemas/SimpleApiGroupRepository'),
    ('/v1/repositories/pub/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/pub/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/pypi/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/r/group/{repositoryName}', '#/components/schemas/SimpleApiGroupRepository'),
    ('/v1/repositories/r/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/r/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/rubygems/group/{repositoryName}', '#/components/schemas/SimpleApiGroupRepository'),
    ('/v1/repositories/rubygems/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
    ('/v1/repositories/rubygems/proxy/{repositoryName}', '#/components/schemas/SimpleApiProxyRepository'),
    ('/v1/repositories/swift/hosted/{repositoryName}', '#/components/schemas/SimpleApiHostedRepository'),
]
i = 0
for p, ref in paths_to_fix_repository_schema_ref:
    responses = json_spec['paths'][p]['get']['responses']
    responses.pop('default', None)
    ensure_response(p, 'get', '200', 'successful operation')
    responses['200']['content']['application/json']['schema'] = {'$ref': ref}
    i = i + 1
print(f'   Fixed {i} repository responses')

with open('./spec/openapi.yaml', 'w') as output_yaml_specfile:
    output_yaml_specfile.write(yaml_dump(json_spec))
