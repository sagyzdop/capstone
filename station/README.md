# Station

> **Status:** Draft · **Updated:** 2026-10-04

## Purpose

The laptop on the vehicle. It is the **orchestrator** and the **only compute node**.

## Responsibilities

- [ ] Receive drone video and images
- [ ] Detect and tag victims
- [ ] Plan the robot's path
- [ ] Orchestrate the mission
- [ ] Present the operator map and feed

## Interfaces

See [docs/interfaces.md](../docs/interfaces.md).

## Constraints

Laptop compute budget, latency, and WiFi bandwidth: TBD.

## Contents

| File | Description |
| --- | --- |
| [detection-data-analysis.md](detection-data-analysis.md) | Person sizes vs model input size per dataset |
| [dataset-suitability.md](dataset-suitability.md) | Full dataset audit: quality, density, coverage, leakage, downscaling, RGB + IR fusion, model options |
