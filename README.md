# Music Transcription & Generation

Team 03's Project ROCKY for SNU SWPP 2026.

## MIDI-RWKV experiment worktree

This worktree is dedicated to evaluating pretrained MIDI-RWKV for missing-track
generation on BabySlakh. It removes each Piano, Guitar, Bass, or Drums family
from a multitrack MIDI, generates one consolidated replacement with
`generate_new_track()`, and evaluates completed outputs with CP, GS, and PCHE.

The reproducible experiment specification, runner, evaluation tools, pretrained
model checkout, and local results are under [`ml/`](ml/). See
[`ml/README.md`](ml/README.md) for the exact task boundary and artifact layout.

The repository is organized as a small monorepo so the client application,
backend services, and machine-learning code can evolve independently while
sharing one issue tracker and CI configuration.

## Repository layout

| Directory | Responsibility |
| --- | --- |
| [`app/`](app/) | User-facing client application and UI integration |
| [`server/`](server/) | API, authentication, orchestration, and persistence |
| [`ml/`](ml/) | Audio preprocessing, transcription, generation, and model experiments |
| [`docs/`](docs/) | Architecture notes, API contracts, and project decisions |
| [`tests/`](tests/) | Cross-component and end-to-end test fixtures |

Each component has its own README with a suggested boundary and setup notes.

## Development workflow

1. Create a focused branch from `main`, using a prefix such as `app/`,
   `server/`, `ml/`, or `docs/`.
2. Make a small, reviewable change and add or update tests with it.
3. Run the checks documented by the component you changed.
4. Open a pull request into `main`; do not commit directly to `main`.

### Parallel work with Git worktrees

Worktrees let each teammate keep an independent checkout while sharing the
same local repository object database. From the primary checkout:

```powershell
git fetch origin
git worktree add .worktrees\app-feature -b app/feature origin/main
git worktree add .worktrees\server-feature -b server/feature origin/main
git worktree list
```

When the work is merged and no longer needed:

```powershell
git worktree remove .worktrees\app-feature
git branch -d app/feature
git worktree prune
```

The `.worktrees/` directory is ignored so worktree checkouts cannot be
accidentally committed. Keep each worktree on one branch at a time, and do
not check in generated model weights, datasets, credentials, or local
environment files.

## Initial setup

Clone the repository and inspect the component README before installing a
runtime. Component-specific dependencies should stay inside that component;
the root should contain only shared tooling and documentation.

```powershell
git clone https://github.com/snuhcs-course/swpp-2026-project-team-03.git
cd swpp-2026-project-team-03
git worktree list
```

## Collaboration conventions

- Use pull requests for all changes.
- Keep commits focused and use imperative commit subjects, for example
  `Add MIDI export endpoint`.
- Record important design choices in `docs/decisions/`.
- Prefer reproducible scripts and pinned dependencies.
- Store large datasets and model artifacts outside Git; document how to fetch
  them in `ml/README.md`.
