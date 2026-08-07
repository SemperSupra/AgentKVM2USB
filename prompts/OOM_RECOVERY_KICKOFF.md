# OOM and Context-Compaction Recovery Kickoff

Use this prompt immediately after a local agent, terminal agent, or coordinator session is interrupted, compacted, restarted, or terminated by an out-of-memory condition.

```text
Recover the current multi-agent work from GitHub. Do not trust this conversation summary, terminal scrollback, pasted report, or compacted context as the current assignment until live GitHub confirms it.

Start in the relevant local checkout, but treat GitHub as authoritative.

Known AgentKVM2USB coordination repository:
- SemperSupra/AgentKVM2USB
- integration branch: recovery/agentkvm2usb-app-capabilities
- last reviewed integration head: 831efef0fb21cf6fd6a77b6b655321201465551c

Known Package Foundry authority:
- control repository: SemperSupra/windows-package-foundry-private
- generated public projection: SemperSupra/windows-package-foundry
- Gate 1 / private issue #1: complete
- next package lane: private issue #2 USBPcap

Do not assume the known SHAs or states are still current. Fetch and verify them.

1. Lossless reconciliation
- fetch/prune every relevant remote;
- inspect every worktree, branch, upstream, HEAD, ahead/behind count, dirty file, staged file, untracked file, stash, detached head, and local-only commit;
- preserve all unknown work;
- never reset, clean, discard, auto-stash, rebase shared work, or force-push;
- fast-forward only clean canonical checkouts when safe.

2. Reconstruct live coordination state
Read in this order:
- docs/EXECUTION_CHECKPOINT.md;
- docs/ACTIVE_WORKSTREAMS.md;
- prompts/MULTI_AGENT_DISPATCH.md;
- AGENTS.md;
- the specifically assigned GitHub issue and all comments;
- associated pull requests and review threads;
- current remote branches and hosted checks;
- finite START/CHECKPOINT/HANDOFF claims in every involved repository.

3. Classify the supplied summary
Explicitly label the pasted or compacted report as one of:
- CURRENT: live issue, PR, branch, claim, and remote heads confirm it describes the active lane;
- HISTORICAL: it describes completed, merged, closed, released, or superseded work;
- CONFLICTING: it disagrees with live GitHub or overlaps another valid claim.

Do not merely repeat a HISTORICAL report. Do not continue from a CONFLICTING report. Explain the classification in one paragraph and proceed from live GitHub.

4. Resolve the actual assignment
Identify the newest explicit lane assignment from the user and live GitHub. Verify:
- repository;
- issue;
- branch;
- expected base and remote head;
- pull request state;
- claim ownership and expiry;
- allowed scope;
- safety boundaries;
- entry and exit gates.

A completed Issue #1 eligibility report is not a valid response to an Issue #2 USBPcap assignment. If the current assignment is private Foundry issue #2 and no branch or PR exists, create a fresh issue-2-usbpcap branch and isolated worktree only after claim preflight.

5. Execute rather than recap
After reconciliation and claim preflight:
- begin the assigned unblocked lane;
- create the finite START claim;
- create or reuse the correct isolated worktree and issue-specific branch;
- open an early draft PR for tracked changes;
- perform the bounded work until a genuine human, hardware, authorization, safety, or external dependency gate is reached;
- use CHECKPOINT renewals;
- finish with HANDOFF and claim release.

Do not return only a summary of already-completed work unless the live assignment is specifically to audit that history.

6. Current safety boundaries
- do not automate UAC or reboot;
- do not install USBPcap until private Foundry issue #2 approves the exact route;
- do not automate vendor login, cookies, tokens, entitlement, downloads, or license acceptance;
- do not start capture, send target input, recable, or write persistent device state;
- do not modify AgentKVM2USB PR #13 before its target-receipt gate;
- do not commit proprietary artifacts, credentials, raw captures, or private machine evidence.

7. Recovery report
Return:
- live verified repository heads;
- all worktrees and preserved work;
- summary classification: CURRENT, HISTORICAL, or CONFLICTING;
- active claims and collision decisions;
- actual assigned lane;
- issue, branch, worktree, PR, claim ID, and expiry;
- work started or exact blocker;
- validation and push state;
- next-agent handoff.
```
