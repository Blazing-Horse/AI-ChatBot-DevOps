# How we work

1. Every change starts as an issue. Assign it to yourself.
2. Create a branch in this repository (not a fork): `feat/<issue>-<short-name>` or `fix/<issue>-<short-name>`.
3. Push, then open a pull request that says `Closes #<issue>`.
4. Wait for the three checks (`lint-test`, `build-scan`, `terraform-plan`) to pass, and for one approval from a maintainer who is not the author.
5. The maintainer who approved squashes and merges. The branch is deleted and the deploy starts automatically.

Nobody pushes to `main` directly, and only maintainers can merge. GitHub blocks everything else.
