# Releasing ServiceFlow

ServiceFlow releases are built once in GitHub Actions. The same tested archive is then attached to the GitHub Release and, when explicitly requested, published to Ansible Galaxy.

## Required GitHub configuration

Create a GitHub Environment named `galaxy` and add this environment secret:

```text
ANSIBLE_GALAXY_TOKEN
```

Do not store the token as a repository file, workflow input, issue comment or shell command in documentation. Environment protection rules may be used to require manual approval before the Galaxy job starts.

The release workflow has `contents: write` only so it can create the GitHub Release. The Galaxy token is exposed only to the `galaxy` job.

## Release tag format

The Git tag must exactly match the version in `galaxy.yml`:

```text
0.1.0
```

A tag such as `v0.1.0` is rejected because the collection metadata contains `0.1.0`.

Create and verify a signed tag:

```bash
git switch main
git pull --ff-only
git tag -s 0.1.0 -m "mraibo.serviceflow 0.1.0"
git tag -v 0.1.0
git push origin 0.1.0
```

Pushing the tag automatically:

1. checks out the exact tag;
2. validates the tag against `galaxy.yml` and `CHANGELOG.md`;
3. builds the collection;
4. rejects ignored local directories in the archive;
5. installs and smoke-tests the built archive;
6. generates `SHA256SUMS`;
7. uploads a workflow artifact;
8. creates the GitHub Release and attaches the archive and checksum.

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

The workflow rebuilds from the exact existing tag and publishes the resulting archive with the environment secret. It refuses to publish when the tag does not match `galaxy.yml` or the token is unavailable.

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
  ansible-doc mraibo.serviceflow.log_readiness
```

Verify on GitHub and Galaxy that:

- the release tag points to the intended commit;
- the GitHub Release contains the collection archive and `SHA256SUMS`;
- Galaxy shows the expected version;
- README and documentation links render correctly;
- no local build or acceptance directories are present in the published archive.

## Failed or repeated runs

The build and GitHub Release upload are repeatable. Existing release assets are replaced with `--clobber`.

Galaxy versions are immutable. Do not try to overwrite an already published version. Correct a post-publication defect by increasing the collection version and creating a new release.
