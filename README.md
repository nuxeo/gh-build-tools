# gh-build-tools

This repository contains shared/reusable CI configurations for GitHub Actions to
serve the repositories of the Nuxeo org but virtually usable by everyone.

Here follows the list of GitHub Actions topics available in the current document:

- [gh-build-tools](#gh-build-tools)
  - [GitHub Actions](#github-actions)
    - [nuxeo-helmfile-install](#nuxeo-helmfile-install)
    - [nuxeo-mvn-properties](#nuxeo-mvn-properties)
    - [setup-maven-build](#setup-maven-build)
    - [update-nuxeo-parent](#update-nuxeo-parent)
  - [Release](#release)

## GitHub Actions

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
        uses: nuxeo/gh-build-tools/.github/actions/nuxeo-mvn-properties@OPSEXP-3626-mvn-properties
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
