#!/usr/bin/env python3
"""Test runner script for paintball bot"""
import subprocess
import sys
import os
from pathlib import Path


def run_tests(test_type="all", verbose=True):
    """Run tests based on type"""
    
    # Change to project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    # Base pytest command
    cmd = ["venv\\Scripts\\python.exe", "-m", "pytest"]
    
    if verbose:
        cmd.append("-v")
    
    # Add coverage
    cmd.extend(["--cov=bot", "--cov-report=html", "--cov-report=term-missing"])
    
    # Select test type
    if test_type == "unit":
        cmd.append("tests/unit/")
    elif test_type == "integration":
        cmd.append("tests/integration/")
    elif test_type == "e2e":
        cmd.append("tests/e2e/")
    elif test_type == "fast":
        cmd.extend(["tests/unit/", "tests/integration/"])
    else:  # all
        cmd.append("tests/")
    
    print(f"Running {test_type} tests...")
    print(f"Command: {' '.join(cmd)}")
    
    # Run tests
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main():
    """Main function"""
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
    else:
        test_type = "all"
    
    # Validate test type
    valid_types = ["all", "unit", "integration", "e2e", "fast"]
    if test_type not in valid_types:
        print(f"Invalid test type: {test_type}")
        print(f"Valid types: {', '.join(valid_types)}")
        sys.exit(1)
    
    # Run tests
    exit_code = run_tests(test_type)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
