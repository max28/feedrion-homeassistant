# Before making this repository public

1. **Runners**: delete the `CI_RUNS_ON` repository variable. Self-hosted
   runners must never serve a public repository.
2. **Secret scan** of the whole history (GitHub secret scanning, or
   `gitleaks detect --log-opts=--all`).
3. Repository description and topics (`home-assistant`, `hacs`,
   `hacs-integration`), then drop `description topics` from the HACS job's
   `ignore`.
4. Submit the icon to `home-assistant/brands` (custom_integrations/feedrion),
   then drop `brands` from the same `ignore`.
5. Settings ▸ Actions ▸ require approval for workflows from forks; enable
   private vulnerability reporting.
6. Optionally submit to the HACS default list.
