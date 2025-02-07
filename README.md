# measure-syft

A tool to measure and compare the performance of different versions of [Syft](https://github.com/anchore/syft).

## Introduction

When making changes to Syft, particularly those that might affect performance, it's useful to measure the impact across different versions. This tool automates the process of:

1. Fetching the latest release of Syft
2. Building it from source
3. Running performance tests
4. Testing subsequent commits to main
5. Comparing performance between branches (when testing PRs)

The tool generates a detailed Markdown report showing performance metrics for each tested version.

## Installation

measure-syft is written in Python and requires a few dependencies.

### Pre-requisites

* Python 3.x
* Git
* Go (for building Syft)
* Docker or Podman (for running container tests)

You can use either [uv](https://github.com/astral-sh/uv) or Python's built-in venv to set up the environment:

Using uv:
```shell
git clone https://github.com/popey/measure-syft
cd measure-syft
uv venv
source ./venv/bin/activate
uv pip install requests
```

Using venv:
```shell
git clone https://github.com/popey/measure-syft
cd measure-syft
python -m venv venv
source ./venv/bin/activate
pip install requests
```

## Usage

There are two main ways to use measure-syft:

### 1. Testing commits after latest release

To test all commits from the latest release to main:

```shell
./measure-syft.py
```

This will:
- Find the latest Syft release
- Clone and build that version
- Run performance tests
- Test each subsequent commit up to main
- Generate a report in the `results` directory

### 2. Testing a specific PR

To compare main against a PR branch:

```shell
./measure-syft.py --pr feat/parallelize-file-hashing
```

This will:
- Build and test main
- Build and test the specified PR branch
- Generate a comparison report

## Configuration

The script uses several configuration variables that can be modified in the source:

* `test_container`: The container image to use for testing
* `iterations`: Number of test runs per version (default: 5)
* `build_dir`: Where to clone and build Syft
* `results_dir`: Where to store test results
* `platform`: Container platform to test against

## Output

The script generates a Markdown report containing:

* Test date and time
* Container being tested
* Environment variables
* Table of results showing:
  * Version/commit
  * Minimum runtime
  * Maximum runtime
  * Average runtime

Example output:
```markdown
# Syft Performance Test Results

Date: 2024-02-07 10:00:00
Container: docker.io/huggingface/transformers-all-latest-torch-nightly-gpu:latest
Environment Variables:
- SYFT_PARALLELISM=48
- SYFT_CHECK_FOR_APP_UPDATE=false

## Results
| Version/Description | Commit | Min (s) | Max (s) | Avg (s) |
|-------------------|--------|---------|---------|---------|
| v1.19.0 | - | 45.23 | 47.12 | 46.18 |
| Add parallel... | [abc123](https://...) | 42.11 | 43.89 | 43.00 |
```

## Caveats

This tool is primarily designed for performance testing and comparison. The results can be affected by system load and other factors, so it's recommended to:

* Run tests multiple times
* Keep the test environment as consistent as possible
* Consider the min/max/average values rather than individual run times

## License

MIT
