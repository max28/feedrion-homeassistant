# Before making this repository public

1. **Runners**: delete the `CI_RUNS_ON` repository variable. Self-hosted
   runners must never serve a public repository.
2. **Secret scan** of the whole history (GitHub secret scanning, or
   `gitleaks detect --log-opts=--all`).
3. Repository description and topics (`home-assistant`, `hacs`,
   `hacs-integration`). Done; the HACS check no longer ignores them.
4. The icon ships in `custom_components/feedrion/brand/` (Home Assistant
   2026.3+ reads it there); nothing to submit to `home-assistant/brands`.
5. Settings ▸ Actions ▸ require approval for workflows from forks; enable
   private vulnerability reporting.
6. Optionally submit to the HACS default list.
