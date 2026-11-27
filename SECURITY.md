# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately through
GitHub instead: on the repository's **Security** tab, choose **Report a vulnerability**. Only the
maintainer can see the report.

Useful things to include:

- what an attacker could do (for example, read an API key, password or log URL)
- the steps or a minimal config/ADIF file that shows it (with fake credentials)
- the version or commit you tested

You should get a first reply within a week. Fixes go into `main` and the next release.

## Supported versions

This is a small hobby project. Only the latest release and `main` get security fixes.

## Scope

dxcc-flagmap handles credentials for the services it reads from: Wavelog API keys, LoTW
username/password, Club Log, QRZ Logbook and World Radio League keys, and ADIF URLs that may
carry tokens. Examples of what counts as a vulnerability:

- a credential showing up in an error message, log line, output file or Actions log
- a key being sent to the wrong host, over plain HTTP, or on a redirect
- a crafted ADIF file or API response that makes the tool write outside its output folder,
  run code, or hang
- a weakness in `.github/workflows/publish.yml` that would let a fork or pull request reach
  repository secrets

Out of scope: problems in the services themselves (Wavelog, LoTW, Club Log, QRZ, WRL) and
leaks caused by a user committing their own keys to a public repository. Keep keys in Actions
secrets or environment variables, never in config files.

## If you leaked a key

Revoke or regenerate it at the service (Wavelog: *Account > API keys*, Club Log / QRZ / WRL:
their API settings pages, LoTW: change your password), then update your repository secret.
Deleting the commit is not enough, because forks and caches keep it.
