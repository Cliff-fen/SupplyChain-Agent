# Dependencies and example data

Runtime dependencies are declared in `backend/pyproject.toml` and
`frontend/package.json`; the frontend lockfile records resolved versions.
The release workflow generates a software bill of materials for review.

The local supply-chain seed tables contain synthetic example records.
Optional UCI dataset import scripts download public datasets separately;
their source links and usage details are documented in `docs/knowledge-base/`.
Those downloaded datasets, user documents and business records are not part
of the repository.
