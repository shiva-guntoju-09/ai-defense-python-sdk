# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2026-03-20

### Added

- **Agent Runtime SDK (`agentsec`)** — New `aidefense.runtime.agentsec` module for transparent, 2-line integration to protect LLM and MCP interactions. Supports API mode (inspection) and Gateway mode (proxy). Configurable via `agentsec.yaml`.
- **MCP Inspection API (`MCPInspectionClient`)** — New client for inspecting MCP JSON-RPC 2.0 messages with purpose-built methods: `inspect()`, `inspect_tool_call()`, `inspect_resource_read()`, `inspect_prompt_get()`, `inspect_response()`.
- **Streaming inspection** for Amazon Bedrock and LiteLLM providers in `agentsec`.
- **Context manager protocol** for OpenAI streaming wrappers.
- **Async support** — Full async API for chat inspection, auth handling, request handler, and config loading with retry support.
- **MCP Management APIs (`mcpscan`)** — New module with `MCPScanClient`, `ResourceConnectionClient`, and `MCPPolicyClient`.
- **`processed_rules` support** in MCP inspection responses.
- **Configurable retry count** — Scanning retry count is now environment-driven.
- **ME Central endpoint** in management config.
- Agent framework examples: CrewAI, LangGraph, AutoGen, Google ADK, Semantic Kernel, LlamaIndex.
- Cloud runtime deployment examples: AWS Bedrock AgentCore, GCP Vertex AI Agent Engine, Microsoft Azure AI Foundry.
- RST documentation for `agentsec` and MCP inspection modules.

### Fixed

- Region mismatch, singleton poisoning, MCP parsing, input validation, and event model issues.
- Removed DEBUG log leaks and fixed `http_inspect` body handling.
- Bedrock streaming — convert `EventStream` to iterator in streaming wrappers.
- CrewAI Azure hang by removing deployment path from `base_url`.
- AutoGen `LLMConfig` for ag2 v0.11+ API.
- Mistralai v2 import path change.
- Agentcore direct-deploy packaging — added `aidefense` dependency and bundled `_shared`.
- Foundry MCP test import path (`get_patched_clients`).
- Python 3.9 compatibility fixes and CI skip guards for agentsec tests.
- Correct endpoint configuration.

### Changed

- Renamed "Runtime Protection" to "Agent Runtime SDK" across all documentation.
- Updated README with agentsec provider list, YAML config, and examples.

### Security

- Bumped `urllib3` from 2.2.3 to 2.6.3.
- Bumped `aiohttp` from 3.13.2 to 3.13.3.

## [2.0.0] - 2025-12-05

### Added

- Initial public release of `cisco-aidefense-sdk`.
- `ChatInspectionClient` for chat prompt/response inspection.
- `HttpInspectionClient` for HTTP request/response inspection.
- `ModelScanClient` for AI/ML model file and repository scanning.
- `ManagementClient` for application, connection, policy, and event management.
- `AiValidationClient` for AI validation jobs.
- Strong input validation, flexible configuration, and typed exceptions.
- Customizable PII/PCI/PHI entity lists for granular inspection control.

[Unreleased]: https://github.com/cisco-ai-defense/ai-defense-python-sdk/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/cisco-ai-defense/ai-defense-python-sdk/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/cisco-ai-defense/ai-defense-python-sdk/releases/tag/v2.0.0
