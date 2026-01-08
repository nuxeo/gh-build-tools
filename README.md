# gh-build-tools
Shared GitHub Actions and Reusable Workflows

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
