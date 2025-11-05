#!/usr/bin/env python3
"""Quick test script for development"""
import subprocess
import sys
import os
from pathlib import Path


def main():
    """Run quick tests for development"""
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    print("Running quick tests...")
    
    # Run unit tests only (fastest)
    cmd = ["venv\\Scripts\\python.exe", "-m", "pytest", "tests/unit/", "-v", "--tb=short"]
    
    print(f"Command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("Quick tests passed!")
    else:
        print("Quick tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
