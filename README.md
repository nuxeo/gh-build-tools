# gh-build-tools

This repository contains shared/reusable CI configurations for GitHub Actions to
serve the repositories of the Nuxeo org but virtually usable by everyone.

Here follows the list of GitHub Actions topics available in the current document:

- [gh-build-tools](#gh-build-tools)
  - [GitHub Actions](#github-actions)
    - [nos-publish](#nos-publish)
    - [nuxeo-docker-build](#nuxeo-docker-build)
    - [nuxeo-helmfile-install](#nuxeo-helmfile-install)
    - [nuxeo-mvn-properties](#nuxeo-mvn-properties)
    - [setup-maven-build](#setup-maven-build)
    - [update-nuxeo-parent](#update-nuxeo-parent)
  - [Release](#release)

## GitHub Actions

### nos-publish

Publish Nuxeo package to Nuxeo Online Services (NOS).

```yaml
      - uses: nuxeo/gh-build-tools/.github/actions/nos-publish@v0.8.0
        with:
          nos-env: production # Market place target env (either 'production' or 'staging')
          nos-username: ${{ secrets.NOS_CONNECT_USERNAME }}
          nos-token: ${{ secrets.NOS_CONNECT_TOKEN }}
          skip-verify: 'false' # optional, default is 'false'
          package-path: ./module.zip
```

Inputs:

Check `action.yml` for the full list of inputs and their description.

Outputs:

- package-url: URL of the published package on NOS Marketplace
- publishing-status: publication status (based either on publish step outcome of verification step outcome)

### nuxeo-docker-build

Build a customized Nuxeo Docker image by layering:

- A chosen base image tag
- Online Nuxeo Connect marketplace modules (requires `NUXEO_CLID` secret)
- Offline local addon `.zip`/`.jar` files
- Optional OS packages installed through the private yum repository

Pushes the resulting image to a target registry (default `ghcr.io`) and outputs the full image URL.

```yaml
      - name: Build Nuxeo image
        uses: nuxeo/gh-build-tools/.github/actions/nuxeo-docker-build@v0.8.0
        with:
          base-image-tag: 2023
          base-registry-username: ${{ secrets.NUXEO_REGISTRY_USERNAME }}
          base-registry-password: ${{ secrets.NUXEO_REGISTRY_PASSWORD }}
          nuxeo-connect-modules: "nuxeo-web-ui nuxeo-drive" # optional
          nuxeo-clid: ${{ secrets.NUXEO_CLID }} # optional if nuxeo-connect-modules is empty
          nuxeo-local-modules-path: addons # directory with offline addon zips
          os-packages: "ImageMagick jq" # optional
          image-name: my-nuxeo-custom
          image-tag: ${{ github.sha }}
          registry: ghcr.io
          registry-username: ${{ secrets.GITHUB_USERNAME }}
          registry-password: ${{ secrets.GITHUB_TOKEN }}
```

Example with local action registry:

```yaml
permissions:
  contents: write
  packages: write

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      registry:
        image: registry:3
        ports:
          - 5000:5000
    steps:
      - name: Build base docker image
        uses: nuxeo/gh-build-tools/.github/actions/nuxeo-docker-build@v0.8.0
        with:
          buildx-driver-opts: network=host # to access local registry
          base-image-tag: ${{ env.NUXEO_VERSION }}
          base-registry-username: ${{ secrets.NUXEO_DOCKER_USERNAME }}
          base-registry-password: ${{ secrets.NUXEO_DOCKER_TOKEN }}
          nuxeo-connect-modules: example-module
          nuxeo-clid: ${{ secrets.CONNECT_CLID }}
          os-packages: |
            ffmpeg-nuxeo
            ccextractor
          os-packages-user: ${{ secrets.NUXEO_DOCKER_USERNAME }}
          os-packages-token: ${{ secrets.NUXEO_DOCKER_TOKEN }}
          image-name: example-nuxeo
          image-tag: main
          image-title: "Nuxeo AI Core"
          local-registry: true # use local registry service
          registry: localhost:5000 # local registry address
          push-image: true
          platforms: linux/amd64
```

The image can then be reused in subsequent steps as part of a multi-stage
Dockerfile build:

```Dockerfile
FROM localhost:5000/example-nuxeo:main AS nuxeo-base
```

Inputs:

Check `action.yml` for the full list of inputs and their descriptions.

Outputs:

- The composite action sets output `image-url` to the fully qualified reference.

Notes:

- If no connect modules are provided, that phase is skipped.
- If the addons directory does not exist it is created empty (offline install skipped).
- Set `push-image: true` to push the image to the target registry.
- Provide private yum repo credentials via inputs (`os-packages-user`, `os-packages-token`) if needed (templated by `nuxeo-private.repo`).

### nuxeo-helmfile-install

Install nuxeo workloads using helmfile. Port forward discovered services to
localhost.

Example usage (in below example, we need a kind config file with additional node
label):

```yaml
      - name: Setup cluster
        uses: Alfresco/alfresco-build-tools/.github/actions/setup-kind@v12.0.0
        with:
          ingress-nginx-ref: controller-v1.12.1
          metrics: "true"
          kind-config-path: .github/kind.yml
      - name: Install helmfile workloads
        id: helmfile-install
        uses: nuxeo/gh-build-tools/.github/actions/nuxeo-helmfile-install@v0.1.0
        with:
          docker-registry: ${{ env.DOCKER_REGISTRY }}
          docker-registry-username: ${{ github.actor }}
          docker-registry-password: ${{ secrets.GITHUB_TOKEN }}
          github-username: ${{ secrets.PLATFORM_BOT_USERNAME }}
          github-token: ${{ secrets.PLATFORM_BOT_TOKEN }}
          helmfile-workdirectory: ci/helm-GHA
          helmfile-environment: mongodbUnitTests
      - name: Create project properties file based on discovered services
        run: |
          MONGODB_PORT=$(echo '${{ steps.helmfile-install.outputs.map }}' | jq -r '.mongodb')
          KAFKA_PORT=$(echo '${{ steps.helmfile-install.outputs.map }}' | jq -r '.kafka')
          cat <<EOF > "$HOME/nuxeo-test-mongodb.properties"
          nuxeo.test.stream=kafka
          nuxeo.test.kafka.servers=localhost:$KAFKA_PORT
          nuxeo.test.mongodb.dbname=nuxeo
          nuxeo.test.mongodb.server=mongodb://localhost:$MONGODB_PORT
          EOF
```

Inputs:

Check `action.yml` for the full list of inputs and their description.

Outputs:

- map: JSON object mapping service names to their forwarded localhost ports

### nuxeo-mvn-properties

Generate Maven properties file for Nuxeo tests based on provided inputs.

Example usage:

```yaml
      - name: Create project properties file
        uses: nuxeo/gh-build-tools/.github/actions/nuxeo-mvn-properties@v0.8.0
        with:
          environment: mongodb # used to name the properties file
          kafka-servers: localhost:9092
          mongodb-server: mongodb://localhost:27017
          additional-properties: |
            nuxeo.test.custom.property1=value1
            nuxeo.test.custom.property2=value2
```

For the list of all available inputs, check `action.yml` file.

### setup-maven-build

Performs the setup of required build tools (eg.: Maven, Java)

Example usage:

```yaml
      - name: Setup Maven build
        uses: nuxeo/gh-build-tools/.github/actions/setup-maven-build@v0.7.1
        with:
          java-version: '17'
          java-distribution: 'temurin'
```

For the list of all available inputs, check `action.yml` file.

### update-nuxeo-parent

Updates if needed the nuxeo-parent version in the pom.xml file to the latest release version.

Example usage:

```yaml
      - uses: nuxeo/gh-build-tools/.github/actions/update-nuxeo-parent@v0.4.0
        with:
          base-branch: "lts-2025"
          java-version: "21"
          github-actor: ${{ secrets.PLATFORM_BOT_USERNAME }}
          github-token: ${{ secrets.PLATFORM_BOT_TOKEN }}
          mvn-repo-username: ${{ secrets.REPOSITORY_MANAGER_USERNAME }}
          mvn-repo-password: ${{ secrets.REPOSITORY_MANAGER_PASSWORD }}
```

For the list of all available inputs, check `action.yml` file.

## Release

Add a label to the PR among `release/major`, `release/minor`, or `release/patch`
to trigger a release upon merging the PR.

New versions should follow [Semantic versioning](https://semver.org/), so:

- A bump in the third number will be required if you are bug fixing an existing
  action.
- A bump in the second number will be required if you introduced a new action or
  improved an existing action, ensuring backward compatibility.
- A bump in the first number will be required if there are major changes in the
  repository layout, or if users are required to change their workflow config
  when upgrading to the new version of an existing action.
