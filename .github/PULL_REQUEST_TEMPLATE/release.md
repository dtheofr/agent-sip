<!-- Title: chore(release): X.Y.Z -->

## Release X.Y.Z

Bump: <!-- minor | patch --> because <!-- feat or breaking change present -> minor;
fixes only -> patch -->

Included since vA.B.C: <!-- list of #PRs -->

<!-- Paste the new CHANGELOG section here. -->

- [ ] `[Unreleased]` moved to `## [X.Y.Z] - YYYY-MM-DD`, empty `[Unreleased]` kept
- [ ] `__version__ = "X.Y.Z"` is the only change outside `CHANGELOG.md`
- [ ] CI green on `main` at the base commit

Merging creates the GitHub Release and deploys to the server.
