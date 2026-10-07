# Future ideas

Bigger, more speculative directions for `honest-agent` -- unlike `TODO.md`
(scoped work we've already designed, just waiting on missing information),
these are rougher ideas worth exploring later, not committed designs.

## Auto root-cause investigation + PR-on-fix for regressions

When an eval that used to pass starts failing, today the only thing that
happens is a human gets alerted (`honest-agent notify` → Slack) and can dig in
manually via `honest-agent logs` / the report. The idea: wire a failing result
into a second agent whose job is to investigate *why* it regressed and, if it
finds a genuine, fixable cause, open a PR with the fix.

### The idea

1. `thresholds.failing_rows` already identifies which eval(s) regressed
   this run. We already capture rich forensic context per result: the full
   exchange with the model and tools (the raw layer, `raw.events`), every tool/SQL call it made
   (`tool_calls`), which model ran it (`results.model_name`), and the run
   timestamp -- more than enough to start an investigation from.
2. Feed a failure to an "investigator" agent, whose job is to correlate it
   against things `honest-agent` doesn't currently model at all:
   - **Model version changes** -- did `model_name` change between the last
     passing run and this one? A new model version can genuinely change
     behavior.
   - **Changes to the tested agent's own tools/prompts/MCP server** -- not
     something `honest-agent` has visibility into today; would need read
     access to whatever repo defines those.
   - **Changes to the underlying data/warehouse models the agent queries**
     (e.g. a dbt model got renamed or refactored) -- would need git history
     access to that separate project.
   - **A legitimate change in the real-world answer** -- "what's our total
     revenue" genuinely has a new correct number every month. This is a
     fundamentally different case from a real regression, and telling the
     two apart is the hard part of this whole idea.
3. If the investigator is confident it found a real, fixable bug (not a
   stale `expected_answer`), open a PR with a proposed fix -- against
   `honest-agent`'s own eval definitions if the *expected answer* is what's
   stale, or against the tested system's own codebase if the *agent/data*
   actually broke.

### Why this is interesting

The current system already generates a detailed forensic record (trace +
tool calls + provenance) for every result; this would put that record to
active use instead of just displaying it in a report someone has to notice
and read.

### Open questions / risks -- unresolved, not just implementation detail

- **Telling "the agent broke" apart from "the world changed" is the crux.**
  An investigator that can't reliably distinguish these would either spam
  PRs for non-bugs or, worse, silently patch `expected_answer` to hide a
  real regression.
- **Scope of what the investigator can even see.** Today `honest-agent` only
  knows about its own eval results -- root-causing a regression means
  reading the tested agent's own codebase/config, which `honest-agent` has no
  concept of yet (not even a pointer to where that lives).
- **Auto-opening a PR is a real, hard-to-reverse action against someone
  else's repo.** Would need explicit scoping/guardrails before ever running
  autonomously -- very much "confirm before acting" territory, consistent
  with how the rest of this project has been built.
- **Sequencing**: not worth building until the basics (manual investigation
  via `honest-agent logs`, the report, Slack alerts) have actually been used
  for a while and we know what real regressions look like in practice, so
  the investigator's job is grounded in real cases rather than guesses.
