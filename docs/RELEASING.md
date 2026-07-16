# Releasing ServiceFlow

ServiceFlow releases are built once in GitHub Actions. The same tested archive is then attached to the GitHub Release and, when explicitly requested, published to Ansible Galaxy.

## Required GitHub configuration

The Galaxy API token belongs to the Galaxy account, not to an individual GitHub repository. The same active token may therefore publish collections from multiple repositories when that Galaxy account has permission for the target namespace.

Galaxy currently exposes one active API token per account. Loading or generating a new token invalidates the previous token. Every GitHub repository or environment still holding the old value must then be updated before its next publication.

Recommended setup:

1. create a GitHub Environment named `galaxy`;
2. add this environment secret:

```text
ANSIBLE_GALAXY_TOKEN
```

3. optionally require manual deployment approval for the environment;
4. use the same active Galaxy token in each publishing repository, or use an organization secret restricted to selected repositories when the repositories belong to a GitHub organization.

A repository secret with the same name also works, but an environment secret provides a narrower publication boundary and optional approval. Do not keep duplicate secrets longer than necessary.

Do not store the token as a repository file, workflow input, issue comment, chat message or shell command in documentation. The release workflow has `contents: write` only so it can create the GitHub Release. The Galaxy token is exposed only to the `galaxy` job.

When rotating the token:

1. generate or load the new Galaxy token once;
2. update `ANSIBLE_GALAXY_TOKEN` in every repository or shared organization secret that publishes to Galaxy;
3. run one non-release validation or wait until the next intended publication;
4. remove obsolete duplicate secrets;
5. never regenerate the token merely to create a separate value for each repository, because regeneration invalidates the previous value globally for the Galaxy account.

## Release tag format

The Git tag must exactly match the version in `galaxy.yml`:

```text
0.1.0
```

A tag such as `v0.1.0` is rejected when the collection metadata contains `0.1.0`.

Create and verify a signed tag when a suitable signing key is available:

```bash
git switch main
git pull --ff-only
git tag -s 0.1.0 -m "mraibo.serviceflow 0.1.0"
git tag -v 0.1.0
git push origin 0.1.0
```

An annotated unsigned tag is acceptable when the release environment has no configured signing key:

```bash
git tag -a 0.1.0 -m "mraibo.serviceflow 0.1.0"
git push origin 0.1.0
```

Before pushing either form, verify the target commit:

```bash
git rev-list -n 1 0.1.0
```

Pushing the tag automatically:

1. checks out the exact tag;
2. validates the tag against `galaxy.yml` and `CHANGELOG.md`;
3. builds the collection;
4. rejects ignored local directories in the archive;
5. installs and smoke-tests the built archive;
6. verifies module, filter and role documentation;
7. generates `SHA256SUMS`;
8. uploads a workflow artifact;
9. creates the GitHub Release and attaches the archive and checksum.

A tag push does **not** publish to Galaxy automatically.

## Publish the accepted artifact to Galaxy

After the tag workflow and GitHub Release succeed:

1. open **Actions → Release → Run workflow**;
2. select the default branch containing the release workflow;
3. enter the existing tag, for example `0.1.0`;
4. leave `create_release` disabled when the GitHub Release already exists;
5. enable `publish_galaxy`;
6. run the workflow;
7. approve the `galaxy` environment deployment when an approval rule is configured.

The workflow rebuilds from the exact existing tag and publishes the resulting archive with the configured GitHub secret. It refuses to publish when the tag does not match `galaxy.yml` or the token is unavailable.

## Post-publication verification

Install the published version into an empty directory:

```bash
tmpdir="$(mktemp -d)"
cd "$tmpdir"
ansible-galaxy collection install mraibo.serviceflow:0.1.0 -p collections
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-galaxy collection list mraibo.serviceflow
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-doc -t role mraibo.serviceflow.lifecycle
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-doc -t filter mraibo.serviceflow.serviceflow_plan
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-doc mraibo.serviceflow.log_readiness
```

Verify on GitHub and Galaxy that:

- the release tag points to the intended commit;
- the GitHub Release contains the collection archive and `SHA256SUMS`;
- Galaxy shows the expected version;
- README and documentation links render correctly;
- the role README and filter documentation are visible;
- no local build or acceptance directories are present in the published archive.

## Failed or repeated runs

The build and GitHub Release upload are repeatable. Existing release assets are replaced with `--clobber`.

Galaxy versions are immutable. Do not try to overwrite an already published version. Correct a post-publication defect by increasing the collection version and creating a new release.
