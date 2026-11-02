# SM070 P2 gap-fill addendum (read after the main brief)

The main brief named in your prompt describes the whole task. This addendum overrides it where they differ.

## You are finishing a reviewed pull request, not starting one

A research agent filled five cells on a branch, a second agent reviewed it, and the reviewer REOPENED the cells listed below because what filled them did not measure the cause. Your job is to give each open cell an honest answer: a figure that measures its cause, or a `none` record that names at least eight genuinely relevant sources you opened (use the sources already in `sources/` on that branch wherever they are relevant, and open any new ones yourself). Read the PR's review comment and the reviewer's commit to see exactly what was ruled and why.

## Rulings you must apply (they were made on these PRs)

- **A cost-composition share is not evidence of the cause.** The share of diesel, equipment, materials, labour or services in a cost base does not measure plant hours above what was priced, prices rising on a fixed price, or more hours than the work needed. Those shares now sit in `context/` with `exposure_kind: context` and no subtype. Do not refile them under a cause.
- **An owner-side figure does not become a contractor figure.** Say whose money it is.
- **A fine fixed by statute (an infringement notice at a fixed number of penalty units) is a tariff, not a measured cost.**
- **A frequency or a count is not a figure** (the schema has no unit for it). Put it in the `sample_note` of the cell's `none` record.
- A `none` record is a real answer. Do not pad a cell with a poor figure to avoid one.

## Mechanics (replacing the brief's section 1 and step 5)

Work on the existing PR branch, adding commits to it. Do NOT open a new PR.
```
git -C <your disease-economics checkout> fetch origin
git -C <your disease-economics checkout> worktree add -B gapfill-<name> /tmp/p2-worktrees/gapfill-<name> origin/<PR branch>
cd /tmp/p2-worktrees/gapfill-<name>
```
Run `python3 scripts/validate.py --base origin/main`, `python3 -m unittest discover -s tests`, and `python3 scripts/grid.py --disease <disease> --country <country>` until clean and your cells are no longer `empty`. Commit with `git add sources diseases context` only and end the message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, then `git push origin HEAD:<PR branch>`. Add a PR comment (`gh pr comment <n> --repo demitonapp/disease-economics`) saying what you added per cell. Do not merge. Do not touch any other branch.

## Your final reply (under 250 words)

Per open cell: state, what you filed, the one figure you are least sure of; the frequencies the schema cannot hold; anything blocked.
