#!/usr/bin/env python3
# tests/smart_selection/run_tests.py
"""Test runner for Smart Selection Engine.

Provides convenient commands for running different test suites.

Usage:
    python run_tests.py unit      # Run unit tests only
    python run_tests.py e2e       # Run end-to-end tests
    python run_tests.py bench     # Run benchmarks
    python run_tests.py all       # Run all tests (no benchmarks)
    python run_tests.py full      # Run everything including benchmarks
"""

import os
import sys
import subprocess


def main():
    """Run the specified test suite."""
    # Get the directory this script is in
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))

    # Parse command
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()
    extra_args = sys.argv[2:]

    # Common pytest args
    base_args = [sys.executable, '-m', 'pytest', '-v']

    if command == 'unit':
        # Run unit tests (everything except e2e and benchmarks)
        args = base_args + [
            os.path.join(script_dir, 'unit'),
            '-m', 'not e2e and not benchmark',
        ] + extra_args

    elif command == 'e2e':
        # Run end-to-end tests
        args = base_args + [
            os.path.join(script_dir, 'e2e'),
            '-m', 'e2e',
        ] + extra_args

    elif command == 'bench':
        # Run benchmarks
        args = base_args + [
            os.path.join(script_dir, 'benchmarks'),
        ] + extra_args

    elif command == 'all':
        # Run all tests except benchmarks
        args = base_args + [
            script_dir,
            '-m', 'not benchmark',
            '--benchmark-disable',
        ] + extra_args

    elif command == 'full':
        # Run everything including benchmarks
        args = base_args + [
            script_dir,
        ] + extra_args

    elif command == 'quick':
        # Run quick tests only (exclude slow and wallust)
        args = base_args + [
            script_dir,
            '-m', 'not slow and not wallust and not benchmark',
            '--benchmark-disable',
        ] + extra_args

    elif command == 'coverage':
        # Run with coverage
        args = base_args + [
            script_dir,
            '--benchmark-disable',
            '--cov=variety.smart_selection',
            '--cov-report=term-missing',
        ] + extra_args

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    # Run pytest
    print(f"Running: {' '.join(args)}")
    result = subprocess.run(args, cwd=project_root)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
