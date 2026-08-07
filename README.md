<!--

    Copyright 2019-Present Sonatype Inc.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

-->

# Sonatype Repository Server API Client(s)

[![CI](https://github.com/sonatype-nexus-community/nexus-repo-api-client/actions/workflows/build.yaml/badge.svg?branch=main)](https://github.com/sonatype-nexus-community/nexus-repo-api-client/actions/workflows/build.yaml)
[![GitHub license](https://img.shields.io/github/license/sonatype-nexus-community/nexus-repo-api-client)](https://github.com/sonatype-nexus-community/nexus-repo-api-client/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/sonatype-nexus-community/nexus-repo-api-client)](https://github.com/sonatype-nexus-community/nexus-repo-api-client/issues)
[![GitHub forks](https://img.shields.io/github/forks/sonatype-nexus-community/nexus-repo-api-client)](https://github.com/sonatype-nexus-community/nexus-repo-api-client/network)
[![GitHub stars](https://img.shields.io/github/stars/sonatype-nexus-community/nexus-repo-api-client)](https://github.com/sonatype-nexus-community/nexus-repo-api-client/stargazers)

---

This repository produces generated API Clients in various languages and frameworks for use by Customers and other projects.

## Supported Languages & Frameworks

| Language / Framework | Sonatype Nexus Repository Version Added | Public Package Link                                                                                                                                                                                       |
|----------------------|-----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Golang / Go          | 3.67.0                                  | [![go.dev reference](https://img.shields.io/github/v/tag/sonatype-nexus-community/nexus-repo-api-client-go)](https://pkg.go.dev/github.com/sonatype-nexus-community/nexus-repo-api-client-go)             |
| Java (Webclient)     | 3.68.1                                  | [![Maven Central Version](https://img.shields.io/maven-central/v/org.sonatype.community/nexus-repo-api-webclient)](https://central.sonatype.com/artifact/org.sonatype.community/nexus-repo-api-webclient) |
| Python               | 3.74.1                                  | [![PyPi](https://img.shields.io/pypi/v/nexus_api_client)](https://pypi.org/project/nexus_api_client/) |
| Typescript (fetch)   | 3.68.0                                  | [![npm](https://img.shields.io/npm/v/%40sonatype%2Fnexus-repo-api-client)](https://www.npmjs.com/package/@sonatype/nexus-repo-api-client)                                                                 |

## Known Issues

There are a number of known issues and changes required to the official OpenAPI spec to generate useful client
libraries.

These are all codified in `update-spec.py` which can be used to obtain the latest OpenAPI Specification from a running
Sonatype IQ Server, apply the required modifications and transform from JSON to YAML - outputting the result
to `spec/openapi.yml`.

See `update-spec.py` for amendments made to the Specification prior to client generation.

## Getting the latest OpenAPI Schema

Get it from your Sonatype Nexus Repository Server at `/service/rest/swagger.json`.

## Generation of API Clients

```
docker run --rm -v "$(PWD):/local" openapitools/openapi-generator-cli batch --clean /local/typescript.yaml

docker run --rm -v "$(PWD):/local" openapitools/openapi-generator-cli generate -i /local/spec/openapi.yaml -g typescript-fetch -o /local/out/test -c /local/openapi-config.yaml -v > out.log
```

## Diagnosing Responses that are not Schema Compliant

In the rare event that Sonatype Nexus Repository Server provides a response that does not validate against the schema (our patched schema to be clear), things can be silent - you just never get a response in your code.

Through the use of [Postman](https://www.postman.com) and [opeapi-request-response-validation](https://github.com/gcatanese/openapi-request-response-validation) project by [Beppe Catanese](https://github.com/gcatanese), we can quickly and accurately see where response validation failures occur.

1. Configure the request for which you are not getting a response in Postman exactly as it was sent
2. To that request (you can do this in a Collection if you are using Collections too), add a Test with the code:

    ```
     // define object
     openapiRequestResponseValidation = {
     // define function
     validate: function(pm) {

         const postRequest = {
             url: 'http://localhost:8080/validate',
             method: 'POST',
             header: {'Content-Type': 'application/json'},
             body: {
             mode: 'raw',
             raw: JSON.stringify({
                 method: pm.request.method,
                 path: pm.request.url.getPath(),
                 headers: pm.request.headers,
                 requestAsJson: (pm.request.body != "") ? pm.request.body.raw : null,
                 responseAsJson: pm.response.text(),
                 statusCode: pm.response.code
                 })
             }
         };

         pm.sendRequest(postRequest, (error, response) => {
             if(error != undefined) {
                 pm.expect.fail('Unexpected error ' + error);
             } else {
                 var data = response.json();

                 if(data.valid == false) {
                     console.log(data.errors);
                 }

                 pm.test("OpenAPI validation", () => {
                     pm.expect(data.valid, "Invalid request/response (check Console)").to.equal(true);
                 });

             }
         });
       }
     };

     // invoke function
     openapiRequestResponseValidation.validate(pm);
    ```

3. Start the `openapi-request-response-validation` Container locally:
    ```
    docker run -p 8080:8080 -v ./spec:/openapi -it --rm gcatanese/openapi-request-response-validation
    ```
4. Execute the request in Postman - if the test does not show as passed then you can get details of the failure from two places:
    1. The Postman console
    2. The logs from the running Container

## Changelog

See our [Change Log](./CHANGELOG.md).

## Releasing

We aim to keep the MAJOR and MINOR version component in-line with the version of Sonatype Nexus Repository Manager for which the API Client is
generated - i.e. `3.67.x` are all releases generated for the API specification as shipped with Sonatype Nexus Repository Manager version `3.67.x`.

For example, to perform a "patch" release, add a commit to `main` with a comment like below. The `fix: ` prefix matters.

```
fix: the problem resolved goes here
```

### Go module versioning is special-cased

The policy above (MAJOR.MINOR tracks NXRM's MAJOR.MINOR) applies to the Python, Java and TypeScript clients. The
**Go** client cannot follow it directly, because Go's module system enforces
[semantic import versioning](https://go.dev/ref/mod#major-version-suffixes): once a module reaches major version 2+,
its import path must carry a `/vN` suffix that matches the major version of every tag published for it, and a Go
build can only ever resolve **one version per import path** - there is no way for a consumer to depend on two
incompatible generations of the same Go module at once (unlike npm, which lets two majors of a package coexist via
nested `node_modules`).

This matters here because generator-output changes between NXRM releases are sometimes breaking for Go specifically
- renamed `operationId`s become renamed methods, renamed/restructured models become renamed/restructured Go types,
pointer-vs-value field changes break call sites - even when the same spec change is a compatible/additive change for
Python, Java and TypeScript. When that happens, downstream Go consumers that need to migrate gradually (e.g.
`terraform-provider-sonatyperepo`) need the old and new generations to be importable side by side, which Go only
allows if they live at different `/vN` import paths.

To satisfy that constraint while still keeping the version traceable back to NXRM, the Go client uses:

```
Go major = (NXRM major * 100) + (NXRM minor at which the current generation started)
Go minor = the live NXRM minor version
Go patch = this repo's own release counter within that NXRM minor (as PATCH has always meant here)
```

For example, a generator-output breaking change introduced in NXRM `3.95.0` starts a new generation at Go major
`395`. The Go module's import path becomes `.../nexus-repo-api-client-go/v395`, and its tags become `v395.95.0`,
`v395.95.1`, etc. If NXRM `3.96.0` ships with no further Go-breaking changes, that same generation continues and the
next Go tag is `v395.96.0` - still on the `/v395` import path - rather than bumping to a new major every NXRM minor.

The Go major version (the "generation") only bumps again when a future spec update introduces another
generator-output breaking change for Go. The single source of truth for the current generation number is the
[`.generation`](./.generation) file in this repo, which must always match `go.yaml`'s `packageName` - the release
workflow validates this and fails the release if they drift apart.

Because of this, a jump in the Go module's major version (e.g. `v3` -> `v395`) does **not** imply any equivalent
jump for Python, Java or TypeScript, and does not by itself indicate a breaking change in the underlying NXRM API -
it only reflects Go's own import-path requirements. Also see the equivalent notice in the generated
[`nexus-repo-api-client-go`](https://github.com/sonatype-nexus-community/nexus-repo-api-client-go) repository.

`v3.94.0` of the Go client was published with extensive generator-output breaking changes relative to `v3.93.2` that
were never intended for release; that generation is [retracted](https://go.dev/ref/mod#go-mod-file-retract) via a
`retract` directive in `go.mod` and should not be used - depend on `v395.x.x` (or later) instead.

## The Fine Print

Remember:

It is worth noting that this is **NOT SUPPORTED** by Sonatype, and is a contribution of ours to the open source
community (read: you!)

-   Use this contribution at the risk tolerance that you have
-   Do NOT file Sonatype support tickets related to `nexus-repo-api-client`
-   DO file issues here on GitHub, so that the community can pitch in

Phew, that was easier than I thought. Last but not least of all - have fun!
