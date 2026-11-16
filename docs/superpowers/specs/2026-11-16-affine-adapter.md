# AFFiNE adapter specification

Build cloud.lazycat.app.affine from stable upstream tags and official images.
Use the existing lazycat-action@v1 executor without modifying its repository.
The first adapter release starts fresh: old 0.25.7 data is outside scope.
New data lives under /lzcapp/var/affine and must survive container recreation.

Use three services: AFFiNE, PostgreSQL 16 with pgvector, and Redis 7.4.
Pin dependency images; resolve the selected AFFiNE version to a platform digest.
Preserve an auditable relationship between selected tag, tested image and LPK.
Use native OIDC and an installation-specific HTTPS domain, preserve user config,
and run the official predeploy migrations before starting the server.

The executor's images mode cannot be combined with command preparation.
Run real delivered-image tests in lzc-build.yml's buildscript, before packaging.
Test failure must exit nonzero and prevent packaging/submission. Push is read-only;
schedules and manual non-dry runs publish. Release uploading is independent.
Keep credentials, reports, downloaded images and LPKs out of Git.
This task authorizes implementation, local tests, commit and push; no manual real
store submission or installation on the user's microserver is requested.
