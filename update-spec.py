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

# Fix Schema `MavenHostedApiRepository`
json_spec['components']['schemas']['MavenHostedApiRepository']['properties']['url'] = {
    'type': 'string'
}


# # Fix Response schema for GET /api/v2/applications
# if 'paths' in json_spec and '/api/v2/applications' in json_spec['paths']:
#     if 'get' in json_spec['paths']['/api/v2/applications']:
#         print('Fixing GET /api/v2/application...')
#         json_spec['paths']['/api/v2/applications']['get']['responses'] = {
#             'default': {
#                 'description': 'default response',
#                 'content': {
#                     'application/json': {
#                         'schema': {
#                             '$ref': '#/components/schemas/ApiApplicationListDTO'
#                         }
#                     }
#                 }
#             }
#         }
#
# # Add schemas for /api/v2/config
# if 'components' in json_spec and 'schemas' in json_spec['components'] \
#         and 'SystemConfig' not in json_spec['components']:
#     print('Injecting schema: SystemConfigProperty...')
#     json_spec['components']['schemas']['SystemConfigProperty'] = {
#         'type': 'string',
#         'enum': [
#             'baseUrl',
#             'forceBaseUrl'
#         ]
#     }
#
#     print('Injecting schema: SystemConfig...')
#     json_spec['components']['schemas']['SystemConfig'] = {
#         'properties': {
#             'baseUrl': {
#                 'nullable': True,
#                 'type': 'string'
#             },
#             'forceBaseUrl': {
#                 'nullable': True,
#                 'type': 'boolean'
#             }
#         }
#     }
#
# # Fix Response schema for GET /api/v2/config
# if 'paths' in json_spec and '/api/v2/config' in json_spec['paths']:
#     if 'delete' in json_spec['paths']['/api/v2/config']:
#         print('Fixing DELETE /api/v2/config...')
#         json_spec['paths']['/api/v2/config']['delete']['parameters'][0].update({
#             'schema': {
#                 'items': {
#                     '$ref': '#/components/schemas/SystemConfigProperty'
#                 },
#                 'type': 'array',
#                 'uniqueItems': True
#             }
#         })
#         json_spec['paths']['/api/v2/config']['delete']['responses'] = {
#             204: {
#                 'description': 'System Configuration removed',
#                 'content': {}
#             }
#         }
#
#     if 'get' in json_spec['paths']['/api/v2/config']:
#         print('Fixing GET /api/v2/config...')
#         json_spec['paths']['/api/v2/config']['get']['parameters'][0].update({
#             'schema': {
#                 'items': {
#                     '$ref': '#/components/schemas/SystemConfigProperty'
#                 },
#                 'type': 'array',
#                 'uniqueItems': True
#             }
#         })
#         json_spec['paths']['/api/v2/config']['get']['responses'] = {
#             200: {
#                 'description': 'System Configuration retrieved',
#                 'content': {
#                     'application/json': {
#                         'schema': {
#                             '$ref': '#/components/schemas/SystemConfig'
#                         }
#                     }
#                 }
#             }
#         }
#     if 'put' in json_spec['paths']['/api/v2/config']:
#         print('Fixing GET /api/v2/config...')
#         json_spec['paths']['/api/v2/config']['put']['requestBody'] = {
#             'content': {
#                 'application/json': {
#                     'schema': {
#                         '$ref': '#/components/schemas/SystemConfig'
#                     }
#                 }
#             }
#         }
#         json_spec['paths']['/api/v2/config']['put']['responses'] = {
#             204: {
#                 'description': 'System Configuration updated',
#                 'content': {}
#             }
#         }
#
# # Fix `ApiComponentDetailsDTOV2` schema
# if 'components' in json_spec and 'schemas' in json_spec['components'] \
#         and 'ApiComponentDetailsDTOV2' in json_spec['components']['schemas']:
#     print('Fixing schema: ApiComponentDetailsDTOV2...')
#     new_api_component_details_dto_v2 = json_spec['components']['schemas']['ApiComponentDetailsDTOV2']
#
#     new_api_component_details_dto_v2['properties']['hygieneRating'].update({'nullable': True})
#     new_api_component_details_dto_v2['properties']['integrityRating'].update({'nullable': True})
#     new_api_component_details_dto_v2['properties']['relativePopularity'].update({'nullable': True})
#
#     json_spec['components']['schemas']['ApiComponentDetailsDTOV2'] = new_api_component_details_dto_v2
#
# # Fix `ApiComponentEvaluationResultDTOV2` schema
# if 'components' in json_spec and 'schemas' in json_spec['components'] \
#         and 'ApiComponentEvaluationResultDTOV2' in json_spec['components']['schemas']:
#     print('Fixing schema: ApiComponentEvaluationResultDTOV2...')
#     new_api_cer_dto = json_spec['components']['schemas']['ApiComponentEvaluationResultDTOV2']
#
#     new_api_cer_dto['properties']['errorMessage'].update({'nullable': True})
#
#     json_spec['components']['schemas']['ApiComponentEvaluationResultDTOV2'] = new_api_cer_dto
#
# # Fix `ApiMailConfigurationDTO` schema
# if 'components' in json_spec and 'schemas' in json_spec['components'] \
#         and 'ApiMailConfigurationDTO' in json_spec['components']['schemas']:
#     print('Fixing schema: ApiMailConfigurationDTO...')
#     new_api_mail_configuration_dto = json_spec['components']['schemas']['ApiMailConfigurationDTO']
#
#     new_api_mail_configuration_dto['properties']['password'] = {
#         'type': 'string'
#     }
#
#     json_spec['components']['schemas']['ApiMailConfigurationDTO'] = new_api_mail_configuration_dto
#
# # Fix `ApiProxyServerConfigurationDTO` schema
# if 'components' in json_spec and 'schemas' in json_spec['components'] \
#         and 'ApiProxyServerConfigurationDTO' in json_spec['components']['schemas']:
#     print('Fixing schema: ApiProxyServerConfigurationDTO...')
#     new_api_proxy_server_configuration_dto = json_spec['components']['schemas']['ApiProxyServerConfigurationDTO']
#
#     new_api_proxy_server_configuration_dto['properties']['password'] = {
#         'type': 'string'
#     }
#
#     json_spec['components']['schemas']['ApiProxyServerConfigurationDTO'] = new_api_proxy_server_configuration_dto
#
# # Add missing schema `ApiThirdPartyScanTicketDTO`
# if 'components' in json_spec and 'schemas' in json_spec['components'] \
#         and 'ApiThirdPartyScanTicketDTO' not in json_spec['components']['schemas']:
#     print('Adding schema: ApiThirdPartyScanTicketDTO...')
#
#     json_spec['components']['schemas']['ApiThirdPartyScanTicketDTO'] = {
#         'properties': {
#             'statusUrl': {
#                 'type': 'string'
#             }
#         }
#     }
#
# # Fix Response schema for POST /api/v2/scan/applications/{applicationId}/sources/{source}
# if 'paths' in json_spec and '/api/v2/scan/applications/{applicationId}/sources/{source}' in json_spec['paths']:
#     if 'post' in json_spec['paths']['/api/v2/scan/applications/{applicationId}/sources/{source}']:
#         print('Fixing POST /api/v2/scan/applications/{applicationId}/sources/{source}...')
#         json_spec['paths']['/api/v2/scan/applications/{applicationId}/sources/{source}']['post']['responses'][
#             'default']['content']['application/json'].update({
#             'schema': {
#                 '$ref': '#/components/schemas/ApiThirdPartyScanTicketDTO'
#             }
#         })
#
# # Remove APIs with incomplete schemas
# API_PATHS_TO_REMOVE = {
#     '/api/v2/licenseLegalMetadata/customMultiApplication/report': [],
#     '/api/v2/product/license': [],
#     '/api/v2/config/saml': ['put']
# }
# if 'paths' in json_spec:
#     print('Removing paths...')
#     for path, methods in API_PATHS_TO_REMOVE.items():
#         print(f'   Removing: {path} : {methods}')
#         if path in json_spec['paths']:
#             if len(methods) == 0:
#                 json_spec['paths'].pop(path)
#             else:
#                 for method in methods:
#                     json_spec['paths'][path].pop(method)

with open('./spec/openapi.yaml', 'w') as output_yaml_specfile:
    output_yaml_specfile.write(yaml_dump(json_spec))
