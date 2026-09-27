# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog;
versioning: SemVer.

## [Unreleased]

### Added
- Repository bootstrap: integration skeleton (`vigie` domain, config flow), CI (lint, unit,
  hassfest, HACS), release workflow, issue templates, documentation.
- AIS decoder (`nmea/ais_decoder.py`): Class A types 1/2/3 and Class B types 18/19,
  checksum and length validation, multi-fragment reassembly, tag blocks, own-ship `VDO`
  flag, injectable clock. 39 tests, 98.5 % coverage.
