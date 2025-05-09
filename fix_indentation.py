import re

# Define the file path
file_path = "music_player/models/Yt_DlpModel.py"

# Read the file content
with open(file_path, 'r', encoding='utf-8') as file:
    lines = file.readlines()

# Display relevant line numbers and their content
print("Lines 104-111:")
for i in range(103, 112):  # 0-indexed, so we start at 103 to get line 104
    if i < len(lines):
        line_num = i + 1
        print(f"{line_num}: {repr(lines[i])}")

# Check for indentation issues in the "if use_https" and "if use_m4a" lines
for i, line in enumerate(lines):
    # Look for the problem lines with wrong indentation
    if "if use_https:" in line or "if use_m4a:" in line:
        # If these are indented too much or too little, print the info
        leading_spaces = len(line) - len(line.lstrip())
        print(f"Line {i+1} has {leading_spaces} leading spaces: {repr(line)}")

# Fix the indentation issues
fixed_lines = lines.copy()
for i, line in enumerate(fixed_lines):
    if "if use_https:" in line:
        # Ensure 8 spaces of indentation (2 levels of 4 spaces)
        stripped = line.lstrip()
        fixed_lines[i] = " " * 8 + stripped
    elif "if use_m4a:" in line:
        # Ensure 8 spaces of indentation (2 levels of 4 spaces)
        stripped = line.lstrip()
        fixed_lines[i] = " " * 8 + stripped

# Write the fixed content back to the file
with open(file_path, 'w', encoding='utf-8') as file:
    file.writelines(fixed_lines)

print("\nFixed indentation issues in", file_path) 