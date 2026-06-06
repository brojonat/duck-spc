#!/bin/bash
# Per-skill installs, selected to match the capabilities in README.md.
# Commit the resulting skills-lock.json.
set -e

# Core domain: XmR charts, frozen limits, detection rules
npx skills add brojonat/llmsrules -s statistical-process-control -y
# DuckDB over partitioned Parquet (the compute engine)
npx skills add brojonat/llmsrules -s parquet-analysis -y
# Roadmap: lakehouse source backend
npx skills add brojonat/llmsrules -s ducklake -y
# Packaging and CLI conventions
npx skills add brojonat/llmsrules -s pyproject-config -y
npx skills add brojonat/llmsrules -s python-cli -y
# Demo notebooks (the SPC skill's worked example is marimo)
npx skills add marimo-team/skills -s marimo-notebook -y
# Dev practice
npx skills add obra/superpowers -s test-driven-development -y
npx skills add obra/superpowers -s systematic-debugging -y

# Roadmap (add when the ingestion hot path materializes):
# npx skills add brojonat/llmsrules -s pg-messaging -y
