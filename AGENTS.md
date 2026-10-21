# Shared rules for agents and the team

Using AI and multiple agents is optional. Follow [`docs/TEAM_WORKFLOW.md`](docs/TEAM_WORKFLOW.md),
[`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) and [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md).

## Before you start
1. Read the Issue: acceptance criteria, owner, scope, dependencies.
2. Check active Issues/PRs (and the GitHub Project, if you have access) for
   collisions in files, modules and contracts. The board does not lock edits.
3. Check `git status`, the current branch and local changes. Never discard
   anyone else's work.
4. Mark the task as in progress if authorized; without access, tell the owner
   instead of claiming an update.

## Limits and isolation
- One branch per Issue/sub-task. Never commit directly to `main` or `dev`.
- Each concurrent agent on the same machine needs its own worktree or clone.
- Edit only the modules/files in scope. Scope changes need prior agreement.
- Changes to authentication, dependencies, migrations, global settings and
  shared APIs need the owner's approval.
- Make the smallest working solution. No unrequested abstractions or dependencies.
- Run the relevant tests and report real results; never claim a test you did not run.

## Multiple agents and integration
- Split the main Issue into linked sub-tasks with mostly independent scope.
- Define shared interfaces, inputs/outputs, dependencies and merge order first.
- Each agent works on its own branch and opens its own PR; a designated
  integrator merges them into an integration branch when needed.
- Check semantic conflicts beyond merge conflicts (contracts, migrations, business rules).
- If you overlap with a teammate's or agent's work, stop and coordinate before editing.
- Never force-push another person's branch.

## Delivery
- The PR references the Issue and lists modules changed, contracts, tests and open items.
- Finish only after the agreed integration and review.
- Keep authorship and attribution accurate; never invent authorship or hide required disclosure.
- Without GitHub access or write permission, hand over a report for manual updating.
