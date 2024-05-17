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

import requests
import sys

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
        'name': 'Apache 2.0',
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
                    i = i+1
                if str(method).lower() == 'post':
                    json_spec['paths'][path]['post'][
                        'operationId'] = f'create{format.capitalize()}{type.capitalize()}Repository'
                    i = i + 1
                if str(method).lower() == 'put':
                    json_spec['paths'][path]['put'][
                        'operationId'] = f'update{format.capitalize()}{type.capitalize()}Repository'
                    i = i + 1
print(f'   Fixed {i} Repository Operations')

# Fix Schemas relating to Repositories that are missing `format`, `type` and `url`
repository_schemas_to_fix = [
    'MavenHostedApiRepository',
    'MavenProxyApiRepository',
    'SimpleApiGroupRepository'
]
print('Fixing Repository Schemas...')
for s in repository_schemas_to_fix:
    json_spec['components']['schemas'][s]['properties']['format'] = {
        'type': 'string',
        'default': 'maven2'
    }
    json_spec['components']['schemas'][s]['properties']['type'] = {
        'type': 'string',
        'default': 'hosted'
    }
    json_spec['components']['schemas'][s]['properties']['url'] = {
        'type': 'string'
    }
    print(f'   Fixed `{s}`')

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
]
i = 0
print('Overriding operation IDs...')
for o in operations_to_fix:
    print(f'    Setting OperationID to {o['operation_id']} for {o['method']}:{o['path']}')
    json_spec['paths'][o['path']][o['method']]['operationId'] = o['operation_id']
    i = i + 1
print(f'Overwrote {i} Operation IDs')

with open('./spec/openapi.yaml', 'w') as output_yaml_specfile:
    output_yaml_specfile.write(yaml_dump(json_spec))
