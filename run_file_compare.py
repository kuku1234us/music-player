#!/usr/bin/env python3
"""
Launcher script for the File Comparison and Deletion App
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from file_compare_app import main
    main()
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Please ensure PyQt6 and qtawesome are installed:")
    print("pip install PyQt6 qtawesome")
    sys.exit(1)
except Exception as e:
    print(f"Error running application: {e}")
    sys.exit(1) 