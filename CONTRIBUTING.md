# Contributing to Isaac Sim MCP Server

Thank you for your interest in contributing to Isaac Sim MCP Server! We welcome contributions from the community and are grateful for any help you can provide.

## How Can You Contribute?

- Reporting bugs
- Suggesting new features or tools
- Improving documentation
- Submitting pull requests with bug fixes or new features
- Adding support for new Isaac Sim versions or robots

## Getting Started

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- NVIDIA Isaac Sim installed
- Git

### Setting Up the Development Environment

1. Fork the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/isaacsim-mcp-server.git
   cd isaacsim-mcp-server
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Install pre-commit hooks (if available):

   ```bash
   uv run pre-commit install
   ```

### Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Please ensure your code passes all checks before submitting:

```bash
uv run ruff check .
uv run ruff format .
```

## Did You Find a Bug?

- **Ensure the bug was not already reported** by searching the existing [GitHub Issues](https://github.com/whats2000/isaacsim-mcp-server/issues).
- If you cannot find an open issue addressing the problem, [open a new one](https://github.com/whats2000/isaacsim-mcp-server/issues/new/choose). Use the **Bug Report** template and fill in as much detail as possible.

## Do You Want to Request a Feature?

- Check the [existing feature requests](https://github.com/whats2000/isaacsim-mcp-server/issues?q=label%3A%22Feature+request%22) to see if someone has already proposed it.
- If not, [open a new feature request](https://github.com/whats2000/isaacsim-mcp-server/issues/new/choose) using the **Feature Request** template.

## Create a Pull Request

1. **Create a branch** from `main` for your changes:

   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes** and commit with clear, descriptive messages.

3. **Run the linter** to ensure code quality:

   ```bash
   uv run ruff check .
   uv run ruff format .
   ```

4. **Run the tests** (if applicable):

   ```bash
   uv run pytest
   ```

5. **Push your branch** and open a Pull Request against `main`.

6. Fill in the PR template with a clear description of your changes.

### PR Guidelines

- Keep PRs focused on a single change.
- Include relevant tests for new features or bug fixes.
- Update documentation if your change affects user-facing behavior.
- Link any related issues in the PR description.

## Project Structure

```
isaacsim-mcp-server/
├── isaac_mcp/              # Main MCP server package
│   └── tools/              # Tool implementations (9 categories)
├── isaac.sim.mcp_extension/ # Isaac Sim extension module
├── tests/                  # Test suite
├── scripts/                # Setup and run scripts
└── docs/                   # Documentation
```

## Adding a New Tool

If you're adding a new MCP tool:

1. Create or update the appropriate file in `isaac_mcp/tools/`.
2. Follow the existing tool patterns for consistency.
3. Add tests for your new tool.
4. Update the documentation to reflect the new capability.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## Questions?

If you have questions about contributing, feel free to open a [Discussion](https://github.com/whats2000/isaacsim-mcp-server/discussions) or an issue.

Thank you for helping improve Isaac Sim MCP Server!
