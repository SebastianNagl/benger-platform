# Contributing to BenGER Platform

Thank you for your interest in contributing to BenGER! This document provides guidelines for contributing to the project.

## Developer Certificate of Origin (DCO)

By contributing to this project, you agree to the Developer Certificate of Origin (DCO). This means you certify that you wrote (or otherwise have the right to submit) the code you're contributing under the project's Apache-2.0 license.

All commits must include a `Signed-off-by` line:

```
Signed-off-by: Your Name <your.email@example.com>
```

You can add this automatically with `git commit -s`.

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](https://github.com/SebastianNagl/benger-platform/issues) for bug reports and feature requests
- Check existing issues before creating a new one
- Include reproduction steps, expected behavior, and actual behavior for bugs

### Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Ensure tests pass: `make test`
5. Commit with DCO sign-off: `git commit -s`
6. Push and open a Pull Request

### Pull Request Guidelines

- Keep PRs focused on a single change
- Include a clear description of what and why
- Reference related issues
- Ensure CI passes

## Development Setup

```bash
# Clone
git clone https://github.com/SebastianNagl/benger-platform.git
cd benger-platform

# Start development environment
make dev

# Run tests
make test
```

See the [README](README.md) for detailed setup instructions.

## Code Style

- **Python:** Follow existing patterns in the codebase. No strict formatter enforced.
- **TypeScript/React:** Follow existing patterns. Tailwind CSS for styling.
- **Commits:** Clear, concise messages. Present tense ("Add feature" not "Added feature").

## What's In Scope

Community contributions are welcome for:
- Bug fixes
- New evaluation metrics
- Documentation improvements
- Infrastructure improvements
- UI/UX enhancements to core features
- i18n translations

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
