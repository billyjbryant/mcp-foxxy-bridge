#!/bin/bash
# Smart commit script that handles pre-commit formatting changes

echo "Running pre-commit checks and committing..."

# Try to commit
git commit "$@"
exit_code=$?

# If commit failed due to pre-commit changes (exit code 1), re-add and retry
if [ $exit_code -eq 1 ]; then
    echo "Pre-commit hooks made changes, re-adding files and retrying commit..."
    git add -u  # Add all modified tracked files
    git commit "$@"
    exit_code=$?
fi

exit $exit_code
